from jupyterhub.spawner import SimpleLocalProcessSpawner

c.JupyterHubOutpost.spawner_class = SimpleLocalProcessSpawner
c.SimpleLocalProcessSpawner.port = 4567
c.SimpleLocalProcessSpawner.cmd = "/bin/echo"
c.SimpleLocalProcessSpawner.args = "Hello World"


async def flavors(jupyterhub_name):
    if jupyterhub_name == "authenticated":
        return {
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
        }
    else:
        return {
            "typea": {
                "max": 1,
                "weight": 10,
                "display_name": "2GB RAM, 1VCPU, 120 hours",
                "description": "JupyterLab will run for max 120 hours with 2GB RAM and 1VCPU.",
            },
            "typeb": {
                "max": 1,
                "weight": 9,
                "display_name": "4GB RAM, 1VCPUs, 12 hours",
                "description": "JupyterLab will run for max 12 hours with 4GB RAM and 1VCPUs.",
                "runtime": {"hours": 2},
            },
        }


c.JupyterHubOutpost.flavors = flavors
c.JupyterHubOutpost.flavors_undefined_max = 0


async def flavors_update_token(jupyterhub_name):
    if jupyterhub_name == "authenticated":
        return "secret1"
    else:
        return "secret2"


c.JupyterHubOutpost.flavors_update_token = flavors_update_token


async def authorization(jupyterhub_name, auth_dict):
    if auth_dict.get("username", "").endswith("mycomp.org"):
        return ["my", "flavors"]
    else:
        return False


c.JupyterHubOutpost.authorization = authorization
