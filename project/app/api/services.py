import asyncio
import time
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
from fastapi import BackgroundTasks
from fastapi import Depends
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasicCredentials
from spawner import get_spawner
from spawner import get_wrapper
from spawner import remove_spawner
from sqlalchemy.orm import Session
from users import verify_user

from .utils import async_start
from .utils import full_stop_and_remove
from .utils import get_auth_state
from .utils import validate_flavor

router = APIRouter()

from exceptions import catch_exception


import os
import logging

logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
log = logging.getLogger(logger_name)

# background_tasks = set()


@router.get("/flavors/")
@catch_exception
async def list_flavors(
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)],
    db: Session = Depends(get_db),
) -> dict:
    log.debug(f"List flavors for {jupyterhub_name}")
    wrapper = get_wrapper()
    current_flavor_values = await wrapper._outpostspawner_get_flavor_values(
        db, jupyterhub_name
    )
    return current_flavor_values


@router.get("/services/")
@catch_exception
async def list_services(
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)],
    db: Session = Depends(get_db),
) -> List[dict]:
    log.debug(f"List services for {jupyterhub_name}")
    return get_services_all(jupyterhub_name, db)


@router.get("/services/{service_name}")
@router.get("/services/{service_name}/{start_id}")
@catch_exception
async def get_services(
    service_name: str,
    start_id: str = "0",
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)] = None,
    request: Request = None,
    db: Session = Depends(get_db),
) -> JSONResponse:
    log.debug(f"Get service {service_name} for {jupyterhub_name}")
    service = get_service(jupyterhub_name, service_name, start_id, db)
    spawner = await get_spawner(
        jupyterhub_name,
        service_name,
        start_id,
        decrypt(service.body),
        get_auth_state(request.headers),
    )
    ret = await spawner._outpostspawner_db_poll(db)
    return JSONResponse(content={"status": ret}, status_code=200)


@router.delete("/services/{service_name}")
@router.delete("/services/{service_name}/{start_id}")
@catch_exception
async def delete_service(
    service_name: str,
    background_tasks: BackgroundTasks,
    start_id: str = "0",
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)] = None,
    request: Request = None,
    db: Session = Depends(get_db),
) -> JSONResponse:
    # Check if service exists to throw correct error message
    service = get_service(jupyterhub_name, service_name, start_id, db)
    if request.headers.get("execution-type", "sync") == "async":
        log.info(f"Delete service {service_name} for {jupyterhub_name} in background")
        body = decrypt(service.body)
        # Service object will be deleted at the end of this function
        # before we can stop it. So we have to retrieve
        # database information now and pass it to the backend

        # If there's no state yet, because the service is cancelled
        # before the start process has stored a state,
        # we should wait for it for max 60
        # seconds, so we have a chance to cancel it correctly.
        until = time.time() + 60
        state = {}
        while time.time() < until:
            try:
                service = get_service(jupyterhub_name, service_name, start_id, db)
                if service.stop_pending:
                    # It's already stopping, no need to wait for it here.
                    # This happens if async_start was cancelled and stops
                    # the service itself.
                    log.info(
                        f"{jupyterhub_name} - {service_name} is already stopping. No need to stop it twice"
                    )
                    return JSONResponse(content={}, status_code=202)

                if not service.state_stored:
                    log.debug(
                        f"{jupyterhub_name}-{service_name} - State not stored yet"
                    )
                    await asyncio.sleep(1)
                    continue
                log.debug(
                    f"{jupyterhub_name}-{service_name} - Load state: {decrypt(service.state)}"
                )
                state = decrypt(service.state)
            except:
                log.exception(
                    f"{jupyterhub_name}-{service_name} - Could not load service"
                )
                await asyncio.sleep(1)
            else:
                log.info(
                    f"{jupyterhub_name}-{service_name} - Service fully loaded. Forward with cancel."
                )
                break

        log.info(f"{jupyterhub_name}-{service_name} - Forward {state} to stop")

        try:
            # Send update before deleting service.
            # Otherwise hub might use deprecated information
            auth_state = get_auth_state(request.headers)
            spawner = await get_spawner(
                jupyterhub_name,
                service_name,
                start_id,
                body,
                auth_state,
                state,
            )
            flavor_update_url = spawner.get_env().get(
                "JUPYTERHUB_FLAVORS_UPDATE_URL", ""
            )
            flavor_update_token = spawner.get_env().get(
                "JUPYTERHUB_FLAVORS_UPDATE_TOKEN", None
            )
            # Reduce number of <flavor> by one, since it will be deleted soon
            wrapper = get_wrapper()
            await wrapper._outpostspawner_send_flavor_update(
                db,
                service_name,
                jupyterhub_name,
                flavor_update_url,
                flavor_update_token,
                reduce_one_flavor_count=service.flavor,
            )
        except:
            log.exception(f"Could not send flavor update to {jupyterhub_name}.")

        task = background_tasks.add_task(
            full_stop_and_remove,
            jupyterhub_name,
            service_name,
            start_id,
            db,
            request,
            body=body,
            state=state,
            run_async=True,
        )
        return JSONResponse(content={}, status_code=202, background=task)
    else:
        log.info(f"Delete service {service_name} for {jupyterhub_name} and wait for it")
        await full_stop_and_remove(jupyterhub_name, service_name, start_id, db, request)
        return JSONResponse(content={}, status_code=200)


