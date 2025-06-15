from elasticsearch import Elasticsearch
import os

es = Elasticsearch("http://elasticsearch:9200")

INDEX_NAME = "pdf_chunks"

def ensure_index():
    if not es.indices.exists(index=INDEX_NAME):
        es.indices.create(index=INDEX_NAME, mappings={
            "properties": {
                "filename": {"type": "keyword"},
                "chunk_size": {"type": "integer"},
                "chunk_index": {"type": "integer"},
                "pages": {"type": "integer"},
                "text": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1536,  # adjust to match your embedding model
                    "index": True,
                    "similarity": "cosine"
                }
            }
        })

def save_chunks_to_es(filename: str, chunks: list):
    ensure_index()

    for chunk in chunks:
        doc = {
            "filename": filename,
            "chunk_size": chunk.chunk_size,
            "chunk_index": chunk.chunk_index,
            "pages": chunk.pages,
            "text": chunk.text,
            "embedding": chunk.embedding
        }
        doc_id = f"{filename}_{chunk.chunk_size}_{chunk.chunk_index}"
        es.index(index=INDEX_NAME, id=doc_id, document=doc)
