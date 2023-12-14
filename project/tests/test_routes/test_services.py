import time
from datetime import datetime
from datetime import timedelta

import pytest
from app.database.schemas import decrypt
from app.database.schemas import encrypt
from app.database.utils import get_service
from pytest import raises
from spawner import get_spawner
from tests.conftest import auth_user2_b64
from tests.conftest import auth_user_b64
from tests.conftest import auth_user_wrong_pw

jupyterhub_name = "authenticated"
jupyterhub_name2 = "authenticated2"

headers_auth_user = {"Authorization": f"Basic {auth_user_b64}"}

headers_auth_user2 = {"Authorization": f"Basic {auth_user2_b64}"}

headers_auth_wrong_pw = {"Authorization": f"Basic {auth_user_wrong_pw}"}

auth_state_required = "./tests/test_routes/auth_state_required.py"
simple_direct = "./tests/test_routes/simple_direct.py"
simple_flavors_max_0 = "./tests/test_routes/simple_flavors_max_0.py"
simple_flavors_auth_exception = "./tests/test_routes/simple_flavors_exception.py"
simple_override = "./tests/test_routes/simple_override.py"
simple_direct_sanitized = "./tests/test_routes/simple_direct_sanitized.py"


@pytest.mark.parametrize("spawner_config", [simple_flavors_max_0])
def test_flavors_endpoint(client):
    response = client.get("/flavors", headers=headers_auth_user)
    assert response.status_code == 200
    assert response.json() == {
        "_undefined": {
            "current": 0,
            "max": 0,
            "display_name": "default flavor",
            "weight": 1,
        },
        "typea": {
            "max": 5,
            "weight": 10,
            "current": 0,
            "display_name": "2GB RAM, 1VCPU, 120 hours",
            "description": "JupyterLab will run for max 120 hours with 2GB RAM and 1VCPU.",
            "runtime": {"hours": 2},
        },
        "typeb": {
            "max": 5,
            "weight": 9,
            "current": 0,
            "display_name": "4GB RAM, 1VCPUs, 12 hours",
            "description": "JupyterLab will run for max 12 hours with 4GB RAM and 1VCPUs.",
            "runtime": {"hours": 2},
        },
    }

    response = client.get("/flavors", headers=headers_auth_user2)
    assert response.status_code == 200
    assert response.json() == {
        "_undefined": {
            "current": 0,
            "max": 0,
            "display_name": "default flavor",
            "weight": 1,
        },
        "typea": {
            "max": 1,
            "weight": 10,
            "current": 0,
            "display_name": "2GB RAM, 1VCPU, 120 hours",
            "description": "JupyterLab will run for max 120 hours with 2GB RAM and 1VCPU.",
        },
        "typeb": {
            "max": 1,
            "weight": 9,
            "current": 0,
            "display_name": "4GB RAM, 1VCPUs, 12 hours",
            "description": "JupyterLab will run for max 12 hours with 4GB RAM and 1VCPUs.",
            "runtime": {"hours": 2},
        },
    }


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_create_get(client):
    service_name = "user-servername"
    service_data = {"name": service_name, "env": {"JUPYTERHUB_USER": "user1"}}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200
    assert "service" in response.json().keys()
    assert response.json().get("service", "") == "127.0.0.1:4567"

    response = client.get(f"/services/{service_name}", headers=headers_auth_user)
    assert response.status_code == 200
    assert response.json().get("status", "") == 0


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_create_get_running(client):
    service_name = "user-servername"
    service_data = {"name": service_name, "misc": {"cmd": "sleep", "args": "5"}}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200
    assert "service" in response.json().keys()
    assert response.json().get("service", "") == "127.0.0.1:4567"

    response = client.get(f"/services/{service_name}", headers=headers_auth_user)
    assert response.status_code == 200
    assert response.json().get("status", "") == None


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_delete(client, db_session):
    service_name = "user-servername"
    service_data = {"name": service_name, "misc": {"cmd": "sleep", "args": "5"}}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200, response.text

    response = client.get(f"/services/{service_name}", headers=headers_auth_user)
    assert response.status_code == 200, response.text
    assert response.json().get("status", "") == None

    response = client.delete(f"/services/{service_name}", headers=headers_auth_user)
    assert response.status_code == 200, response.text

    response = client.get(f"/services/{service_name}", headers=headers_auth_user)
    assert response.status_code == 404, response.text

    from fastapi.exceptions import HTTPException

    with raises(HTTPException):
        get_service(jupyterhub_name, service_name, "0", db_session)


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_list_respects_authentication(client):
    response = client.get("/services/", headers=headers_auth_user)
    assert response.status_code == 200, response.text
    assert response.json() == []
    service_name = "user-servername"
    service_data = {"name": service_name, "misc": {"cmd": "sleep", "args": "5"}}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    response = client.get("/services/", headers=headers_auth_user)
    assert response.status_code == 200, response.text
    assert response.json() != []

    response = client.get("/services/", headers=headers_auth_user2)
    assert response.status_code == 200, response.text
    assert response.json() == []


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_list_userid(client):
    response = client.get("/services/", headers=headers_auth_user)
    assert response.status_code == 200, response.text
    assert response.json() == []
    service_name = "user-servername"
    service_data = {
        "name": service_name,
        "misc": {"cmd": "sleep", "args": "5"},
        "env": {"JUPYTERHUB_USER_ID": "17"},
    }
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    response = client.get("/services/", headers=headers_auth_user)
    assert response.status_code == 200, response.text
    assert response.json() != []
    assert response.json()[0]["jupyterhub_userid"] == "17"


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_401_endpoints(client):
    response = client.get("/services/0/0", headers=headers_auth_wrong_pw)
    assert response.status_code == 401, response.text
    response = client.delete("/services/0/0", headers=headers_auth_wrong_pw)
    assert response.status_code == 401, response.text
    response = client.get("/services/", headers=headers_auth_wrong_pw)
    assert response.status_code == 401, response.text
    service_name = "user-servername"
    service_data = {"name": service_name, "misc": {"cmd": "sleep", "args": "5"}}
    response = client.post(
        "/services", json=service_data, headers=headers_auth_wrong_pw
    )
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_list(client):
    response = client.get("/services/", headers=headers_auth_user)
    assert response.status_code == 200, response.text
    assert response.json() == []


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_404_get(client):
    response = client.get("/services/0", headers=headers_auth_user)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_404_delete(client):
    response = client.delete("/services/0", headers=headers_auth_user)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("spawner_config", [simple_direct])
