from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from uuid import uuid4
import requests
from app.db.db import SessionLocal, Document

router = APIRouter(prefix="/docs", tags=["documents"])

PDF_WORKER_URL = "http://pdf_worker:8000/pdfworker"
UNSTRUCTURED_API_URL = "http://unstructured_custom:8000/parse/"

# ===== Schemas =====
class DocumentMetadata(BaseModel):
    title: Optional[str] = None
    year: Optional[int] = None
    type: Optional[str] = None
    topic: Optional[str] = None
    authors: Optional[List[str]] = None
    isbn: Optional[str] = None
    doi: Optional[str] = None
    publisher: Optional[str] = None

class PrepareResponse(BaseModel):
    doc_id: str
    filename: str
    metadata: DocumentMetadata
    preview: dict  # { pages_processed, chars, sample? }

class JobResponse(BaseModel):
    job_id: str
    status: str
    progress: Optional[int] = None
    message: Optional[str] = None
    result: Optional[dict] = None

# ===== Upload→Prepare (metadata + 5-page preview) =====
@router.post("/{file_id}/prepare", response_model=PrepareResponse)
def prepare_document(file_id: str):
    # 1) metadata via pdf_worker
    meta_res = requests.post(f"{PDF_WORKER_URL}/metadata/{file_id}")
    if meta_res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"metadata error: {meta_res.text}")
    metadata = meta_res.json()

    # 2) save Document row
    db = SessionLocal()
    try:
        doc_id = str(uuid4())
        doc = Document(
            id=doc_id, filename=file_id,
            title=metadata.get("title"),
            year=metadata.get("year"),
            type=metadata.get("type"),
            topic=metadata.get("topic"),
            authors=metadata.get("authors"),
            isbn=metadata.get("isbn"),
            doi=metadata.get("doi"),
            publisher=metadata.get("publisher"),
        )
        db.add(doc); db.commit()
    finally:
        db.close()

    # 3) preview (first 5 pages) via unstructured
    prev = requests.post("http://backend:8000/backend/extract/preview/", params={"filename": file_id})
    if prev.status_code != 200:
        raise HTTPException(status_code=500, detail=f"preview error: {prev.text}")

    preview = prev.json()
    return PrepareResponse(doc_id=doc_id, filename=file_id, metadata=DocumentMetadata(**metadata), preview=preview)

# ===== Process (clean→chunk→embed) =====
@router.post("/{doc_id}/process", response_model=JobResponse)
def process_document(doc_id: str):
    """
    Option A (simple): run sync and return done.
    Option B (scalable): enqueue a job & return job_id.
    Here: return a pseudo job and perform sync for now.
    """
    # call your existing internal pipeline (images, captions, text clean, chunk, embed)
    # e.g. requests.post(f"{PDF_WORKER_URL}/process/{doc_id}") or local service function
    # For now, pretend success:
    return JobResponse(job_id=f"proc-{doc_id}", status="done", progress=100, result={"chunks": "N/A", "captions": "N/A"})

# ===== Job status (placeholder) =====
@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    # If you add Celery/Redis, wire real status here
    return JobResponse(job_id=job_id, status="done", progress=100)
