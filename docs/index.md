(front-page)=

# JupyterHub Outpost

The JupyterHub Outpost service in combination with the [OutpostSpawner](https://github.com/kreuzert/jupyterhub-outpostspawner) enables JupyterHub to spawn single-user notebook servers on heterogenous remote resources.  

## Overview  
  
The JupyterHub community has created many useful [JupyterHub Spawners](https://jupyterhub.readthedocs.io/en/latest/reference/spawners.html#examples) over the past years, allowing JupyterHub to use the specific features of different systems. For most of these Spawners, JupyterHub has to run locally on the system itself. The JupyterHub Outpost service allows the use of these Spawners on remote systems with no modifications to their code, provided that JupyterHub uses the [OutpostSpawner](https://github.com/kreuzert/jupyterhub-outpostspawner/) as mediator.  

While Spawners like the [SSHSpawner](https://github.com/NERSC/sshspawner) can already spawn single-user servers on remote systems, they are not able to utilize system-specific features like [KubeSpawner](https://github.com/jupyterhub/kubespawner) or [BatchSpawner](https://github.com/jupyterhub/batchspawner). 
  
The JupyterHub Outpost service in combination with the OutpostSpawner enables a single JupyterHub to spawn single-user notebook servers using a variety of Spawners on a variety of remote systems.
  
- Use one JupyterHub to offer single-user servers on multiple systems of potentially different types.
- Each (remote) system may use a different JupyterHub Spawner.
- Forward spawn events gathered by the remote Spawner to the user.
- Users can override the configuration of the remote Spawner at runtime (e.g. to select a different Docker Image).
- Integrated SSH port forwarding solution to reach otherwise isolated remote single-user servers.
- Supports the JupyterHub `internal_ssl` feature.
- One JupyterHub Outpost can be connected to multiple JupyterHubs without the Hubs interfering with each other.
  
## Requirements  
  
At least one JupyterHub running on a Kubernetes Cluster (recommended is the use of [Zero2JupyterHub](https://z2jh.jupyter.org/en/stable/)). It is not necessary that the JupyterHub Outpost service runs on Kubernetes, but recommended.  


## License

```{eval-rst}
.. literalinclude:: ../LICENSE
```
  
```{eval-rst}
.. toctree::
    :maxdepth: 2
    :caption: General

    architecture
```

```{eval-rst}
.. toctree::
    :maxdepth: 2
    :caption: Usage

    usage/installation
    usage/configuration
    apiendpoints
```
