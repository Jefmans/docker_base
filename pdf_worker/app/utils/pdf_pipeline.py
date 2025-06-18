import fitz  # PyMuPDF
from typing import List, Dict
from .image_caption_extractor import extract_images_and_captions
from .remove_captions import remove_captions_from_pages
from .clean_headers_footers import collect_repeating_lines, remove_repeating_lines
from .clean_page_numbers import detect_page_numbers, remove_page_numbers
from .text_chunker import chunk_text_with_overlap  # You must define or reuse this
from .embed_text_chunks import embed_and_store_chunks  # You must define or reuse this
from .embed_captions import embed_and_store_captions
from ..models.image_model import ImageMetadata


def process_pdf(file_path: str, book_id: str, source_pdf: str) -> None:
    """
    Full pipeline to process a PDF:
    - Extract and save images + captions
    - Clean headers, footers, page numbers
    - Chunk and embed cleaned text
    - Embed and store captions
    """
    print(f"📄 Starting processing for: {source_pdf}")

    # Load document and extract raw text
    doc = fitz.open(file_path)
    pages_text = [page.get_text().splitlines() for page in doc]

    # 1. Extract images and captions
    image_records: List[ImageMetadata] = extract_images_and_captions(doc, book_id, source_pdf)

    # 2. Remove caption text from pages
    pages_text = remove_captions_from_pages(pages_text, image_records)

    # 3. Detect and remove headers/footers
    header_set, footer_set = collect_repeating_lines(pages_text, n=5, lookahead=2, threshold=95)
    pages_text = remove_repeating_lines(pages_text, header_set, footer_set, n=5)

    # 4. Detect and remove page numbers
    page_number_sequences = detect_page_numbers(pages_text)
    pages_text = remove_page_numbers(pages_text, page_number_sequences)

    # 5. Recombine page texts for chunking
    page_text_map = {i: "\n".join(lines) for i, lines in enumerate(pages_text)}

    # 6. Chunk and embed text with page tracking
    chunks = chunk_text_with_overlap(page_text_map)  # include chunk size, page range, text
    embed_and_store_chunks(chunks, book_id)

    # 7. Embed and store captions
    embed_and_store_captions(image_records)

    print(f"✅ Finished processing: {source_pdf}")
