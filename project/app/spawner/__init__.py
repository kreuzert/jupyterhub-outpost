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
    jupyterhub_name: str, service_name: str, orig_body: bytes, auth_state: dict = {}
) -> Spawner:
    ret = await get_wrapper().get_spawner(
        jupyterhub_name, service_name, orig_body, auth_state
    )
    return ret


def remove_spawner(jupyterhub_name: str, service_name: str) -> None:
    get_wrapper().remove_spawner(jupyterhub_name, service_name)
