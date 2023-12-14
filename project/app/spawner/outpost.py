import asyncio
import copy
import inspect
import json
import logging
import os
import socket
import sys
import time
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import yaml
from async_generator import aclosing
from database import models as service_model
from database.schemas import decrypt
from database.schemas import encrypt
from database.utils import get_service
from jupyterhub.log import CoroutineLogFormatter
from jupyterhub.spawner import LocalProcessSpawner
from jupyterhub.spawner import Spawner
from jupyterhub.traitlets import EntryPointType
from jupyterhub.utils import iterate_until
from jupyterhub.utils import maybe_future
from sqlalchemy import func
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

from . import logging_utils
from .hub import certs_dir
from .hub import OutpostJupyterHub
from .hub import OutpostSpawner
from .hub import OutpostUser

logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
outpost_log = logging.getLogger(logger_name)


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
    logging_config_cache = {}
    logging_config_last_update = 0
    logging_config_file = os.environ.get("LOGGING_CONFIG_PATH")

    def remove_spawner(self, jupyterhub_name, service_name, start_id):
        if f"{jupyterhub_name}-{service_name}-{start_id}" in self.spawners.keys():
            self.log.debug(
                f"Remove spawner in memory {service_name} ({start_id}) for {jupyterhub_name}"
            )
            spawner = self.spawners[f"{jupyterhub_name}-{service_name}-{start_id}"]
            cert_base_path = f"{certs_dir}/{jupyterhub_name}-{service_name}-{start_id}"
            cert_basenames = [
                f"{service_name}.key",
                f"{service_name}.crt",
                "notebooks-ca_trust.crt",
                "hub-ca.crt",
                "proxy-api-ca.crt",
                "proxy-client-ca.crt",
                "notebooks-ca.crt",
                "services-ca.crt",
                f"{spawner.user.name}.key",
                f"{spawner.user.name}.crt",
            ]
            for basename in cert_basenames:
                try:
                    Path(f"{cert_base_path}/{basename}").unlink(missing_ok=True)
                except:
                    self.log.exception(f"Could not delete {basename} cert file.")
            try:
                Path(cert_base_path).rmdir()
            except:
                self.log.exception(
                    f"Could not delete parent cert dir of {jupyterhub_name}-{service_name} ({start_id})."
                )
            del self.spawners[f"{jupyterhub_name}-{service_name}-{start_id}"]

    async def get_spawner(
        self,
        jupyterhub_name,
        service_name,
        start_id,
        orig_body,
        auth_state={},
        certs={},
        internal_trust_bundles={},
        state={},
    ):
        if f"{jupyterhub_name}-{service_name}-{start_id}" not in self.spawners:
            self.log.debug(
                f"Create Spawner object {service_name} ({start_id}) for {jupyterhub_name}"
            )
            spawner = await self._new_spawner(
                jupyterhub_name,
                service_name,
                start_id,
                orig_body,
                auth_state,
                certs,
                internal_trust_bundles,
                state,
            )
            self.spawners[f"{jupyterhub_name}-{service_name}-{start_id}"] = spawner
        return self.spawners[f"{jupyterhub_name}-{service_name}-{start_id}"]

    allow_override = Any(
        default_value=None,
        help="""
        An optional hook function you can implement to decide if
        the Spawner configuration can be overriden.
        
        The parameter for this function will be the credential username
        and the used `misc` (from JupyterHub.OutpostSpawner.custom_misc)
        configuration in this request.
        
        The result of this function has to be a boolean.
        True: if it's ok to override the given values
        False: if it's not ok to override.
        
        This may be a coroutine.

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
        An optional hook function you can implement to modify the
        response of the start process. 
        
        The result of this function will be sent to JupyterHub in the Location
        header.
        
        This may be a coroutine.

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

    flavors_undefined_max = Any(
        default_value=-1,
        config=True,
        help="""
        Configure the amount of JupyterLabs JupyterHubOutpost should offer,
        if flavor is not defined in user_options, or the given flavor is not
        configured in JupyterHubOutpost.flavors .
        Set to -1 to not restrict it.
        Set 0 to not allow undefined flavors (or flavors that are not part of 
        JupyterHubOutpost.flavors ) at all.
        
        default: -1
        
        May be a coroutine.
        
        Example::
        
            async def flavors_undefined_max(jupyterhub_name):
                if jupyterhub_name == "empire":
                    # The empire is not allowed to use our resources,
                    # other than the defined JupyterHubOutpost.flavors
                    return 0
                elif jupyterhub_name == "rebellion":
                    # The rebellion JupyterHub can use all available
                    # resources
                    return -1
                else:
                    # Other JupyterHubs may start up to 10 "undefined" /
                    # not configured notebook servers on this Outpost.
                    return 10
            
            c.JupyterHubOutpost.flavors_undefined_max = flavors_undefined_max
        """,
    )

    async def get_flavors_undefined_max(self, jupyterhub_name):
        if callable(self.flavors_undefined_max):
            flavors_undefined_max = self.flavors_undefined_max(jupyterhub_name)
            if inspect.isawaitable(flavors_undefined_max):
                flavors_undefined_max = await flavors_undefined_max
        else:
            flavors_undefined_max = self.flavors_undefined_max
        return flavors_undefined_max

    flavors = Any(
        default_value={},
        config=True,
        help="""
        Configure the amount of resources JupyterHubOutpost should offer
        in general, or depending on the connected JupyterHub. Can be a dict
        or a function. -1 is interpreted as infinite.
        Set JupyterHubOutpost.flavors_undefined_max to set a maximum value
        for not configured or undefined flavors. 
        
        May be a coroutine.
        
        Example::
            
            async def flavors(jupyterhub_name):
                if jupyterhub_name == "empire":
                    return {
                        "type_a": 2,
                        "type_b": 2
                    }
                elif jupyterhub_name == "rebellion":
                    # allow unlimited type_a 
                    return {
                        "type_a": -1,
                        "type_b": 70
                    }
                else:                
                    return {}
            
            c.JupyterHubOutpost.flavors = flavors
        """,
    )

    async def get_flavors(self, jupyterhub_name):
        if callable(self.flavors):
            flavors = self.flavors(jupyterhub_name)
            if inspect.isawaitable(flavors):
                flavors = await flavors
        else:
            flavors = self.flavors
        return flavors

    flavors_update_token = Any(
        default_value="",
        config=True,
        help="""
        Whenever a notebook server was started / stopped, JupyterHub Outpost
        will use the env variable JUPYTERHUB_FLAVORS_UPDATE_URL (sent in request
        by OutpostSpawner), to send JupyterHub the current usage numbers
        per flavor for this JupyterHub.
        
        To authenticate this update, JupyterHub expects a service token as authentication,
        which can be configured here. 
        
        Can be a string or a callable.
        
        May be a coroutine.
        
        Example::
        
            import os
            async def flavors_update_token(jupyterhub_name):
                if jupyterhub_name == "abc":
                    return os.environ.get("JUPYTERHUB_ABC_UPDATE_FLAVORS_TOKEN", "")
                elif jupyterhub_name == "def":
                    return os.environ.get("JUPYTERHUB_DEF_UPDATE_FLAVORS_TOKEN", "")
                else:
                    # No request send to JupyterHub with updated information
                    return ""
            c.JupyterHubOutpost.flavors_update_token = flavors_update_token
        """,
    )

    async def get_flavors_update_token(self, jupyterhub_name):
        if callable(self.flavors_update_token):
            flavors_update_token = self.flavors_update_token(jupyterhub_name)
            if inspect.isawaitable(flavors_update_token):
                flavors_update_token = await flavors_update_token
        else:
            flavors_update_token = self.flavors_update_token
        return flavors_update_token

    send_events = Any(
        default_value=True,
        config=True,
        help="""
        Whether JupyterHub Outpost should send events to JupyterHub or not.
        This must be boolean or a callable.
        If this setting is true and JUPYTERHUB_EVENTS_URL is given via request
        body, JupyterHub Outpost will send events to JupyterHub.
        
        May be a coroutine.
        
        Example::
        
            async def send_events(jupyterhub_name):
                if jupyterhub_name == "abc":
                    return False
                else:
                    return True
            c.JupyterHubOutpost.send_events = send_events
        """,
    )

    async def get_send_events(self, jupyterhub_name):
        if callable(self.send_events):
            send_events = self.send_events(jupyterhub_name)
            if inspect.isawaitable(send_events):
                send_events = await send_events
        else:
            send_events = self.send_events
        return send_events

    http_client = Any

    @default("http_client")
    def _default_http_client(self):
        return AsyncHTTPClient(force_instance=True, defaults=dict(validate_cert=False))

    async def _outpostspawner_get_flavor_values(self, db, jupyterhub_name):
        configured_flavors = await self.get_flavors(jupyterhub_name)
        flavors = (
            db.query(
                service_model.Service.flavor,
                func.count(service_model.Service.flavor),
            )
            .filter(service_model.Service.jupyterhub_username == jupyterhub_name)
            .group_by(service_model.Service.flavor)
        )
        undefined_max = await self.get_flavors_undefined_max(jupyterhub_name)
        ret = {
            "_undefined": {
                "max": undefined_max,
                "current": 0,
                "display_name": "default flavor",
                "weight": 1,
            }
        }
        # Add flavors that are already running
        for flavor in flavors:
            if flavor[0] in configured_flavors.keys():
                ret[flavor[0]] = configured_flavors[flavor[0]]
                ret[flavor[0]]["current"] = flavor[1]
            else:
                ret["_undefined"]["current"] += flavor[1]
        # Add flavors which are not running yet
        for flavor_name, flavor_description in configured_flavors.items():
            if flavor_name not in ret.keys():
                ret[flavor_name] = flavor_description
                ret[flavor_name]["current"] = 0
        return ret

    async def _outpostspawner_send_flavor_update(
        self, db, service_name, jupyterhub_name, flavor_update_url
    ):
        try:
            token = await self.get_flavors_update_token(jupyterhub_name)
        except:
            token = False
            self.log.exception(
                f"{service_name} - Could not receive auth token for {jupyterhub_name} to send flavor updates."
            )
        if not (token and flavor_update_url):
            self.log.info(
                f"{service_name} - Do not send flavor update to {jupyterhub_name}"
            )
            return
        request_header = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = await self._outpostspawner_get_flavor_values(db, jupyterhub_name)

        req = HTTPRequest(
            url=flavor_update_url,
            method="POST",
            headers=request_header,
            body=json.dumps(body),
            **self.get_request_kwargs(),
        )
        try:
            await self.http_client.fetch(req)
        except:
            self.log.exception(
                f"{service_name} - Could not send flavor update to {flavor_update_url}"
            )

    # Create a DummySpawner object.
    async def _new_spawner(
        wrapper,
        jupyterhub_name,
        service_name,
        start_id,
        orig_body,
        auth_state,
        certs,
        internal_trust_bundles,
        state,
    ):
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
            spawn_future = None
            name = service_name
            log = wrapper.log

            async def _outpostspawner_send_event(self, event):
                request_header = {
                    "Authorization": f"token {self.get_env().get('JUPYTERHUB_API_TOKEN')}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                event_url = self.get_env().get("JUPYTERHUB_EVENTS_URL", "")
                req = HTTPRequest(
                    url=event_url,
                    method="POST",
                    headers=request_header,
                    body=json.dumps(event),
                    **wrapper.get_request_kwargs(),
                )
                try:
                    await wrapper.http_client.fetch(req)
                except:
                    self.log.exception(
                        f"{self._log_name} - Could not send event to {event_url} for {self._log_name}: {event.get('html_message', event.get('message', ''))}"
                    )

            async def _outpostspawner_forward_events(self):
                # retrieve progress events from the Spawner
                self._spawn_pending = True
                async with aclosing(
                    iterate_until(self._spawn_future, self._generate_progress())
                ) as events:
                    try:
                        async for event in events:
                            # don't allow events to sneakily set the 'ready' flag
                            if "ready" in event:
                                event.pop("ready", None)
                            await self._outpostspawner_send_event(event)
                    except asyncio.CancelledError:
                        pass

                await asyncio.wait([self._spawn_future])
                self._spawn_pending = False

            async def _outpostspawner_db_start(self, db):
                wrapper.update_logging()
                self.log.info(f"{self._log_name} - Start service")

                self._spawn_future = asyncio.ensure_future(
                    self._outpostspawner_db_start_call(db)
                )

                forward_future = None
                send_events = await wrapper.get_send_events(self.jupyterhub_name)
                if self.get_env().get("JUPYTERHUB_EVENTS_URL", "") and send_events:
                    forward_future = self._outpostspawner_forward_events()

                await asyncio.wait([self._spawn_future])
                if forward_future:
                    await forward_future
                try:
                    return self._spawn_future.result()
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

                try:
                    ret = await maybe_future(self.start())
                    if inspect.isawaitable(ret):
                        ret = await ret
                    if wrapper.sanitize_start_response:
                        ret = wrapper.sanitize_start_response(self, ret)
                        if inspect.isawaitable(ret):
                            ret = await ret
                    if type(ret) == tuple and len(ret) == 2:
                        ret = f"{ret[0]}:{ret[1]}"
                except:
                    self.log.exception(f"{self._log_name} - Start failed")
                    raise
                service = get_service(jupyterhub_name, self.name, self.start_id, db)
                flavors = await wrapper.get_flavors(jupyterhub_name)
                if service.flavor in flavors.keys():
                    runtime = flavors[service.flavor].get("runtime", False)
                    if runtime:
                        service.end_date = datetime.now() + timedelta(**runtime)
                service.state = encrypt(self.get_state())
                service.state_stored = True
                service.start_response = encrypt({"service": ret})
                db.commit()
                return ret

            async def _outpostspawner_db_poll(self, db):
                # Update from db
                wrapper.update_logging()
                self.log.debug(f"{self._log_name} - Poll service")

                # wait up to 5 seconds until the state is stored
                until = time.time() + 5
                while time.time() < until:
                    service = get_service(jupyterhub_name, self.name, self.start_id, db)
                    if service.state_stored:
                        self.log.debug(
                            f"{self._log_name} - Load state from database: {decrypt(service.state)}"
                        )
                        self.load_state(decrypt(service.state))
                        break
                    else:
                        self.log.debug(
                            f"{self._log_name} - Wait for load until state is stored"
                        )
                        await asyncio.sleep(1)

                ret = self.poll()
                if inspect.isawaitable(ret):
                    ret = await ret
                if service:
                    service.last_update = datetime.now()
                    db.commit()
                return ret

            async def _outpostspawner_db_stop(self, db, now=False):
                wrapper.update_logging()
                self.log.info(f"{self._log_name} - Stop service")
                _outpostspawner_stop_future = asyncio.ensure_future(
                    self._outpostspawner_db_stop_call(db, now)
                )
                await asyncio.wait([_outpostspawner_stop_future])
                return _outpostspawner_stop_future.result()

            async def _outpostspawner_db_stop_call(self, db, now=False):
                # Update from db if possible
                try:
                    service = get_service(jupyterhub_name, self.name, self.start_id, db)
                    self.log.debug(
                        f"{self._log_name} - Load state from database: {decrypt(service.state)}"
                    )
                    self.load_state(decrypt(service.state))
                except:
                    service = None
                    self.log.debug(f"{self._log_name} - Could not load service")
                try:
                    ret = self.stop(now)
                    if inspect.isawaitable(ret):
                        ret = await ret
                except:
                    self.log.exception(f"{self._log_name} - Stop failed")
                try:
                    self.run_post_stop_hook()
                except:
                    self.log.exception(f"{self._log_name} - Run post stop hook failed")
                self.clear_state()
                if service:
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

        # Update config file for each Spawner creation
        config_file = os.environ.get("OUTPOST_CONFIG_FILE", "spawner_config.py")
        wrapper.load_config_file(config_file)
        spawner_class_name = (
            wrapper.config.get("JupyterHubOutpost", {})
            .get("spawner_class", LocalProcessSpawner)
            .__name__
        )
        config = wrapper.config.get(spawner_class_name, {})
        config.update(
            {
                "hub": OutpostJupyterHub(orig_body).hub,
                "user": OutpostUser(orig_body, auth_state),
            }
        )
        for key, value in orig_body.get("misc", {}).items():
            wrapper.log.debug(
                f"{config['user'].name}:{service_name} - Override configuration via misc for {service_name}: {key} - {value}"
            )
            config[key] = value

        wrapper.log.info(
            f"{config['user'].name}:{service_name} - Create Spawner ( {spawner_class_name} ) object for jupyterhub {jupyterhub_name}"
        )
        spawner = DummySpawner(
            jupyterhub_name,
            service_name,
            start_id,
            orig_body,
            certs,
            internal_trust_bundles,
            **config,
        )
        if state:
            wrapper.log.info(
                f"{spawner._log_name} - Load state after creating object: {state}"
            )
            spawner.load_state(state)
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
        default_value=False,
        help="""
        Whether ssh tunnels should be recreated at Outpost start or not.
        If you have outsourced the port forwarding to an extra system, you can
        set this to false.
        
        This may be a coroutine.
        
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

        for log in (app_log, access_log, gen_log, outpost_log):
            # ensure all log statements identify the application they come from
            log.name = self.log.name

        # hook up tornado's and oauthlib's loggers to our own
        for name in ("tornado", "oauthlib", logger_name):
            logger = logging.getLogger(name)
            logger.parent = self.log
            logger.setLevel(self.log.level)
            if name != logger_name:
                logger.propagate = True

    def update_logging(self):
        try:
            last_change = os.path.getmtime(self.logging_config_file)
        except:
            self.log.exception(
                f"Could not load logging config {self.logging_config_file}"
            )
            last_change = 0
        if last_change > self.logging_config_last_update:
            self.log.debug("Update logging config")
            with open(self.logging_config_file, "r") as f:
                ret = yaml.full_load(f)

            self.logging_config_cache = ret

            if self.logging_config_last_update == 0:
                # In trace will be sensitive information like tokens
                logging.addLevelName(5, "TRACE")

                def trace_func(self, message, *args, **kws):
                    if self.isEnabledFor(5):
                        # Yes, logger takes its '*args' as 'args'.
                        self._log(5, message, args, **kws)

                logging.Logger.trace = trace_func

                for _log in [outpost_log, self.log]:
                    # First call
                    # Remove default StreamHandler
                    if len(_log.handlers) > 0:
                        _log.removeHandler(_log.handlers[0])

                    _log.setLevel(5)

            self.logging_config_last_update = last_change

            for _log in [outpost_log, self.log]:
                logger_handlers = _log.handlers
                handler_names = [x.name for x in logger_handlers]

                for handler_name, handler_config in self.logging_config_cache.items():
                    if (
                        not handler_config.get("enabled", False)
                    ) and handler_name in handler_names:
                        # Handler was disabled, remove it
                        _log.debug(f"Logging handler remove ({handler_name}) ... ")
                        _log.handlers = [
                            x for x in logger_handlers if x.name != handler_name
                        ]
                        _log.debug(f"Logging handler remove ({handler_name}) ... done")
                    elif handler_config.get("enabled", False):
                        # Recreate handlers which has changed their config
                        configuration = copy.deepcopy(handler_config)

                        # map some special values
                        if handler_name == "stream":
                            if configuration["stream"] == "ext://sys.stdout":
                                configuration["stream"] = sys.stdout
                            elif configuration["stream"] == "ext://sys.stderr":
                                configuration["stream"] = sys.stderr
                        elif handler_name == "syslog":
                            if configuration["socktype"] == "ext://socket.SOCK_STREAM":
                                configuration["socktype"] = socket.SOCK_STREAM
                            elif configuration["socktype"] == "ext://socket.SOCK_DGRAM":
                                configuration["socktype"] = socket.SOCK_DGRAM

                        _ = configuration.pop("enabled")
                        formatter_name = configuration.pop("formatter")
                        level = logging_utils.get_level(configuration.pop("level"))
                        none_keys = []
                        for key, value in configuration.items():
                            if value is None:
                                none_keys.append(key)
                        for x in none_keys:
                            _ = configuration.pop(x)

                        # Create handler, formatter, and add it
                        handler = logging_utils.supported_handler_classes[handler_name](
                            **configuration
                        )
                        formatter = logging_utils.supported_formatter_classes[
                            formatter_name
                        ](**logging_utils.supported_formatter_kwargs[formatter_name])
                        handler.name = handler_name
                        handler.setLevel(level)
                        handler.setFormatter(formatter)
                        if handler_name in handler_names:
                            # Remove previously added handler
                            _log.handlers = [
                                x for x in logger_handlers if x.name != handler_name
                            ]
                        _log.addHandler(handler)

                        if "filename" in configuration:
                            # filename is already used in log.x(extra)
                            configuration["file_name"] = configuration["filename"]
                            del configuration["filename"]
                        _log.debug(
                            f"Logging handler added ({handler_name})",
                            extra=configuration,
                        )

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
