#!/bin/bash

export SSHD_LOG_PATH=${SSHD_LOG_PATH:-/home/${USERNAME}/sshd.log}
/usr/sbin/sshd -f /etc/ssh/sshd_config -E ${SSHD_LOG_PATH}

# Database setup / wait for database
if [ "$SQL_TYPE" == "postgresql" ]; then
    echo "Waiting for postgresql..."
    while ! nc -z $SQL_HOST $SQL_PORT; do
        sleep 0.1
    done
    echo "$(date) PostgreSQL started"
fi

cd ${HOME}/app
su ${USERNAME}

/usr/local/bin/gunicorn -c gunicorn_http.py main:app
# uvicorn --app-dir app main:app --proxy-headers --workers ${UVICORN_WORKERS} --host ${HOST:-0.0.0.0} --port ${PORT:-8080} ${@}
