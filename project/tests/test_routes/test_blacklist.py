from unittest.mock import patch

import pytest
from tests.conftest import auth_user_b64

headers_auth_user = {"Authorization": f"Basic {auth_user_b64}"}

simple_blacklist = "./tests/test_routes/simple_blacklist.py"

BLOCKED_USER = "b93ed915bf334a77a4a5daea40c84d41@login.helmholtz.de"
ALLOWED_USER = "allowed-user@example.org"


@pytest.mark.parametrize("spawner_config", [simple_blacklist])
def test_create_service_blocked_user(client):
    service_name = "user-servername"
    service_data = {"name": service_name, "env": {"JUPYTERHUB_USER": BLOCKED_USER}}
    with patch(
        "spawner.utils.get_forbidden_users_from_disk", return_value=[BLOCKED_USER]
    ), patch("spawner.outpost.get_flavors_from_disk", return_value={}), patch(
        "spawner.utils.get_flavors_from_disk", return_value={}
    ):
        response = client.post(
            "/services", json=service_data, headers=headers_auth_user
        )
    assert response.status_code == 419, response.text
    # Error is surfaced via the existing SpawnerException mechanism
    assert response.json().get("class", "")
    assert "not allowed to start a notebook" in response.json().get("args", [])

    # No service row may be created for a blocked user
    response = client.get(f"/services/{service_name}", headers=headers_auth_user)
    assert response.status_code == 419  # get_service raises -> not found / error


@pytest.mark.parametrize("spawner_config", [simple_blacklist])
def test_create_service_blocked_user_no_authentication(client):
    """Blocking must rely on env.JUPYTERHUB_USER, not the optional authentication block."""
    service_name = "user-servername"
    service_data = {"name": service_name, "env": {"JUPYTERHUB_USER": BLOCKED_USER}}
    with patch(
        "spawner.utils.get_forbidden_users_from_disk", return_value=[BLOCKED_USER]
    ), patch("spawner.outpost.get_flavors_from_disk", return_value={}), patch(
        "spawner.utils.get_flavors_from_disk", return_value={}
    ):
        response = client.post(
            "/services", json=service_data, headers=headers_auth_user
        )
    assert response.status_code == 419, response.text


@pytest.mark.parametrize("spawner_config", [simple_blacklist])
def test_create_service_allowed_user(client):
    service_name = "user-servername"
    service_data = {"name": service_name, "env": {"JUPYTERHUB_USER": ALLOWED_USER}}
    with patch(
        "spawner.utils.get_forbidden_users_from_disk", return_value=[BLOCKED_USER]
    ), patch("spawner.outpost.get_flavors_from_disk", return_value={}), patch(
        "spawner.utils.get_flavors_from_disk", return_value={}
    ):
        response = client.post(
            "/services", json=service_data, headers=headers_auth_user
        )
    assert response.status_code == 200, response.text
    assert "service" in response.json().keys()
    assert response.json().get("service", "") == "127.0.0.1:4567"


@pytest.mark.parametrize("spawner_config", [simple_blacklist])
def test_create_service_allowed_user_missing_configmap(client):
    """If the blacklist ConfigMap is missing, no user may be blocked (default empty)."""
    service_name = "user-servername"
    service_data = {"name": service_name, "env": {"JUPYTERHUB_USER": BLOCKED_USER}}
    with patch(
        "spawner.utils.get_forbidden_users_from_disk", return_value=[]
    ), patch("spawner.outpost.get_flavors_from_disk", return_value={}), patch(
        "spawner.utils.get_flavors_from_disk", return_value={}
    ):
        response = client.post(
            "/services", json=service_data, headers=headers_auth_user
        )
    assert response.status_code == 200, response.text
    assert "service" in response.json().keys()
    assert response.json().get("service", "") == "127.0.0.1:4567"
