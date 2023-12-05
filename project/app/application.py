import logging
import os

from api.services import router as services_router
from exceptions import SpawnerException
from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
log = logging.getLogger(logger_name)


import os
import multiprocessing
from datetime import datetime
from database.utils import get_services_all
import asyncio
from api.services import full_stop_and_remove
from database.utils import get_db

background_tasks = []


async def check_enddates():
    while True:
        log.info("Periodic check for ended services")
        print("Periodic check for ended services")
        now = datetime.utcnow()
        db = next(get_db())
        services = get_services_all(jupyterhub_name=None, db=db)
        for service in services:
            log.info(f"Compare now: {now.replace(tzinfo=None)}")
            log.info(f"and     end: {service['end_date'].replace(tzinfo=None)}")
            print(f"Compare now: {now.replace(tzinfo=None)}")
            print(f"and     end: {service['end_date'].replace(tzinfo=None)}")
            if service["end_date"].replace(tzinfo=None) > now.replace(tzinfo=None):
                try:
                    log.info(
                        f"end_date check - Stop and remove {service['name']} (end_date: {service['end_date']})"
                    )
                    print(
                        f"end_date check - Stop and remove {service['name']} (end_date: {service['end_date']})"
                    )
                    await full_stop_and_remove(
                        service["jupyterhub"], service["name"], db
                    )
                except:
                    log.exception("end_date check - Could not stop and remove service")
        await asyncio.sleep(30)


def sync_check_enddates(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_enddates())


def create_application() -> FastAPI:
    global background_tasks
    loop = asyncio.get_event_loop()
    proc = multiprocessing.Process(target=sync_check_enddates, args=(loop,))
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
    log.info("Start JupyterHubOutpost ( (55ed4c44))")
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
