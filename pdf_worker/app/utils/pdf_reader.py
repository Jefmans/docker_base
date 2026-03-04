from langchain_community.document_loaders import PyMuPDFLoader

from app.utils.minio_utils import ensure_bucket_exists, get_minio_client


def read_pdf_from_minio(filename: str, bucket: str = "uploads") -> list:
    
    minio_client = get_minio_client()
    ensure_bucket_exists(minio_client, bucket)

    # Download file from MinIO
    local_path = f"/tmp/{filename}"
    minio_client.fget_object(bucket, filename, local_path)

    # Extract text using LangChain loader
    loader = PyMuPDFLoader(local_path)
    documents = loader.load()
    return documents 


def download_from_minio(filename: str, bucket: str = "uploads") -> list:
    
    minio_client = get_minio_client()
    ensure_bucket_exists(minio_client, bucket)

    # Download file from MinIO
    local_path = f"/tmp/{filename}"
    minio_client.fget_object(bucket, filename, local_path)

    return local_path




