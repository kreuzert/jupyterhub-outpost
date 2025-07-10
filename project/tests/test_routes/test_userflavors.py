import copy
from unittest.mock import patch

import pytest
import spawner
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
simple_override = "./tests/test_routes/simple_override.py"


simple_flavors = {
    "flavors": {
        "typea": {
            "max": 5,
            "weight": 10,
            "display_name": "2GB RAM, 1VCPU, 120 hours",
            "description": "JupyterLab will run for max 120 hours with 2GB RAM and 1VCPU.",
            "runtime": {"hours": 2},
        },
        "typeb": {
            "max": 5,
            "weight": 9,
            "display_name": "4GB RAM, 1VCPUs, 12 hours",
            "description": "JupyterLab will run for max 12 hours with 4GB RAM and 1VCPUs.",
            "runtime": {"hours": 2},
        },
    },
    "hubs": {
        "default": {"jupyterhub_name": "authentica.*d", "flavors": ["typea", "typeb"]},
        "restrictedGroup": {"jupyterhub_name": ["authenticated2"], "flavors": []},
    },
}


@pytest.mark.parametrize("spawner_config", [simple_authorization])
def test_authorization(client):
    with patch(
        "spawner.outpost.get_flavors_from_disk", return_value=simple_flavors
    ), patch("spawner.utils.get_flavors_from_disk", return_value=simple_flavors):
        response = client.post(
            "/userflavors",
            json={"username": "user1@mycomp.org"},
            headers=headers_auth_user,
        )
    assert response.status_code == 200, response.json()
    expected_flavors = simple_flavors["flavors"]
    expected_flavors["typea"]["current"] = 0
    expected_flavors["typeb"]["current"] = 0
    assert response.json() == expected_flavors

    with patch(
        "spawner.outpost.get_flavors_from_disk", return_value=simple_flavors
    ), patch("spawner.utils.get_flavors_from_disk", return_value=simple_flavors):
        response2 = client.post(
            "/userflavors",
            json={"username": "user1@other.org"},
            headers=headers_auth_user2,
        )
    assert response2.status_code == 200
    assert response2.json() == {}


@pytest.mark.parametrize("spawner_config", [None])
def test_authorization_flavor_hub_flavors(client):
    mock_flavor_data = copy.deepcopy(simple_flavors)
    mock_flavor_data["hubs"]["default"]["flavors"] = ["typea"]
    expected_user_flavors = {"typea": mock_flavor_data["flavors"]["typea"]}
    expected_user_flavors["typea"]["current"] = 0

    with patch(
        "spawner.outpost.get_flavors_from_disk", return_value=mock_flavor_data
    ), patch("spawner.utils.get_flavors_from_disk", return_value=mock_flavor_data):
        response = client.post(
            "/userflavors", json={"username": "user1"}, headers=headers_auth_user
        )

    assert response.status_code == 200
    assert response.json() == expected_user_flavors


@pytest.mark.parametrize("spawner_config", [None])
def test_authorization_flavor_hub_flavorsoverride(client):
    mock_flavor_data = copy.deepcopy(simple_flavors)
    mock_flavor_data["hubs"]["default"]["flavors"] = ["typea"]
    mock_flavor_data["hubs"]["default"]["flavorsOverride"] = {
        "typea": {"runtime": {"hours": 1}, "max": 18}
    }
    expected_user_flavors = {"typea": mock_flavor_data["flavors"]["typea"]}
    expected_user_flavors["typea"]["current"] = 0
    expected_user_flavors["typea"]["max"] = 18
    expected_user_flavors["typea"]["runtime"] = {"hours": 1}

    with patch(
        "spawner.outpost.get_flavors_from_disk", return_value=mock_flavor_data
    ), patch("spawner.utils.get_flavors_from_disk", return_value=mock_flavor_data):
        response = client.post(
            "/userflavors", json={"username": "user1"}, headers=headers_auth_user
        )

    assert response.status_code == 200
    assert response.json() == expected_user_flavors


