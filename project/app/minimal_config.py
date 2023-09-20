import os

from kubespawner import KubeSpawner

logged_logger_name = os.environ.get("LOGGER_NAME", "Outpost")
c.JupyterHubOutpost.log_format = f"%(color)s[%(levelname)1.1s %(asctime)s.%(msecs).03d {logged_logger_name} %(name)s %(module)s:%(lineno)d]%(end_color)s %(message)s"

c.JupyterHubOutpost.spawner_class = KubeSpawner

c.KubeSpawner.image = "jupyter/minimal-notebook:notebook-7.0.3"
