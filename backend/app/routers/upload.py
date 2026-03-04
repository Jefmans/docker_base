from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from minio import Minio
import uuid
import io
from sqlalchemy.orm import Session

from app.db.db import get_db
from app.db.models.document_orm import Document
from app.repositories.job_repo import create_processing_job
from app.repositories.project_repo import get_or_create_project, normalize_project_name
from app.utils.minio_utils import ensure_bucket_exists, get_minio_client

router = APIRouter()

# Connect to MinIO
minio_client = get_minio_client()

BUCKET_NAME = "uploads"

@router.post("/upload/")
async def upload_file(
    file: UploadFile = File(...),
    project_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    try:
        ensure_bucket_exists(minio_client, BUCKET_NAME)

        # Generate a unique file name
        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        content = await file.read()

        # Wrap bytes in a stream
        stream = io.BytesIO(content)        

        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=unique_filename,
            data=stream,
            length=len(content),
            content_type=file.content_type,
        )

        project = None
        normalized_project_name = normalize_project_name(project_name)
        if normalized_project_name:
            project, _created = get_or_create_project(db, normalized_project_name)

        document = Document(
            filename=unique_filename,
            project_id=project.id if project else None,
        )
        db.add(document)
        db.flush()

        job = create_processing_job(
            db,
            document.id,
            payload={"filename": unique_filename},
        )
        db.commit()

        return {
            "document_id": str(document.id),
            "job_id": str(job.id),
            "filename": unique_filename,
            "display_name": file.filename,
            "project_id": str(project.id) if project else None,
            "project_name": project.name if project else None,
            "status": job.status.value,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
