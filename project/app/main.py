import inspect
import logging

from application import app
from database import models
from database.schemas import decrypt
from spawner import get_wrapper
from starlette.responses import RedirectResponse
from tornado.httpclient import AsyncHTTPClient
from tornado.httpclient import HTTPRequest


log = logging.getLogger("uvicorn")


@app.get("/")
def main():
    return RedirectResponse(url="/docs")


@app.get("/ping")
def ping():
    return {"ping": "pong!"}


@app.on_event("startup")
async def recreate_tunnels():
    wrapper = get_wrapper()

    log.info("Recreate ssh tunnels during start up")
    from database import SessionLocal

    try:
        db = SessionLocal()
        services = db.query(models.Service).all()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        http_client = AsyncHTTPClient(
            force_instance=True, defaults=dict(validate_cert=False)
        )
        for service in services:
            try:
                if callable(wrapper.ssh_recreate_at_start):
                    ssh_recreate_at_start = wrapper.ssh_recreate_at_start(
                        wrapper, service.jupyterhub_username
                    )
                    if inspect.isawaitable(ssh_recreate_at_start):
                        ssh_recreate_at_start = await ssh_recreate_at_start
                else:
                    ssh_recreate_at_start = wrapper.ssh_recreate_at_start
                if ssh_recreate_at_start:
                    body = decrypt(service.body)
                    tunnel_url = body.get("env", {}).get(
                        "JUPYTERHUB_SETUPTUNNEL_URL", ""
                    )
                    api_token = body.get("env", {}).get("JUPYTERHUB_API_TOKEN", "")
                    start_response = decrypt(service.start_response)

                    if tunnel_url and api_token:
                        headers["Authorization"] = f"token {api_token}"
                        req = HTTPRequest(
                            url=tunnel_url,
                            method="POST",
                            headers=headers,
                            body=start_response,
                        )
                        try:
                            await http_client.fetch(req)
                            log.info(f"Tunnel restarted for {service.name}")
                        except:
                            log.exception(
                                f"Could not restart tunnel during startup for {service.name}"
                            )
            except:
                log.exception(f"Could not restart tunnel for {service.name}")
    finally:
        db.close()


background_task = []

import os
from datetime import datetime
from database.utils import get_services_all
import asyncio
from api.services import full_stop_and_remove
from database.utils import get_db


class BackgroundRunner:
    def __init__(self):
        logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
        self.log = logging.getLogger(logger_name)

    async def check_enddates(self):
        while True:
            self.log.info("Periodic check for ended services")
            now = datetime.now()
            services = get_services_all(jupyterhub_name=None, db=next(get_db()))
            for service in services:
                if service["end_date"] > now:
                    try:
                        self.log.info(f"Stop and remove {service['name']}")
                        await full_stop_and_remove(
                            service["jupyterhub"], service["name"]
                        )
                    except:
                        self.log.exception("Could not stop and remove service")
            await asyncio.sleep(30)


runner = BackgroundRunner()


@app.on_event("startup")
async def app_startup():
    asyncio.create_task(runner.check_enddates())


# @app.on_event("shutdown")
# async def shutdown_event():
#     log.info("shutting down")
