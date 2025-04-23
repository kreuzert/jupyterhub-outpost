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

    async def stop(self, *args, **kwargs):
        pass


class OutpostSpawner:
    environment = {}
    jupyterhub_name = ""
    start_id = ""
    flavor = {}

    def clear_state(self):
        store_unique_id = self.start_id
        super().clear_state()
        self.start_id = store_unique_id

    def __init__(
        self,
        jupyterhub_name,
        service_name,
        start_id,
        orig_body,
        certs,
        internal_trust_bundles,
        user_flavor,
        **config,
    ):
        self.user = config["user"]
        self.hub = config["hub"]
        self.jupyterhub_name = jupyterhub_name
        self.start_id = start_id
        self.name = service_name
        self.environment = {}
        env = orig_body.get("environment", {})
        if not env:
            env = orig_body.get("env", {})
        for key, value in env.items():
            self.environment[key] = str(value)
        self.user_options = orig_body.get("user_options", {})
        self.flavor = user_flavor

        if certs:
            self.internal_ssl = True
            out_dir = f"{certs_dir}/{jupyterhub_name}-{self.name}-{self.start_id}"
            shutil.rmtree(out_dir, ignore_errors=True)
            os.makedirs(out_dir, 0o700, exist_ok=True)

            self.cert_paths = {
                "keyfile": f"{out_dir}/{self.user.name}.key",
                "certfile": f"{out_dir}/{self.user.name}.crt",
                "cafile": f"{out_dir}/notebooks-ca_trust.crt",
            }
            for key, path in self.cert_paths.items():
                with open(path, "w") as f:
                    f.write(certs.get(key, ""))

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
                    f.write(internal_trust_bundles.get(key, ""))
                self.internal_trust_bundles[key] = path
        else:
            self.internal_ssl = False
            self.environment.pop("JUPYTERHUB_SSL_CERTFILE", None)
            self.environment.pop("JUPYTERHUB_SSL_KEYFILE", None)
            self.environment.pop("JUPYTERHUB_SSL_CLIENT_CA", None)

        for k, v in config.items():
            if hasattr(self, k):
                try:
                    setattr(self, k, v)
                except:
                    pass
        super().__init__()

    def get_env(self):
        env = super().get_env()
        env.update(self.environment)
        return env
