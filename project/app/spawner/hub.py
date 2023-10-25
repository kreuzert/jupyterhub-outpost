import os
import shutil

from jupyterhub.utils import url_escape_path

certs_dir = "/tmp/jupyterhub-certs"


class OutpostHub:
    api_url = ""
    base_url = ""
    public_host = ""

    def __init__(self, orig_body, *args, **kwargs) -> None:
        self.api_url = orig_body.get("env", {}).get("JUPYTERHUB_API_URL", "")
        self.base_url = orig_body.get("env", {}).get("JUPYTERHUB_BASE_URL", "")
        self.public_host = orig_body.get("env", {}).get("JUPYTERHUB_HOST", "")


class OutpostJupyterHub:
    hub = None

    def __init__(self, orig_body, *args, **kwargs):
        self.hub = OutpostHub(orig_body)


class OutpostUser:
    url = ""
    id = -1
    auth_state = {}

    @property
    def escaped_name(self):
        """My name, escaped for use in URLs, cookies, etc."""
        return url_escape_path(self.name)

    def __init__(self, orig_body, auth_state, *args, **kwargs):
        self.name = orig_body.get("env", {}).get("JUPYTERHUB_USER", "")
        self.id = int(orig_body.get("env", {}).get("JUPYTERHUB_USER_ID", "-1"))
        self.auth_state = auth_state

    async def get_auth_state(self):
        return self.auth_state


class OutpostSpawner:
    env = {}
    jupyterhub_name = ""

    def __init__(self, jupyterhub_name, service_name, orig_body, **config):
        self.user = config["user"]
        self.hub = config["hub"]
        self.jupyterhub_name = jupyterhub_name
        self.name = service_name
        for key, value in orig_body.get("env", {}).items():
            self.env[key] = str(value)
        self.user_options = orig_body.get("user_options", {})

        if orig_body.get("certs", {}):
            self.internal_ssl = True
            out_dir = f"{certs_dir}/{jupyterhub_name}-{self.name}"
            shutil.rmtree(out_dir, ignore_errors=True)
            os.makedirs(out_dir, 0o700, exist_ok=True)

            self.cert_paths = {
                "keyfile": f"{out_dir}/{self.user.name}.key",
                "certfile": f"{out_dir}/{self.user.name}.crt",
                "cafile": f"{out_dir}/notebooks-ca_trust.crt",
            }
            for key, path in self.cert_paths.items():
                with open(path, "w") as f:
                    f.write(orig_body.get("certs", {}).get(key, ""))

            internal_trust_bundles_list = [
                "hub-ca",
                "proxy-api-ca",
                "proxy-client-ca",
                "notebooks-ca",
                "services-ca",
            ]
            self.internal_trust_bundles = {}
            for key in internal_trust_bundles_list:
                path = f"{out_dir}/{key}.crt"
                with open(path, "w") as f:
                    f.write(orig_body.get("internal_trust_bundles", {}).get(key, ""))
                self.internal_trust_bundles[key] = path
        else:
            self.internal_ssl = False
            self.env.pop("JUPYTERHUB_SSL_CERTFILE", None)
            self.env.pop("JUPYTERHUB_SSL_KEYFILE", None)
            self.env.pop("JUPYTERHUB_SSL_CLIENT_CA", None)

        super().__init__(**config)

    def get_env(self):
        env = super().get_env()
        env.update(self.env)
        return env
