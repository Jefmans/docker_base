from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from minio import Minio
import uuid
import io
from sqlalchemy.orm import Session

from app.db.db import get_db
from app.db.models.document_orm import Document
from app.repositories.job_repo import create_processing_job

router = APIRouter()

# Connect to MinIO
minio_client = Minio(
    "minio:9000",  # Container name + default port
    access_key="minioadmin",
    secret_key="minioadmin123",
    secure=False
)

BUCKET_NAME = "uploads"

@router.post("/upload/")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
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

        document = Document(filename=unique_filename)
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
            "status": job.status.value,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
