#!/bin/bash

if [[ -n $AUTHORIZED_KEYS_PATH ]]; then
    sed -i -e "s@.ssh/authorized_keys@${AUTHORIZED_KEYS_PATH}@g" /etc/ssh/sshd_config
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
fi

cd $HOME
su ${USERNAME}

export SPAWNER_CONFIG_FILE=${SPAWNER_CONFIG_FILE:-${APP_HOME}/outpost_config.py}

uvicorn --app-dir app main:app --proxy-headers --host ${HOST:-0.0.0.0} --port ${PORT:-8080} ${@}
