from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.processing_job_orm import ProcessingJob, ProcessingJobStatus


def create_processing_job(
    db: Session,
    document_id: UUID,
    *,
    job_type: str = "pdf_ingest",
    payload: dict | None = None,
) -> ProcessingJob:
    job = ProcessingJob(
        document_id=document_id,
        job_type=job_type,
        status=ProcessingJobStatus.PENDING,
        payload=payload or {},
    )
    db.add(job)
    db.flush()
    return job


def get_processing_job(db: Session, job_id: UUID | str) -> ProcessingJob | None:
    return db.get(ProcessingJob, job_id)


def list_document_jobs(db: Session, document_id: UUID | str) -> list[ProcessingJob]:
    stmt = (
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def claim_next_processing_job(
    db: Session,
    *,
    worker_name: str,
    job_type: str = "pdf_ingest",
) -> ProcessingJob | None:
    stmt = (
        select(ProcessingJob)
        .where(
            ProcessingJob.status == ProcessingJobStatus.PENDING,
            ProcessingJob.job_type == job_type,
        )
        .order_by(ProcessingJob.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    job = db.execute(stmt).scalars().first()
    if job is None:
        return None

    job.status = ProcessingJobStatus.RUNNING
    job.worker_name = worker_name
    job.attempt_count = (job.attempt_count or 0) + 1
    job.started_at = datetime.utcnow()
    job.finished_at = None
    job.error_message = None
    db.flush()
    return job


def mark_processing_job_completed(
    db: Session,
    job: ProcessingJob,
    *,
    payload: dict | None = None,
) -> None:
    current_payload = dict(job.payload or {})
    if payload:
        current_payload.update(payload)
    job.payload = current_payload
    job.status = ProcessingJobStatus.COMPLETED
    job.finished_at = datetime.utcnow()
    job.error_message = None
    db.flush()


def mark_processing_job_failed(db: Session, job: ProcessingJob, *, error_message: str) -> None:
    job.status = ProcessingJobStatus.FAILED
    job.finished_at = datetime.utcnow()
    job.error_message = error_message
    db.flush()
