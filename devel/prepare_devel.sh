#!/bin/bash

NAMESPACE=outpost
INSTANCE_NAME="kube"
SECRET_USERS="outpost-users"
SECRET_CRYPTKEY="outpost-cryptkey"
SECRET_GENERICS=""
SECRET_DB="outpost-db"

POD_NAME=$(kubectl -n ${NAMESPACE} get pods --selector app.kubernetes.io/instance=${INSTANCE_NAME} -o jsonpath='{.items..metadata.name}')
echo $POD_NAME
IMAGE=$(kubectl -n ${NAMESPACE} get pod ${POD_NAME} -o jsonpath='{.spec.containers[0].image}')
IMAGE_TAG=${IMAGE##*:}
IMAGE_NAME=${IMAGE%%:*}

if [[ ! $IMAGE_TAG == "devel" ]]; then
    echo "JupyterHub Outpost is not using the devel image"
    DEPL_NAME=$(kubectl -n ${NAMESPACE} get deployment --selector app.kubernetes.io/instance=${INSTANCE_NAME} -o jsonpath='{.items..metadata.name}')
    echo "Run \"kubectl -n ${NAMESPACE} set image deployment ${DEPL_NAME} jupyterhub-outpost=${IMAGE_NAME}:devel\" first"
else
    DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

    if [[ ! -f ${DIR}/devel ]]; then
        ssh-keygen -f ${DIR}/devel -t ed25519
    fi

    KUBERNETES_SERVICE_HOST=$(kubectl -n ${NAMESPACE} exec ${POD_NAME} -- env | grep KUBERNETES_SERVICE_HOST)
    KUBERNETES_SERVICE_HOST=${KUBERNETES_SERVICE_HOST##*=}

    KUBERNETES_SERVICE_PORT=$(kubectl -n ${NAMESPACE} exec ${POD_NAME} -- env | grep KUBERNETES_SERVICE_PORT)
    KUBERNETES_SERVICE_PORT=${KUBERNETES_SERVICE_PORT##*=}

    CRYPT_KEY=$(kubectl -n ${NAMESPACE} get secret ${SECRET_CRYPTKEY} -o jsonpath='{.data.secret_key}' | base64 -d)
    USERNAMES=$(kubectl -n ${NAMESPACE} get secret ${SECRET_USERS} -o jsonpath='{.data.usernames}' | base64 -d)
    PASSWORDS=$(kubectl -n ${NAMESPACE} get secret ${SECRET_USERS} -o jsonpath='{.data.passwords}' | base64 -d)

    if [[ ! $SECRET_GENERICS == "" ]]; then
        JUPYTERHUB_CLEANUP_NAMES=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.JUPYTERHUB_CLEANUP_NAMES}' | base64 -d)
        JUPYTERHUB_CLEANUP_TOKENS=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.JUPYTERHUB_CLEANUP_TOKENS}' | base64 -d)
        JUPYTERHUB_CLEANUP_URLS=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.JUPYTERHUB_CLEANUP_URLS}' | base64 -d)
        FLAVOR_DEV1_AUTH_TOKEN=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.FLAVOR_DEV1_AUTH_TOKEN}' | base64 -d)
        FLAVOR_DEV2_AUTH_TOKEN=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.FLAVOR_DEV2_AUTH_TOKEN}' | base64 -d)
    fi

    SQL_USER=$(kubectl -n ${NAMESPACE} get secret ${SECRET_DB} -o jsonpath='{.data.SQL_USER}' | base64 -d)
    SQL_DATABASE=$(kubectl -n ${NAMESPACE} get secret ${SECRET_DB} -o jsonpath='{.data.SQL_DATABASE}' | base64 -d)
    SQL_PASSWORD=$(kubectl -n ${NAMESPACE} get secret ${SECRET_DB} -o jsonpath='{.data.SQL_PASSWORD}' | base64 -d)

    SQL_HOST=$(kubectl -n ${NAMESPACE} get secret ${SECRET_DB} -o jsonpath='{.data.SQL_HOST}' | base64 -d)
    SQL_PORT=$(kubectl -n ${NAMESPACE} get secret ${SECRET_DB} -o jsonpath='{.data.SQL_PORT}' | base64 -d)
    SQL_TYPE=$(kubectl -n ${NAMESPACE} get secret ${SECRET_DB} -o jsonpath='{.data.SQL_TYPE}' | base64 -d)

    sed -e "s@<FLAVOR_DEV2_AUTH_TOKEN>@${FLAVOR_DEV2_AUTH_TOKEN}@g" -e "s@<FLAVOR_DEV1_AUTH_TOKEN>@${FLAVOR_DEV1_AUTH_TOKEN}@g" -e "s@<JUPYTERHUB_CLEANUP_NAMES>@${JUPYTERHUB_CLEANUP_NAMES}@g" -e "s@<JUPYTERHUB_CLEANUP_TOKENS>@${JUPYTERHUB_CLEANUP_TOKENS}@g" -e "s@<JUPYTERHUB_CLEANUP_URLS>@${JUPYTERHUB_CLEANUP_URLS}@g" -e "s@<usernames>@${USERNAMES}@g" -e "s@<passwords>@${PASSWORDS}@g" -e "s@<crypt_key>@${CRYPT_KEY}@g" -e "s@<SQL_TYPE>@${SQL_TYPE}@g" -e "s@<SQL_PASSWORD>@${SQL_PASSWORD}@g" -e "s@<SQL_DATABASE>@${SQL_DATABASE}@g" -e "s@<SQL_HOST>@${SQL_HOST}@g" -e "s@<SQL_PORT>@${SQL_PORT}@g" -e "s@<SQL_USER>@${SQL_USER}@g" -e "s@<KUBERNETES_SERVICE_HOST>@${KUBERNETES_SERVICE_HOST}@g" -e "s@<KUBERNETES_SERVICE_PORT>@${KUBERNETES_SERVICE_PORT}@g" ${DIR}/launch.json.template > ${DIR}/launch.json

    kubectl -n ${NAMESPACE} cp ${DIR}/devel.pub ${POD_NAME}:/home/jhuboutpost/.ssh/authorized_keys
    kubectl -n ${NAMESPACE} cp ${DIR}/settings.json ${POD_NAME}:/home/jhuboutpost/app/.vscode/.
    kubectl -n ${NAMESPACE} cp ${DIR}/launch.json ${POD_NAME}:/home/jhuboutpost/app/.vscode/.

    kubectl -n ${NAMESPACE} exec -it ${POD_NAME} -- chown 1000:1000 /home/jhuboutpost/.ssh/authorized_keys

    echo "kubectl -n ${NAMESPACE} port-forward pod/${POD_NAME} 2223:2222"
fi
