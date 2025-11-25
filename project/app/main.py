import asyncio
import datetime
import inspect
import logging
import multiprocessing
import os
from contextlib import asynccontextmanager

import requests
from api.services import full_stop_and_remove
from api.services import router as services_router
from database import models
from database.schemas import decrypt
from database.utils import get_services_all
from exceptions import SpawnerException
from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from spawner import get_wrapper
from tornado.httpclient import AsyncHTTPClient
from tornado.httpclient import HTTPRequest


logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
log = logging.getLogger(logger_name)

background_tasks = []


async def check_running_services():
    wrapper = get_wrapper()
    wrapper.init_logging()
    wrapper.update_logging()
    from database import db_url
    from database import engine_kwargs
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, **engine_kwargs)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sleep_timer = int(os.environ.get("JUPYTERHUB_CLEANUP_SLEEP_TIMER", "1800"))
    jhub_cleanup_names = os.environ.get("JUPYTERHUB_CLEANUP_NAMES", "")
    jhub_cleanup_urls = os.environ.get("JUPYTERHUB_CLEANUP_URLS", "")
    jhub_cleanup_tokens = os.environ.get("JUPYTERHUB_CLEANUP_TOKENS", "")
    if jhub_cleanup_names and jhub_cleanup_urls and jhub_cleanup_tokens:
        log.info(
            f"PeriodicCheck - Env variables are all set. Start check every 30 seconds for {jhub_cleanup_names}."
        )
        jhub_cleanup_names = jhub_cleanup_names.split(";")
        jhub_cleanup_urls_list = jhub_cleanup_urls.split(";")
        jhub_cleanup_tokens_list = jhub_cleanup_tokens.split(";")
        c_min = min(
            len(jhub_cleanup_names),
            len(jhub_cleanup_urls_list),
            len(jhub_cleanup_tokens_list),
        )
        c_max = max(
            len(jhub_cleanup_names),
            len(jhub_cleanup_urls_list),
            len(jhub_cleanup_tokens_list),
        )
        if c_min != c_max:
            log.warning(
                "PeriodicCheck - Mismatch in lengths of JUPYTERHUB_CLEANUP_NAMES, JUPYTERHUB_CLEANUP_URLS, and JUPYTERHUB_CLEANUP_TOKENS"
            )
        for i in range(c_min):
            log.info(
                f"PeriodicCheck - Values at index {i}: {jhub_cleanup_names[i]} {jhub_cleanup_urls_list[i]} {bool(jhub_cleanup_tokens_list[i])}"
            )
        while True:
            try:
                db = SessionLocal()
                running_services_in_jhub = {}
                running_services_on_system = {}
                i = 0
                for jhub_cleanup_name in jhub_cleanup_names:
                    if str(
                        os.environ.get("JUPYTERHUB_CLEANUP_K8S_CHECK", "false")
                    ).lower() in ["1", "true"]:
                        # If in a k8s cluster: list running servers
                        try:
                            from kubernetes_asyncio import client, config

                            config.load_incluster_config()
                            v1 = client.CoreV1Api()
                            namespace = os.environ.get(
                                "JUPYTERHUB_CLEANUP_NAMESPACE", "outpost"
                            )
                            label_selector = f"app={jhub_cleanup_name}"
                            pods = await v1.list_namespaced_pod(
                                namespace=namespace,
                                label_selector=label_selector,
                                _request_timeout=60,
                            )
                            await v1.api_client.close()
                            pod_names = [
                                pod.metadata.labels["hub.jupyter.org/servername"]
                                for pod in pods.items
                            ]
                            running_services_on_system[jhub_cleanup_name] = pod_names
                        except:
                            log.exception(
                                "PeriodicCheck - Could not check running services in kubernetes cluster"
                            )
                    # call request, check if it's running
                    try:
                        r = requests.get(
                            jhub_cleanup_urls_list[i],
                            headers={
                                "Authorization": f"token {jhub_cleanup_tokens_list[i]}",
                                "Accept": "application/json",
                            },
                            timeout=3,
                        )
                        r.raise_for_status()
                        running_services_in_jhub[jhub_cleanup_name] = r.json()
                    except:
                        log.exception(
                            f"PeriodicCheck - Could not check running services for {jhub_cleanup_name}"
                        )
                    finally:
                        i += 1
                all_services = get_services_all(db=db)
                all_services_names = []
                for service in all_services:
                    try:
                        all_services_names.append(service["name"])
                    except:
                        log.exception(
                            "PeriodicCheck - Could not add service name to list"
                        )
                    if service["jupyterhub"] in running_services_in_jhub.keys():
                        # Only check services which are running at least 30 minutes
                        if (
                            f"{service['jupyterhub_userid']}_{service['name']}_{service['start_id']}"
                            not in running_services_in_jhub[service["jupyterhub"]]
                            and (
                                datetime.datetime.now(datetime.timezone.utc)
                                - service["start_date"]
                            ).total_seconds()
                            > 1800
                        ):
                            log.info(
                                f"PeriodicCheck - {service['jupyterhub_userid']}_{service['name']}_{service['start_id']} is no longer running at {service['jupyterhub']}. Stop it."
                            )
                            try:
                                await full_stop_and_remove(
                                    service["jupyterhub"],
                                    service["name"],
                                    service["start_id"],
                                    db,
                                )
                            except:
                                log.exception(
                                    "PeriodicCheck - Could not stop / delete service object"
                                )
                for jhub_cleanup_name in jhub_cleanup_names:
                    if str(
                        os.environ.get("JUPYTERHUB_CLEANUP_K8S_CHECK", "false")
                    ).lower() in ["1", "true"]:
                        if (
                            len(running_services_on_system.get(jhub_cleanup_name, []))
                            > 0
                        ):
                            try:
                                v1 = None
                                namespace = os.environ.get(
                                    "JUPYTERHUB_CLEANUP_NAMESPACE", "outpost"
                                )
                                for pod_name in running_services_on_system.get(
                                    jhub_cleanup_name, []
                                ):
                                    if pod_name not in all_services_names:
                                        try:
                                            if not v1:
                                                from kubernetes_asyncio import (
                                                    client,
                                                    config,
                                                )

                                                config.load_incluster_config()
                                                v1 = client.CoreV1Api()
                                            await v1.delete_namespaced_pod(
                                                pod_name,
                                                namespace,
                                                grace_period_seconds=0,
                                                _request_timeout=60,
                                            )
                                            log.info(
                                                f"PeriodicCheck - Deleted pod {pod_name}"
                                            )
                                        except:
                                            log.exception(
                                                f"PeriodicCheck - Could not delete pod {pod_name}"
                                            )
                            except:
                                log.exception("PeriodicCheck - Could not delete pods")
                            finally:
                                try:
                                    await v1.api_client.close()
                                except:
                                    pass
            except:
                log.exception(
                    "PeriodicCheck - Unexpected error in internal cleanup service"
                )
            finally:
                db.close()
                await asyncio.sleep(sleep_timer)
    else:
        log.info(
            "PeriodicCheck - environment variables JUPYTERHUB_CLEANUP_NAMES, JUPYTERHUB_CLEANUP_URLS and JUPYTERHUB_CLEANUP_TOKENS not set. Do not run periodic cleanup check in background."
        )


