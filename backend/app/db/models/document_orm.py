from datetime import datetime
from uuid import uuid4

from sqlalchemy import ARRAY, Column, ForeignKey, Integer, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    filename = Column(String, unique=True, index=True, nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True)
    title = Column(String)
    year = Column(Integer)
    type = Column(String)
    topic = Column(String)
    authors = Column(ARRAY(String))
    isbn = Column(String)
    doi = Column(String)
    publisher = Column(String)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
