from jupyterhub.spawner import SimpleLocalProcessSpawner

c.JupyterHubOutpost.spawner_class = SimpleLocalProcessSpawner
c.SimpleLocalProcessSpawner.port = 4567
c.SimpleLocalProcessSpawner.cmd = "/bin/echo"
c.SimpleLocalProcessSpawner.args = "Hello World"


async def flavors_update_token(jupyterhub_name):
    raise Exception("nope")


c.JupyterHubOutpost.flavors_update_token = flavors_update_token
