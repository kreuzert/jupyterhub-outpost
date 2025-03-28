from jupyterhub.spawner import SimpleLocalProcessSpawner

c.JupyterHubOutpost.spawner_class = SimpleLocalProcessSpawner
c.SimpleLocalProcessSpawner.port = 4567
c.SimpleLocalProcessSpawner.cmd = "/bin/echo"
c.SimpleLocalProcessSpawner.args = "Hello World"

c.JupyterHubOutpost.global_max_per_user = 0


async def flavors_update_token(jupyterhub_name):
    if jupyterhub_name == "authenticated":
        return "secret1"
    else:
        return "secret2"


c.JupyterHubOutpost.flavors_update_token = flavors_update_token
