from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column, Enum as SqlEnum, ForeignKey, Integer, String, TIMESTAMP, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class ProcessingJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    job_type = Column(String, nullable=False, default="pdf_ingest")
    status = Column(SqlEnum(ProcessingJobStatus), nullable=False, default=ProcessingJobStatus.PENDING, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    worker_name = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    started_at = Column(TIMESTAMP, nullable=True)
    finished_at = Column(TIMESTAMP, nullable=True)