def not_yet_test_404_patch(client):
    response = client.patch("/services/0")
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_create_start_sanitize_default(client):
    response = client.post("/services", json={"name": 0}, headers=headers_auth_user)
    assert response.json().get("service", "") == "127.0.0.1:4567"


@pytest.mark.parametrize("spawner_config", [simple_direct_sanitized])
def test_create_start_sanitize(client):
    service_name = "user-servername"
    response = client.post(
        "/services", json={"name": service_name}, headers=headers_auth_user
    )
    assert response.json().get("service", "") == "127.0.0.1--4567"


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_last_update_updated(client, db_session):
    service_name = "user-servername"
    service_data = {"name": service_name}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200, response.text
    service = get_service(jupyterhub_name, service_name, "0", db_session)
    after_spawn = service.last_update

    response = client.get(f"/services/{service_name}", headers=headers_auth_user)
    after_poll = service.last_update
    assert after_spawn != after_poll


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [simple_direct])
async def test_certs_not_stored_in_db(client, db_session):
    service_name = "user-servername"
    service_data = {
        "name": service_name,
        "certs": {
            "keyfile": "cert.key",
            "certfile": "cert.crt",
            "cafile": "hub_ca.crt",
        },
        "internal_trust_bundles": {
            "hub-ca": "anything",
            "proxy-api-ca": "useless",
            "proxy-client-ca": "to",
            "notebooks-ca": "fill",
            "services-ca": "sausage",
        },
        "env": {"JUPYTERHUB_USER": "user"},
    }
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200, response.text
    service = get_service(jupyterhub_name, service_name, "0", db_session)
    body = decrypt(service.body)
    assert "env" in body.keys()
    assert "certs" not in body.keys()
    assert "internal_trust_bundles" not in body.keys()

    # Certs should not stored in database, but in memory it's required
    spawner = await get_spawner(jupyterhub_name, service_name, "0", {})

    # certs are stored in paths describe in cert_paths
    assert spawner.cert_paths
    for key, value in service_data["certs"].items():
        with open(spawner.cert_paths[key], "r") as f:
            assert f.read() == value

    # internal_trust_bundles stored in paths described, too
    assert spawner.internal_trust_bundles
    for key, value in service_data["internal_trust_bundles"].items():
        with open(spawner.internal_trust_bundles[key], "r") as f:
            assert f.read() == value


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_do_not_get_other_services(client, db_session):
    service_name = "user-servername"
    service_data = {"name": service_name}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200, response.text

    response = client.get(f"/services/{service_name}", headers=headers_auth_user2)
    # 404 because the combination jupyterhub_name <-> service_name does not exist
    assert response.status_code == 404


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_do_not_delete_other_services(client, db_session):
    service_name = "user-servername"
    service_data = {"name": service_name}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200, response.text

    response = client.delete(f"/services/{service_name}", headers=headers_auth_user2)
    # 404 because the combination jupyterhub_name <-> service_name does not exist
    assert response.status_code == 404
    response = client.delete(f"/services/{service_name}", headers=headers_auth_user)
    assert response.status_code == 200


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_allow_same_name_twice_different_jupyterhub(client, db_session):
    # Two different jupyterhub can start services with the same name
    service_name = "user-servername"
    service_data = {"name": service_name}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    response2 = client.post("/services", json=service_data, headers=headers_auth_user2)
    service1 = get_service("authenticated", service_name, "0", db_session)
    service2 = get_service("authenticated2", service_name, "0", db_session)
    service3 = get_service("authenticated", service_name, "0", db_session)
    state1 = decrypt(service1.state)
    state2 = decrypt(service2.state)
    state3 = decrypt(service3.state)
    assert state1["pid"] != state2["pid"]
    assert state1["pid"] == state3["pid"]


