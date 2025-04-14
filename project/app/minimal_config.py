import logging
import os

import yaml
from kubernetes import client
from kubernetes import config
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


class EventsCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.funcName in ["_watch_and_update"]:
            return False
        return True


uvicorn_access.addFilter(UvicornFilter())

logging.getLogger(logged_logger_name).addFilter(EventsCheckFilter())

c.JupyterHubOutpost.spawner_class = KubeSpawner

c.KubeSpawner.start_timeout = 600


def get_flavor_resources(flavor):
    with open("/mnt/flavors/flavors.yaml", "r") as f:
        flavor_config = yaml.full_load(f)

    if flavor not in flavor_config.get("flavors", {}).keys():
        raise Exception(f"Flavor {flavor} not configured. Abort start.")

    return flavor_config["flavors"][flavor].get("resources", {})


c.JupyterHubOutpost.global_max_per_user = 5


def delete_previous_events(spawner):
    config.load_incluster_config()
    v1 = client.CoreV1Api()
    events = v1.list_namespaced_event(
        namespace=spawner.namespace,
        field_selector=f"involvedObject.name={spawner.pod_name}",
    )
    for event in events.items:
        name = event.metadata.name
        if name:
            v1.delete_namespaced_event(name=name, namespace=spawner.namespace)


async def pre_spawn_hook(spawner):
    # This will avoid the spamming of old events to a new spawn event
    # Requires JupyterHub Outpost Helm Chart 1.0.7 or newer
    delete_previous_events(spawner)


c.KubeSpawner.pre_spawn_hook = pre_spawn_hook


async def profile_list(spawner):
    jupyterhub_name = spawner.jupyterhub_name
    spawner.log.info(
        f"{spawner._log_name} - Received these user_options from {jupyterhub_name}-JupyterHub: {spawner.user_options}"
    )
    slug = spawner.user_options.get("profile", "default")
    default_image = "jupyter/minimal-notebook:notebook-7.0.3"
    flavor = spawner.user_options["flavor"]
    resources = get_flavor_resources(flavor)

    kubespawner_override = {
        "cpu_guarantee": resources["cpu_guarantee"],
        "cpu_limit": resources["cpu_limit"],
        "mem_guarantee": resources["mem_guarantee"],
        "mem_limit": resources["mem_limit"],
        # "node_selector": node_selector,
        "image": default_image,
        "slug": slug,
    }

    for key, value in kubespawner_override.items():
        kubespawner_override[key] = value

    return [
        {
            "display_name": "default",
            "default": True,
            "slug": slug,
            "kubespawner_override": kubespawner_override,
        }
    ]


c.KubeSpawner.profile_list = profile_list
