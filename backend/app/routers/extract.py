from fastapi import APIRouter, HTTPException
from minio import Minio
import requests
import io
import fitz  # PyMuPDF


router = APIRouter()

MINIO_BUCKET = "uploads"

minio_client = Minio(
    "minio:9000",
    access_key="minioadmin",
    secret_key="minioadmin123",
    secure=False
)

UNSTRUCTURED_API_URL = "http://95.216.215.141:8000/general/v0/general"

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



def extract_first_5_pages(pdf_bytes: bytes) -> io.BytesIO:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        new_doc = fitz.open()
        for i in range(min(5, len(doc))):
            new_doc.insert_pdf(doc, from_page=i, to_page=i)

        output = io.BytesIO()
        new_doc.save(output)
        output.seek(0)
        return output
    except Exception as e:
        raise RuntimeError(f"PDF processing failed: {e}")


@router.post("/extract/preview/")
def extract_preview(filename: str):
    try:
        # Step 1: Get file from MinIO
        response = minio_client.get_object(MINIO_BUCKET, filename)
        file_data = response.read()

        # Step 2: Trim PDF to 5 pages
        short_pdf = extract_first_5_pages(file_data)

        # Step 3: Send to unstructured API
        files = {"files": (filename, short_pdf, "application/pdf")}
        res = requests.post(UNSTRUCTURED_API_URL, files=files)

        if res.status_code != 200:
            raise Exception(res.text)

        elements = res.json()
        text = "\n".join(e.get("text", "") for e in elements if e.get("text"))

        return {
            "filename": filename,
            "pages_processed": 5,
            "extracted_characters": len(text),
            "preview": text[:500]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))