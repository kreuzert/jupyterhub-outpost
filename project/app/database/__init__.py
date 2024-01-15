import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
SQL_DATABASE_URL = os.getenv(
    "DATABASE_URL", "/file:memdb?mode=memory&cache=shared&uri=true"
)
SQL_TYPE = os.getenv("SQL_TYPE", "sqlite")
SQL_DATABASE = os.getenv("SQL_DATABASE")
SQL_HOST = os.getenv("SQL_HOST")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")
SQL_PORT = os.getenv("SQL_PORT", "5432")
SQL_USER = os.getenv("SQL_USER")
db_url = ""

# recycle – If set to a value other than -1, number of seconds between connection recycling, which means upon checkout, if this timeout is surpassed the connection will be closed and replaced with a newly opened connection. Defaults to -1.
# pre_ping - if True, the pool will emit a “ping” (typically “SELECT 1”, but is dialect-specific) on the connection upon checkout, to test if the connection is alive or not. If not, the connection is transparently re-connected and upon success, all other pooled connections established prior to that timestamp are invalidated. Requires that a dialect is passed as well to interpret the disconnection error.
engine_kwargs = {"pool_recycle": 300, "pool_pre_ping": True}

if SQL_TYPE in ["sqlite", "sqlite+pysqlite"]:
    db_url = f"{SQL_TYPE}://{SQL_DATABASE_URL}"
    engine_kwargs.update({"connect_args": {"check_same_thread": False}})
elif SQL_TYPE == "postgresql":
    db_url = (
        f"{SQL_TYPE}://{SQL_USER}:{SQL_PASSWORD}@{SQL_HOST}:{SQL_PORT}/{SQL_DATABASE}"
    )
else:
    raise Exception(
        f"SQL_TYPE {SQL_TYPE} not supported. Use 'sqlite', 'sqlite+pysqlite' or 'postgresql'."
    )

engine = create_engine(db_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from database.models import Base

Base.metadata.create_all(engine)
