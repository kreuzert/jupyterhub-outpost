import json
import logging
import os

from unicorespawner import UnicoreSpawner

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

# Not all JupyterHubs are allowed to override this configuration
async def allow_override(jupyterhub_name, misc):
    if jupyterhub_name == "vanilla":
        return True
    return False


c.JupyterHubOutpost.allow_override = allow_override

# Port-Forwarding feature in Outpost is not used with UnicoreSpawner
c.JupyterHubOutpost.ssh_recreate_at_start = False


c.JupyterHubOutpost.spawner_class = UnicoreSpawner

# These are the systems supported by this Outpost configurations.
system_config = {
    "JURECA": {"url": "https://zam2125.zam.kfa-juelich.de:9112/JURECA/rest/core"},
    "JUWELS": {"url": "https://zam2125.zam.kfa-juelich.de:9112/JUWELS/rest/core"},
    "JUSUF": {"url": "https://zam2125.zam.kfa-juelich.de:9112/JUSUF/rest/core"},
    "HDFML": {"url": "https://zam2125.zam.kfa-juelich.de:9112/HDFML/rest/core"},
    "DEEP": {"url": "https://zam2125.zam.kfa-juelich.de:9112/DEEP/rest/core"},
}


async def site_urls(spawner):
    system = spawner.user_options.get("system", "None")
    return system_config.get(system, {}).get("url", "None")


c.UnicoreSpawner.unicore_site_url = site_urls

# If user_options.partition is in here it will start an interactive job
# The value will be used in job description at "Login node"
partition_to_login_nodes = {
    "JURECA": {"LoginNode": "jureca??.fz-juelich.de"},
    "JUWELS": {
        "LoginNode": "juwels0?.fz-juelich.de",
        "LoginNodeVis": "juwelsvis??.fz-juelich.de",
        "LoginNodeBooster": "juwels2?.fz-juelich.de",
    },
    "JUSUF": {
        "LoginNode": "jusuf?.fz-juelich.de",
    },
    "HDFML": {"LoginNode": "hdfmll??.fz-juelich.de"},
    "DEEP": {"LoginNode": "deep.fz-juelich.de"},
}

# Load job description from configmap volumeMount
# Add parameters given by user options
async def get_job_description(spawner):
    job = spawner.user_options.get("job", "None")
    system = spawner.user_options.get("system", "None")
    partition = spawner.user_options.get("partition", "None")

    if os.path.isfile(f"/mnt/jobs/{job}_job_description.json"):
        with open(f"/mnt/jobs/{job}_job_description.json", "r") as f:
            job_description = json.load(f)
    elif os.path.isfile("/mnt/jobs/common_job_description.json"):
        with open("/mnt/jobs/common_job_description.json", "r") as f:
            job_description = json.load(f)
    else:
        raise Exception(f"Could not find job description file for {job}")

    job_description["Imports"] = []
    for subdir, dirs, files in os.walk("/mnt/jobs"):
        for file in files:
            for prefix in ["common_", f"{job}_"]:
                if file.startswith(prefix):
                    if file == f"{prefix}job_description.json":
                        continue
                    with open(os.path.join(subdir, file), "r") as f:
                        tmp = f.read().strip()
                        job_description["Imports"].append(
                            {
                                "From": "inline://dummy",
                                "To": file.removeprefix(prefix),
                                "Data": tmp,
                            }
                        )

    if "Environment" not in job_description.keys():
        job_description["Environment"] = {}
    for key, value in spawner.get_env().items():
        if key.startswith("JUPYTERHUB_") and key not in [
            "JUPYTERHUB_OAUTH_SCOPES",
            "JUPYTERHUB_API_TOKEN",
        ]:
            job_description["Environment"][key] = str(value)

    is_interactive = partition in partition_to_login_nodes.get(system, {}).keys()
    if is_interactive:
        job_description["Job type"] = "on_login_node"
        job_description["Login node"] = partition_to_login_nodes[system][partition]
    else:
        job_description["Job type"] = "batch"
        nodes = spawner.user_options.get("nodes", "1")
        runtime = spawner.user_options.get("runtime", "30")
        gpus = spawner.user_options.get("gpus", None)
        job_description["Resources"] = {
            "Queue": partition,
            "Runtime": runtime,
            "Nodes": nodes,
        }
        if gpus:
            job_description["Resources"]["GPUS"] = gpus

    return job_description


# within the job description (or its input files) variables are used.
# Values for these variables are defined in here
async def additional_replacements(spawner):
    remote_port = os.environ.get("REMOTE_PORT", "56589")
    return {
        "system": {
            "JUWELS": {
                "remote_port": remote_port,
                "hostname_base": "jwlogin",
                "hostname_cpulimit": "login|vis",
                "hostname_all": "'jwlogin02i' 'jwlogin03i' 'jwlogin04i' 'jwlogin05i' 'jwlogin06i' 'jwlogin07i' 'jwlogin08i' 'jwlogin09i' 'jwlogin10i' 'jwlogin11i'",
            },
            "JURECA": {
                "remote_port": remote_port,
                "hostname_base": "jrlogin",
                "hostname_cpulimit": "login|vis",
                "hostname_all": "'jrlogin01i' 'jrlogin02i' 'jrlogin03i' 'jrlogin04i' 'jrlogin05i' 'jrlogin06i' 'jrlogin07i' 'jrlogin08i' 'jrlogin09i' 'jrlogin10i' 'jrlogin11i' 'jrlogin12i'",
            },
            "JUSUF": {
                "remote_port": remote_port,
                "hostname_base": "jsfl0",
                "hostname_cpulimit": "login|vis",
                "hostname_all": "'jsfl01i' 'jsfl02i' 'jsfl03i' 'jsfl04i'",
            },
            "HDFML": {
                "remote_port": remote_port,
                "hostname_base": "hdfmll",
                "hostname_cpulimit": "login|vis",
                "hostname_all": "'hdfmll01i' 'hdfmll02i'",
            },
            "DEEP": {
                "remote_port": remote_port,
                "hostname_base": "deepv",
                "hostname_cpulimit": "login|vis",
                "hostname_all": "'deepv'",
            },
        },
    }


c.UnicoreSpawner.additional_replacements = additional_replacements

# Authentication configuration for UNICORE
async def transport_kwargs(spawner):
    auth_state = await spawner.user.get_auth_state()
    return {
        "oidc": True,
        "verify": False,
        "timeout": 30,
        "credential": auth_state["access_token"],
    }


async def transport_preferences(spawner):
    account = spawner.user_options.get("account", "None")
    project = spawner.user_options.get("project", "None")
    return f"uid:{account},group:{project}"


c.UnicoreSpawner.unicore_transport_kwargs = transport_kwargs
c.UnicoreSpawner.unicore_transport_preferences = transport_preferences


# Available jobs in this Outpost
job_descriptions = {"JupyterLab_3.6": get_job_description}
c.UnicoreSpawner.job_descriptions = job_descriptions


c.UnicoreSpawner.show_first_default_event = False
c.UnicoreSpawner.unicore_internal_forwarding = False
