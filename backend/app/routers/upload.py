from fastapi import APIRouter, UploadFile, File, HTTPException
from minio import Minio
import uuid

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
async def upload_file(file: UploadFile = File(...)):
    try:
        # Generate a unique file name
        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        content = await file.read()

        minio_client.put_object(
            bucket_name=BUCKET_NAME,
            object_name=unique_filename,
            data=content,
            length=len(content),
            content_type=file.content_type,
        )

        return {
            "filename": unique_filename,
            "link": f"/minio/uploads/{unique_filename}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
