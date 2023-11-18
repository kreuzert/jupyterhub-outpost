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

export GUNICORN_CONFIG_FILE=${GUNICORN_CONFIG_FILE:-gunicorn_http.py}
/usr/local/bin/gunicorn -c ${GUNICORN_CONFIG_FILE} main:app
