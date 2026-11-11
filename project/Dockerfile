FROM python:3.13-alpine3.23

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

# The official python image ships a CycloneDX SBOM for pip's *vendored*
# dependencies (site-packages/pip/_vendor/bom.cdx.json). Scanners (trivy,
# artifacthub) treat every listed component as an installed package,
# producing false positives - e.g. the copy of setuptools (70.3.0) pip
# vendors internally is reported as CVE-2025-47273 even though the
# actually installed packages come from requirements_pip.txt. The file is
# pure metadata that pip does not use at runtime, so remove it to keep
# scans limited to what is really installed.
#
# This must run AFTER the pip upgrade above: upgrading pip re-copies the
# SBOM alongside the new version, so deleting it before the upgrade
# would leave the image dirty again.
RUN find /usr/local/lib -name bom.cdx.json -path "*/pip/_vendor/*" -delete

COPY ./project/app ${APP_HOME}
COPY ./project/entrypoint.sh /src/entrypoint.sh
COPY ./project/gunicorn_http.py ${APP_HOME}/gunicorn_http.py
RUN chown -R ${USERNAME}:users ${HOME} && \
    chown -R ${USERNAME}:users /src && \
    chmod 755 ${HOME}/.ssh && \
    chmod 755 /src/entrypoint.sh

ENTRYPOINT ["/src/entrypoint.sh"]