@pytest.mark.parametrize("spawner_config", [None])
def test_authorization_flavor_user_flavorsoverride(client):
    mock_flavor_data = copy.deepcopy(simple_flavors)
    mock_flavor_data["hubs"]["default"]["flavors"] = ["typea"]
    mock_flavor_data["hubs"]["default"]["flavorsOverride"] = {
        "typea": {"runtime": {"hours": 1}, "max": 18}
    }
    mock_flavor_data["users"] = {
        "key1": {
            "authentication": {"username": "user1"},
            "flavors": ["typea", "typeb"],
            "flavorsOverride": {"typea": {"runtime": {"hours": 2}}},
        }
    }
    expected_user_flavors = {
        "typea": mock_flavor_data["flavors"]["typea"],
        "typeb": mock_flavor_data["flavors"]["typeb"],
    }
    expected_user_flavors["typea"]["current"] = 0
    expected_user_flavors["typea"]["max"] = 18
    expected_user_flavors["typea"]["runtime"] = {"hours": 2}
    expected_user_flavors["typeb"]["current"] = 0

    with patch(
        "spawner.outpost.get_flavors_from_disk", return_value=mock_flavor_data
    ), patch("spawner.utils.get_flavors_from_disk", return_value=mock_flavor_data):
        response = client.post(
            "/userflavors", json={"username": "user1"}, headers=headers_auth_user
        )

    assert response.status_code == 200
    assert response.json() == expected_user_flavors


@pytest.mark.parametrize("spawner_config", [simple_override])
def test_authorization_flavor_user_flavorsoverride_manipulate_function(client):
    mock_flavor_data = copy.deepcopy(simple_flavors)
    mock_flavor_data["hubs"]["default"]["flavors"] = ["typea"]
    mock_flavor_data["hubs"]["default"]["flavorsOverride"] = {
        "typea": {"runtime": {"hours": 1}, "max": 18}
    }
    mock_flavor_data["users"] = {
        "key1": {
            "authentication": {"username": "user1"},
            "flavors": ["typea", "typeb"],
            "flavorsOverride": {"typea": {"runtime": {"hours": 2}}},
        }
    }
    expected_user_flavors = {
        "typea": mock_flavor_data["flavors"]["typea"],
        "typeb": mock_flavor_data["flavors"]["typeb"],
    }
    expected_user_flavors["typea"]["current"] = 0
    expected_user_flavors["typea"]["max"] = 18
    expected_user_flavors["typea"]["runtime"] = {"hours": 2}
    expected_user_flavors["typeb"]["current"] = 0

    with patch(
        "spawner.outpost.get_flavors_from_disk", return_value=mock_flavor_data
    ), patch("spawner.utils.get_flavors_from_disk", return_value=mock_flavor_data):
        response = client.post(
            "/userflavors", json={"username": "USER1"}, headers=headers_auth_user
        )

    assert response.status_code == 200
    assert response.json() == expected_user_flavors


@pytest.mark.parametrize("spawner_config", [None])
def test_authorization_flavor_user_flavorsoverride_weight(client):
    mock_flavor_data = copy.deepcopy(simple_flavors)
    mock_flavor_data["hubs"]["default"]["flavors"] = ["typea"]
    mock_flavor_data["hubs"]["default"]["flavorsOverride"] = {
        "typea": {"runtime": {"hours": 1}, "max": 18}
    }
    mock_flavor_data["users"] = {
        "key1": {
            "authentication": {"username": "user1"},
            "flavors": ["typea", "typeb"],
            "flavorsOverride": {"typea": {"runtime": {"hours": 2}}},
        },
        "key2": {
            "weight": 6,
            "authentication": {"username": "user1"},
            "flavors": ["typea", "typeb"],
            "flavorsOverride": {"typea": {"runtime": {"hours": 4}}},
        },
    }
    expected_user_flavors = {
        "typea": mock_flavor_data["flavors"]["typea"],
        "typeb": mock_flavor_data["flavors"]["typeb"],
    }
    expected_user_flavors["typea"]["current"] = 0
    expected_user_flavors["typea"]["max"] = 18
    expected_user_flavors["typea"]["runtime"] = {"hours": 4}
    expected_user_flavors["typeb"]["current"] = 0

    with patch(
        "spawner.outpost.get_flavors_from_disk", return_value=mock_flavor_data
    ), patch("spawner.utils.get_flavors_from_disk", return_value=mock_flavor_data):
        response = client.post(
            "/userflavors", json={"username": "user1"}, headers=headers_auth_user
        )

    assert response.status_code == 200
    assert response.json() == expected_user_flavors


