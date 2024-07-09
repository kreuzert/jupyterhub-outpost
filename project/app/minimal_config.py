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

c.KubeSpawner.start_timeout = 600

async def profile_list(spawner):
    jupyterhub_name = spawner.jupyterhub_name
    spawner.log.info(f"{spawner._log_name} - Received these user_options from {jupyterhub_name}-JupyterHub: {spawner.user_options}")
    slug = spawner.user_options.get("profile", "default")
    default_image = "jupyter/minimal-notebook:notebook-7.0.3"
    ret_list = [
        {
            "display_name": "JupyterLab/custom",
            "slug": "JupyterLab/custom",
            "kubespawner_override": {
                "image": spawner.user_options.get("image", "NoImageAvailable")
            }
        },
        {
            "display_name": "default",
            "default": True,
            "kubespawner_override": {
                "image": default_image
            }
        }
    ]
    slug_in_profile_list = False
    for profile in ret_list:
        if profile.get("display_name", "") == slug or profile.get("slug", "") == slug:
            slug_in_profile_list = True
            break
    if not slug_in_profile_list:
        ret_list.append({
            "display_name": slug,
            "slug": slug,
            "kubespawner_override": {
                "image": default_image
            }
        })
    return ret_list

c.KubeSpawner.profile_list = profile_list