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


async def lowercase_name(authentication):
    if "username" in authentication.keys():
        authentication["username"] = authentication["username"].lower()
    return authentication


c.JupyterHubOutpost.update_user_authentication = lowercase_name
