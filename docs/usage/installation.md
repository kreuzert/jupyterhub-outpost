# Installation 

This section covers example configurations and instructions, to install the [JupyterHub Outpost service](https://artifacthub.io/packages/helm/jupyterhub-outpost/jupyterhub-outpost). 

## Local installation

This chapter shows a simple installation of the JupyterHub Outpost service on the same Kubernetes cluster as the JupyterHub is running. If you don't want to connect external JupyterHubs to your JupyterHub Outpost, you won't need ssh port-forwarding between JupyterHub and the Outpost service. 

### Pre-Requirements

One Kubernetes cluster up and running.

### Requirements

To authenticate the JupyterHub instance, we have to create username+password. 

```
OUTPOST_PASSWORD=$(uuidgen)

kubectl -n outpost create secret generic --from-literal=usernames=jupyterhub --from-literal=passwords=${OUTPOST_PASSWORD} outpost-users
```

```{admonition} Note 
If you want to connect multiple JupyterHubs to one JupyterHub Outpost, you have to create a secret with semicolon-separated usernames and passwords.  
`kubectl create secret generics --from-literal=usernames=one,two,three --from-literal=passwords=pw1;pw2;pw3 outpost-users`
```

An encryption key is required, so data in the database can be encrypted.

```
SECRET_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

kubectl -n outpost create secret generic outpost-cryptkey --from-literal=secret_key=${SECRET_KEY}
```

### Configuration

```
cat <<EOF >> outpost_values.yaml
cryptSecret: outpost-cryptkey
outpostUsers: outpost-users
EOF
```

### Installation

```
helm repo add jupyterhub-outpost https://kreuzert.github.io/jupyterhub-outpost/charts/
helm repo update
helm upgrade --install --create-namespace --version <version> --namespace outpost -f outpost_values.yaml outpost jupyterhub-outpost/jupyterhub-outpost
```

Afterwards, you have to update the JupyterHub OutpostSpawner configuration with the correct IP address + credentials for this JupyterHub Outpost service.

## Remote installation

This chapter shows a simple installation of the JupyterHub Outpost service on a different Kubernetes cluster as the JupyterHub is running.  

### Pre-Requirements

One Kubernetes cluster up and running.

### Requirements

To authenticate the JupyterHub instance, we have to create username+password. 

```
OUTPOST_PASSWORD=$(uuidgen)

kubectl -n outpost create secret generic --from-literal=usernames=jupyterhub --from-literal=passwords=${OUTPOST_PASSWORD} outpost-users
```

```{admonition} Note 
If you want to connect multiple JupyterHubs to one JupyterHub Outpost, you have to create a secret with semicolon-separated usernames and passwords.  
`kubectl create secret generics --from-literal=usernames=one,two,three --from-literal=passwords=pw1;pw2;pw3 outpost-users`
```

An encryption key is required, so data in the database can be encrypted.

```
SECRET_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

kubectl -n outpost create secret generic outpost-cryptkey --from-literal=secret_key=${SECRET_KEY}
```

### Configuration

You have to ask the administrator of all connected JupyterHubs for their ssh-publickey. In this scenario we're using NodePort as service types. JupyterHub must be able to reach the JupyterHub Outpost service at the ports `30080` (access to the Outpost API) and `30022` (access to ssh daemon for port-forwarding). 

```{admonition} Warning
In this scenario, the communication between JupyterHub and JupyterHub Outpost will not be encrypted. Do not use this in production. You'll find an example with encryption below.
```


```
cat <<EOF >> outpost_values.yaml
cryptSecret: outpost-cryptkey
outpostUsers: outpost-users
sshPublicKeys:
  - restrict,port-forwarding,command="/bin/echo No commands allowed" $(cat jupyterhub-sshkey.pub)
service:
  type: NodePort
  ports:
    nodePort: 30080
servicessh:
  type: NodePort
  ports:
    nodePort: 30022
EOF
```

```{admonition} Note 
You can use the same [options](https://manpages.debian.org/experimental/openssh-server/authorized_keys.5.en.html#AUTHORIZED_KEYS_FILE_FORMAT) for each public key as in ~/.ssh/authorized_keys . At least port-forwarding must be allowed.
```

### Installation

```
helm repo add jupyterhub-outpost https://kreuzert.github.io/jupyterhub-outpost/charts/
helm repo update
helm upgrade --install --create-namespace --version <version> --namespace outpost -f outpost_values.yaml outpost jupyterhub-outpost/jupyterhub-outpost
```

Ensure that everything is running. Double check that the ports 30080 and 30022 are reachable from JupyterHub.  
Afterwards, you have to update the JupyterHub OutpostSpawner configuration with the correct IP address + credentials for this JupyterHub Outpost service.

## Encryption via ingress

When running JupyterHub Outpost on production, you should ensure some encryption. An easy way is to use ingress-nginx with a certificate.
For this example we've installed [cert-manager, hairpin-proxy, let's encrypt issuer](https://gitlab.jsc.fz-juelich.de/kaas/fleet-deployments/-/tree/cert-manager) and [ingress-nginx](https://artifacthub.io/packages/helm/ingress-nginx/ingress-nginx). If you already have a certificate you will only need ingress-nginx.

This example is an addition to the examples above.

### Configuration

```
FLOATING_IP_SSH=<EXTERNAL_IP_FOR_SSH_ACCESS>
cat <<EOF >> outpost_remote_values_ingress.yaml
cryptSecret: outpost-cryptkey
outpostUsers: outpost-users
sshPublicKeys:
  - restrict,port-forwarding,command="/bin/echo No commands allowed" $(cat jupyterhub-sshkey.pub)
servicessh:
  type: LoadBalancer
  loadBalancerIP: ${FLOATING_IP_SSH}
ingress:
  enabled: true
  annotations:
    acme.cert-manager.io/http01-edit-in-place: "false"
    cert-manager.io/cluster-issuer: letsencrypt-cluster-issuer
  hosts:
  - myremoteoutpost.com
  tls:
  - hosts:
    - myremoteoutpost.com
    secretName: outpost-tls-certmanager
EOF
```

JupyterHub will now be able to reach the JupyterHub Outpost API at `https://myremoteoutpost.com/services` and the ssh daemon for port-forwarding at `${FLOATING_IP_SSH}` on port 22.

## Persistent database

To use postgresql as database (or something similar) use extraEnvVarsSecrets. All variations can be found in the [source code](https://github.com/kreuzert/jupyterhub-outpost/blob/main/project/app/database/__init__.py) itself.

### Pre-Requirements

Install [postgres](https://artifacthub.io/packages/helm/bitnami/postgresql).  

Create Username and database.
Example SQL commands:
```
CREATE USER jupyterhuboutpost WITH ENCRYPTED PASSWORD '...';
CREATE DATABASE jupyterhuboutpost OWNER jupyterhuboutpost;
```

### Requirement
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

### Configuration

Add it to your values.yaml file:  

```
...
extraEnvVarsSecrets:
  - my-db-secret
```
