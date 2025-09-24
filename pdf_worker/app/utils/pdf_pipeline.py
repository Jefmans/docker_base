import fitz  # PyMuPDF
from typing import List
from app.utils.image_extraction import process_images_and_captions
from app.utils.cleaning.header_footer import collect_repeating_lines, remove_repeating_lines
from app.utils.cleaning.page_numbers import detect_page_numbers, remove_page_numbers
from app.utils.text_chunker import chunk_text
from app.utils.embedding import embed_chunks_streaming
from app.utils.embed_captions import embed_and_store_captions
from app.utils.es import save_chunks_to_es
from app.models import ImageMetadata
from app.utils.cleaning.clean_text_pipeline import clean_document_text



import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_pdf(file_path: str, book_id: str, source_pdf: str):
    print(f"📘 Starting full processing for: {source_pdf}")

    # Step 1: Cleaned full-page text using centralized logic
    cleaned_pages = clean_document_text(file_path)

    # Step 2: Extract and save images + captions
    doc = fitz.open(file_path)
    page_range = list(range(len(doc)))  # full document
    image_records: List[ImageMetadata] = process_images_and_captions(
        pdf_path=file_path,
        page_range=page_range,
        book_id=book_id
    )

    # Step 3: Remove caption lines from cleaned text
    for img in image_records:
        if img.caption.strip():
            page_idx = img.page_number - 1
            if 0 <= page_idx < len(cleaned_pages):
                cleaned_pages[page_idx] = "\n".join([
                    line for line in cleaned_pages[page_idx].splitlines()
                    if img.caption.strip() not in line.strip()
                ])

    # Step 4: Chunk the cleaned text
    # chunks = chunk_text(cleaned_pages, chunk_sizes=[200, 400, 800, 1600])
    chunks = chunk_text(cleaned_pages, chunk_sizes=[400, 1600])
    logger.info(f"🔖 Total chunks created: {len(chunks)}")

    # Step 5: Embed and save chunks
    embed_chunks_streaming(
        chunks,
        save_fn=lambda batch: save_chunks_to_es(source_pdf, batch)
    )

    # Step 6: Embed and store captions
    embed_and_store_captions(image_records)


    chunks_count = len(chunks)
    captions_indexed = len([r for r in image_records if r.caption and r.caption.strip()])
    print(f"✅ Finished processing: {source_pdf}")
    return {
        "pages": len(cleaned_pages),
        "chunks_indexed": chunks_count,
        "captions_indexed": captions_indexed
        }    