async def check_enddates():
    wrapper = get_wrapper()
    wrapper.init_logging()
    wrapper.update_logging()
    from database import db_url
    from database import engine_kwargs
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, **engine_kwargs)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sleep_timer = int(os.environ.get("JUPYTERHUB_CHECK_ENDDATES_SLEEP_TIMER", "60"))
    while True:
        try:
            log.debug("Periodic check for ended services")
            now = datetime.datetime.now(datetime.timezone.utc)
            db = SessionLocal()
            services = get_services_all(jupyterhub_name=None, db=db)
            for service in services:
                try:
                    end_date = service["end_date"]
                    expired = now > end_date
                except:
                    # Previously we stored end_dates without timezones. Try to add one
                    try:
                        expired = now > end_date.replace(tzinfo=datetime.timezone.utc)
                    except:
                        expired = False
                        log.exception(f"Could not check end_date for {service}")
                if expired:
                    try:
                        log.info(
                            f"end_date check - Stop and remove {service['name']} ({service['start_id']}) ({service['jupyterhub']}) (end_date: {end_date})"
                        )
                        await full_stop_and_remove(
                            service["jupyterhub"],
                            service["name"],
                            service["start_id"],
                            db,
                        )
                    except:
                        log.exception(
                            "end_date check - Could not stop and remove service"
                        )
        except:
            log.exception("Exception in end date checked.")
        finally:
            db.close()
            await asyncio.sleep(sleep_timer)


def sync_check_enddates(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_enddates())


def sync_check_services(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_running_services())


