import json
import os
from datetime import datetime
from datetime import timezone

from cryptography.fernet import Fernet
from pydantic import BaseModel
from pydantic import ConfigDict


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

    model_config = ConfigDict(from_attribute=True)


class Service(BaseModel):
    name: str
    start_id: str
    jupyterhub: JupyterHub | None = None
    jupyterhub_user_id: int | None = 0
    last_update: datetime | None = datetime.now(timezone.utc)
    start_date: datetime | None = datetime.now(timezone.utc)
    end_date: datetime | None = datetime.max.replace(tzinfo=timezone.utc)
    state_stored: bool | None = False
    start_pending: bool | None = True
    stop_pending: bool | None = False
    body: bytes
    state: bytes
    start_response: bytes
    flavor: str | None = None

    model_config = ConfigDict(from_attribute=True)

    def __init__(self, *args, **kwargs):
        body = {}
        body["env"] = kwargs.pop("env", {})
        body["misc"] = kwargs.pop("misc", {})
        start_id = kwargs.get("user_options", {}).pop("start_id", "0")
        kwargs["start_id"] = start_id
        body["user_options"] = kwargs.pop("user_options", {})
        body["certs"] = kwargs.pop("certs", {})
        body["internal_trust_bundles"] = kwargs.pop("internal_trust_bundles", {})
        kwargs["body"] = encrypt(body)
        state = kwargs.pop("state", {})
        kwargs["state"] = encrypt(state)
        now = datetime.now(timezone.utc)
        kwargs["start_date"] = now
        kwargs["last_update"] = now
        kwargs["start_response"] = encrypt({})
        kwargs["jupyterhub_user_id"] = int(
            body.get("env", {}).get("JUPYTERHUB_USER_ID", "0")
        )
        flavor = body.get("flavor", body.get("user_options", {}).get("flavor", None))
        if flavor:
            kwargs["flavor"] = flavor
        super().__init__(*args, **kwargs)
