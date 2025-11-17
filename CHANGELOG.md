# Changelog
## 2.1.0 (2025-11-17)
- Feature: Added credits endpoint to support JupyterHub Credit Service extension. Spawner credit values/interval can be configured via flavor

## 2.0.9 (2025-10-14)
- BugFix: Update User.auth_state when receiving a Request with auth_state information in it.

## 2.0.8 (2025-10-13)
- Support ingresses with prefixes via `OUTPOST_BASE_PATH` env variable.

## 2.0.7 (2025-07-15)
- Upgrade base image + python packages

## 2.0.6 (2025-07-10)
- Added c.JupyterHubOutpost.update_user_authentication . Allows for manipulating user authentication input before matching against configuration.

## 2.0.5 (2025-07-09)
- Minor logging improvements: Log result of user_flavor checks in trace level

## 2.0.4 (2025-06-25)
- Added c.JupyterHubOutpost.ssh_recreate_at_start_global hook. Allows for recreation of ssh-tunnels on per-hub level instead of per-server level.

## 2.0.3 (2025-06-25)
- Tunnel recreation during startup now in background for better performance and faster starts

## 2.0.2 (2025-06-25)
- Fix Startup behaviour (initial logging configuration, ssh-tunnel recreation)

## 2.0.1 (2025-04-28)
- Fixed a bug in exception handling when deleting services fails

## 2.0.0 (2025-04-24)
- Simplified user specific flavor configuration
- Database change: jupyterhub_user_id (Integer) added to `Service` table

## 1.0.6 (2025-04-22)
- Minor logging improvements

## 1.0.5 (2024-10-29)
- Security updates (alpine image, python packages)
- Using `BackgroundTasks` instead of `asyncio.tasks` for async calls ([merge request](jupyterjsc/k8s/images/jupyterhub-outpost!9))

## 1.0.4 (2024-07-09)
Improved default configuration to work with any submitted profile

## 1.0.3 (2024-05-15)

### fixed (2 changes)

- [Improved default sqlite behaviour. Fixed end_date checks.](jupyterjsc/k8s/images/jupyterhub-outpost@09a1cfe57cd9fdcf3e0ae557b80ffbd60a3e65fe) ([merge request](jupyterjsc/k8s/images/jupyterhub-outpost!7))

## 1.0.1 (2024-05-07)

### fixed (1 change)
Default number of processes reduced to 1, to prevent memory-sqlite errors

## 1.0.0 (2024-04-22)

Release of version 1.0.0.
