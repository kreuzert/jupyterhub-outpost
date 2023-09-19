import logging
import os
import traceback
from functools import wraps

logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
log = logging.getLogger(logger_name)

# Sender can get info with:
# json_message = json.loads(exc.response.body.decode())
# json_message["args"]


class SpawnerException(Exception):
    module = ""
    class_name = ""
    traceback = ""
    args = []
    kwargs = {}

    def __init__(self, module, class_name, traceback, args=[], kwargs={}):
        self.module = module
        self.class_name = class_name
        self.traceback = traceback
        self.args = args
        self.kwargs = kwargs


def catch_exception(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            module = getattr(e, "__module__", "")
            if module == "fastapi.exceptions":
                raise e
            args = getattr(e, "args", [])
            msg = "Unknown"
            if len(args) > 0:
                msg = args[0]
            log.exception(f"Exception: {msg}")
            raise SpawnerException(
                module,
                e.__class__.__name__,
                traceback.format_exc(),
                args,
                getattr(e, "kwargs", {}),
            )

    return wrapper
