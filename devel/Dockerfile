FROM ubuntu:noble-20250619
# FROM ubuntu:oracular-20241009

ENV DEBIAN_FRONTEND=noninteractive

ENV USERNAME=jhuboutpost
ENV PYTHONUNBUFFERED=1
ENV HOME=/home/${USERNAME}
ENV APP_HOME=/home/${USERNAME}/app

RUN apt update && \
    apt -y upgrade && \
    apt -y install adduser && \
    apt clean && \
    rm -rf /var/lib/apt/lists/*

# create app user
RUN EXISTING_USER=$(getent passwd 1000 | cut -d: -f1) && if [ -n "$EXISTING_USER" ]; then userdel -r "$EXISTING_USER"; fi
RUN adduser --uid 1000 --disabled-password ${USERNAME}
RUN mkdir -p ${APP_HOME} && mkdir -p ${HOME}/.ssh
WORKDIR ${APP_HOME}

# Install requirements
COPY ./devel/requirements_apt.txt /tmp/requirements_apt.txt
COPY ./devel/requirements_pip.txt /tmp/requirements_pip.txt

RUN apt update && \
    cat /tmp/requirements_apt.txt | xargs apt install -yq && \
    apt clean && \
    rm -rf /var/lib/apt/lists/* && \
    python3 -m venv ${HOME}/venv && \
    ${HOME}/venv/bin/python3 -m ensurepip && \
    ${HOME}/venv/bin/pip3 install -r /tmp/requirements_pip.txt && \
    chown -R ${USERNAME}:users ${HOME} && \
    rm /tmp/requirements_pip.txt && \
    rm /tmp/requirements_apt.txt && \
    sed -i -r \
    -e "s/^#PasswordAuthentication yes/PasswordAuthentication no/g" \
    -e "s/^#AllowTcpForwarding yes/AllowTcpForwarding yes/g" \
    -e "s/^#Port 22/Port 2222/g" \
    /etc/ssh/sshd_config && \
    mkdir -p /run/sshd && \
    ssh-keygen -A

RUN echo ${USERNAME}:$(uuidgen) | chpasswd

COPY project/app ${APP_HOME}
COPY devel/entrypoint.sh /src/entrypoint.sh
RUN chown -R ${USERNAME}:users ${HOME} && \
    chmod 755 ${HOME}/.ssh && \
    chmod 755 /src/entrypoint.sh

ENTRYPOINT ["/src/entrypoint.sh"]
