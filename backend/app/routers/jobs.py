from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.db import get_db
from app.db.models.document_orm import Document
from app.repositories.job_repo import (
    claim_next_processing_job,
    get_processing_job,
    list_document_jobs,
    mark_processing_job_completed,
    mark_processing_job_failed,
)
from app.schemas import ImageMetadata
from app.utils.save_images import save_image_metadata_list


router = APIRouter()


class ClaimJobRequest(BaseModel):
    worker_name: str = "pdf_worker"


class DocumentMetadataPayload(BaseModel):
    title: Optional[str] = None
    year: Optional[int] = None
    type: Optional[str] = None
    topic: Optional[str] = None
    authors: Optional[list[str]] = None
    isbn: Optional[str] = None
    doi: Optional[str] = None
    publisher: Optional[str] = None


class CompleteJobRequest(BaseModel):
    metadata: Optional[DocumentMetadataPayload] = None
    images: list[ImageMetadata] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class FailJobRequest(BaseModel):
    error: str


def _job_to_dict(job, document: Document) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "document_id": str(document.id),
        "filename": document.filename,
        "status": job.status.value,
        "job_type": job.job_type,
        "attempt_count": job.attempt_count,
        "worker_name": job.worker_name,
        "error_message": job.error_message,
        "payload": dict(job.payload or {}),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = get_processing_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    document = db.get(Document, job.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _job_to_dict(job, document)


@router.get("/documents/{document_id}/jobs")
def get_document_jobs(document_id: UUID, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    jobs = list_document_jobs(db, document_id)
    return {
        "document_id": str(document.id),
        "filename": document.filename,
        "jobs": [_job_to_dict(job, document) for job in jobs],
    }


@router.post("/internal/jobs/claim")
def claim_job(request: ClaimJobRequest, db: Session = Depends(get_db)):
    job = claim_next_processing_job(db, worker_name=request.worker_name)
    if job is None:
        db.commit()
        return Response(status_code=204)

    document = db.get(Document, job.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    db.commit()
    return {
        "id": str(job.id),
        "document_id": str(document.id),
        "filename": document.filename,
        "job_type": job.job_type,
        "payload": dict(job.payload or {}),
        "attempt_count": job.attempt_count,
    }


@router.post("/internal/jobs/{job_id}/complete")
def complete_job(job_id: UUID, request: CompleteJobRequest, db: Session = Depends(get_db)):
    job = get_processing_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    document = db.get(Document, job.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if request.metadata is not None:
        metadata = request.metadata
        document.title = metadata.title
        document.year = metadata.year
        document.type = metadata.type
        document.topic = metadata.topic
        document.authors = metadata.authors
        document.isbn = metadata.isbn
        document.doi = metadata.doi
        document.publisher = metadata.publisher

    if request.images:
        save_image_metadata_list(db, request.images)

    mark_processing_job_completed(db, job, payload={"stats": request.stats})
    db.commit()

    return {
        "status": "completed",
        "job_id": str(job.id),
        "document_id": str(document.id),
        "stats": request.stats,
    }


@router.post("/internal/jobs/{job_id}/fail")
def fail_job(job_id: UUID, request: FailJobRequest, db: Session = Depends(get_db)):
    job = get_processing_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    mark_processing_job_failed(db, job, error_message=request.error)
    db.commit()

    return {"status": "failed", "job_id": str(job.id)}
