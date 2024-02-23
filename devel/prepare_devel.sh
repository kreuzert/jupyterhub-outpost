#!/bin/bash

KUBECONFIG=...
NAMESPACE=outpost

POD_NAME=$(kubectl -n ${NAMESPACE} get pods --selector app.kubernetes.io/instance=kube -o jsonpath='{.items..metadata.name}')
echo $POD_NAME

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

if [[ ! -f ${DIR}/devel ]]; then
    ssh-keygen -f ${DIR}/devel -t ed25519
fi

KUBERNETES_SERVICE_HOST=$(kubectl -n ${NAMESPACE} exec ${POD_NAME} -- env | grep KUBERNETES_SERVICE_HOST)
KUBERNETES_SERVICE_HOST=${KUBERNETES_SERVICE_HOST##*=}
echo $KUBERNETES_SERVICE_HOST

KUBERNETES_SERVICE_PORT=$(kubectl -n ${NAMESPACE} exec ${POD_NAME} -- env | grep KUBERNETES_SERVICE_PORT)
KUBERNETES_SERVICE_PORT=${KUBERNETES_SERVICE_PORT##*=}

#SUPERUSER_PASS=$(kubectl -n ${NAMESPACE} get secret drf-k8smgr-passwds -o jsonpath='{.data.SUPERUSER_PASS}' | base64 -d)
#JUPYTERHUBDEV1_USER_PASS=$(kubectl -n ${NAMESPACE} get secret drf-k8smgr-passwds -o jsonpath='{.data.JUPYTERHUBDEV1_USER_PASS}' | base64 -d)
#JUPYTERHUBDEV2_USER_PASS=$(kubectl -n ${NAMESPACE} get secret drf-k8smgr-passwds -o jsonpath='{.data.JUPYTERHUBDEV2_USER_PASS}' | base64 -d)

CRYPT_KEY=$(kubectl -n ${NAMESPACE} get secret outpost-cryptkey -o jsonpath='{.data.secret_key}' | base64 -d)
USERNAMES=$(kubectl -n ${NAMESPACE} get secret outpost-users -o jsonpath='{.data.usernames}' | base64 -d)
PASSWORDS=$(kubectl -n ${NAMESPACE} get secret outpost-users -o jsonpath='{.data.passwords}' | base64 -d)
JUPYTERHUB_CLEANUP_NAMES=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.JUPYTERHUB_CLEANUP_NAMES}' | base64 -d)
JUPYTERHUB_CLEANUP_TOKENS=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.JUPYTERHUB_CLEANUP_TOKENS}' | base64 -d)
JUPYTERHUB_CLEANUP_URLS=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.JUPYTERHUB_CLEANUP_URLS}' | base64 -d)
FLAVOR_DEV1_AUTH_TOKEN=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.FLAVOR_DEV1_AUTH_TOKEN}' | base64 -d)
FLAVOR_DEV2_AUTH_TOKEN=$(kubectl -n ${NAMESPACE} get secret outpost-generics -o jsonpath='{.data.FLAVOR_DEV2_AUTH_TOKEN}' | base64 -d)

SQL_USER=$(kubectl -n ${NAMESPACE} get secret outpost-db -o jsonpath='{.data.SQL_USER}' | base64 -d)
SQL_DATABASE=$(kubectl -n ${NAMESPACE} get secret outpost-db -o jsonpath='{.data.SQL_DATABASE}' | base64 -d)
SQL_PASSWORD=$(kubectl -n ${NAMESPACE} get secret outpost-db -o jsonpath='{.data.SQL_PASSWORD}' | base64 -d)

SQL_HOST=$(kubectl -n ${NAMESPACE} get secret outpost-db -o jsonpath='{.data.SQL_HOST}' | base64 -d)
SQL_PORT=$(kubectl -n ${NAMESPACE} get secret outpost-db -o jsonpath='{.data.SQL_PORT}' | base64 -d)
SQL_TYPE=$(kubectl -n ${NAMESPACE} get secret outpost-db -o jsonpath='{.data.SQL_TYPE}' | base64 -d)

#sed -e "s@<SUPERUSER_PASS>@${SUPERUSER_PASS}@g" -e "s@<JUPYTERHUBDEV1_USER_PASS>@${JUPYTERHUBDEV1_USER_PASS}@g" -e "s@<JUPYTERHUBDEV2_USER_PASS>@${JUPYTERHUBDEV2_USER_PASS}@g" -e "s@<KUBERNETES_SERVICE_HOST>@${KUBERNETES_SERVICE_HOST}@g" -e "s@<KUBERNETES_SERVICE_PORT>@${KUBERNETES_SERVICE_PORT}@g" -e "s@<SQL_TYPE>@${SQL_TYPE}@g" -e "s@<SQL_PASSWORD>@${SQL_PASSWORD}@g" -e "s@<SQL_DATABASE>@${SQL_DATABASE}@g" -e "s@<SQL_HOST>@${SQL_HOST}@g" -e "s@<SQL_PORT>@${SQL_PORT}@g" -e "s@<SQL_USER>@${SQL_USER}@g" ${DIR}/launch.json.template > ${DIR}/launch.json
sed -e "s@<FLAVOR_DEV2_AUTH_TOKEN>@${FLAVOR_DEV2_AUTH_TOKEN}@g" -e "s@<FLAVOR_DEV1_AUTH_TOKEN>@${FLAVOR_DEV1_AUTH_TOKEN}@g" -e "s@<JUPYTERHUB_CLEANUP_NAMES>@${JUPYTERHUB_CLEANUP_NAMES}@g" -e "s@<JUPYTERHUB_CLEANUP_TOKENS>@${JUPYTERHUB_CLEANUP_TOKENS}@g" -e "s@<JUPYTERHUB_CLEANUP_URLS>@${JUPYTERHUB_CLEANUP_URLS}@g" -e "s@<usernames>@${USERNAMES}@g" -e "s@<passwords>@${PASSWORDS}@g" -e "s@<crypt_key>@${CRYPT_KEY}@g" -e "s@<SQL_TYPE>@${SQL_TYPE}@g" -e "s@<SQL_PASSWORD>@${SQL_PASSWORD}@g" -e "s@<SQL_DATABASE>@${SQL_DATABASE}@g" -e "s@<SQL_HOST>@${SQL_HOST}@g" -e "s@<SQL_PORT>@${SQL_PORT}@g" -e "s@<SQL_USER>@${SQL_USER}@g" -e "s@<KUBERNETES_SERVICE_HOST>@${KUBERNETES_SERVICE_HOST}@g" -e "s@<KUBERNETES_SERVICE_PORT>@${KUBERNETES_SERVICE_PORT}@g" ${DIR}/launch.json.template > ${DIR}/launch.json

kubectl -n ${NAMESPACE} cp ${DIR}/devel.pub ${POD_NAME}:/home/jhuboutpost/.ssh/authorized_keys
kubectl -n ${NAMESPACE} cp ${DIR}/settings.json ${POD_NAME}:/home/jhuboutpost/app/.vscode/.
kubectl -n ${NAMESPACE} cp ${DIR}/launch.json ${POD_NAME}:/home/jhuboutpost/app/.vscode/.

echo "kubectl -n ${NAMESPACE} port-forward pod/${POD_NAME} 2223:2222"
