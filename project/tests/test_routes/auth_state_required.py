from jupyterhub.spawner import SimpleLocalProcessSpawner


class AuthStateSimpleLocalProcessSpawner(SimpleLocalProcessSpawner):
    async def start(self):
        auth_state = await self.user.get_auth_state()
        assert auth_state.get("access_token") == "secret"
        return await super().start()

    async def poll(self):
        auth_state = await self.user.get_auth_state()
        assert auth_state.get("access_token") == "secret"
        return await super().poll()

    async def stop(self, now=False):
        auth_state = await self.user.get_auth_state()
        assert auth_state.get("access_token") == "secret"
        return await super().stop(now=now)


c.JupyterHubOutpost.spawner_class = AuthStateSimpleLocalProcessSpawner
c.AuthStateSimpleLocalProcessSpawner.port = 4567
c.AuthStateSimpleLocalProcessSpawner.cmd = "/bin/echo"
c.AuthStateSimpleLocalProcessSpawner.args = "Hello World"
