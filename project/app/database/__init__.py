import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
SQL_DATABASE_URL = os.getenv("DATABASE_URL", "/./test.db")
SQL_TYPE = os.getenv("SQL_TYPE", "sqlite")
SQL_DATABASE = os.getenv("SQL_DATABASE")
SQL_HOST = os.getenv("SQL_HOST")
SQL_PASSWORD = os.getenv("SQL_PASSWORD")
SQL_PORT = os.getenv("SQL_PORT", "5432")
SQL_USER = os.getenv("SQL_USER")
db_url = ""
engine_kwargs = {}

if SQL_TYPE in ["sqlite", "sqlite+pysqlite"]:
    db_url = f"{SQL_TYPE}://{SQL_DATABASE_URL}"
    engine_kwargs = {"connect_args": {"check_same_thread": False}}
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
