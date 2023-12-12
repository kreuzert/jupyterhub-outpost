from database.schemas import decrypt
from jupyterhub.spawner import Spawner

from .outpost import JupyterHubOutpost

_wrapper = None


def get_wrapper() -> JupyterHubOutpost:
    global _wrapper
    if not _wrapper:
        _wrapper = JupyterHubOutpost()
    return _wrapper


def remove_wrapper() -> None:
    global _wrapper
    del _wrapper


async def get_spawner(
    jupyterhub_name: str,
    service_name: str,
    unique_start_id: str,
    orig_body: bytes,
    auth_state: dict = {},
    certs: dict = {},
    internal_trust_bundles: dict = {},
    state: dict = {},
) -> Spawner:
    if not certs and "certs" in orig_body.keys():
        certs = orig_body.pop("certs", {})
    if not internal_trust_bundles and "internal_trust_bundles" in orig_body.keys():
        internal_trust_bundles = orig_body.pop("internal_trust_bundles", {})
    ret = await get_wrapper().get_spawner(
        jupyterhub_name,
        service_name,
        unique_start_id,
        orig_body,
        auth_state,
        certs,
        internal_trust_bundles,
        state,
    )
    return ret


def remove_spawner(
    jupyterhub_name: str, service_name: str, unique_start_id: str
) -> None:
    get_wrapper().remove_spawner(jupyterhub_name, service_name, unique_start_id)
