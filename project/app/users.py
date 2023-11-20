"""
We're using a environment user base.
You just have to add a semicolon separated in `usernames` 
and `passwords`.
"""
import logging
import os
from typing import Annotated

from database.schemas import decrypt
from database.schemas import encrypt
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import HTTPBasic
from fastapi.security import HTTPBasicCredentials

log = logging.getLogger("uvicorn")


security = HTTPBasic()


_users = {}


def get_users():
    global _users
    if not _users:
        usernames_via_env = [x for x in os.environ.get("usernames", "").split(";") if x]
        passwords_via_env = [x for x in os.environ.get("passwords", "").split(";") if x]
        if usernames_via_env and passwords_via_env:
            for i in range(len(usernames_via_env)):
                if i >= len(passwords_via_env):
                    log.warning(
                        f"No password available for {usernames_via_env[i]}. User not created."
                    )
                else:
                    _users[usernames_via_env[i]] = encrypt(passwords_via_env[i])
    return _users


def verify_user(credentials: Annotated[HTTPBasicCredentials, Depends(security)]):
    users = get_users()
    if credentials.username not in users.keys() or not credentials.password == decrypt(
        users[credentials.username], return_type="str"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
