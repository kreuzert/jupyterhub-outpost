import pytest
from app.database.schemas import decrypt
from app.database.schemas import encrypt
from app.database.utils import get_service
from pytest import raises
from tests.conftest import auth_user2_b64
from tests.conftest import auth_user_b64
from tests.conftest import auth_user_wrong_pw

jupyterhub_name = "authenticated"
jupyterhub_name2 = "authenticated2"

headers_auth_user = {"Authorization": f"Basic {auth_user_b64}"}

headers_auth_user2 = {"Authorization": f"Basic {auth_user2_b64}"}

headers_auth_wrong_pw = {"Authorization": f"Basic {auth_user_wrong_pw}"}

simple_direct = "./tests/test_routes/simple_direct.py"
simple_override = "./tests/test_routes/simple_override.py"
simple_direct_sanitized = "./tests/test_routes/simple_direct_sanitized.py"


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
        get_service(jupyterhub_name, service_name, db_session)


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
def test_401_endpoints(client):
    response = client.get("/services/0", headers=headers_auth_wrong_pw)
    assert response.status_code == 401, response.text
    response = client.delete("/services/0", headers=headers_auth_wrong_pw)
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
    service = get_service(jupyterhub_name, service_name, db_session)
    after_spawn = service.last_update

    response = client.get(f"/services/{service_name}", headers=headers_auth_user)
    after_poll = service.last_update
    assert after_spawn != after_poll


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
    service1 = get_service("authenticated", service_name, db_session)
    service2 = get_service("authenticated2", service_name, db_session)
    service3 = get_service("authenticated", service_name, db_session)
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
    # Two different jupyterhub can start services with the same name
    service_name = "user-servername"
    service_data = {"name": service_name}
    response = client.post("/services", json=service_data, headers=headers_auth_user2)
    assert response.status_code == 200