@pytest.mark.parametrize("spawner_config", [None])
def test_authorization_flavor_user_flavorsoverride_regex(client):
    mock_flavor_data = copy.deepcopy(simple_flavors)
    mock_flavor_data["hubs"]["default"]["flavors"] = ["typea"]
    mock_flavor_data["hubs"]["default"]["flavorsOverride"] = {
        "typea": {"runtime": {"hours": 1}, "max": 18}
    }
    mock_flavor_data["users"] = {
        "key1": {
            "authentication": {"username": "us..1"},
            "flavors": ["typea", "typeb"],
            "flavorsOverride": {"typea": {"runtime": {"hours": 2}}},
        }
    }
    expected_user_flavors = {
        "typea": mock_flavor_data["flavors"]["typea"],
        "typeb": mock_flavor_data["flavors"]["typeb"],
    }
    expected_user_flavors["typea"]["current"] = 0
    expected_user_flavors["typea"]["max"] = 18
    expected_user_flavors["typea"]["runtime"] = {"hours": 2}
    expected_user_flavors["typeb"]["current"] = 0

    with patch(
        "spawner.outpost.get_flavors_from_disk", return_value=mock_flavor_data
    ), patch("spawner.utils.get_flavors_from_disk", return_value=mock_flavor_data):
        response = client.post(
            "/userflavors", json={"username": "user1"}, headers=headers_auth_user
        )

    assert response.status_code == 200
    assert response.json() == expected_user_flavors


@pytest.mark.parametrize("spawner_config", [None])
def test_authorization_flavor_user_flavorsoverride_regex_nomatch(client):
    mock_flavor_data = copy.deepcopy(simple_flavors)
    mock_flavor_data["hubs"]["default"]["flavors"] = ["typea"]
    mock_flavor_data["hubs"]["default"]["flavorsOverride"] = {
        "typea": {"runtime": {"hours": 1}, "max": 18}
    }
    mock_flavor_data["users"] = {
        "key1": {
            "authentication": {"username": "us..1"},
            "flavors": ["typea", "typeb"],
            "flavorsOverride": {"typea": {"runtime": {"hours": 2}}},
        },
        "key2": {
            "weight": 4,
            "authentication": {"username": "user1"},
            "flavors": ["typea", "typeb"],
            "flavorsOverride": {"typea": {"runtime": {"hours": 4}}},
        },
    }
    expected_user_flavors = {
        "typea": mock_flavor_data["flavors"]["typea"],
        "typeb": mock_flavor_data["flavors"]["typeb"],
    }
    expected_user_flavors["typea"]["current"] = 0
    expected_user_flavors["typea"]["max"] = 18
    expected_user_flavors["typea"]["runtime"] = {"hours": 4}
    expected_user_flavors["typeb"]["current"] = 0

    with patch(
        "spawner.outpost.get_flavors_from_disk", return_value=mock_flavor_data
    ), patch("spawner.utils.get_flavors_from_disk", return_value=mock_flavor_data):
        response = client.post(
            "/userflavors", json={"username": "user1"}, headers=headers_auth_user
        )

    assert response.status_code == 200
    assert response.json() == expected_user_flavors


