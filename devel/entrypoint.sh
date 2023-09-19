#!/bin/bash

USERNAME=jupyterhuboutpost

# Start sshd service
export SSHD_LOG_PATH=${SSHD_LOG_PATH:-/home/${USERNAME}/sshd.log}
/usr/sbin/sshd -f /etc/ssh/sshd_config -E ${SSHD_LOG_PATH}

mkdir -p /home/${USERNAME}/.ssh
chmod 755 /home/${USERNAME}/.ssh

mkdir -p /home/${USERNAME}/app/.vscode
chmod 755 /home/${USERNAME}/app/.vscode
chown -R ${USERNAME}:users /home/${USERNAME}

# Set secret key
export SECRET_KEY=${SECRET_KEY:-$(uuidgen)}

# Database setup / wait for database
if [ "$SQL_TYPE" == "postgresql" ]; then
    echo "Waiting for postgresql..."
    while ! nc -z $SQL_HOST $SQL_PORT; do
        sleep 0.1
    done
    echo "$(date) PostgreSQL started"
fi

while true; do
    sleep 30
done
