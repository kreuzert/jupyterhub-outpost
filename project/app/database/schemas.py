import json
import os
from datetime import datetime

from pydantic import BaseModel


class JupyterHub(BaseModel):
    name: str

    class Config:
        orm_mode = True


class Service(BaseModel):
    name: str
    jupyterhub: JupyterHub | None = None
    last_update: datetime | None = datetime.utcnow()
    start_date: datetime | None = datetime.utcnow()
    start_pending: bool | None = True
    stop_pending: bool | None = False
    body: dict
    state: dict
    start_response: dict

    class Config:
        orm_mode = True

    def __init__(self, *args, **kwargs):
        body = {}
        body["env"] = kwargs.pop("env", {})
        body["misc"] = kwargs.pop("misc", {})
        body["user_options"] = kwargs.pop("user_options", {})
        body["certs"] = kwargs.pop("certs", {})
        kwargs["body"] = body
        state = kwargs.pop("state", {})
        kwargs["state"] = state
        kwargs["start_response"] = {}
        super().__init__(*args, **kwargs)