@asynccontextmanager
async def lifespan(app: FastAPI):
    wrapper = get_wrapper()
    wrapper.init_logging()
    wrapper.update_logging()

    pid = os.getpid()
    lockfile = "/tmp/lifespan.lock"
    if not os.path.exists(lockfile):
        with open(lockfile, "w") as f:
            f.write(str(pid))
        print(f"Running lifespan init in first worker only ({pid}) ...")
        # Your init logic here
        await recreate_tunnels()
        print(f"Running lifespan init in first worker only ({pid}) ... done")
    else:
        print(f"Skipping lifespan init in this worker ({pid})")
    yield
    await shutdown_event()


def create_application() -> FastAPI:
    loop = None
    if os.environ.get("CHECK_ENDDATES", "true").lower() in ["true", "1"]:
        if not loop:
            loop = asyncio.get_event_loop()
        proc = multiprocessing.Process(target=sync_check_enddates, args=(loop,))
        background_tasks.append(proc)
        proc.start()
    if os.environ.get("CHECK_SERVICES", "true").lower() in ["true", "1"]:
        if not loop:
            loop = asyncio.get_event_loop()
        proc = multiprocessing.Process(target=sync_check_services, args=(loop,))
        background_tasks.append(proc)
        proc.start()
    if os.environ.get("DEBUG", "false").lower() in ["true", "1"]:
        import threading

        if not loop:
            loop = asyncio.new_event_loop()
        # check_enddates = threading.Thread(target=sync_check_enddates, args=(loop,))
        # check_enddates.start()
        check_services = threading.Thread(target=sync_check_services, args=(loop,))
        check_services.start()
    root_path = os.environ.get("OUTPOST_BASE_PATH", "")
    application = FastAPI(lifespan=lifespan, root_path=root_path)
    application.include_router(services_router)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    if root_path:
        log.info(f"Start JupyterHubOutpost with prefix {root_path}")
    else:
        log.info("Start JupyterHubOutpost")
    return application


app = create_application()


@app.get("/ping")
def ping():
    return {"ping": "pong!"}


async def recreate_tunnels():
    wrapper = get_wrapper()

    log.info("Recreate ssh tunnels during start up")
    from database import SessionLocal
    import json

    try:
        db = SessionLocal()
        services = db.query(models.Service).all()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        http_client = AsyncHTTPClient(
            force_instance=True, defaults=dict(validate_cert=False)
        )
        background_set = set()

        def fetch_in_background(req, service_name):
            task = asyncio.create_task(_do_fetch(req, service_name))
            background_set.add(task)
            task.add_done_callback(background_set.discard)

        async def _do_fetch(req, service_name):
            for attempt in range(5):
                try:
                    await http_client.fetch(req)
                    log.info(
                        f"Tunnel restarted for {service_name} (attempt {attempt + 1})"
                    )
                    return
                except Exception:
                    log.exception(
                        f"Attempt {attempt + 1}/5: Could not restart tunnel during startup for {service_name}"
                    )
                    await asyncio.sleep(5)

            log.error(f"Failed to restart tunnel for {service_name} after 5 attempts.")

        jupyterhub_usernames = list(
            {x.jupyterhub_username for x in services if x.jupyterhub_username}
        )

        if callable(wrapper.ssh_recreate_at_start_global):
            ssh_recreate_at_start_global = wrapper.ssh_recreate_at_start_global(
                wrapper, jupyterhub_usernames
            )
            if inspect.isawaitable(ssh_recreate_at_start_global):
                ssh_recreate_at_start_global = await ssh_recreate_at_start_global
        else:
            ssh_recreate_at_start_global = wrapper.ssh_recreate_at_start_global

        if not ssh_recreate_at_start_global:
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
                        if isinstance(start_response, dict):
                            start_response = json.dumps(start_response)

                        if tunnel_url and api_token:
                            headers["Authorization"] = f"token {api_token}"
                            req = HTTPRequest(
                                url=tunnel_url,
                                method="POST",
                                headers=headers,
                                body=start_response,
                            )
                            try:
                                fetch_in_background(req, service.name)
                            except:
                                log.exception(
                                    f"Could not restart tunnel during startup for {service.name}"
                                )
                except:
                    log.exception(f"Could not restart tunnel for {service.name}")
    finally:
        db.close()


async def shutdown_event():
    for t in background_tasks:
        t.terminate()


@app.exception_handler(SpawnerException)
async def spawner_exception_handler(
    request: Request, exc: SpawnerException
) -> JSONResponse:
    return JSONResponse(
        status_code=419,
        content={
            "module": exc.module,
            "class": exc.class_name,
            "traceback": exc.traceback,
            "args": exc.args,
            "kwargs": exc.kwargs,
        },
    )
