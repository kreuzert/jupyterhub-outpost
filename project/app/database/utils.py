import logging
import os

from database import models as service_model
from database import schemas as service_schema
from database import SessionLocal
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session


logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
log = logging.getLogger(logger_name)


def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


def get_or_create_jupyterhub(
    jupyterhub_name: str, db: Session = Depends(get_db)
) -> service_schema.JupyterHub:
    jhub = (
        db.query(service_model.JupyterHub)
        .filter(service_model.JupyterHub.name == jupyterhub_name)
        .first()
    )
    if not jhub:
        log.info(f"Create JupyterHub in db: {jupyterhub_name}")
        jhub_model = service_model.JupyterHub(name=jupyterhub_name)
        db.add(jhub_model)
        db.commit()
        jhub = (
            db.query(service_model.JupyterHub)
            .filter(service_model.JupyterHub.name == jupyterhub_name)
            .first()
        )
    return jhub


def get_service(
    jupyterhub_name, service_name: str, db: Session = Depends(get_db)
) -> service_schema.Service:
    jupyterhub = get_or_create_jupyterhub(jupyterhub_name, db)
    service = (
        db.query(service_model.Service)
        .filter(service_model.Service.name == service_name)
        .filter(service_model.Service.jupyterhub == jupyterhub)
        .first()
    )
    if not service:
        log.info(f"Service {service_name} for {jupyterhub_name} does not exist")
        raise HTTPException(status_code=404, detail="Item not found")
    return service


def get_services_all(
    jupyterhub_name, db: Session = Depends(get_db)
) -> service_schema.Service:
    jupyterhub = get_or_create_jupyterhub(jupyterhub_name, db)
    services = (
        db.query(service_model.Service)
        .filter(service_model.Service.jupyterhub == jupyterhub)
        .all()
    )
    service_list = [
        {
            "name": x.name,
            "start_date": x.start_date,
            "last_update": x.last_update,
            "start_pending": x.start_pending,
            "stop_pending": x.stop_pending,
        }
        for x in services
    ]
    return service_list
