<!--- app-name: JupyterHub Outpost -->

# JupyterHub Outpost

[![Documentation Status](https://readthedocs.org/projects/jupyterhub-outpostspawner/badge/?version=latest)](https://jupyterhub-outpostspawner.readthedocs.io/en/latest/?badge=latest)
[![GitHub JupyterHub Outpost](https://img.shields.io/badge/Source_code-github-blue?logo=github&logoColor=white)](https://github.com/kreuzert/jupyterhub-outpost)

JupyterHub Outpost can be used as an additional, external source to start and manage single-user servers. Like in JupyterHub itself, different Spawners can be configured at the Outpost. It's best used together with the [jupyterhub-outpostspawner](https://pypi.org/project/jupyterhub-outpostspawner/) configured at JupyterHub.

[Overview of JupyterHub OutpostSpawner and JupyterHub Outpost](https://jupyterhub-outpostspawner.readthedocs.io/)

## TL;DR

```console
helm repo add jupyterhub-outpost https://kreuzert.github.io/jupyterhub-outpost/charts/
helm install my-jupyterhub-outpost jupyterhub-outpost/jupyterhub-outpost --version <version>
```

## Introduction

This chart bootstraps a [JupyterHub Outpost](https://github.com/kreuzert/jupyterhub-outpost) deployment on a [Kubernetes](https://kubernetes.io) cluster using the [Helm](https://helm.sh) package manager.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.2.0+
- SSH public keys (private key must be configured in JupyterHub)
- existing kubernetes secret with usernames and passwords (default secret name: `outpost-users`, keys required: `usernames` and `passwords`)
- existing secret to enable encryption in database

## Installing the Chart

To install the chart with the release name `my-jupyterhub-outpost`:

```console
SECRET_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

kubectl create secret generic outpost-users --from-literal=usernames=jupyterhub1 --from-literal=passwords=passwd1
kubectl create secret generic outpost-cryptkey --from-literal=secret_key=${SECRET_KEY}

cat <<EOF >> values.yaml
cryptSecret: outpost-cryptkey
outpostUsers: outpost-users
sshPublicKeys:
  - ssh-ed25519 AAAC3....
EOF

helm repo add jupyterhub-outpost https://kreuzert.github.io/jupyterhub-outpost/charts/
helm install my-jupyterhub-outpost jupyterhub-outpost/jupyterhub-outpost --version <version> -f values.yaml"
```

The command deploys JupyterHub Outpost on the Kubernetes cluster in the default configuration. At least one public key should be configured at `sshPublicKeys`. If multiple JupyterHubs should be supported, you need one ssh public key for each JupyterHub. Additionally, a secret with usernames / passwords for these JupyterHubs is required (see `outpostUsers` parameter). To add a custom configuration (like `jupyterhub_config.py` for JupyterHub) override the `outpostConfig` configuration. It will be stored in a ConfigMap and mounted into the deployment.


## Uninstalling the Chart

To uninstall/delete the `my-jupyterhub-outpost` deployment:

```console
helm delete --purge my-jupyterhub-outpost
```

## Parameters

### Outpost Configuration

| Name                     | Description                                                                                                                                              | Value |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `nameOverride`           | String to partially override common.names.fullname template (will maintain the release name)                                                             | `""`  |
| `fullnameOverride`       | String to fully override common.names.fullname template                                                                                                  | `""`  |
| `cryptSecret`            | Existing secret containing `secret_key`. To create a key run `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` | `""`  |
| `sshPublicKeys`          | Public keys, to enable port-forwarding from JupyterHub to the Outpost. May containt ssh options like `from=...`                                          | `[]`  |
| `outpostUsers`           | Name of existing Secret with `usernames` and `passwords`. Multiple values must be semicolon separated                                                    | `""`  |
| `outpostConfig`          | Configuration of Outpost Application. See documentation for more information.                                                                            | `""`  |
| `extraPythonPackages     | Array containing python packages, that should be installed (normally the Spawner you want to configure)                                                  | `[]`  |

### Extra Envs / Secrets / Containers

| Name                     | Description                                                                                                     | Value |
| ------------------------ | --------------------------------------------------------------------------------------------------------------- | ------|
| `extraEnvVars`           | Array containing extra environment variables                                                                    | `[]`  |
| `extraEnvVarsCMs`        | Extra ConfigMaps with extra environment variables                                                               | `[]`  |
| `extraEnvVarsSecrets`    | Extra Secrets with extra environment variables                                                                  | `[]`  |
| `extraVolumes`           | Extra volumes to add to the deployment                                                                          | `[]`  |
| `extraVolumeMounts`      | Extra volume mounts to add to the container. Normally used with `extraVolumes`                                  | `[]`  |
| `initContainers`         | Extra init containers to add to the deployment                                                                  | `[]`  |
| `sidecars`               | Extra sidecar containers to add to the deployment                                                               | `[]`  |

### Configure Database
To use postgresql as database (or something similar) use extraEnvVarsSecrets.
All variations can be found in the [source code](https://github.com/kreuzert/jupyterhub-outpost/blob/main/project/app/database/__init__.py) itself.

Example:
Create a secret with required values before installing JupyterHub Outpost:
```
kind: Secret
metadata:
  name: my-db-secret
...
stringData:
  SQL_TYPE: "postgresql"
  SQL_USER: "jupyterhuboutpost"
  SQL_PASSWORD: "..."
  SQL_HOST: "postgres.database.svc"
  SQL_PORT: "5432"
  SQL_DATABASE: "jupyterhuboutpost"
```
  
Add it in values.yaml for the JupyterHub Outpost installation:
```
extraEnvVarsSecrets:
  - my-db-secret
```
  

### More

More configurations can be found within the templates. If anything is missing, please create an issue on GitHub and it will be added. If you want to contribute, feel free to also add an issue to contact us.
