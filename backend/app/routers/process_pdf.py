from fastapi import APIRouter, HTTPException
from app.utils.pdf_reader import read_pdf_from_minio

router = APIRouter()

@router.post("/process/{filename}")
def process_file(filename: str):
    try:
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF supported for now")

        docs = read_pdf_from_minio(filename)
        return {
            "filename": filename,
            "chunks": len(docs),
            "preview": docs[0].page_content[:200] if docs else "No content"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
