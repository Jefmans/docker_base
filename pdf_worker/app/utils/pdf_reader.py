from langchain.document_loaders import PyMuPDFLoader
from minio import Minio
import os

def read_pdf_from_minio(filename: str, bucket: str = "uploads") -> list:
    minio_client = Minio(
        "minio:9000",
        access_key="minioadmin",
        secret_key="minioadmin123",
        secure=False
    )

    # Download file from MinIO
    local_path = f"/tmp/{filename}"
    minio_client.fget_object(bucket, filename, local_path)

    # Extract text using LangChain loader
    loader = PyMuPDFLoader(local_path)
    documents = loader.load()
    return documents 
