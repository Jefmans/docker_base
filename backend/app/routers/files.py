from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from minio import Minio
import uuid, io

router = APIRouter(prefix="/files", tags=["files"])

minio_client = Minio("minio:9000", access_key="minioadmin", secret_key="minioadmin123", secure=False)
BUCKET_NAME = "uploads"

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int

@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    try:
        file_id = f"{uuid.uuid4()}_{file.filename}"
        content = await file.read()
        stream = io.BytesIO(content)
        minio_client.put_object(BUCKET_NAME, file_id, stream, len(content), content_type=file.content_type)
        return UploadResponse(file_id=file_id, filename=file.filename, size=len(content))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
