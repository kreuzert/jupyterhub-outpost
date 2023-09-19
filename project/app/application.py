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


def create_application() -> FastAPI:
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