@router.post("/services")
@catch_exception
async def add_service(
    service: service_schema.Service,
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)],
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JSONResponse:
    log.info(f"Create service {service.name} for {jupyterhub_name}")
    jupyterhub = get_or_create_jupyterhub(jupyterhub_name, db)
    flavor = await validate_flavor(service, jupyterhub_name, request, db)
    d = service.model_dump()

    # Do not store certs and internal_trust_bundles from db
    # That's just to much unused data, it's only used during startup
    # and therefore it's enough to store it in memory
    dec_body = decrypt(service.body)
    certs = dec_body.pop("certs", {})
    internal_trust_bundles = dec_body.pop("internal_trust_bundles", {})
    d["body"] = encrypt(dec_body)

    # Add jupyterhub to db
    d["jupyterhub"] = jupyterhub

    new_service = service_model.Service(**d)
    db.add(new_service)
    db.commit()

    start_id = service.start_id
    remove_spawner(jupyterhub_name, service.name, start_id)
    spawner = await get_spawner(
        jupyterhub_name,
        service.name,
        start_id,
        decrypt(service.body),
        get_auth_state(request.headers),
        certs,
        internal_trust_bundles,
        user_flavor=flavor,
    )
    flavor_update_url = spawner.get_env().get("JUPYTERHUB_FLAVORS_UPDATE_URL", "")
    flavor_update_token = spawner.get_env().get("JUPYTERHUB_FLAVORS_UPDATE_TOKEN", None)

    if request.headers.get("execution-type", "sync") == "async":
        # Send update already at this point before actually starting the service.
        # Otherwise Hub might use deprecated data
        wrapper = get_wrapper()
        await wrapper._outpostspawner_send_flavor_update(
            db, service.name, jupyterhub_name, flavor_update_url, flavor_update_token
        )
        task = background_tasks.add_task(
            async_start,
            service,
            jupyterhub_name,
            request,
            db,
            spawner,
            flavor_update_url,
            flavor_update_token,
            sync=False,
        )

        return JSONResponse(content={"service": ""}, status_code=202, background=task)
    else:
        ret = await async_start(
            service,
            jupyterhub_name,
            request,
            db,
            spawner,
            flavor_update_url,
            flavor_update_token,
        )
        return JSONResponse(content={"service": ret}, status_code=200)


@router.post("/userflavors")
@catch_exception
async def userflavors(
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)],
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    user_authentication = await request.json()
    wrapper = get_wrapper()
    ret = await wrapper._outpostspawner_get_flavor_values(
        db, jupyterhub_name, user_authentication
    )
    return JSONResponse(content=ret, status_code=200)
