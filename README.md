# JupyterHub Outpost
[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/jupyterhub-outpost)](https://artifacthub.io/packages/search?repo=jupyterhub-outpost)
[![Documentation Status](https://readthedocs.org/projects/jupyterhub-outpostspawner/badge/?version=latest)](https://jupyterhub-outpostspawner.readthedocs.io/en/latest/?badge=latest)

JupyterHub Outpost can be used as an additional, external source to start and manage single-user servers. Like in JupyterHub itself, different Spawners can be configured at the Outpost. It's best used together with the [jupyterhub-outpostspawner](https://pypi.org/project/jupyterhub-outpostspawner/) configured at JupyterHub.

[Overview of JupyterHub OutpostSpawner and JupyterHub Outpost](https://jupyterhub-outpostspawner.readthedocs.io/)

## Overview  
  
The JupyterHub community created many useful [JupyterHub Spawner](https://jupyterhub.readthedocs.io/en/latest/reference/spawners.html#examples) over the past years, to allow JupyterHub to use the specific resources of different systems. For most of these Spawners JupyterHub has to run at the system itself. The OutpostSpawner enables the use of these Spawners on remote systems.  

Other Spawners like [SSHSpawner](https://github.com/NERSC/sshspawner) can spawn single-user servers on remote systems, but are not able to use system-specific features like [KubeSpawner](https://github.com/jupyterhub/kubespawner) or [BatchSpawner](https://github.com/jupyterhub/batchspawner).  
  
With the OutpostSpawner a single JupyterHub can offer multiple remote systems of different types. It comes with an additional REST API called "JupyterHub Outpost". This JupyterHub Outpost can use any JupyterHub Spawner and will manage the lifecycle of the single-user servers.  
  
- Use one JupyterHub to offer single-user servers on multiple systems.
- Each system may use a different JupyterHub Spawner.
- Integrated SSH port forwarding solution to reach remote single-user server.
- supports the JupyterHub `internal_ssl` feature.
- shows events gathered by the remote Spawner to the user.
- Users can override the configuration of the remote Spawner at runtime (e.g. to select a different Docker Image).
- One JupyterHub Outpost can be connected to multiple JupyterHubs, without interfering with each other.
  
## Requirements  
  
JupyterHub must run on a Kubernetes Cluster (recommended is the use of Zero2JupyterHub).  
The JupyterHub Outpost must fulfill the requirements of the configured Spawner class. 
