import asyncio
import datetime
import logging
import os
import traceback

from database.schemas import decrypt
from database.utils import get_service
from kubernetes_asyncio import client
from kubernetes_asyncio import config
from spawner import get_spawner
from spawner import get_wrapper
from spawner import remove_spawner

logger_name = os.environ.get("LOGGER_NAME", "JupyterHubOutpost")
log = logging.getLogger(logger_name)


def is_ingress_activated():
    wrapper = get_wrapper()
    try:
        if wrapper.config.get("JupyterHubOutpost", {}).get(
            "spawner_class"
        ).__name__ == "KubeSpawner" and wrapper.config.get("ingress_enabled", False):
            return True
    except:
        log.exception("Could not check if ingress is enabled")
    return False


async def create_ingress(service, jupyterhub_name, spawner):
    if not is_ingress_activated():
        return
    log.info(f"{service.name} - Create ingress resource for server")

    wrapper = get_wrapper()
    ingress_class = wrapper.config.get("ingress_class", None)
    ingress_name = f"{jupyterhub_name}-{service.name}-{spawner.user.id}"

    await config.load_kube_config()
    api_instance = client.NetworkingV1Api()

    annotations = {}
    tls_secret = False
    if spawner.internal_ssl:
        # When JupyterHub brings it's own certificate to the server, let's use it
        annotations["nginx.ingress.kubernetes.io/ssl-passthrough"] = "true"
        annotations["nginx.ingress.kubernetes.io/backend-protocol"] = "HTTPS"
    else:
        tls_secret = wrapper.config.get("ingress_tls_secretname", False)

    if ingress_class:
        annotations["kubernetes.io/ingress.class"] = ingress_class

    dns_name = wrapper.config.get("ingress_host", "host.com")

    ingress_metadata = client.V1ObjectMeta(
        name=ingress_name, namespace=spawner.namespace, annotations=annotations
    )
    base_url = spawner.get_env().get("JUPYTERHUB_BASE_URL", "/")
    path = f"{base_url}{spawner.user.name}"
    ingress_spec = client.V1IngressSpec(
        rules=[
            client.V1IngressRule(
                host=dns_name,
                http=client.V1HTTPIngressRuleValue(
                    paths=[
                        client.V1HTTPIngressPath(
                            path="/",
                            path_type="Prefix",
                            backend=client.V1IngressBackend(
                                service=client.V1IngressServiceBackend(
                                    name=spawner.dns_name.split(".")[0],
                                    port=client.V1ServiceBackendPort(
                                        number=spawner.port
                                    ),
                                )
                            ),
                        )
                    ]
                ),
            )
        ]
    )

    # If SSL passthrough is disabled, add TLS termination
    if tls_secret:
        ingress_spec.tls = [
            client.V1IngressTLS(hosts=[dns_name], secret_name=tls_secret)
        ]

    ingress_body = client.V1Ingress(
        api_version="networking.k8s.io/v1",
        kind="Ingress",
        metadata=ingress_metadata,
        spec=ingress_spec,
    )

    try:
        await api_instance.create_namespaced_ingress(
            namespace=spawner.namespace, body=ingress_body
        )
        log.info(f"Ingress '{ingress_name}' created successfully.")
    except client.ApiException as e:
        log.exception(f"Error creating ingress: {e}")
    finally:
        await api_instance.api_client.close()  # Ensure the connection is closed


async def async_start(
    service,
    jupyterhub_name,
    request,
    db,
    spawner,
    flavor_update_url,
    flavor_update_token,
    sync=True,
):
    # remove spawner from wrapper to ensure it's using the current config
    wrapper = get_wrapper()
    try:
        await create_ingress(service, jupyterhub_name, spawner)
        ret = await spawner._outpostspawner_db_start(db)
    except Exception as e:
        log.exception(f"{jupyterhub_name} - {service.name} - Could not start")
        if not sync:
            # Send cancel event to JupyterHub, otherwise JHub will never see
            # an error, because this function is running async and the response
            # was already sent to JHub
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            details = traceback.format_exc().replace("\n", "<br>")
            event = {
                "failed": True,
                "progress": 100,
                "html_message": f"<details><summary>{now}: JupyterHub Outpost could not start service: {str(e)}</summary>{details}</details>",
            }
            await spawner._outpostspawner_send_event(event)
        try:
            await full_stop_and_remove(
                jupyterhub_name,
                service.name,
                service.start_id,
                db,
                request,
            )
        except:
            log.exception(
                f"{jupyterhub_name}-{service.name} - Could not stop and remove"
            )
        try:
            # Send flavor update also for failed start attempts. Otherwise hubs
            # will never retrieve the correct flavors, if their init_configuration
            # is not set correctly
            await wrapper._outpostspawner_send_flavor_update(
                db,
                service.name,
                jupyterhub_name,
                flavor_update_url,
                flavor_update_token,
            )
        except:
            pass
        raise e
    else:
        service_ = get_service(jupyterhub_name, service.name, service.start_id, db)
        service_.start_pending = False
        db.add(service_)
        db.commit()
        await wrapper._outpostspawner_send_flavor_update(
            db, service.name, jupyterhub_name, flavor_update_url, flavor_update_token
        )
        return ret


