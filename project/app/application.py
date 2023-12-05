import asyncio
import logging
import multiprocessing
import os
from datetime import datetime
from datetime import timezone

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


async def check_enddates():
    while True:
        try:
            log.info("Periodic check for ended services")
            now = datetime.now(timezone.utc)
            db = next(get_db())
            services = get_services_all(jupyterhub_name=None, db=db)
            for service in services:
                end_date = service["end_date"]
                if now > end_date:
                    try:
                        log.info(
                            f"end_date check - Stop and remove {service['name']} ({service['jupyterhub']}) (end_date: {end_date})"
                        )
                        await full_stop_and_remove(
                            service["jupyterhub"], service["name"], db
                        )
                    except:
                        log.exception(
                            "end_date check - Could not stop and remove service"
                        )
            await asyncio.sleep(30)
        except:
            log.exception("Exception in end date checked.")
            await asyncio.sleep(30)


def sync_check_enddates(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_enddates())


wrapper = get_wrapper()
wrapper.init_logging()
wrapper.update_logging()


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
