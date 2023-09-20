import base64
from typing import Any
from typing import Generator

import pytest
from app.api.services import router as service_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def start_application():
    app = FastAPI()
    app.include_router(service_router)
    return app


SQL_DATABASE_URL = "/:memory:"
SQL_TYPE = "sqlite+pysqlite"
db_url = "sqlite+pysqlite:///:memory:"
engine = create_engine(
    db_url, connect_args={"check_same_thread": False}, echo=True, future=True
)
# Use connect_args parameter only with sqlite
SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function", autouse=True)
def app(spawner_config, monkeypatch) -> Generator[FastAPI, Any, None]:
    """
    Create a fresh database on each test case.
    """
    monkeypatch.setenv("OUTPOST_CONFIG_FILE", spawner_config)
    _app = start_application()
    import spawner
    from spawner import hub
    from uuid import uuid4

    _wrapper = spawner.JupyterHubOutpost()

    def get_wrapper():
        return _wrapper

    monkeypatch.setattr(spawner, "get_wrapper", get_wrapper)
    monkeypatch.setattr(spawner, "_wrapper", _wrapper)
    monkeypatch.setattr(hub, "certs_dir", f"/tmp/jupyterhub-certs/{uuid4().hex}")
    yield _app
    from spawner import remove_wrapper

    remove_wrapper()


auth_username = "authenticated"
auth_username2 = "authenticated2"
auth_username_passwd = "passwd"
auth_username2_passwd = "passwd2"
auth_user_b64 = base64.b64encode(
    f"{auth_username}:{auth_username_passwd}".encode()
).decode()
auth_user2_b64 = base64.b64encode(
    f"{auth_username2}:{auth_username2_passwd}".encode()
).decode()
auth_user_wrong_pw = base64.b64encode(
    f"{auth_username}:{auth_username_passwd}w".encode()
).decode()


@pytest.fixture(scope="session")
def monkeysession():
    with pytest.MonkeyPatch.context() as mp:
        yield mp


@pytest.fixture(scope="session", autouse=True)
def set_user(monkeysession):
    monkeypatch = monkeysession
    monkeypatch.setenv("usernames", f"{auth_username};{auth_username2}")
    monkeypatch.setenv("passwords", f"{auth_username_passwd};{auth_username2_passwd}")
    monkeypatch.setenv(
        "OUTPOST_CRYPT_KEY", "UMmHjHvWjvObNBdjfICzbG8RK7-W-nujsMnN9AAVioU=s"
    )


@pytest.fixture(scope="function")
def db_session(app: FastAPI) -> Generator[SessionTesting, Any, None]:
    from database import Base

    Base.metadata.create_all(engine)  # Create the tables.
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionTesting(bind=connection)
    from database.models import JupyterHub

    auth_user = JupyterHub(name="authenticated")
    session.add(auth_user)
    session.commit()
    yield session  # use the session in tests.
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(
    app: FastAPI, db_session: SessionTesting
) -> Generator[TestClient, Any, None]:
    """
    Create a new FastAPI TestClient that uses the `db_session` fixture to override
    the `get_db` dependency that is injected into routes.
    """

    def _get_test_db():
        try:
            yield db_session
        finally:
            pass

    from database.utils import get_db

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as client:
        yield client
