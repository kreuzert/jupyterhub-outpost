from jupyterhub.spawner import SimpleLocalProcessSpawner

c.JupyterHubOutpost.spawner_class = SimpleLocalProcessSpawner
c.SimpleLocalProcessSpawner.port = 4567
c.SimpleLocalProcessSpawner.cmd = "/bin/echo"
c.SimpleLocalProcessSpawner.args = "Hello World"


def check_allowed(dec_body):
    # Imported lazily at call time (not config-load time) to keep the config
    # file free of app-package top-level imports, consistent with the other
    # test config files.
    from spawner.utils import get_forbidden_users_from_disk

    forbidden_users = set(get_forbidden_users_from_disk())
    user = dec_body.get("env", {}).get("JUPYTERHUB_USER", "")
    if user in forbidden_users:
        raise Exception(f"User {user} is not allowed to start a notebook")


c.JupyterHubOutpost.check_allowed = check_allowed
