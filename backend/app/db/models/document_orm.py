from datetime import datetime
from uuid import uuid4

from sqlalchemy import ARRAY, Column, Integer, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    filename = Column(String, unique=True, index=True, nullable=False)
    title = Column(String)
    year = Column(Integer)
    type = Column(String)
    topic = Column(String)
    authors = Column(ARRAY(String))
    isbn = Column(String)
    doi = Column(String)
    publisher = Column(String)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
