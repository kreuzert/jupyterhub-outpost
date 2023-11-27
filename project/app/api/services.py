import asyncio
from typing import Annotated
from typing import List

from database import models as service_model
from database import schemas as service_schema
from database.schemas import decrypt
from database.schemas import encrypt
from database.utils import get_db
from database.utils import get_or_create_jupyterhub
from database.utils import get_service
from database.utils import get_services_all
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasicCredentials
from spawner import get_spawner
from spawner import get_wrapper
from spawner import remove_spawner
from sqlalchemy.orm import Session
from users import verify_user

router = APIRouter()

from exceptions import catch_exception


import os
import logging

logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
log = logging.getLogger(logger_name)

background_tasks = set()


def get_auth_state(headers):
    ret = {}
    for key, value in headers.items():
        if key.startswith("auth-state-"):
            ret[key[len("auth-state-") :]] = value
    return ret


async def full_stop_and_remove(
    jupyterhub_name, service_name, db, request, delete=False
):
    service = get_service(jupyterhub_name, service_name, db)
    service.stop_pending = True
    db.add(service)
    db.commit()
    wrapper = get_wrapper()
    spawner = await get_spawner(
        jupyterhub_name,
        service_name,
        decrypt(service.body),
        get_auth_state(request.headers),
    )
    flavor_update_url = spawner.get_env().get("JUPYTERHUB_FLAVORS_UPDATE_URL", "")
    spawner.log.info(f"{spawner._log_name} - Stop service and remove it from database.")
    try:
        await spawner._outpostspawner_db_stop(db)
    except:
        spawner.log.exception(f"{spawner._log_name} - Stop failed.")
    finally:
        try:
            await wrapper._outpostspawner_send_flavor_update(
                db, service_name, jupyterhub_name, flavor_update_url
            )
        except:
            spawner.log.exception(
                f"{spawner._log_name} - Could not send flavor update to {jupyterhub_name}."
            )
        remove_spawner(jupyterhub_name, service_name)
    if delete:
        try:
            db.delete(service)
        except:
            log.exception(
                f"{jupyterhub_name}-{service_name} - Could not delete service from database"
            )


@router.get("/services/")
@catch_exception
async def list_services(
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)],
    db: Session = Depends(get_db),
) -> List[dict]:
    log.debug(f"List services for {jupyterhub_name}")
    return get_services_all(jupyterhub_name, db)


@router.get("/services/{service_name}")
@catch_exception
async def get_services(
    service_name: str,
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)],
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    log.debug(f"Get service {service_name} for {jupyterhub_name}")
    service = get_service(jupyterhub_name, service_name, db)
    spawner = await get_spawner(
        jupyterhub_name,
        service_name,
        decrypt(service.body),
        get_auth_state(request.headers),
    )
    ret = await spawner._outpostspawner_db_poll(db)
    return JSONResponse(content={"status": ret}, status_code=200)


@router.delete("/services/{service_name}")
@catch_exception
async def delete_service(
    service_name: str,
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)],
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    log.info(f"Delete service {service_name} for {jupyterhub_name}")
    await full_stop_and_remove(jupyterhub_name, service_name, db, request)
    return JSONResponse(content={}, status_code=200)


@router.post("/services")
@catch_exception
async def add_service(
    service: service_schema.Service,
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)],
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    log.info(f"Create service {service.name} for {jupyterhub_name}")
    jupyterhub = get_or_create_jupyterhub(jupyterhub_name, db)
    service_name = service.name
    d = service.dict()

    # Do not store certs and internal_trust_bundles from db
    # That's just to much unused data, it's only used during startup
    # and therefore it's enough to store it in memory
    dec_body = decrypt(service.body)
    certs = dec_body.pop("certs", {})
    internal_trust_bundles = dec_body.pop("internal_trust_bundles", {})
    d["body"] = encrypt(dec_body)

    # Add jupyterhub to db
    d["jupyterhub"] = jupyterhub

    # check if the chosen flavor is currently available, before adding the service to
    # the database
    wrapper = get_wrapper()
    flavor = dec_body.get("user_options", {}).get("flavor", "_undefined")
    current_flavor_values = await wrapper._outpostspawner_get_flavor_values(
        db, jupyterhub_name
    )
    if flavor in current_flavor_values.keys():
        current_flavor_value = current_flavor_values.get(flavor, {}).get("current", 0)
    else:
        current_flavor_value = current_flavor_values.get("_undefined", {}).get(
            "current", 0
        )
    undefined_max = await wrapper.get_flavors_undefined_max(jupyterhub_name)
    max_flavor_value = current_flavor_values.get(flavor, {}).get("max", undefined_max)
    if current_flavor_value >= max_flavor_value and max_flavor_value != -1:
        # max = -1 -> infinite
        raise Exception(
            f"{service_name} - Start with {flavor} for {jupyterhub_name} not allowed. Maximum ({max_flavor_value}) already reached."
        )

    new_service = service_model.Service(**d)
    db.add(new_service)
    db.commit()

    async def async_start():
        # remove spawner from wrapper to ensure it's using the current config
        remove_spawner(jupyterhub_name, service.name)
        spawner = await get_spawner(
            jupyterhub_name,
            service.name,
            decrypt(service.body),
            get_auth_state(request.headers),
            certs,
            internal_trust_bundles,
        )
        flavor_update_url = spawner.get_env().get("JUPYTERHUB_FLAVORS_UPDATE_URL", "")
        try:
            ret = await spawner._outpostspawner_db_start(db)
        except Exception as e:
            try:
                await full_stop_and_remove(jupyterhub_name, service_name, db, request)
            except:
                log.exception(
                    f"{jupyterhub_name}-{service_name} - Could not stop and remove"
                )
            raise e
        else:
            service_ = get_service(jupyterhub_name, service.name, db)
            service_.start_pending = False
            db.add(service_)
            db.commit()
            await wrapper._outpostspawner_send_flavor_update(
                db, service.name, jupyterhub_name, flavor_update_url
            )
            return ret

    if request.headers.get("execution-type", "sync") == "async":
        task = asyncio.create_task(async_start())
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return JSONResponse(content={"service": ""}, status_code=202)
    else:
        ret = await async_start()
        return JSONResponse(content={"service": ret}, status_code=200)


## Configuration für flavors (Traitlets) hinzufügen
## Tests schreiben:
# 1. flavor taucht in Datenbank auf
# 2. Configuration funktioniert
# 3. Certs werden gelöscht, wenn spawner aus mem gelöscht wurde
# 4. reached max flavor wirft sinnvolle Exception
# 5. failed start function -> no service / spawner left in db/mem
