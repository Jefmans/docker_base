from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
