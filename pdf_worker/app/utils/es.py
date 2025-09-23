from elasticsearch import Elasticsearch
import os

es = Elasticsearch("http://elasticsearch:9200")

PDF_CHUNKS = "pdf_chunks"
CAPTIONS = "captions"

PDF_CHUNKS_MAPPING = {
    "properties": {
        "id":         {"type": "keyword"},
        "filename":   {"type": "keyword"},
        "chunk_size": {"type": "integer"},
        "chunk_index":{"type": "integer"},
        "pages":      {"type": "integer"},   # array<int> is fine
        "text":       {"type": "text"},
        "vector":     {
            "type": "dense_vector", 
            "dims": 1536, 
            "index": True, 
            "similarity": "cosine"
            }
    }
}

CAPTIONS_MAPPING = {
    "properties": {
        "book_id":    {"type": "keyword"},
        "source_pdf": {"type": "keyword"},
        "filename":   {"type": "keyword"},
        "page_number":{"type": "integer"},
        "xref":       {"type": "integer"},
        "text":       {"type": "text"},
        "vector":     {
            "type": "dense_vector", 
            "dims": 1536, 
            "index": True, 
            "similarity": "cosine"
            }
    }
}

def ensure_index(name: str, mapping: dict):
    if not es.indices.exists(index=name):
        es.indices.create(index=name, mappings=mapping)

def ensure_all_indices():
    ensure_index(PDF_CHUNKS, PDF_CHUNKS_MAPPING)
    ensure_index(CAPTIONS, CAPTIONS_MAPPING)


def save_chunks_to_es(filename: str, chunks: list):
    ensure_index(PDF_CHUNKS, PDF_CHUNKS_MAPPING)
    for chunk in chunks:
        doc_id = f"{filename}_{chunk.chunk_size}_{chunk.chunk_index}"
        doc = {
            "id": doc_id,
            "filename": filename,
            "chunk_size": chunk.chunk_size,
            "chunk_index": chunk.chunk_index,
            "pages": chunk.pages,
            "text": chunk.text,
            "vector": chunk.embedding,
        }
        es.index(index=PDF_CHUNKS, id=doc_id, document=doc)

