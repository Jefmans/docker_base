from fastapi import APIRouter, HTTPException
from minio import Minio
import requests
import io

router = APIRouter()

MINIO_BUCKET = "uploads"

minio_client = Minio(
    "minio:9000",
    access_key="minioadmin",
    secret_key="minioadmin123",
    secure=False
)

UNSTRUCTURED_API_URL = "http://unstructured:8000/general/v0/general"

@router.post("/extract/")
def extract_text(filename: str):
    try:
        # Step 1: Get file from MinIO
        response = minio_client.get_object(MINIO_BUCKET, filename)
        file_data = response.read()
        file_stream = io.BytesIO(file_data)

        # Step 2: Send file to unstructured API
        files = {"files": (filename, file_stream)}
        res = requests.post(UNSTRUCTURED_API_URL, files=files)

        if res.status_code != 200:
            raise Exception(res.text)

        elements = res.json()

        # Step 3: Join content into single text block
        text = "\n".join(e.get("text", "") for e in elements if e.get("text"))

        # Optional: Save to disk or return
        return {
            "filename": filename,
            "extracted_characters": len(text),
            "preview": text[:500]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
