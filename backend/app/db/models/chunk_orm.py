# app/db/models/chunk_orm.py
from sqlalchemy import Column, String, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class ChunkORM(Base):
    __tablename__ = "chunks"
    id = Column(String, primary_key=True)  # ES id or stable hash
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)  # NEW
    text = Column(Text, nullable=False)
    page = Column(Integer, nullable=True)
    source = Column(String, nullable=True)  # (keep for back-compat; plan to deprecate)
