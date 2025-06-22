from fastapi import FastAPI, HTTPException
from app.utils.pdf_reader import read_pdf_from_minio, download_from_minio

from app.utils.metadata import get_doc_info
# from app.utils.image_extraction import extract_images_and_captions  # to implement
from app.models import DocumentMetadata, ImageMetadata

from typing import Optional, List
from dataclasses import dataclass, asdict
from app.utils.image_extraction import process_images_and_captions
# import fitz  # PyMuPDF
from app.utils.cleaning.clean_text_pipeline import clean_document_text
# from app.utils.text_chunker import chunk_text


# from app.utils.cleaning.clean_text_pipeline import clean_document_text
from app.utils.text_chunker import chunk_text
# from app.utils.embedding import embed_chunks
from app.models import TextChunkEmbedding
from app.utils.es import save_chunks_to_es



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


# @app.post("/images/{filename}", response_model=List[ImageMetadata])
# def extract_images(filename: str):
#     try:
#         return extract_images_and_captions(filename)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

@app.post("/images/{filename}", response_model=List[ImageMetadata])
def extract_images(filename: str):
    try:
        local_path = download_from_minio(filename)
        # doc = fitz.open(local_path)
        # page_range = list(range(len(doc)))  # Process all pages; change if needed
        page_range=(38, 55, 56, 57)
        return process_images_and_captions(local_path, page_range, book_id=filename.split("_")[0])
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
            "page_count": len(set(p for chunk in chunks for p in chunk["pages"]))
        }


    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/embed_chunks/{filename}", response_model=List[TextChunkEmbedding])
def process_clean_embed_chunks(filename: str):
    try:
        local_path = download_from_minio(filename)

        # Step 1: Clean
        cleaned_pages = clean_document_text(local_path)

        # Step 2: Chunk
        chunks = chunk_text(cleaned_pages, chunk_sizes=[200, 400, 800, 1600])

        # Step 3: Embed
        embedded = embed_chunks(chunks)

        # ✅ Step 4: Save to ES
        save_chunks_to_es(filename, embedded)

        return embedded

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from app.utils.pdf_pipeline import process_pdf

@app.post("/process/full/{filename}")
def full_pdf_pipeline(filename: str):
    try:
        local_path = download_from_minio(filename)
        book_id = filename.split("_")[0]
        process_pdf(local_path, book_id, filename)
        return {
            "status": "✅ done",
            "filename": filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
