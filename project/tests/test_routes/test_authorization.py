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
simple_authorization = "./tests/test_routes/simple_authorization.py"
simple_direct = "./tests/test_routes/simple_direct.py"


@pytest.mark.parametrize("spawner_config", [simple_authorization])
def test_authorization(client):
    response = client.post(
        "/authorization",
        json={"username": "user1@mycomp.org"},
        headers=headers_auth_user,
    )
    assert response.status_code == 200
    assert response.json() == ["my", "flavors"]

    response2 = client.post(
        "/authorization",
        json={"username": "user1@other.org"},
        headers=headers_auth_user,
    )
    assert response2.status_code == 200
    assert response2.json() == False


@pytest.mark.parametrize("spawner_config", [simple_direct])
def test_authorization_default(client):
    response = client.post(
        "/authorization", json={"username": "user1"}, headers=headers_auth_user
    )
    assert response.status_code == 200
    assert response.json() == True
