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
from spawner import remove_spawner
from sqlalchemy.orm import Session
from users import verify_user

router = APIRouter()

from exceptions import catch_exception


import os
import logging

logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
log = logging.getLogger(logger_name)


def get_auth_state(headers):
    ret = {}
    for key, value in headers.items():
        if key.startswith("auth-state-"):
            ret[key[len("auth-state-") :]] = value
    return ret


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
    log.debug(f"Delete service {service_name} for {jupyterhub_name}")
    service = get_service(jupyterhub_name, service_name, db)
    service.stop_pending = True
    db.add(service)
    db.commit()
    spawner = await get_spawner(
        jupyterhub_name,
        service_name,
        decrypt(service.body),
        get_auth_state(request.headers),
    )
    await spawner._outpostspawner_db_stop(db)
    remove_spawner(jupyterhub_name, service_name)
    return JSONResponse(content={}, status_code=200)


@router.post("/services")
@catch_exception
async def add_service(
    service: service_schema.Service,
    jupyterhub_name: Annotated[HTTPBasicCredentials, Depends(verify_user)],
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    log.debug(f"Create service {service.name} for {jupyterhub_name}")
    jupyterhub = get_or_create_jupyterhub(jupyterhub_name, db)
    d = service.dict()
    d["jupyterhub"] = jupyterhub
    new_service = service_model.Service(**d)
    db.add(new_service)
    db.commit()
    spawner = await get_spawner(
        jupyterhub_name,
        service.name,
        decrypt(service.body),
        get_auth_state(request.headers),
    )
    ret = await spawner._outpostspawner_db_start(db)
    service = get_service(jupyterhub_name, service.name, db)
    service.start_pending = False
    db.add(service)
    db.commit()
    return JSONResponse(content={"service": ret}, status_code=200)
