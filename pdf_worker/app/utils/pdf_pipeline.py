import fitz  # PyMuPDF
from typing import List
from app.utils.image_extraction import process_images_and_captions
from app.utils.cleaning.header_footer import collect_repeating_lines, remove_repeating_lines
from app.utils.cleaning.page_numbers import detect_page_numbers, remove_page_numbers
from app.utils.text_chunker import chunk_text
from app.utils.embedding import embed_chunks
from app.utils.embed_captions import embed_and_store_captions
from app.utils.es import save_chunks_to_es
from app.models import ImageMetadata


import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def process_pdf(file_path: str, book_id: str, source_pdf: str):
    print(f"📘 Starting full processing for: {source_pdf}")

    # Step 1: Load PDF
    doc = fitz.open(file_path)
    pages_text = [page.get_text().splitlines() for page in doc]
    # pages_text = [page.get_text().splitlines() for page in doc[59:62]]



    # Step 2: Extract and save images + captions
    page_range = list(range(len(doc)))  # You may restrict this if needed
    image_records: List[ImageMetadata] = process_images_and_captions(
        pdf_path=file_path,
        page_range=page_range,
        book_id=book_id
    )

    # Step 3: Remove caption lines from the text (by exact match per page)
    for img in image_records:
        if img.caption.strip():
            page_idx = img.page_number - 1
            if 0 <= page_idx < len(pages_text):
                pages_text[page_idx] = [
                    line for line in pages_text[page_idx]
                    if img.caption.strip() not in line.strip()
                ]

    # Step 4: Remove headers and footers
    logger.info(f"--- 1 ---")
    header_set, footer_set = collect_repeating_lines(pages_text, n=5, lookahead=2, threshold=95)
    pages_text = remove_repeating_lines(pages_text, header_set, footer_set, n=5)
    logger.info(f"--- 2 ---")
    # Step 5: Remove page numbers
    page_number_sequences = detect_page_numbers(pages_text)
    pages_text = remove_page_numbers(pages_text, page_number_sequences)
    logger.info(f"--- 3 ---")
    # Step 6: Normalize and chunk text
    cleaned_pages = ["\n".join(lines) for lines in pages_text]
    chunks = chunk_text(cleaned_pages, chunk_sizes=[200, 400, 800, 1600])
    # chunks = chunk_text(cleaned_pages, chunk_sizes=[400, 800])
    logger.info(f"--- 4 ---")
    # Step 7: Embed and save text chunks
    embedded_chunks = embed_chunks(chunks)
    save_chunks_to_es(source_pdf, embedded_chunks)
    logger.info(f"--- 5 ---")
    # Step 8: Embed and save captions
    embed_and_store_captions(image_records)

    print(f"✅ Finished processing: {source_pdf}")