@pytest.mark.parametrize("spawner_config", [simple_override])
def test_override_allowed(client, db_session):
    # Two different jupyterhub can start services with the same name
    service_name = "user-servername"
    service_data = {"name": service_name, "misc": {"image": "override_image"}}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200


@pytest.mark.parametrize("spawner_config", [simple_override])
def test_override_allowed_419(client, db_session):
    # Two different jupyterhub can start services with the same name
    service_name = "user-servername"
    service_data = {"name": service_name, "misc": {"image": "override_image"}}
    response = client.post("/services", json=service_data, headers=headers_auth_user2)
    assert response.status_code == 419


@pytest.mark.parametrize("spawner_config", [simple_override])
def test_override_allowed_419_error_msg(client, db_session):
    # Two different jupyterhub can start services with the same name
    service_name = "user-servername"
    service_data = {"name": service_name, "misc": {"image": "override_image"}}
    response = client.post("/services", json=service_data, headers=headers_auth_user2)
    x = response.status_code
    assert response.status_code == 419
    args_list = [str(s) for s in response.json().get("args", [])]
    message = f"{response.json().get('module')}{response.json().get('class')}: {' - '.join(args_list)}"
    assert (
        message
        == f"Exception: {jupyterhub_name2} is not allowed to override the configuration. Used keys: {list(service_data.get('misc', {}).keys())}"
    )


@pytest.mark.parametrize("spawner_config", [simple_override])
def test_override_allowed_no_misc_always_allowed(client, db_session):
    service_name = "user-servername"
    service_data = {"name": service_name}
    response = client.post("/services", json=service_data, headers=headers_auth_user2)
    assert response.status_code == 200


