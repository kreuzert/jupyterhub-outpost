import asyncio
import inspect
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from async_generator import aclosing
from database.schemas import decrypt
from database.schemas import encrypt
from database.utils import get_service
from jupyterhub.log import CoroutineLogFormatter
from jupyterhub.spawner import LocalProcessSpawner
from jupyterhub.spawner import Spawner
from jupyterhub.traitlets import EntryPointType
from jupyterhub.utils import iterate_until
from jupyterhub.utils import maybe_future
from tornado.httpclient import AsyncHTTPClient
from tornado.httpclient import HTTPRequest
from tornado.log import access_log
from tornado.log import app_log
from tornado.log import gen_log
from traitlets import Any
from traitlets import Bool
from traitlets import Callable
from traitlets import default
from traitlets import Dict
from traitlets import Instance
from traitlets import List
from traitlets import Union
from traitlets.config import Application

from .hub import OutpostJupyterHub
from .hub import OutpostSpawner
from .hub import OutpostUser


class JupyterHubOutpost(Application):
    """
    This class will contain the Spawner objects.
    You can configure your own JupyterHub Spawner
    like you're used to do for JupyterHub itself.

    Example config file ( at $OUTPOST_CONFIG_FILE):
    ```
    from jupyterhub.spawner import SimpleLocalProcessSpawner
    c.JupyterHubOutpost.spawner_class = SimpleLocalProcessSpawner
    c.SimpleLocalProcessSpawner.port = 4567
    ```

    """

    # Contains all spawner objects.
    spawners = {}

    def remove_spawner(self, jupyterhub_name, service_name):
        self.log.debug(f"Remove spawner in memory {service_name} for {jupyterhub_name}")
        if f"{jupyterhub_name}-{service_name}" in self.spawners.keys():
            if self.spawners[f"{jupyterhub_name}-{service_name}"].cert_paths:
                for path in self.spawners[
                    f"{jupyterhub_name}-{service_name}"
                ].cert_paths.values():
                    try:
                        Path(path).unlink(missing_ok=True)
                    except:
                        self.log.exception(f"Could not delete {path} cert file.")
                for path in self.spawners[
                    f"{jupyterhub_name}-{service_name}"
                ].internal_trust_bundles.values():
                    try:
                        Path(path).unlink(missing_ok=True)
                    except:
                        self.log.exception(f"Could not delete {path} cert file.")
                try:
                    Path(
                        self.spawners[f"{jupyterhub_name}-{service_name}"].cert_paths[
                            "certfile"
                        ]
                    ).parent.rmdir()
                except:
                    self.log.exception(
                        "Could not delete parent cert dir of {self._log_name}."
                    )
            del self.spawners[f"{jupyterhub_name}-{service_name}"]

    async def get_spawner(self, jupyterhub_name, service_name, orig_body):
        if f"{jupyterhub_name}-{service_name}" not in self.spawners:
            self.log.debug(
                f"Create Spawner object {service_name} for {jupyterhub_name}"
            )
            spawner = await self._new_spawner(jupyterhub_name, service_name, orig_body)
            self.spawners[f"{jupyterhub_name}-{service_name}"] = spawner
        return self.spawners[f"{jupyterhub_name}-{service_name}"]

    allow_override = Any(
        default_value=None,
        help="""
        An optional hook function that you can implement to decide if
        the Spawner configuration can be overriden.
        
        The parameter for this function will be the credential username
        and the used `misc` (from JupyterHub.OutpostSpawner.custom_misc)
        configuration in this request.
        
        The result of this function has to be a boolean.
        True: if it's ok to override the given values
        False: if it's not ok to override.
        
        This maybe a coroutine. 

        Example::
        
            async def allow_override(jupyterhub_credential, misc):
                if jupyterhub_credential == "jupyterhub":
                    return True
                return False

            c.JupyterHubOutpost.allow_override = allow_override

        """,
    ).tag(config=True)

    sanitize_start_response = Any(
        default_value=None,
        help="""
        An optional hook function that you can implement to modify the
        response of the start process. 
        
        The result of this function will be sent to JupyterHub in the Location
        header.
        
        This maybe a coroutine.

        Example::
        
            async def my_sanitize_start_response(spawner, start_response):
                return f"{start_response[0]}:{start_response[1]}"

            c.JupyterHubOutpost.sanitize_start_response = my_sanitize_start_response

        """,
    ).tag(config=True)

    request_kwargs = Union(
        [Dict(), Callable()],
        default_value={"validate_cert": False, "request_timeout": 10},
        help="""
        Allows you to add additional keywords to HTTPRequest Object.
        Example::
        
            ca_certs,
            validate_cert,
            request_timeout
        """,
    ).tag(config=True)

    def get_request_kwargs(self):
        if callable(self.request_kwargs):
            request_kwargs = self.request_kwargs(self)
        else:
            request_kwargs = self.request_kwargs
        return request_kwargs

    # Create a DummySpawner object.
    async def _new_spawner(wrapper, jupyterhub_name, service_name, orig_body):
        # self.config.get('spawner_class', LocalProcessSpawner).get()
        # spawner_class = self.config.get("JupyterHubOutpost", {}).get("spawner_class", LocalProcessSpawner)
        class DummySpawner(
            OutpostSpawner,
            wrapper.config.get("JupyterHubOutpost", {}).get(
                "spawner_class", LocalProcessSpawner
            ),
        ):
            spawner_class = str(
                wrapper.config.get("JupyterHubOutpost", {}).get(
                    "spawner_class", LocalProcessSpawner
                )
            )
            name = service_name
            log = wrapper.log
            http_client = Any

            @default("http_client")
            def _default_http_client(self):
                return AsyncHTTPClient(
                    force_instance=True, defaults=dict(validate_cert=False)
                )

            async def _outpostspawner_send_event(self, event):
                request_header = {
                    "Authorization": f"token {self.env.get('JUPYTERHUB_API_TOKEN')}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                event_url = self.env.get("JUPYTERHUB_EVENTS_URL", "")
                req = HTTPRequest(
                    url=event_url,
                    method="POST",
                    headers=request_header,
                    body=json.dumps(event),
                    **wrapper.get_request_kwargs(),
                )
                try:
                    await self.http_client.fetch(req)
                except:
                    self.log.exception(
                        f"Could not send event to {event_url} for {self._log_name}: {event.get('html_message', event.get('message', ''))}"
                    )

            async def _outpostspawner_forward_events(self, future):
                # retrieve progress events from the Spawner
                self._spawn_pending = True
                async with aclosing(
                    iterate_until(future, self._generate_progress())
                ) as events:
                    try:
                        async for event in events:
                            # don't allow events to sneakily set the 'ready' flag
                            if "ready" in event:
                                event.pop("ready", None)
                            await self._outpostspawner_send_event(event)
                    except asyncio.CancelledError:
                        pass

                await asyncio.wait([future])
                future = None
                self._spawn_pending = False

            async def _outpostspawner_db_start(self, db):
                _outpostspawner_start_future = asyncio.ensure_future(
                    self._outpostspawner_db_start_call(db)
                )
                if self.env.get("JUPYTERHUB_EVENTS_URL", ""):
                    asyncio.ensure_future(
                        self._outpostspawner_forward_events(
                            _outpostspawner_start_future
                        )
                    )
                await asyncio.wait([_outpostspawner_start_future])
                try:
                    return _outpostspawner_start_future.result()
                except asyncio.CancelledError:
                    raise Exception(f"Start of {self._log_name} was cancelled.")

            async def _outpostspawner_db_start_call(self, db):
                self.clear_state()
                self.run_pre_spawn_hook()
                if self.cert_paths:
                    cert_paths = self.move_certs(self.cert_paths)
                    if inspect.isawaitable(cert_paths):
                        cert_paths = await cert_paths
                    self.cert_paths = cert_paths

                ret = await maybe_future(self.start())
                if wrapper.sanitize_start_response:
                    ret = wrapper.sanitize_start_response(self, ret)
                    if inspect.isawaitable(ret):
                        ret = await ret
                elif type(ret) == tuple and len(ret) == 2:
                    ret = f"{ret[0]}:{ret[1]}"

                service = get_service(jupyterhub_name, self.name, db)
                service.state = encrypt(self.get_state())
                service.start_response = encrypt({"service": ret})
                db.commit()
                return ret

            async def _outpostspawner_db_poll(self, db):
                # Update from db
                service = get_service(jupyterhub_name, self.name, db)
                self.load_state(decrypt(service.state))
                ret = self.poll()
                if inspect.isawaitable(ret):
                    ret = await ret
                service.last_update = datetime.now()
                db.commit()
                return ret

            async def _outpostspawner_db_stop(self, db, now=False):
                _outpostspawner_stop_future = asyncio.ensure_future(
                    self._outpostspawner_db_stop_call(db, now)
                )
                await asyncio.wait([_outpostspawner_stop_future])
                return _outpostspawner_stop_future.result()

            async def _outpostspawner_db_stop_call(self, db, now=False):
                # Update from db
                service = get_service(jupyterhub_name, self.name, db)
                self.load_state(decrypt(service.state))
                ret = self.stop(now)
                if inspect.isawaitable(ret):
                    ret = await ret
                self.run_post_stop_hook()
                self.clear_state()
                db.delete(service)
                db.commit()
                return ret

        if wrapper.allow_override and orig_body.get("misc", {}):
            ret = wrapper.allow_override(jupyterhub_name, orig_body.get("misc", {}))
            if inspect.isawaitable(ret):
                ret = await ret
            if not ret:
                raise Exception(
                    f"{jupyterhub_name} is not allowed to override the configuration. Used keys: {list(orig_body.get('misc', {}).keys())}"
                )

        spawner_class_name = (
            wrapper.config.get("JupyterHubOutpost", {})
            .get("spawner_class", LocalProcessSpawner)
            .__name__
        )
        config = wrapper.config.get(spawner_class_name, {})
        config.update(
            {"hub": OutpostJupyterHub(orig_body).hub, "user": OutpostUser(orig_body)}
        )
        for key, value in orig_body.get("misc", {}).items():
            wrapper.log.debug(
                f"Override configuration via misc for {service_name}: {key} - {value}"
            )
            config[key] = value

        spawner = DummySpawner(jupyterhub_name, service_name, orig_body, **config)
        return spawner

    _log_formatter_cls = CoroutineLogFormatter

    @default("log_format")
    def _log_format_default(self):
        """override default log format to include time"""
        return "%(color)s[%(levelname)1.1s %(asctime)s.%(msecs).03d %(name)s %(module)s:%(lineno)d]%(end_color)s %(message)s"

    @default("log_datefmt")
    def _log_datefmt_default(self):
        """Exclude date from default date format"""
        return "%Y-%m-%d %H:%M:%S"

    extra_log_handlers = List(
        Instance(logging.Handler), help="Extra log handlers to set on JupyterHub logger"
    ).tag(config=True)

    ssh_recreate_at_start = Union(
        [Callable(), Bool()],
        default_value=True,
        help="""
        Whether ssh tunnels should be recreated at Outpost start or not.
        If you have outsourced the port forwarding to an extra system, you can
        set this to false.
        
        This maybe a coroutine.
        
        Example::  
        
            async def restart_tunnels(wrapper, jupyterhub_credential):
                if jupyterhub_credential == "local_jupyterhub":
                    return False
                return True

            c.JupyterHubOutpost.ssh_recreate_at_start = restart_tunnels
            # c.JupyterHubOutpost.ssh_recreate_at_start = False
        """,
    ).tag(config=True)

    @default("log_level")
    def _log_level_default(self):
        return logging.INFO

    def init_logging(self):
        # This prevents double log messages because tornado use a root logger that
        # self.log is a child of. The logging module dipatches log messages to a log
        # and all of its ancenstors until propagate is set to False.
        self.log.propagate = False

        _formatter = self._log_formatter_cls(
            fmt=self.log_format, datefmt=self.log_datefmt
        )
        for handler in self.extra_log_handlers:
            if handler.formatter is None:
                handler.setFormatter(_formatter)
            self.log.addHandler(handler)

        # disable curl debug, which is TOO MUCH
        logging.getLogger("tornado.curl_httpclient").setLevel(
            max(self.log_level, logging.INFO)
        )

        for log in (app_log, access_log, gen_log):
            # ensure all log statements identify the application they come from
            log.name = self.log.name

        # hook up tornado's and oauthlib's loggers to our own
        for name in ("tornado", "oauthlib"):
            logger = logging.getLogger(name)
            logger.propagate = True
            logger.parent = self.log
            logger.setLevel(self.log.level)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spawners = {}
        config_file = os.environ.get("OUTPOST_CONFIG_FILE", "spawner_config.py")
        self.load_config_file(config_file)
        self.init_logging()
        self.log.debug(f"Load config file: {config_file}")

    # class for spawning single-user servers
    spawner_class = EntryPointType(
        default_value=LocalProcessSpawner,
        klass=Spawner,
        entry_point_group="jupyterhub.spawners",
        help="""The class to use for spawning single-user servers.

        Should be a subclass of :class:`jupyterhub.spawner.Spawner`.
        """,
    ).tag(config=True)
