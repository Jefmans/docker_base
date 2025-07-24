from typing import List
from elasticsearch import Elasticsearch, helpers
from langchain.embeddings import OpenAIEmbeddings
from app.models import ImageMetadata  # Adjust import as needed
import os
from urllib.parse import quote


# Initialize embedding model
embedding_model = OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Elasticsearch client
es = Elasticsearch(hosts=[os.getenv("ELASTICSEARCH_HOST", "http://elasticsearch:9200")])

def embed_and_store_captions(records: List[ImageMetadata], index_name: str = "captions"):
    """
    Embed caption texts from ImageMetadata list and index them in Elasticsearch.
    """
    # Filter records that have a caption
    valid_records = [r for r in records if r.caption and r.caption.strip()]
    if not valid_records:
        print("No valid captions to embed.")
        return

    texts = [r.caption for r in valid_records]
    embeddings = embedding_model.embed_documents(texts)

    payloads = []
    for record, embedding in zip(valid_records, embeddings):
        doc_id = f"{record.book_id}_{record.page_number}_{record.xref}"
        # filename = record.filename

        # minio_path = f"/minio/images/{quote(filename)}"  # or construct full URL if frontend needed

        payloads.append({
            "_index": index_name,
            "_id": doc_id,
            "_source": {
                "book_id": record.book_id,
                "page_number": record.page_number,
                "text": record.caption,
                # "embedding": embedding,
                "vector": embedding,
                "source_pdf": record.source_pdf,
                "xref": record.xref,
                "filename": record.filename,
            }
        })

    helpers.bulk(es, payloads)
    print(f"✅ Embedded and indexed {len(payloads)} captions into '{index_name}'")
