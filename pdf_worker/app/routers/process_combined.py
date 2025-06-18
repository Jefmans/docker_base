### File: pdf_worker/app/routers/process_combined.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.pdf_pipeline import process_pdf
import os

router = APIRouter()

class PDFPipelineRequest(BaseModel):
    file_path: str
    book_id: str
    source_pdf: str

@router.post("/run")
def run_pipeline(request: PDFPipelineRequest):
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        process_pdf(
            file_path=request.file_path,
            book_id=request.book_id,
            source_pdf=request.source_pdf
        )
        return {"status": "success", "message": f"{request.source_pdf} processed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


### File: pdf_worker/app/main.py (update)

from fastapi import FastAPI
from app.routers import extract, health, upload, process_pdf, process_combined

app = FastAPI()

app.include_router(health.router)
app.include_router(upload.router)
app.include_router(extract.router)
app.include_router(process_pdf.router)
app.include_router(process_combined.router, prefix="/pipeline")


### Example Request (from backend or test script)

# POST http://localhost/pdfworker/pipeline/run
# JSON Body:
# {
#   "file_path": "/data/de_witte.pdf",
#   "book_id": "abc123",
#   "source_pdf": "de_witte.pdf"
# }
