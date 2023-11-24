import json
import os
from datetime import datetime

from cryptography.fernet import Fernet
from pydantic import BaseModel


def encrypt(data):
    if data is None:
        data = {}

    fernet = Fernet(os.environ.get("OUTPOST_CRYPT_KEY"))
    if type(data) == dict:
        data = json.dumps(data)
    if type(data) == str:
        data = data.encode()
    return fernet.encrypt(data)


def decrypt(bytes_data, return_type="dict"):
    if bytes_data is None:
        bytes_data = encrypt({})

    fernet = Fernet(os.environ.get("OUTPOST_CRYPT_KEY"))
    ret = fernet.decrypt(bytes_data)
    if return_type == "dict":
        ret = json.loads(ret)
    elif return_type == "str":
        ret = ret.decode()
    return ret


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
    body: bytes
    state: bytes
    start_response: bytes
    flavor: str | None = "_undefined"

    class Config:
        orm_mode = True

    def __init__(self, *args, **kwargs):
        body = {}
        body["env"] = kwargs.pop("env", {})
        body["misc"] = kwargs.pop("misc", {})
        body["user_options"] = kwargs.pop("user_options", {})
        body["certs"] = kwargs.pop("certs", {})
        body["internal_trust_bundles"] = kwargs.pop("internal_trust_bundles", {})
        # kwargs["body"] = body
        kwargs["flavor"] = body.get("user_options", {}).get("flavor", "_undefined")
        kwargs["body"] = encrypt(body)
        state = kwargs.pop("state", {})
        kwargs["state"] = encrypt(state)
        kwargs["start_response"] = encrypt({})
        super().__init__(*args, **kwargs)
