from fastapi import FastAPI, HTTPException
from app.utils.pdf_reader import read_pdf_from_minio

from app.utils.metadata import get_doc_info
# from app.utils.image_extraction import extract_images_and_captions  # to implement
from app.models import DocumentMetadata, ImageMetadata

app = FastAPI(root_path="/pdfworker")

@app.post("/extract/{filename}")
def extract_pdf(filename: str):
    try:
        docs = read_pdf_from_minio(filename)
        return {
            "filename": filename,
            "chunks": len(docs),
            "pages": [doc.page_content for doc in docs],
            "preview": docs[0].page_content[:200] if docs else "No content"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/metadata/{filename}", response_model=DocumentMetadata)
def extract_metadata(filename: str):
    try:
        local_path = download_from_minio(filename)
        return get_doc_info(local_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/images/{filename}", response_model=List[ImageMetadata])
def extract_images(filename: str):
    try:
        return extract_images_and_captions(filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))