# FROM jupyterjsc/jupyterhub-outpost:devel
# RUN groupadd --gid 988 docker && usermod -aG docker jhuboutpost
FROM jupyterjsc/jupyterhub-outpost:2.3.1
RUN addgroup -g 988 docker && addgroup jhuboutpost docker

RUN pip install dockerspawner==14.0.0
