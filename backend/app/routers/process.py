import uuid

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.db import Document, SessionLocal, get_db
from app.schemas import ImageMetadata
from app.utils.save_images import save_image_metadata_list


router = APIRouter()

PDF_WORKER_URL = "http://pdf_worker:8000"


@router.post("/process/metadata/{filename}")
def process_metadata(filename: str):
    try:
        response = requests.post(f"{PDF_WORKER_URL}/metadata/{filename}")
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Metadata extraction failed")
        metadata = response.json()

        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.filename == filename).first()
            if doc is None:
                doc = Document(id=uuid.uuid4(), filename=filename)
                db.add(doc)

            doc.title = metadata["title"]
            doc.year = metadata["year"]
            doc.type = metadata["type"]
            doc.topic = metadata["topic"]
            doc.authors = metadata.get("authors")
            doc.isbn = metadata.get("isbn")
            doc.doi = metadata.get("doi")
            doc.publisher = metadata.get("publisher")
            db.commit()
        finally:
            db.close()

        return {
            "status": "success",
            "filename": filename,
            "title": metadata["title"],
            "year": metadata["year"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process/images/{filename}")
def process_images_and_save(filename: str, db: Session = Depends(get_db)):
    try:
        response = requests.post(f"{PDF_WORKER_URL}/images/{filename}")
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="pdf_worker error: " + response.text)

        image_data = response.json()
        metadata_list = [ImageMetadata(**entry) for entry in image_data]

        save_image_metadata_list(db, metadata_list)
        db.commit()

        return {
            "status": "success",
            "count": len(metadata_list),
            "saved": [meta.filename for meta in metadata_list],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
