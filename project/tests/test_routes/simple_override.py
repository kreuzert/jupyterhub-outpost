from jupyterhub.spawner import SimpleLocalProcessSpawner

c.JupyterHubOutpost.spawner_class = SimpleLocalProcessSpawner
c.SimpleLocalProcessSpawner.port = 4567
c.SimpleLocalProcessSpawner.cmd = "/bin/echo"
c.SimpleLocalProcessSpawner.args = "Hello World"


async def allow_override(jupyterhub_name, misc):
    if jupyterhub_name == "authenticated":
        return True
    return False


c.JupyterHubOutpost.allow_override = allow_override
