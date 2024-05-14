#!/bin/bash

if [[ -d /mnt/authorized_keys ]]; then
    cp /mnt/authorized_keys/* ${HOME}/.ssh/.
    chown -R ${USERNAME}:users ${HOME}/.ssh
    chmod 600 ${HOME}/.ssh/*
fi

export SSHD_LOG_PATH=${SSHD_LOG_PATH:-/home/${USERNAME}/sshd.log}
/usr/sbin/sshd -f /etc/ssh/sshd_config -E ${SSHD_LOG_PATH}

# Database setup / wait for database
if [ "$SQL_TYPE" == "postgresql" ]; then
    echo "Waiting for postgresql..."
    while ! nc -z $SQL_HOST $SQL_PORT; do
        sleep 0.1
    done
    echo "$(date) PostgreSQL started"
elif [ "${SQL_TYPE:-sqlite}" == "sqlite" ]; then
    if [ -z ${SQL_DATABASE_URL} ]; then
        touch /tmp/sqlite.db
	chown -R jhuboutpost:users /tmp/sqlite.db
	chmod 666 /tmp/sqlite.db
    fi
fi

cd ${HOME}/app
su ${USERNAME}

export GUNICORN_CONFIG_FILE=${GUNICORN_CONFIG_FILE:-gunicorn_http.py}
/usr/local/bin/gunicorn -c ${GUNICORN_CONFIG_FILE} main:app
