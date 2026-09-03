import os

from dockerspawner import DockerSpawner

c.JupyterHubOutpost.spawner_class = DockerSpawner

# That's the hostname / ip where the Outpost can reach the Jupyter notebook server
async def my_sanitize_start_response(spawner, start_response):
    s = f"{spawner.container_id[:12]}:{start_response[1]}"
    spawner.log.debug(f"Sanitizing start response: https://{s}")
    return s


c.JupyterHubOutpost.sanitize_start_response = my_sanitize_start_response

c.DockerSpawner.network_name = os.environ["DOCKER_NETWORK_NAME"]

c.DockerSpawner.remove = True

c.DockerSpawner.image = "quay.io/jupyter/minimal-notebook:latest"

# The quay.io jupyter minimal notebook has an internal health check
# configured. This disables it, because it does not use client certificates
# and fails anyway if you're using c.JupyterHub.internal_ssl = True
c.DockerSpawner.extra_create_kwargs = {"healthcheck": {"Test": ["NONE"]}}
