from jupyterhub.spawner import SimpleLocalProcessSpawner


async def sanitize_start(spawner, response):
    return f"{response[0]}--{response[1]}"


c.JupyterHubOutpost.spawner_class = SimpleLocalProcessSpawner
c.JupyterHubOutpost.sanitize_start_response = sanitize_start
c.SimpleLocalProcessSpawner.port = 4567
c.SimpleLocalProcessSpawner.cmd = "/bin/echo"
c.SimpleLocalProcessSpawner.args = "Hello World"
