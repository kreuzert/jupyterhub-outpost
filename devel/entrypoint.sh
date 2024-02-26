#!/bin/bash

USERNAME=jhuboutpost

# Start sshd service
export SSHD_LOG_PATH=${SSHD_LOG_PATH:-/home/${USERNAME}/sshd.log}
/usr/sbin/sshd -f /etc/ssh/sshd_config -E ${SSHD_LOG_PATH}

mkdir -p /home/${USERNAME}/.ssh
chmod 755 /home/${USERNAME}/.ssh

cp /mnt/outpost_config/outpost_config.py /home/${USERNAME}/app/outpost_config.py
cp /mnt/outpost_config/logging_config.yaml /home/${USERNAME}/app/logging_config.yaml
chmod 644 /home/${USERNAME}/app/outpost_config.py
chmod 644 /home/${USERNAME}/app/logging_config.yaml

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

cd ${HOME}/app
su ${USERNAME}
pip install jupyterhub-kubespawner kubernetes

while true; do
    sleep 30
done