@pytest.mark.parametrize("spawner_config", [auth_state_required])
def test_auth_state_in_start_poll_stop(client, db_session):
    import copy

    service_name = "user-servername"
    service_data = {"name": service_name, "misc": {"cmd": "sleep", "args": "5"}}
    headers = copy.deepcopy(headers_auth_user)
    headers["Auth-State-access_token"] = "secret"
    response = client.post("/services", json=service_data, headers=headers)
    assert response.status_code == 200, response.text

    response = client.get(f"/services/{service_name}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json().get("status", "") == None

    response = client.delete(f"/services/{service_name}", headers=headers)
    assert response.status_code == 200, response.text

    response = client.get(f"/services/{service_name}", headers=headers)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("spawner_config", [auth_state_required])
def test_auth_state_in_start_poll_async_stop(client, db_session):
    import copy

    service_name = "user-servername"
    service_data = {"name": service_name, "misc": {"cmd": "sleep", "args": "5"}}
    headers = copy.deepcopy(headers_auth_user)
    headers["Auth-State-access_token"] = "secret"
    response = client.post("/services", json=service_data, headers=headers)
    assert response.status_code == 200, response.text

    response = client.get(f"/services/{service_name}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json().get("status", "") == None

    headers["execution-type"] = "async"
    response = client.delete(f"/services/{service_name}", headers=headers)
    assert response.status_code == 202, response.text

    time.sleep(10)

    response = client.get(f"/services/{service_name}", headers=headers)
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [simple_flavors_max_0])
async def test_flavor_max_0(client, db_session):
    service_name = "user-servername"
    service_data = {"name": service_name, "env": {"JUPYTERHUB_USER": "user1"}}
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 419
    assert (
        response.json().get("args")[0]
        == f"user-servername - Start with _undefined for {jupyterhub_name} not allowed. Maximum (0) already reached."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [simple_flavors_max_0])
async def test_flavor_runtime_in_enddate(client, db_session):
    service_name = "user-servername"
    service_data = {
        "name": service_name,
        "env": {"JUPYTERHUB_USER": "user1"},
        "user_options": {"flavor": "typea"},
    }
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200
    svc = get_service(jupyterhub_name, service_name, "0", db_session)
    assert datetime.now() + timedelta(minutes=120) > svc.end_date
    assert datetime.now() + timedelta(minutes=119) < svc.end_date


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [simple_flavors_max_0])
async def test_flavor_runtime_no_enddate(client, db_session):
    service_name = "user-servername"
    service_data = {
        "name": service_name,
        "env": {"JUPYTERHUB_USER": "user1"},
        "user_options": {"flavor": "typea"},
    }
    response = client.post("/services", json=service_data, headers=headers_auth_user2)
    assert response.status_code == 200
    svc = get_service(jupyterhub_name2, service_name, "0", db_session)
    assert datetime.max == svc.end_date


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [simple_flavors_max_0])
async def test_flavor_hub_specific_allowance(client, db_session, monkeypatch):
    mock_args = None
    calls = 0

    async def mock_fetch(self, *args, **kwargs):
        nonlocal mock_args
        nonlocal calls
        mock_args = args
        calls += 1

    from tornado.httpclient import AsyncHTTPClient

    monkeypatch.setattr(AsyncHTTPClient, "fetch", mock_fetch)

    service_data = [
        {
            "name": "user-servername-1",
            "env": {
                "JUPYTERHUB_USER": "user1",
                "JUPYTERHUB_FLAVORS_UPDATE_URL": "mock_url",
            },
            "user_options": {"flavor": "typea"},
        },
        {
            "name": "user-servername-2",
            "env": {
                "JUPYTERHUB_USER": "user1",
                "JUPYTERHUB_FLAVORS_UPDATE_URL": "mock_url",
            },
            "user_options": {"flavor": "typea"},
        },
        {
            "name": "user-servername-3",
            "env": {"JUPYTERHUB_USER": "user1"},
            "user_options": {"flavor": "typea"},
        },
        {
            "name": "user-servername-4",
            "env": {"JUPYTERHUB_USER": "user1"},
            "user_options": {"flavor": "typea"},
        },
        {
            "name": "user-servername-5",
            "env": {"JUPYTERHUB_USER": "user1"},
            "user_options": {"flavor": "typea"},
        },
        {
            "name": "user-servername-6",
            "env": {
                "JUPYTERHUB_USER": "user1",
                "JUPYTERHUB_FLAVORS_UPDATE_URL": "mock_url",
            },
            "user_options": {"flavor": "typea"},
        },
    ]

    # Start 5 notebook server in name of JupyterHub "authenticated" (headers_auth_user)
    # This should be fine
    i = 0
    for service_d in service_data[:5]:
        response = client.post("/services", json=service_d, headers=headers_auth_user)
        assert response.status_code == 200, response.text
        if i < 2:
            # Should be called when mock_url and token is set
            assert mock_args[0].headers["Authorization"] == "token secret1"
            assert mock_args[0].url == "mock_url"
            i += 1
            assert calls == i
        else:
            # Should not be called when mock_url is not set
            assert calls == i

    # The sixth one should fail
    response = client.post("/services", json=service_data[5], headers=headers_auth_user)
    assert response.status_code == 419
    assert (
        response.json().get("args")[0]
        == f"{service_data[5]['name']} - Start with typea for {jupyterhub_name} not allowed. Maximum (5) already reached."
    )
    # assert mock_args[0].headers["Authorization"] == "token secret1"
    # assert mock_args[0].url == "mock_url"
    # i += 1
    assert calls == i

    # Stop one previously started of typea
    response = client.delete(
        f"/services/{service_data[0]['name']}", headers=headers_auth_user
    )
    assert response.status_code == 200, response.text
    assert mock_args[0].headers["Authorization"] == "token secret1"
    assert mock_args[0].url == "mock_url"
    i += 1
    assert calls == i

    # The sixth one should now succeed
    response = client.post("/services", json=service_data[5], headers=headers_auth_user)
    assert response.status_code == 200
    assert mock_args[0].headers["Authorization"] == "token secret1"
    assert mock_args[0].url == "mock_url"
    i += 1
    assert calls == i

    # For jupyterhub "authenticated2" it should fail after one successful start
    response = client.post(
        "/services", json=service_data[0], headers=headers_auth_user2
    )
    assert response.status_code == 200
    assert mock_args[0].headers["Authorization"] == "token secret2"
    assert mock_args[0].url == "mock_url"
    i += 1
    assert calls == i
    response = client.post(
        "/services", json=service_data[1], headers=headers_auth_user2
    )
    assert response.status_code == 419
    # assert mock_args[0].headers["Authorization"] == "token secret2"
    # assert mock_args[0].url == "mock_url"
    # i += 1
    assert calls == i
    assert (
        response.json().get("args")[0]
        == f"{service_data[1]['name']} - Start with typea for {jupyterhub_name2} not allowed. Maximum (1) already reached."
    )

    other_flavor = {
        "name": "user-servername-other",
        "env": {
            "JUPYTERHUB_USER": "user1",
            "JUPYTERHUB_FLAVORS_UPDATE_URL": "mock_url",
        },
        "user_options": {"flavor": "typec"},
    }
    # typec is not configured in flavors, this should not be allowed
    response = client.post("/services", json=other_flavor, headers=headers_auth_user2)
    assert response.status_code == 419
    assert (
        response.json().get("args")[0]
        == f"{other_flavor['name']} - Start with typec for {jupyterhub_name2} not allowed. Maximum (0) already reached."
    )
    # assert mock_args[0].headers["Authorization"] == "token secret2"
    # assert mock_args[0].url == "mock_url"
    # i += 1
    assert calls == i


@pytest.mark.asyncio
@pytest.mark.parametrize("spawner_config", [simple_flavors_auth_exception])
async def test_flavor_auth_exception(client, db_session, monkeypatch):
    mock_args = None
    calls = 0

    async def mock_fetch(self, *args, **kwargs):
        nonlocal mock_args
        nonlocal calls
        mock_args = args
        calls += 1

    from tornado.httpclient import AsyncHTTPClient

    monkeypatch.setattr(AsyncHTTPClient, "fetch", mock_fetch)

    service_data = {
        "name": "user-servername-1",
        "env": {
            "JUPYTERHUB_USER": "user1",
            "JUPYTERHUB_FLAVORS_UPDATE_URL": "mock_url",
        },
        "user_options": {"flavor": "typea"},
    }

    # Start should work, even if the auth token is not configured correctly
    response = client.post("/services", json=service_data, headers=headers_auth_user)
    assert response.status_code == 200, response.text
    assert calls == 0
