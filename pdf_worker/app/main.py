from typing import List

import fitz
from fastapi import FastAPI, HTTPException

from app.models import DocumentMetadata, ImageMetadata, TextChunkEmbedding
from app.utils.cleaning.clean_text_pipeline import clean_document_text
from app.utils.embedding import embed_chunks
from app.utils.es import ensure_all_indices, save_chunks_to_es
from app.utils.image_extraction import process_images_and_captions
from app.utils.metadata import get_doc_info
from app.utils.pdf_pipeline import process_pdf
from app.utils.pdf_reader import download_from_minio, read_pdf_from_minio
from app.utils.text_chunker import chunk_text
from app.worker import start_worker_thread


app = FastAPI(root_path="/pdfworker")


@app.on_event("startup")
def _startup():
    ensure_all_indices()
    start_worker_thread()


@app.post("/extract/{filename}")
def extract_pdf(filename: str):
    try:
        docs = read_pdf_from_minio(filename)
        return {
            "filename": filename,
            "chunks": len(docs),
            "pages": [doc.page_content for doc in docs],
            "preview": docs[0].page_content[:200] if docs else "No content",
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
        local_path = download_from_minio(filename)
        doc = fitz.open(local_path)
        page_range = list(range(len(doc)))
        doc.close()
        return process_images_and_captions(
            local_path,
            page_range,
            book_id=filename.split("_", 1)[0],
            source_pdf=filename,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clean_chunks/{filename}")
def process_and_chunk_pdf(filename: str):
    try:
        local_path = download_from_minio(filename)
        cleaned_pages = clean_document_text(local_path)
        chunks = chunk_text(cleaned_pages, chunk_sizes=[200, 400, 800, 1600])

        return {
            "status": "success",
            "chunk_sizes": list(set(c["chunk_size"] for c in chunks)),
            "chunks": chunks,
            "page_count": len(set(p for chunk in chunks for p in chunk["pages"])),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/embed_chunks/{filename}", response_model=List[TextChunkEmbedding])
def process_clean_embed_chunks(filename: str):
    try:
        local_path = download_from_minio(filename)
        cleaned_pages = clean_document_text(local_path)
        chunks = chunk_text(cleaned_pages, chunk_sizes=[800, 1600])
        embedded = embed_chunks(chunks)
        save_chunks_to_es(filename, embedded, book_id=filename.split("_", 1)[0], source_pdf=filename)
        return embedded
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process/full/{filename}")
def full_pdf_pipeline(filename: str):
    try:
        local_path = download_from_minio(filename)
        book_id = filename.split("_", 1)[0]
        stats = process_pdf(local_path, book_id, filename) or {}
        return {
            "status": "success",
            "filename": filename,
            **stats,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