# Flavor Validation must check a few things
# 1. Is flavor set? With JupyterHub Outpost 2.0 a flavor is mandatory
# 2. Flavors may have a limit per user
# 3. Flavors may have a global limit
# 4. Outpost may have an overall limit for a user
async def validate_flavor(service, jupyterhub_name, request, db):
    request_json = await request.json()
    user_authentication = request_json.get("authentication", {})
    wrapper = get_wrapper()

    # 1. Is flavor set?
    if not service.flavor:
        raise Exception(
            f"{service.name} - Start without flavor not allowed. Define user_options.flavor"
        )

    # Get the current flavor usage and global flavor limit
    current_flavor_values = await wrapper._outpostspawner_get_flavor_values(
        db, jupyterhub_name, user_authentication
    )

    dec_body = decrypt(service.body)
    user_id = int(dec_body.get("env", {}).get("JUPYTERHUB_USER_ID", "0"))

    if service.flavor in current_flavor_values.keys():
        current_flavor_value = current_flavor_values.get(service.flavor, {}).get(
            "current", 0
        )
        user_servers_flavor = (
            await wrapper._outpostspawner_flavor_max_user_flavor_validation(
                db, jupyterhub_name, service.flavor, user_id
            )
        )
        flavor_max_per_user = current_flavor_values.get(service.flavor, {}).get(
            "maxPerUser", None
        )
        # 2. User has reached maximum of services per-user limit
        if flavor_max_per_user and user_servers_flavor >= flavor_max_per_user:
            raise Exception(
                f"{service.name} - Start with flavor {service.flavor} not allowed. Each user may only start {flavor_max_per_user} of {service.flavor}"
            )
    else:
        raise Exception(
            f"{service.name} - Start with flavor {service.flavor} not allowed. Allowed values for user: {list(current_flavor_values.keys())}"
        )

    max_flavor_value = current_flavor_values.get(service.flavor, {}).get("max", -1)
    if current_flavor_value >= max_flavor_value and max_flavor_value != -1:
        # 3. All users + hubs together have reached the maximum per-flavor limit
        raise Exception(
            f"{service.name} - Start with {service.flavor} for {jupyterhub_name} not allowed. Maximum ({max_flavor_value}) already reached."
        )

    # Unrelated to the flavor, each user should have a maximum list of servers
    user_global_count = await wrapper._outpostspawner_flavor_max_user_validation(
        db, jupyterhub_name, user_id
    )
    if (
        wrapper.global_max_per_user != -1
        and user_global_count >= wrapper.global_max_per_user
    ):
        raise Exception(
            f"{service.name} - User with user id {user_id} of {jupyterhub_name} has reached the maximum limit of services ({wrapper.global_max_per_user})"
        )

    return current_flavor_values[service.flavor]


async def full_stop_and_remove(
    jupyterhub_name,
    service_name,
    start_id,
    db,
    request=None,
    body={},
    state={},
    run_async=False,
):
    if not run_async:
        try:
            service = get_service(jupyterhub_name, service_name, start_id, db)
            if service.stop_pending:
                log.info(
                    f"{jupyterhub_name} - {service_name} is already stopping. No need to stop it twice"
                )
                db.delete(service)
                db.commit()
                return
        except:
            log.warning(
                f"{jupyterhub_name} - {service_name} Does not exist. No need to stop it again"
            )
            return
        service.stop_pending = True
        db.add(service)
        db.commit()
        body = decrypt(service.body)
    wrapper = get_wrapper()
    if request:
        auth_state = get_auth_state(request.headers)
    else:
        auth_state = {}

    spawner = await get_spawner(
        jupyterhub_name,
        service_name,
        start_id,
        body,
        auth_state,
        state,
    )
    flavor_update_url = spawner.get_env().get("JUPYTERHUB_FLAVORS_UPDATE_URL", "")
    flavor_update_token = spawner.get_env().get("JUPYTERHUB_FLAVORS_UPDATE_TOKEN", "")
    spawner.log.info(f"{spawner._log_name} - Stop service and remove it from database.")
    try:
        await spawner._outpostspawner_db_stop(db)
    except:
        spawner.log.exception(f"{spawner._log_name} - Stop failed.")
    finally:
        remove_spawner(jupyterhub_name, service_name, start_id)
    try:
        service = get_service(jupyterhub_name, service_name, start_id, db)
        db.delete(service)
        db.commit()
    except Exception as e:
        log.debug(
            f"{jupyterhub_name}-{service_name} - Could not delete service from database"
        )

    # Send update after service was deleted from db
    try:
        await wrapper._outpostspawner_send_flavor_update(
            db, service_name, jupyterhub_name, flavor_update_url, flavor_update_token
        )
    except:
        spawner.log.exception(
            f"{spawner._log_name} - Could not send flavor update to {jupyterhub_name}."
        )


def get_auth_state(headers):
    ret = {}
    for key, value in headers.items():
        if key.startswith("auth-state-"):
            ret[key[len("auth-state-") :]] = value
    return ret
