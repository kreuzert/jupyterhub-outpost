from datetime import datetime
from datetime import timezone
from typing import List

from database import Base
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.types import DateTime
from sqlalchemy.types import LargeBinary


class JupyterHub(Base):
    __tablename__ = "jupyterhub"

    # username = Column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(primary_key=True)
    services: Mapped[List["Service"]] = relationship(back_populates="jupyterhub")


class Service(Base):
    __tablename__ = "service"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name = Column(String)
    start_id = Column(String, default="0")
    jupyterhub_username: Mapped[str] = mapped_column(ForeignKey("jupyterhub.name"))
    last_update = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    start_date = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    end_date = Column(
        DateTime(timezone=True), default=datetime.max.replace(tzinfo=timezone.utc)
    )
    state_stored = Column(Boolean, default=False)
    start_pending = Column(Boolean, default=True)
    stop_pending = Column(Boolean, default=False)
    body = Column(LargeBinary, default=None)
    state = Column(LargeBinary, default=None)
    start_response = Column(LargeBinary, default=None)
    jupyterhub: Mapped["JupyterHub"] = relationship(back_populates="services")
    jupyterhub_user_id = Column(Integer, default=0)
    flavor = Column(String, default=None)
