from fastapi import APIRouter, HTTPException
import requests
import uuid
from app.db import SessionLocal, Document

router = APIRouter()

PDF_WORKER_URL = "http://pdf_worker:8000/pdfworker"

@router.post("/process/metadata/{filename}")
def process_metadata(filename: str):
    try:
        # Step 1: Extract metadata via worker
        response = requests.post(f"{PDF_WORKER_URL}/metadata/{filename}")
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Metadata extraction failed")
        metadata = response.json()

        # Step 2: Store in Postgres
        db = SessionLocal()
        doc = Document(
            id=uuid.uuid4(),
            filename=filename,
            title=metadata["title"],
            year=metadata["year"],
            type=metadata["type"],
            topic=metadata["topic"],
            authors=metadata.get("authors"),
            isbn=metadata.get("isbn"),
            doi=metadata.get("doi"),
            publisher=metadata.get("publisher")
        )
        db.add(doc)
        db.commit()
        db.close()

        return {
            "status": "success",
            "filename": filename,
            "title": metadata["title"],
            "year": metadata["year"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
