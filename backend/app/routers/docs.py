# app/routers/docs.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from uuid import uuid4, UUID
import requests
from sqlalchemy.orm import Session
from app.db.db import SessionLocal, Document

router = APIRouter(prefix="/docs", tags=["documents"])

PDF_WORKER_URL = "http://pdf_worker:8000/pdfworker"

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

# ---------- helpers ----------
def _get_or_create_document(db: Session, filename: str, meta: dict) -> UUID:
    existing = db.query(Document).filter(Document.filename == filename).first()
    if existing:
        # update in case metadata improved
        existing.title = meta.get("title")
        existing.year = meta.get("year")
        existing.type = meta.get("type")
        existing.topic = meta.get("topic")
        existing.authors = meta.get("authors")
        existing.isbn = meta.get("isbn")
        existing.doi = meta.get("doi")
        existing.publisher = meta.get("publisher")
        db.commit()
        return existing.id

    # create new
    new_id = uuid4()
    doc = Document(
        id=new_id,
        filename=filename,
        title=meta.get("title"),
        year=meta.get("year"),
        type=meta.get("type"),
        topic=meta.get("topic"),
        authors=meta.get("authors"),
        isbn=meta.get("isbn"),
        doi=meta.get("doi"),
        publisher=meta.get("publisher"),
    )
    db.add(doc)
    db.commit()
    return doc.id

# ---------- route ----------
@router.post("/{file_id}/prepare", response_model=PrepareResponse)
def prepare_document(file_id: str):
    """
    1) Fetch structured metadata from pdf_worker.
    2) Upsert Document in Postgres.
    """
    # 1) metadata
    meta_res = requests.post(f"{PDF_WORKER_URL}/metadata/{file_id}")
    if meta_res.status_code != 200:
        raise HTTPException(status_code=500, detail=f"metadata error: {meta_res.text}")
    metadata = meta_res.json()

    # 2) upsert Document
    db = SessionLocal()
    try:
        doc_id = str(_get_or_create_document(db, filename=file_id, meta=metadata))
    finally:
        db.close()

    return PrepareResponse(
        doc_id=doc_id,
        filename=file_id,
        metadata=DocumentMetadata(**metadata),
    )
