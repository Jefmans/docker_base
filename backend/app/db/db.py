# app/db/db.py
from sqlalchemy import Column, String, TIMESTAMP, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

from app.db.base import Base  # <-- use the single shared Base
from app.db.models.document_orm import Document
from app.db.models.image_record_orm import ImageRecord

DATABASE_URL = "postgresql://test:test@postgres:5432/testdb"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Session(Base):
    __tablename__ = "sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query = Column(String, nullable=False)
    tree = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
