import asyncio
import copy
import fnmatch
import inspect
import json
import logging
import os
import re
import socket
import sys
from datetime import datetime
from datetime import timedelta
from datetime import timezone
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
from traitlets import Integer
from traitlets import List
from traitlets import Union
from traitlets.config import Application

from . import logging_utils
from .hub import certs_dir
from .hub import OutpostJupyterHub
from .hub import OutpostSpawner
from .hub import OutpostUser
from .utils import get_flavors_from_disk


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
    logging_config_file = os.environ.get(
        "LOGGING_CONFIG_PATH", "/mnt/outpost_config/logging_config.yaml"
    )

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
                if Path(cert_base_path).exists():
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
        user_flavor={},
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
                user_flavor,
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

    global_max_per_user = Integer(
        default_value=-1,
        config=True,
        help="""
        Set a global limit of services for each user per hub.
        Independent  of the specific flavor limits.
        """,
    )

    async def get_flavors(self, jupyterhub_name):
        flavor_config = get_flavors_from_disk()

        if not flavor_config:
            return {}

        # If no hub is defined, return all available flavors
        if not jupyterhub_name:
            return flavor_config.get("flavors", {})

        jupyterhub_sets = []
        # check if the given jupyterhub_name is part of any jhub set

        self.log.trace(f"Check for hub specific flavors (hub={jupyterhub_name})...")
        for key, value in flavor_config.get("hubs", {}).items():
            config_jupyterhub_name = value.get("jupyterhub_name", [])
            self.log.trace(f"Check {key} hub configuration")
            if type(config_jupyterhub_name) == list:
                self.log.trace(
                    f"Test if {jupyterhub_name} is in hubs.{key}.jupyterhub_name"
                )
                if jupyterhub_name in config_jupyterhub_name:
                    self.log.trace(
                        f"{jupyterhub_name} in {config_jupyterhub_name} - Add {key} to possible hub sets"
                    )
                    jupyterhub_sets.append((key, value.get("weight", 0)))
                    break
            elif type(config_jupyterhub_name) == str:
                self.log.trace(
                    f"Test if hub value ({jupyterhub_name}) matches the regex pattern {config_jupyterhub_name}"
                )
                try:
                    if re.fullmatch(config_jupyterhub_name, jupyterhub_name):
                        self.log.trace(
                            f"{jupyterhub_name} matches {config_jupyterhub_name} - Add {key} to possible hub sets"
                        )
                        jupyterhub_sets.append((key, value.get("weight", 0)))
                        break
                except re.error:
                    try:
                        if re.fullmatch(
                            fnmatch.translate(config_jupyterhub_name), jupyterhub_name
                        ):
                            self.log.trace(
                                f"{jupyterhub_name} matches {config_jupyterhub_name} - Add {key} to possible hub sets"
                            )
                            jupyterhub_sets.append((key, value.get("weight", 0)))
                            break
                    except:
                        self.log.trace(
                            f"{config_jupyterhub_name} is not a valid regex. Check if strings are equal"
                        )
                        if jupyterhub_name == config_jupyterhub_name:
                            self.log.trace(
                                f"{jupyterhub_name} == {config_jupyterhub_name} - Add {key} to possible hub sets"
                            )
                            jupyterhub_sets.append((key, value.get("weight", 0)))
                            break
            else:
                self.log.warning(
                    f"Flavor hubs.{key}.jupyterhub_name is type {type(config_jupyterhub_name)}. Only list and str (regex or plain comparison) are supported."
                )

        # jupyterhub_name is not allowed to use any flavors
        if len(jupyterhub_sets) == 0:
            self.log.trace(f"No sets for {jupyterhub_name} found. Return all flavors")
            return flavor_config.get("flavors", {})

        jupyterhub_sets = sorted(jupyterhub_sets, key=lambda x: x[1])
        # sorted sorts ascending, we're using weight, so we use the last element
        # with the biggest weight
        jupyterhub_set = jupyterhub_sets[-1][0]
        self.log.debug(f"Sorted matched hub sets. Use hub set {jupyterhub_set}")

        hub_specific_flavors = {}
        hub_specific_flavors_keys = (
            flavor_config.get("hubs", {}).get(jupyterhub_set, {}).get("flavors", [])
        )
        hub_specific_flavors_key_exists = "flavors" in flavor_config.get(
            "hubs", {}
        ).get(jupyterhub_set, {})

        for flavorName, flavorValue in flavor_config.get("flavors", {}).items():
            if (
                not hub_specific_flavors_key_exists
            ) or flavorName in hub_specific_flavors_keys:
                hub_specific_flavors[flavorName] = flavorValue

        self.log.trace(
            f"Check hubs.{jupyterhub_set}.flavorsOverride - This allows you to override any config configured globally in flavors._flavor_"
        )
        for flavorName, overrideDict in (
            flavor_config.get("hubs", {})
            .get(jupyterhub_set, {})
            .get("flavorsOverride", {})
            .items()
        ):
            if flavorName not in hub_specific_flavors.keys():
                self.log.warning(
                    f"Do not override {flavorName} for user set {jupyterhub_set}. Flavor not part of flavors list."
                )
                continue
            for overrideKey, overrideValue in overrideDict.items():
                self.log.trace(
                    f"Override {flavorName}.{overrideKey} to user specific values"
                )
                hub_specific_flavors[flavorName][overrideKey] = overrideValue

        self.log.trace(
            "Hub flavors function ended. Return the following hub specific flavors"
        )
        self.log.trace(hub_specific_flavors)
        return hub_specific_flavors

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

    def matches_pattern(self, pattern, key, value):
        try:
            if re.fullmatch(pattern, value):
                self.log.trace(
                    f"{value} matches regex {pattern} - Add {key} to possible user sets"
                )
                return True
        except re.error:
            pass

        try:
            glob_pattern = fnmatch.translate(pattern)
            if re.fullmatch(glob_pattern, value):
                self.log.trace(
                    f"{value} matches glob {pattern} - Add {key} to possible user sets"
                )
                return True
        except re.error:
            pass

        if value == pattern:
            self.log.trace(f"{value} == {pattern} - Add {key} to possible user sets")
            return True

        return False

    update_user_authentication = Any(
        default_value=None,
        allow_none=True,
        config=True,
        help="""
        Hook to add a function to manipulate user authentication info before 
        matching it against the configured flavors.users information.
        Must return a dict
        
        May be a coroutine.
        
        Example::
        
            async def lowercase_name(authentication):
                if "name" in authentication.keys():
                    authentication["name"] = authentication["name"].lower()
                return authentication
            
            c.JupyterHubOutpost.update_user_authentication = lowercase_name
        """,
    )

    async def run_update_user_authentication(self, authentication):
        if self.update_user_authentication:
            authentication_new = self.update_user_authentication(
                copy.deepcopy(authentication)
            )
            if inspect.isawaitable(authentication_new):
                authentication_new = await authentication_new
            return authentication_new
        else:
            return authentication

    async def flavors_per_user(self, jupyterhub_name, authentication):
        hub_flavors = await self.get_flavors(jupyterhub_name)
        if not authentication:
            return hub_flavors

        flavor_config = get_flavors_from_disk()

        if not flavor_config.get("users", {}):
            self.log.info(
                f"User specific config not set. Use hub ({jupyterhub_name}) specific flavors"
            )
            return hub_flavors

        user_sets = []
        # check if the given user is part of any user set
        self.log.trace("Check for user specific flavors ...")
        self.log.trace(authentication)
        for key, value in flavor_config.get("users", {}).items():
            self.log.trace(f"Check {key} user configuration")
            if "hubs" in value.keys() and jupyterhub_name not in value.get("hubs", []):
                self.log.trace(f"{jupyterhub_name} not in users.{key}.hubs . Skip")
            else:
                negate_authentication = value.get("negate_authentication", False)
                matched = False
                if negate_authentication:
                    self.log.info(
                        f"Negate logic for matching user to users.{key}.authentication. So users who don't match the authentication will use this user set"
                    )
                for config_auth_key, config_auth_value in value.get(
                    "authentication", {}
                ).items():
                    self.log.trace(
                        f"Test if users.{key}.authentication.{config_auth_key} matches with user authentication ..."
                    )
                    for user_auth_key, user_auth_values in authentication.items():
                        if config_auth_key == user_auth_key:
                            if type(user_auth_values) != list:
                                user_auth_values = [user_auth_values]
                            if type(config_auth_value) == str:
                                self.log.trace(
                                    f"Test if any user value in {user_auth_key} ({user_auth_values}) matches the regex pattern {config_auth_value}"
                                )
                                for user_auth_value in user_auth_values:
                                    if self.matches_pattern(
                                        config_auth_value, key, user_auth_value
                                    ):
                                        matched = True
                            elif type(config_auth_value) == list:
                                self.log.trace(
                                    f"Test if any user value in {user_auth_key} ({user_auth_values}) is in list {config_auth_value}"
                                )
                                for user_auth_value in user_auth_values:
                                    if user_auth_value in config_auth_value:
                                        self.log.trace(
                                            f"{user_auth_value} in {config_auth_value} - Add {key} to possible user sets"
                                        )
                                        matched = True
                            else:
                                self.log.warning(
                                    f"Flavor users.{key}.authentication.{config_auth_key} is type {type(config_auth_value)}. Only list and str (regex or plain comparison) are supported."
                                )
                    self.log.trace(
                        f"Test if users.{key}.authentication.{config_auth_key} matches with user authentication ...: {matched}"
                    )
                if (not negate_authentication) and matched:
                    user_sets.append([key, value.get("weight", 0)])
                elif negate_authentication and (not matched):
                    self.log.trace(
                        f"User does not match users.{key}.authentication , but since users.{key}.negatve_authentication is true, the user will be added to the user subset"
                    )
                    user_sets.append([key, value.get("weight", 0)])
        self.log.trace("Check for user specific flavors ... done")
        if len(user_sets) == 0:
            self.log.debug(
                f"No user specific flavor found. Return hub ({jupyterhub_name}) specific flavors."
            )
            return hub_flavors

        user_sets = sorted(user_sets, key=lambda x: x[1])
        # sorted sorts ascending, we're using weight, so we use the last element
        # with the biggest weight
        user_set = user_sets[-1][0]
        self.log.debug(f"Sorted matched user sets. Use user set {user_set}")

        # When "forbidden" is true, we return an empty dict for this uset_set
        if flavor_config.get("users", {}).get(user_set, {}).get("forbidden", False):
            self.log.info(
                f"users.{user_set}.forbidden is True. User's not allowed to use any flavor"
            )
            return {}

        # Copy default flavors for this hub
        all_flavors = await self.get_flavors(None)
        user_flavors = {}
        user_flavor_keys_exists = (
            "flavors" in flavor_config.get("users", {}).get(user_set, {}).keys()
        )
        user_flavor_keys = (
            flavor_config.get("users", {}).get(user_set, {}).get("flavors", [])
        )
        self.log.trace(
            f"users.{user_set}.forbidden is False. Use users.{user_set}.flavors ({user_flavor_keys}) for this user"
        )

        for flavorName, flavorValue in all_flavors.items():
            if (not user_flavor_keys_exists) or flavorName in user_flavor_keys:
                user_flavors[flavorName] = flavorValue

        self.log.trace(
            f"Check users.{user_set}.flavorsOverride - This allows you to override any config configured globally in flavors._flavor_"
        )
        for flavorName, overrideDict in (
            flavor_config.get("users", {})
            .get(user_set, {})
            .get("flavorsOverride", {})
            .items()
        ):
            if flavorName not in user_flavors.keys():
                self.log.warning(
                    f"Do not override {flavorName} for user set {user_set}. Flavor not part of flavors list."
                )
                continue
            for overrideKey, overrideValue in overrideDict.items():
                self.log.trace(
                    f"Override {flavorName}.{overrideKey} to user specific values"
                )
                user_flavors[flavorName][overrideKey] = overrideValue

        self.log.trace(
            "User flavors function ended. Return the following user specific flavors"
        )
        self.log.trace(user_flavors)
        return user_flavors

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

    http_client = Any()

    @default("http_client")
    def _default_http_client(self):
        return AsyncHTTPClient(force_instance=True, defaults=dict(validate_cert=False))

    async def _outpostspawner_flavor_max_user_flavor_validation(
        self, db, jupyterhub_name, flavor, user_id
    ):
        flavor_count = (
            db.query(
                service_model.Service,
            )
            .filter(service_model.Service.jupyterhub_username == jupyterhub_name)
            .filter(service_model.Service.flavor == flavor)
            .filter(service_model.Service.jupyterhub_user_id == user_id)
            .filter(service_model.Service.stop_pending == False)
            .count()
        )
        return flavor_count

    async def _outpostspawner_flavor_max_user_validation(
        self, db, jupyterhub_name, user_id
    ):
        user_total_count = (
            db.query(
                service_model.Service,
            )
            .filter(service_model.Service.jupyterhub_username == jupyterhub_name)
            .filter(service_model.Service.jupyterhub_user_id == user_id)
            .filter(service_model.Service.stop_pending == False)
            .count()
        )
        return user_total_count

    async def _outpostspawner_get_flavor_values(
        self,
        db,
        jupyterhub_name,
        user_authentication={},
        add_one_flavor_count=None,
        reduce_one_flavor_count=None,
    ):
        user_authentication_used = await self.run_update_user_authentication(
            user_authentication
        )
        default_flavors = await self.flavors_per_user(
            jupyterhub_name, user_authentication_used
        )
        configured_flavors = copy.deepcopy(default_flavors)

        flavors = (
            db.query(
                service_model.Service.flavor,
                func.count(service_model.Service.flavor),
            )
            .filter(service_model.Service.jupyterhub_username == jupyterhub_name)
            .filter(service_model.Service.stop_pending == False)
            .group_by(service_model.Service.flavor)
        )
        self.log.debug(
            f"flavors for {jupyterhub_name} - Currently all flavors in database (stopping services not included): {flavors}"
        )
        ret = {}
        # Add flavors that are already running
        for flavor in flavors:
            if flavor[0] in configured_flavors.keys():
                ret[flavor[0]] = configured_flavors[flavor[0]]
                ret[flavor[0]]["current"] = flavor[1]
        # Add flavors which are not running yet
        for flavor_name, flavor_description in configured_flavors.items():
            if flavor_name not in ret.keys():
                ret[flavor_name] = flavor_description
                ret[flavor_name]["current"] = 0
        if add_one_flavor_count and add_one_flavor_count in ret.keys():
            # We may want to send an update to JHub before we've started the service
            # Add this value to the count, if it does not exceed its limit
            self.log.debug(
                f"flavors for {jupyterhub_name} - Add count by one for {add_one_flavor_count}"
            )
            if ret[add_one_flavor_count]["current"] < ret[add_one_flavor_count]["max"]:
                ret[add_one_flavor_count]["current"] += 1
        if reduce_one_flavor_count and reduce_one_flavor_count in ret.keys():
            self.log.debug(
                f"flavors for {jupyterhub_name} - Remove count by one for {add_one_flavor_count}"
            )
            # We may want to send an update to JHub before we've stopped the service
            # Reduce this value from the count, if it does not exceed its limit
            if ret[reduce_one_flavor_count]["current"] > 0:
                ret[reduce_one_flavor_count]["current"] -= 1
        self.log.debug(
            f"flavors for {jupyterhub_name} - Return following flavors: {ret}"
        )
        return ret

    async def _outpostspawner_send_flavor_update(
        self,
        db,
        service_name,
        jupyterhub_name,
        flavor_update_url,
        token,
        add_one_flavor_count=None,
        reduce_one_flavor_count=None,
    ):
        try:
            if not token:
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
        body = await self._outpostspawner_get_flavor_values(
            db,
            jupyterhub_name,
            add_one_flavor_count=add_one_flavor_count,
            reduce_one_flavor_count=reduce_one_flavor_count,
        )

        req = HTTPRequest(
            url=flavor_update_url,
            method="POST",
            headers=request_header,
            body=json.dumps(body),
            **self.get_request_kwargs(),
        )
        self.log.debug(
            f"{service_name} - Send flavor update to {flavor_update_url} - {body}"
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
        user_flavor,
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

                self._spawn_pending = False

            async def _outpostspawner_db_start(self, db):
                wrapper.update_logging()
                self.log.info(f"{self._log_name} - Start service")

                forward_future = None
                send_events = await wrapper.get_send_events(self.jupyterhub_name)
                if self.get_env().get("JUPYTERHUB_EVENTS_URL", "") and send_events:
                    forward_future = asyncio.create_task(
                        self._outpostspawner_forward_events()
                    )

                self._spawn_future = asyncio.create_task(
                    self._outpostspawner_db_start_call(db)
                )

                await self._spawn_future
                if forward_future:
                    await forward_future
                try:
                    return self._spawn_future.result()
                except asyncio.CancelledError:
                    raise Exception(f"Start of {self._log_name} was cancelled.")

            async def _outpostspawner_db_start_call(self, db):
                self.clear_state()
                await maybe_future(self.run_pre_spawn_hook())
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

                runtime = False
                try:
                    runtime = self.flavor.get("runtime", False)
                except:
                    pass
                if runtime:
                    service.end_date = datetime.now(timezone.utc) + timedelta(**runtime)
                    self.log.info(
                        f"{self._log_name} - Set end_date: {service.end_date}"
                    )
                service.state = encrypt(self.get_state())
                service.state_stored = True
                service.start_response = encrypt({"service": ret})
                db.add(service)
                db.commit()
                return ret

            async def _outpostspawner_db_poll(self, db):
                # Update from db
                wrapper.update_logging()
                self.log.debug(f"{self._log_name} - Poll service")

                service = get_service(jupyterhub_name, self.name, self.start_id, db)
                if not service.state_stored:
                    self.log.debug(
                        f"{self._log_name} - Start function not finished yet. Return None"
                    )
                    return None

                try:
                    self.load_state(decrypt(service.state))
                except:
                    self.log.exception(
                        f"{self._log_name} - Could not load state. Return None"
                    )
                    return None

                ret = self.poll()
                if inspect.isawaitable(ret):
                    ret = await ret
                if service:
                    service.last_update = datetime.now(timezone.utc)
                    db.add(service)
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
            user_flavor,
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

    ssh_recreate_at_start_global = Union(
        [Callable(), Bool()],
        default_value=False,
        help="""
        Whether ssh tunnels should be recreated at Outpost start or not.
        If you have outsourced the port forwarding to an extra system, you can
        set this to false.
        If this global function returns a "true-ish" return statement,
        .ssh_recreate_at_start will not be called.
        
        This may be a coroutine.
        
        Example::  


            async def restart_tunnels_global(wrapper, jupyterhub_names):
                import os
                import requests
                ret = False

                for jupyterhub_name in jupyterhub_names:
                    env_prefix = f"RESTART_{jupyterhub_name.upper()}"
                    url = os.environ.get(f"{env_prefix}_URL")
                    token = os.environ.get(f"{env_prefix}_TOKEN")

                    if not url or not token:
                        wrapper.log.warning(f"Missing restart URL or token for {jupyterhub_name}")
                        continue

                    try:
                        wrapper.log.info(f"Restarting tunnels for {jupyterhub_name} via {url}")
                        response = requests.get(
                            url,
                            headers={"Authorization": f"token {token}"},
                            timeout=10,
                        )
                        response.raise_for_status()
                        ret = True
                    except requests.exceptions.RequestException as e:
                        wrapper.log.error(f"Failed to restart tunnels for {jupyterhub_name}: {e}")

                return ret

            c.JupyterHubOutpost.ssh_recreate_at_start_global = restart_tunnels_global
            # c.JupyterHubOutpost.ssh_recreate_at_start_global = False # default
        """,
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

        # In trace will be sensitive information like tokens
        logging.addLevelName(5, "TRACE")

        def trace_func(self, message, *args, **kws):
            if self.isEnabledFor(5):
                # Yes, logger takes its '*args' as 'args'.
                self._log(5, message, args, **kws)

        logging.Logger.trace = trace_func

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

        for _log in [outpost_log, self.log]:
            # First call
            # Remove default StreamHandler
            if len(_log.handlers) > 0:
                _log.removeHandler(_log.handlers[0])

            _log.setLevel(5)

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
        self.log.info("Start JupyterHub Outpost Version <VERSION>")

    # class for spawning single-user servers
    spawner_class = EntryPointType(
        default_value=LocalProcessSpawner,
        klass=Spawner,
        entry_point_group="jupyterhub.spawners",
        help="""The class to use for spawning single-user servers.

        Should be a subclass of :class:`jupyterhub.spawner.Spawner`.
        """,
    ).tag(config=True)
