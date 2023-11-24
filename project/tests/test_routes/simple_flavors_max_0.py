from jupyterhub.spawner import SimpleLocalProcessSpawner

c.JupyterHubOutpost.spawner_class = SimpleLocalProcessSpawner
c.SimpleLocalProcessSpawner.port = 4567
c.SimpleLocalProcessSpawner.cmd = "/bin/echo"
c.SimpleLocalProcessSpawner.args = "Hello World"


async def flavors(jupyterhub_name):
    if jupyterhub_name == "authenticated":
        return {
            "typea": 5,
            "typeb": 5,
        }
    else:
        return {"typea": 1, "typeb": 1}


c.JupyterHubOutpost.flavors = flavors
c.JupyterHubOutpost.flavors_undefined_max = 0


async def flavors_update_token(jupyterhub_name):
    if jupyterhub_name == "authenticated":
        return "secret1"
    else:
        return "secret2"


c.JupyterHubOutpost.flavors_update_token = flavors_update_token
