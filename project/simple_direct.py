from jupyterhub.spawner import SimpleLocalProcessSpawner

c.JupyterHubOutpost.spawner_class = SimpleLocalProcessSpawner


def custom_path(spawner):
    path = spawner.env.get("PATH", "")
    path = f"/home/ubuntu/miniconda3/envs/fastapimgr/bin:{path}"
    return path


# c.SimpleLocalProcessSpawner.environment = { "PATH": custom_path }
c.SimpleLocalProcessSpawner.cmd = (
    "/home/ubuntu/miniconda3/envs/fastapimgr/bin/jupyterhub-singleuser"
)
