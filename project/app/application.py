import asyncio
import logging
import multiprocessing
import os
from datetime import datetime
from datetime import timezone

import requests
from api.services import full_stop_and_remove
from api.services import router as services_router
from database.utils import get_db
from database.utils import get_services_all
from exceptions import SpawnerException
from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from spawner import get_wrapper


logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
log = logging.getLogger(logger_name)

background_tasks = []


async def check_running_services():
    from database import db_url
    from database import engine_kwargs
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, **engine_kwargs)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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
        while True:
            try:
                db = SessionLocal()
                running_services_in_jhub = {}
                i = 0
                for jhub_cleanup_name in jhub_cleanup_names:
                    # call request, check if it's running
                    log.debug(f"PeriodicCheck - Call list servers {jhub_cleanup_name}.")
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
                            "PeriodicCheck - Could not check running services"
                        )
                    finally:
                        i += 1
                all_services = get_services_all(db=db)
                for service in all_services:
                    if service["jupyterhub"] in running_services_in_jhub.keys():
                        if (
                            f"{service['jupyterhub_userid']}_{service['name']}_{service['start_id']}"
                            not in running_services_in_jhub[service["jupyterhub"]]
                        ):
                            log.info(
                                f"PeriodicCheck - {service['name']} is no longer running at {service['jupyterhub']}. Stop it."
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
            except:
                log.exception(
                    "PeriodicCheck - Unexpected error in internal cleanup service"
                )
            finally:
                db.close()
                await asyncio.sleep(30)
    else:
        log.info(
            "PeriodicCheck - environment variables JUPYTERHUB_CLEANUP_NAMES, JUPYTERHUB_CLEANUP_URLS and JUPYTERHUB_CLEANUP_TOKENS not set. Do not run periodic cleanup check in background."
        )


async def check_enddates():
    from database import db_url
    from database import engine_kwargs
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, **engine_kwargs)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    while True:
        try:
            log.debug("Periodic check for ended services")
            now = datetime.now(timezone.utc)
            db = SessionLocal()
            services = get_services_all(jupyterhub_name=None, db=db)
            for service in services:
                end_date = service["end_date"]
                if now > end_date:
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
            await asyncio.sleep(30)


def sync_check_enddates(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_enddates())


def sync_check_services(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_running_services())


wrapper = get_wrapper()
wrapper.init_logging()
wrapper.update_logging()


def create_application() -> FastAPI:
    global background_tasks
    loop = asyncio.get_event_loop()
    proc = multiprocessing.Process(target=sync_check_enddates, args=(loop,))
    background_tasks.append(proc)
    proc.start()
    proc = multiprocessing.Process(target=sync_check_services, args=(loop,))
    background_tasks.append(proc)
    proc.start()
    application = FastAPI()
    application.include_router(services_router)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    log.info("Start JupyterHubOutpost")
    return application


app = create_application()


@app.on_event("shutdown")
async def shutdown_event():
    global background_tasks
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
