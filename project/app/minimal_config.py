import logging
import os

from kubespawner import KubeSpawner

logged_logger_name = os.environ.get("LOGGER_NAME", "Outpost")
c.JupyterHubOutpost.log_format = f"%(color)s[%(levelname)1.1s %(asctime)s.%(msecs).03d {logged_logger_name} %(name)s %(module)s:%(lineno)d]%(end_color)s %(message)s"

# Suppress /ping loggings, created by k8s livenessprobe
uvicorn_access = logging.getLogger("uvicorn.access")


class UvicornFilter(logging.Filter):
    def filter(self, record):
        try:
            if "/ping" in record.args:
                return False
        except:
            pass
        return True


uvicorn_access.addFilter(UvicornFilter())

c.JupyterHubOutpost.spawner_class = KubeSpawner

c.KubeSpawner.image = "jupyter/minimal-notebook:notebook-7.0.3"
c.KubeSpawner.start_timeout = 600
