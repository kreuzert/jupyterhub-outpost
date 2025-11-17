import os

import yaml


def get_flavors_from_disk():
    path = os.environ.get("OUTPOST_FLAVORS_PATH", "/mnt/flavors/flavors.yaml")
    if (not os.path.exists(path)) or (not os.path.isfile(path)):
        return {}
    with open(path, "r") as f:
        flavor_config = yaml.full_load(f)
    return flavor_config
