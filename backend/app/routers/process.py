from fastapi import APIRouter, HTTPException, Depends
import requests
import uuid
from sqlalchemy.orm import Session
from app.db import SessionLocal, get_db
from app.utils.save_images import save_image_metadata_list
from app.db import Document, ImageRecord
from pydantic import BaseModel
from typing import List, Optional
from app.schemas import ImageMetadata  # ✅ This uses the new schema


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






@router.post("/process/images/{filename}")
def process_images_and_save(filename: str, db: Session = Depends(get_db)):
    try:
        # 1. Get image metadata from pdf_worker
        response = requests.post(f"http://pdf_worker:8000/images/{filename}")
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="pdf_worker error: " + response.text)

        image_data = response.json()

        # 2. Validate with Pydantic schema
        metadata_list = [ImageMetadata(**entry) for entry in image_data]

        # 3. Save to PostgreSQL using ORM
        save_image_metadata_list(db, metadata_list)

        return {
            "status": "success",
            "count": len(metadata_list),
            "saved": [meta.filename for meta in metadata_list]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





