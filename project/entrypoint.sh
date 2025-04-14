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

    PSQL_CMD="PGPASSWORD=${SQL_PASSWORD} psql -h $SQL_HOST -U $SQL_USER -d $SQL_DATABASE -tAc"

    CHECK_COLUMN_EXISTS="$PSQL_CMD \"
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'service' 
          AND column_name = 'jupyterhub_user_id';
    \""

    # Run the check
    COLUMN_EXISTS=$(eval $CHECK_COLUMN_EXISTS)

    if [ "$COLUMN_EXISTS" != "1" ]; then
        echo "$(date) Column does not exist. Adding column 'jupyterhub_user_id'..."
        ADD_COLUMN_SQL="
        ALTER TABLE public.service
        ADD COLUMN jupyterhub_user_id INTEGER DEFAULT 0;
        "
        echo "$ADD_COLUMN_SQL" | PGPASSWORD="$SQL_PASSWORD" psql -h "$SQL_HOST" -U "$SQL_USER" -d "$SQL_DATABASE"
        echo "$(date) Column added."
    fi
elif [ "${SQL_TYPE:-sqlite}" == "sqlite" ]; then
    touch ${SQL_DATABASE_URL:-/tmp/sqlite.db}
    chmod 666 ${SQL_DATABASE_URL:-/tmp/sqlite.db}
fi

cd ${HOME}/app
su ${USERNAME}

export GUNICORN_CONFIG_FILE=${GUNICORN_CONFIG_FILE:-gunicorn_http.py}
/usr/local/bin/gunicorn -c ${GUNICORN_CONFIG_FILE} main:app
