import os
import uuid

import pytest
from app.database.schemas import decrypt
from app.database.schemas import encrypt
from spawner import get_spawner
from spawner import remove_spawner

spawner_config_good = "./tests/test_spawner/spawner_config_good.py"
spawner_config_wrongclass = "./tests/test_spawner/spawner_config_wrongclass.py"

jupyterhub_name = "default"


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_config_file_good(app):
    service_name = uuid.uuid4().hex
    spawner = await get_spawner(jupyterhub_name, service_name, {})
    assert spawner.port == 4567


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_wrongclass])
async def test_config_file_wrongclass(app):
    service_name = uuid.uuid4().hex
    spawner = await get_spawner(jupyterhub_name, service_name, {})
    assert spawner.port != 4567


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_simple_spawner(app):
    import subprocess

    service_name = uuid.uuid4().hex
    spawner = await get_spawner(jupyterhub_name, service_name, {})
    spawner.popen_kwargs = {"stdout": subprocess.PIPE}
    await spawner.start()
    stdout = spawner.proc.stdout.read().decode().strip()
    assert stdout == "Hello World"
    spawner.proc.communicate()
    assert 0 == spawner.proc.returncode


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_simple_spawner_dummy_hub(app):
    body = {
        "env": {
            "JUPYTERHUB_API_URL": "http://remotehub/api",
            "JUPYTERHUB_BASE_URL": "/base",
            "JUPYTERHUB_HOST": "hubhost",
        }
    }
    service_name = uuid.uuid4().hex
    spawner = await get_spawner(jupyterhub_name, service_name, body)
    assert spawner.hub.api_url == body["env"]["JUPYTERHUB_API_URL"]
    assert spawner.hub.base_url == body["env"]["JUPYTERHUB_BASE_URL"]
    assert spawner.hub.public_host == body["env"]["JUPYTERHUB_HOST"]


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_simple_spawner_env(app):
    body = {"env": {"JUPYTERHUB_API_URL": "http://remotehub/api"}}
    service_name = uuid.uuid4().hex
    spawner = await get_spawner(jupyterhub_name, service_name, body)
    spawner_env = spawner.get_env()
    assert spawner_env["JUPYTERHUB_API_URL"] == body["env"]["JUPYTERHUB_API_URL"]


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_simple_spawner_user_options(app):
    body = {"user_options": {"key": "value"}}
    service_name = uuid.uuid4().hex
    spawner = await get_spawner(jupyterhub_name, service_name, body)
    spawner_user_options = spawner.user_options
    assert spawner_user_options["key"] == body["user_options"]["key"]


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_simple_spawner_override_others(db_session):
    body = {"misc": {"cmd": ["/bin/test"], "args": ["whatever"]}}

    service_name = uuid.uuid4().hex
    spawner_default = await get_spawner(jupyterhub_name, service_name, {})
    assert spawner_default.cmd == ["/bin/echo"]

    spawner = await get_spawner(jupyterhub_name, 1, body)
    assert spawner.cmd == body["misc"]["cmd"]
    assert spawner.args == body["misc"]["args"]


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_simple_spawner_outpostspawner_db_start(db_session):
    import subprocess
    from database import models as service_model
    from database.utils import get_service

    # Create Service in DB
    service_name = "0"
    new_jupyterhub = service_model.JupyterHub(**{"name": jupyterhub_name})
    new_service = service_model.Service(
        **{"name": service_name, "jupyterhub": new_jupyterhub}
    )
    db_session.add(new_service)
    db_session.commit()

    # Create Spawner
    spawner = await get_spawner(jupyterhub_name, service_name, {})
    spawner.popen_kwargs = {"stdout": subprocess.PIPE}

    # Check db entry
    service = get_service(jupyterhub_name, service_name, db_session)
    assert decrypt(service.state) == {}

    # Start
    await spawner._outpostspawner_db_start(db_session)

    # Check if PID is in db
    service = get_service(jupyterhub_name, service_name, db_session)
    assert "pid" in decrypt(service.state).keys()
    assert decrypt(service.state).get("pid") != 0


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_simple_spawner_two_starts_state_updates(db_session):
    from database import models as service_model
    from database.utils import get_service

    # Create Service in DB
    service_name = "0"
    new_jupyterhub = service_model.JupyterHub(name=jupyterhub_name)
    new_service = service_model.Service(
        **{"name": service_name, "jupyterhub": new_jupyterhub}
    )
    db_session.add(new_service)
    db_session.commit()

    # Create Spawner
    spawner = await get_spawner(jupyterhub_name, service_name, {})

    # Start
    await spawner._outpostspawner_db_start(db_session)

    # Check if PID is in db
    service = get_service(jupyterhub_name, service_name, db_session)
    pid1 = decrypt(service.state).get("pid")

    # Second start
    await spawner._outpostspawner_db_start(db_session)
    service = get_service(jupyterhub_name, service_name, db_session)
    assert pid1 != decrypt(service.state).get("pid")


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_poll(db_session):
    from database import models as service_model

    # Create Service in DB
    service_name = "0"
    new_jupyterhub = service_model.JupyterHub(**{"name": jupyterhub_name})
    new_service = service_model.Service(
        **{"name": service_name, "jupyterhub": new_jupyterhub}
    )
    db_session.add(new_service)
    db_session.commit()

    # Create Spawner
    spawner = await get_spawner(jupyterhub_name, service_name, {})

    # Start
    await spawner._outpostspawner_db_start(db_session)

    # Poll
    poll = await spawner._outpostspawner_db_poll(db_session)

    assert poll == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_remove_spawner(db_session):
    service_name = "0"
    from spawner import get_wrapper

    wrapper = get_wrapper()
    assert f"{jupyterhub_name}-{service_name}" not in wrapper.spawners.keys()
    await get_spawner(jupyterhub_name, service_name, {})
    assert f"{jupyterhub_name}-{service_name}" in wrapper.spawners.keys()
    remove_spawner(jupyterhub_name, service_name)
    assert f"{jupyterhub_name}-{service_name}" not in wrapper.spawners.keys()


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_poll_no_mem(db_session):
    from database import models as service_model

    # Create Service in DB
    service_name = "0"
    new_jupyterhub = service_model.JupyterHub(**{"name": jupyterhub_name})
    new_service = service_model.Service(
        **{"name": service_name, "jupyterhub": new_jupyterhub}
    )
    db_session.add(new_service)
    db_session.commit()

    # Create Spawner
    spawner = await get_spawner(jupyterhub_name, service_name, {})

    # Start
    await spawner._outpostspawner_db_start_call(db_session)

    from spawner import _wrapper

    assert f"{jupyterhub_name}-{service_name}" in _wrapper.spawners.keys()
    del _wrapper.spawners[f"{jupyterhub_name}-{service_name}"]
    assert f"{jupyterhub_name}-{service_name}" not in _wrapper.spawners.keys()

    assert spawner.proc is not None

    del spawner
    spawner = await get_spawner(jupyterhub_name, service_name, {})

    assert spawner.proc is None

    # Poll without existing spawner in memory
    import asyncio

    await asyncio.sleep(2)
    poll = await spawner._outpostspawner_db_poll(db_session)
    assert poll == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_poll_no_mem_wait(db_session):
    from database import models as service_model

    # Create Service in DB
    service_name = "0"
    new_jupyterhub = service_model.JupyterHub(**{"name": jupyterhub_name})
    new_service = service_model.Service(
        **{"name": service_name, "jupyterhub": new_jupyterhub}
    )
    db_session.add(new_service)
    db_session.commit()

    # Create Spawner
    spawner = await get_spawner(jupyterhub_name, service_name, {})
    spawner.cmd = "/bin/sleep"
    spawner.args = "5"

    # Start
    await spawner._outpostspawner_db_start(db_session)

    from spawner import _wrapper

    assert f"{jupyterhub_name}-{service_name}" in _wrapper.spawners.keys()
    del _wrapper.spawners[f"{jupyterhub_name}-{service_name}"]
    assert f"{jupyterhub_name}-{service_name}" not in _wrapper.spawners.keys()

    assert spawner.proc is not None

    del spawner
    spawner = await get_spawner(jupyterhub_name, service_name, {})

    assert spawner.proc is None

    # Poll without existing spawner in memory, should be still running
    poll = await spawner._outpostspawner_db_poll(db_session)
    assert poll == None


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_stop_slow_process(db_session):
    from database import models as service_model

    # Create Service in DB
    service_name = "0"
    new_jupyterhub = service_model.JupyterHub(**{"name": jupyterhub_name})
    new_service = service_model.Service(
        **{"name": service_name, "jupyterhub": new_jupyterhub}
    )
    db_session.add(new_service)
    db_session.commit()

    # Create Spawner
    spawner = await get_spawner(jupyterhub_name, service_name, {})
    spawner.cmd = "/bin/sleep"
    spawner.args = "5"

    # Start
    await spawner._outpostspawner_db_start(db_session)

    # Poll
    poll = await spawner._outpostspawner_db_poll(db_session)
    assert poll == None

    # Stop it
    await spawner._outpostspawner_db_stop(db_session)

    from fastapi.exceptions import HTTPException

    with pytest.raises(HTTPException):
        await spawner._outpostspawner_db_poll(db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_stop_already_stopped(db_session, client):
    from database import models as service_model

    # Create Service in DB
    service_name = "0"
    new_jupyterhub = service_model.JupyterHub(**{"name": jupyterhub_name})
    new_service = service_model.Service(
        **{"name": service_name, "jupyterhub": new_jupyterhub}
    )
    db_session.add(new_service)
    db_session.commit()

    # Create Spawner
    spawner = await get_spawner(jupyterhub_name, service_name, {})

    # Start
    await spawner._outpostspawner_db_start(db_session)

    from time import sleep

    sleep(5)
    # Poll
    poll = await spawner._outpostspawner_db_poll(db_session)
    assert poll == 0

    # Stop it
    await spawner._outpostspawner_db_stop(db_session)

    from fastapi.exceptions import HTTPException

    with pytest.raises(HTTPException):
        await spawner._outpostspawner_db_poll(db_session)


# os.kill creates a zombie process when stopping a subprocess process
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
@pytest.mark.asyncio
async def test_stop_slow_process_no_mem(db_session):
    from database import models as service_model

    # Create Service in DB
    service_name = "0"
    new_jupyterhub = service_model.JupyterHub(**{"name": jupyterhub_name})
    new_service = service_model.Service(
        **{"name": service_name, "jupyterhub": new_jupyterhub}
    )
    db_session.add(new_service)
    db_session.commit()

    # Create Spawner
    body = {"misc": {"cmd": "sleep", "args": "30"}}
    spawner = await get_spawner(jupyterhub_name, service_name, body)

    # Start
    await spawner._outpostspawner_db_start_call(db_session)
    pid = spawner.pid

    # Poll
    poll = await spawner._outpostspawner_db_poll(db_session)
    assert poll == None

    from spawner import _wrapper

    assert f"{jupyterhub_name}-{service_name}" in _wrapper.spawners.keys()
    del _wrapper.spawners[f"{jupyterhub_name}-{service_name}"]
    assert f"{jupyterhub_name}-{service_name}" not in _wrapper.spawners.keys()

    assert spawner.proc is not None

    del spawner

    spawner = await get_spawner(jupyterhub_name, service_name, body)

    assert spawner.proc is None

    # Poll
    poll = await spawner._outpostspawner_db_poll(db_session)
    assert poll == None

    # Stop it
    spawner.kill_timeout = 0
    spawner.interrupt_timeout = 0
    spawner.interrupt_timeout = 0
    await spawner._outpostspawner_db_stop(db_session, now=True)

    import psutil

    proc = psutil.Process(pid)
    assert proc.status() == psutil.STATUS_ZOMBIE


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_certs_created(db_session):
    user_name = "testuser"
    certs = {
        "keyfile": "cert.key",
        "certfile": "cert.crt",
        "cafile": "hub_ca.crt",
    }
    body = {
        "env": {"JUPYTERHUB_USER": user_name},
    }
    service_name = "0"
    # Create Spawner
    spawner = await get_spawner(jupyterhub_name, service_name, body, certs=certs)
    cert_paths = spawner.cert_paths.copy()
    from spawner import hub

    x = hub.certs_dir

    assert cert_paths == {
        "keyfile": f"{hub.certs_dir}/{jupyterhub_name}-{service_name}/{user_name}.key",
        "certfile": f"{hub.certs_dir}/{jupyterhub_name}-{service_name}/{user_name}.crt",
        "cafile": f"{hub.certs_dir}/{jupyterhub_name}-{service_name}/notebooks-ca_trust.crt",
    }
    for key, path in spawner.cert_paths.items():
        with open(path, "r") as f:
            file = f.read()
        assert file == certs[key]

    trust_bundles = spawner.internal_trust_bundles.copy()
    for key, path in spawner.internal_trust_bundles.items():
        assert os.path.exists(path) == True

    # Test cleanup
    remove_spawner(jupyterhub_name, service_name)
    for path in cert_paths.values():
        assert os.path.exists(path) == False
    assert os.path.exists(os.path.dirname(cert_paths["certfile"])) == False

    for key, path in trust_bundles.items():
        assert os.path.exists(path) == False


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [spawner_config_good])
async def test_certs_path_in_env(db_session):
    user_name = "testuser"
    body = {
        "certs": {
            "keyfile": "cert.key",
            "certfile": "cert.crt",
            "cafile": "hub_ca.crt",
        },
        "env": {"JUPYTERHUB_USER": user_name},
    }
    service_name = "0"
    # Create Spawner
    spawner = await get_spawner(
        jupyterhub_name, service_name, body, certs=body["certs"]
    )
    cert_paths = spawner.cert_paths.copy()
    from spawner import hub

    assert cert_paths == {
        "keyfile": f"{hub.certs_dir}/{jupyterhub_name}-{service_name}/{user_name}.key",
        "certfile": f"{hub.certs_dir}/{jupyterhub_name}-{service_name}/{user_name}.crt",
        "cafile": f"{hub.certs_dir}/{jupyterhub_name}-{service_name}/notebooks-ca_trust.crt",
    }
    env = spawner.get_env()
    assert env["JUPYTERHUB_SSL_KEYFILE"] == cert_paths["keyfile"]
    assert env["JUPYTERHUB_SSL_CERTFILE"] == cert_paths["certfile"]
    assert env["JUPYTERHUB_SSL_CLIENT_CA"] == cert_paths["cafile"]
