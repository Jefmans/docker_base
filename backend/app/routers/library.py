from collections import Counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.db import get_db
from app.db.models.document_orm import Document
from app.db.models.image_record_orm import ImageRecord
from app.db.models.processing_job_orm import ProcessingJob, ProcessingJobStatus
from app.db.models.project_orm import Project
from app.repositories.project_repo import get_or_create_project, normalize_project_name
from app.utils.minio_utils import get_minio_client, remove_object_if_exists
from app.utils.search_index import delete_by_filters


router = APIRouter()

UPLOAD_BUCKET = "uploads"
IMAGE_BUCKET = "images"

minio_client = get_minio_client()


class CreateProjectRequest(BaseModel):
    name: str


class UpdateDocumentProjectRequest(BaseModel):
    project_id: UUID | None = None
    project_name: str | None = None


def _display_filename(filename: str) -> str:
    if "_" not in filename:
        return filename
    return filename.split("_", 1)[1]


def _serialize_job(job: ProcessingJob | None) -> dict | None:
    if job is None:
        return None

    return {
        "id": str(job.id),
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


def _serialize_project(project: Project, *, document_count: int = 0) -> dict:
    return {
        "id": str(project.id),
        "name": project.name,
        "document_count": document_count,
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


def _serialize_document(
    document: Document,
    *,
    project: Project | None = None,
    latest_job: ProcessingJob | None = None,
) -> dict:
    return {
        "id": str(document.id),
        "filename": document.filename,
        "display_name": _display_filename(document.filename),
        "project_id": str(project.id) if project else None,
        "project_name": project.name if project else None,
        "title": document.title,
        "year": document.year,
        "type": document.type,
        "topic": document.topic,
        "authors": document.authors or [],
        "isbn": document.isbn,
        "doi": document.doi,
        "publisher": document.publisher,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "latest_job": _serialize_job(latest_job),
    }


def _latest_jobs_for_documents(db: Session, document_ids: list[UUID]) -> dict[UUID, ProcessingJob]:
    if not document_ids:
        return {}

    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.document_id.in_(document_ids))
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )

    latest: dict[UUID, ProcessingJob] = {}
    for job in jobs:
        latest.setdefault(job.document_id, job)
    return latest


@router.get("/projects/")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.name.asc()).all()
    counts = {
        project_id: count
        for project_id, count in (
            db.query(Document.project_id, func.count(Document.id))
            .filter(Document.project_id.isnot(None))
            .group_by(Document.project_id)
            .all()
        )
    }
    unassigned_count = db.query(Document.id).filter(Document.project_id.is_(None)).count()

    return {
        "projects": [
            _serialize_project(project, document_count=counts.get(project.id, 0))
            for project in projects
        ],
        "unassigned_count": unassigned_count,
    }


@router.post("/projects/")
def create_project(request: CreateProjectRequest, db: Session = Depends(get_db)):
    try:
        project, created = get_or_create_project(db, request.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(project)
    return {
        "project": _serialize_project(project),
        "created": created,
    }


@router.get("/documents/")
def list_documents(project_id: UUID | None = None, db: Session = Depends(get_db)):
    query = db.query(Document)
    if project_id is not None:
        query = query.filter(Document.project_id == project_id)

    documents = query.order_by(Document.created_at.desc()).all()
    document_ids = [document.id for document in documents]
    latest_jobs = _latest_jobs_for_documents(db, document_ids)

    project_ids = {document.project_id for document in documents if document.project_id}
    project_by_id = {
        project.id: project
        for project in db.query(Project).filter(Project.id.in_(project_ids)).all()
    } if project_ids else {}

    counts = Counter(document.project_id for document in documents if document.project_id)

    return {
        "documents": [
            _serialize_document(
                document,
                project=project_by_id.get(document.project_id),
                latest_job=latest_jobs.get(document.id),
            )
            for document in documents
        ],
        "project_counts": {str(project_id): count for project_id, count in counts.items()},
    }


@router.patch("/documents/{document_id}")
def update_document_project(
    document_id: UUID,
    request: UpdateDocumentProjectRequest,
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if request.project_id and request.project_name:
        raise HTTPException(status_code=400, detail="Choose project_id or project_name, not both")

    project = None
    if request.project_id is not None:
        project = db.get(Project, request.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        document.project_id = project.id
    elif request.project_name is not None:
        normalized = normalize_project_name(request.project_name)
        if not normalized:
            document.project_id = None
        else:
            project, _created = get_or_create_project(db, normalized)
            document.project_id = project.id
    else:
        raise HTTPException(status_code=400, detail="Provide project_id or project_name")

    db.commit()
    db.refresh(document)

    if document.project_id and project is None:
        project = db.get(Project, document.project_id)

    latest_job = _latest_jobs_for_documents(db, [document.id]).get(document.id)
    return {
        "document": _serialize_document(document, project=project, latest_job=latest_job),
    }


@router.delete("/documents/{document_id}")
def delete_document(document_id: UUID, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    latest_job = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.document_id == document.id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )
    if latest_job and latest_job.status in {ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Cannot delete a document while processing is active")

    image_rows = (
        db.query(ImageRecord)
        .filter(ImageRecord.source_pdf == document.filename)
        .all()
    )

    try:
        removed_upload = remove_object_if_exists(minio_client, UPLOAD_BUCKET, document.filename)
        removed_images = 0
        for image in image_rows:
            if remove_object_if_exists(minio_client, IMAGE_BUCKET, image.filename):
                removed_images += 1

        deleted_chunks = delete_by_filters("pdf_chunks", {"source_pdf": document.filename})
        deleted_captions = delete_by_filters("captions", {"source_pdf": document.filename})

        db.query(ImageRecord).filter(ImageRecord.source_pdf == document.filename).delete(
            synchronize_session=False
        )
        db.delete(document)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}") from exc

    return {
        "status": "deleted",
        "document_id": str(document.id),
        "filename": document.filename,
        "removed_upload": removed_upload,
        "removed_images": removed_images,
        "deleted_chunks": deleted_chunks,
        "deleted_captions": deleted_captions,
    }