@pytest.mark.parametrize("spawner_config", [simple_authorization])
def test_authorization_users_negate_minimal(client):
    flavors = copy.deepcopy(simple_flavors)
    flavors["flavors"]["minimal"] = {
        "max": 2,
        "weight": 15,
        "display_name": "1GB RAM, 1VCPUs, 1 hours",
        "description": "JupyterLab will run for max 1 hours with 1GB RAM and 1VCPUs.",
        "runtime": {"hours": 1},
    }
    flavors["users"] = {
        "negateGroup": {
            "negate_authentication": True,
            "authentication": {"username": ".*mycomp.org"},
            "flavors": ["minimal"],
            "forbidden": False,
        }
    }

    # users with username ending with mycomp.org will get the flavors typea and typeb.
    # All other users will get only the minimal flavor
    with patch("spawner.outpost.get_flavors_from_disk", return_value=flavors), patch(
        "spawner.utils.get_flavors_from_disk", return_value=flavors
    ):
        response = client.post(
            "/userflavors",
            json={"username": "user1@mycomp.org"},
            headers=headers_auth_user,
        )
    assert response.status_code == 200, response.json()
    assert list(response.json().keys()) == ["typea", "typeb"], response.json()

    with patch("spawner.outpost.get_flavors_from_disk", return_value=flavors), patch(
        "spawner.utils.get_flavors_from_disk", return_value=flavors
    ):
        response2 = client.post(
            "/userflavors",
            json={"username": "user1@other.org"},
            headers=headers_auth_user2,
        )
    assert response2.status_code == 200, response2.json()
    assert list(response2.json().keys()) == ["minimal"], response2.json()


@pytest.mark.parametrize("spawner_config", [simple_authorization])
def test_authorization_users_negate_forbidden(client):
    flavors = copy.deepcopy(simple_flavors)
    flavors["flavors"]["minimal"] = {
        "max": 2,
        "weight": 15,
        "display_name": "1GB RAM, 1VCPUs, 1 hours",
        "description": "JupyterLab will run for max 1 hours with 1GB RAM and 1VCPUs.",
        "runtime": {"hours": 1},
    }
    flavors["users"] = {
        "negateGroup": {
            "negate_authentication": True,
            "authentication": {"username": ".*mycomp.org"},
            "flavors": ["minimal"],
            "forbidden": True,
        }
    }

    # users with username ending with mycomp.org will get the flavors typea and typeb.
    # All other users will get nothing
    with patch("spawner.outpost.get_flavors_from_disk", return_value=flavors), patch(
        "spawner.utils.get_flavors_from_disk", return_value=flavors
    ):
        response = client.post(
            "/userflavors",
            json={"username": "user1@mycomp.org"},
            headers=headers_auth_user,
        )
    assert response.status_code == 200, response.json()
    assert list(response.json().keys()) == ["typea", "typeb"], response.json()

    with patch("spawner.outpost.get_flavors_from_disk", return_value=flavors), patch(
        "spawner.utils.get_flavors_from_disk", return_value=flavors
    ):
        response2 = client.post(
            "/userflavors",
            json={"username": "user1@other.org"},
            headers=headers_auth_user2,
        )
    assert response2.status_code == 200, response2.json()
    assert response2.json() == {}, response2.json()


@pytest.mark.parametrize("spawner_config", [simple_authorization])
def test_authorization_users_negate_forbidden_fnmatch_translate(client):
    flavors = copy.deepcopy(simple_flavors)
    flavors["flavors"]["minimal"] = {
        "max": 2,
        "weight": 15,
        "display_name": "1GB RAM, 1VCPUs, 1 hours",
        "description": "JupyterLab will run for max 1 hours with 1GB RAM and 1VCPUs.",
        "runtime": {"hours": 1},
    }
    flavors["users"] = {
        "negateGroup": {
            "negate_authentication": True,
            "authentication": {"username": "*mycomp.org"},
            "flavors": ["minimal"],
            "forbidden": True,
        }
    }

    # users with username ending with mycomp.org will get the flavors typea and typeb.
    # All other users will get nothing
    with patch("spawner.outpost.get_flavors_from_disk", return_value=flavors), patch(
        "spawner.utils.get_flavors_from_disk", return_value=flavors
    ):
        response = client.post(
            "/userflavors",
            json={"username": "user1@mycomp.org"},
            headers=headers_auth_user,
        )
    assert response.status_code == 200, response.json()
    assert list(response.json().keys()) == ["typea", "typeb"], response.json()

    with patch("spawner.outpost.get_flavors_from_disk", return_value=flavors), patch(
        "spawner.utils.get_flavors_from_disk", return_value=flavors
    ):
        response2 = client.post(
            "/userflavors",
            json={"username": "user1@other.org"},
            headers=headers_auth_user2,
        )
    assert response2.status_code == 200, response2.json()
    assert response2.json() == {}, response2.json()
