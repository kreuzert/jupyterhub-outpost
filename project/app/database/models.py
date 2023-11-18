from datetime import datetime
from typing import List

from database import Base
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.types import DateTime
from sqlalchemy.types import JSON


class JupyterHub(Base):
    __tablename__ = "jupyterhub"

    # username = Column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(primary_key=True)
    services: Mapped[List["Service"]] = relationship(back_populates="jupyterhub")


class Service(Base):
    __tablename__ = "service"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name = Column(String)
    jupyterhub_username: Mapped[str] = mapped_column(ForeignKey("jupyterhub.name"))
    last_update = Column(DateTime(timezone=True), default=datetime.now())
    start_date = Column(DateTime(timezone=True), default=datetime.now())
    start_pending = Column(Boolean, default=True)
    stop_pending = Column(Boolean, default=False)
    body = Column("body", MutableDict.as_mutable(JSON), default={})
    state = Column("state", MutableDict.as_mutable(JSON), default={})
    start_response = Column("start_response", MutableDict.as_mutable(JSON), default={})
    jupyterhub: Mapped["JupyterHub"] = relationship(back_populates="services")
