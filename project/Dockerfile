FROM python:3-alpine

ENV USERNAME=jhuboutpost
ENV HOME=/home/${USERNAME}
ENV APP_HOME=/home/${USERNAME}/app

RUN adduser --uid 1000 --gecos "" --disabled-password ${USERNAME}
RUN mkdir -p ${APP_HOME} && mkdir -p ${HOME}/.ssh

WORKDIR ${APP_HOME}

COPY ./project/requirements_apk.txt /src/requirements_apk.txt
COPY ./project/requirements_pip.txt /src/requirements_pip.txt
RUN apk add --virtual=build_dependencies build-base && \
    cat /src/requirements_apk.txt | xargs apk add && \
    pip install -U pip && \
    pip install --no-cache-dir --upgrade -r /src/requirements_pip.txt && \
    apk del --purge -r build_dependencies && \
    chown -R ${USERNAME}:users ${HOME} && \
    sed -i -r \
    -e "s/^#PasswordAuthentication yes/PasswordAuthentication no/g" \
    -e "s/^AllowTcpForwarding no/AllowTcpForwarding yes/g" \
    -e "s/^#Port 22/Port 22/g" \
    /etc/ssh/sshd_config && \
    sed -i -r \
    -e "s/^${USERNAME}:!:/${USERNAME}::/g" \
    /etc/shadow && \
    ssh-keygen -A 

COPY ./project/app ${APP_HOME}
COPY ./project/entrypoint.sh /src/entrypoint.sh
COPY ./project/gunicorn_http.py ${APP_HOME}/gunicorn_http.py
RUN chown -R ${USERNAME}:users ${HOME} && \
    chown -R ${USERNAME}:users /src && \
    chmod 755 ${HOME}/.ssh && \
    chmod 755 /src/entrypoint.sh

ENTRYPOINT ["/src/entrypoint.sh"]
