import logging
import os

from database import models as service_model
from database import schemas as service_schema
from database import SessionLocal
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
    jupyterhub_name: str, db: Session
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
    jupyterhub_name, service_name: str, unique_start_id: str, db: Session
) -> service_schema.Service:
    jupyterhub = get_or_create_jupyterhub(jupyterhub_name, db)
    service = (
        db.query(service_model.Service)
        .filter(service_model.Service.name == service_name)
        .filter(service_model.Service.unique_start_id == unique_start_id)
        .filter(service_model.Service.jupyterhub == jupyterhub)
        .first()
    )
    if not service:
        log.info(
            f"Service {service_name} ({unique_start_id}) for {jupyterhub_name} does not exist"
        )
        raise HTTPException(status_code=404, detail="Item not found")
    return service


def get_services_all(jupyterhub_name=None, db=None) -> service_schema.Service:
    if not db:
        return []
    if jupyterhub_name:
        jupyterhub = get_or_create_jupyterhub(jupyterhub_name, db)
        services = (
            db.query(service_model.Service)
            .filter(service_model.Service.jupyterhub == jupyterhub)
            .all()
        )
    else:
        services = db.query(service_model.Service).all()
    service_list = [
        {
            "name": x.name,
            "unique_start_id": x.unique_start_id,
            "start_date": x.start_date,
            "end_date": x.end_date,
            "jupyterhub": x.jupyterhub_username,
            "last_update": x.last_update,
            "start_pending": x.start_pending,
            "stop_pending": x.stop_pending,
        }
        for x in services
    ]
    return service_list
