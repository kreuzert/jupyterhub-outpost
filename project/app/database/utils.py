import logging
import os

from database import models as service_model
from database import schemas as service_schema
from database import SessionLocal
from database.schemas import decrypt
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
    jupyterhub_name, service_name: str, start_id: str, db: Session
) -> service_schema.Service:
    jupyterhub = get_or_create_jupyterhub(jupyterhub_name, db)
    service = (
        db.query(service_model.Service)
        .filter(service_model.Service.name == service_name)
        .filter(service_model.Service.start_id == start_id)
        .filter(service_model.Service.jupyterhub == jupyterhub)
        .first()
    )
    if not service:
        log.info(
            f"Service {service_name} ({start_id}) for {jupyterhub_name} does not exist"
        )
        raise HTTPException(status_code=404, detail="Item not found")
    db.refresh(service)
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
    service_list = []
    for service in services:
        db.refresh(service)
        service_list.append(
            {
                "name": service.name,
                "start_id": service.start_id,
                "start_date": service.start_date,
                "end_date": service.end_date,
                "jupyterhub": service.jupyterhub_username,
                "jupyterhub_userid": str(service.jupyterhub_user_id),
                "last_update": service.last_update,
                "state_stored": service.state_stored,
                "start_pending": service.start_pending,
                "stop_pending": service.stop_pending,
            }
        )
    return service_list
