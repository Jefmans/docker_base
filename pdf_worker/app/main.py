from langchain.document_loaders import PyMuPDFLoader
from minio import Minio
import os

# Config
bucket = "uploads"
filename = os.getenv("PDF_NAME", "de_witte.pdf")

minio_client = Minio(
    "minio:9000",
    access_key="minioardmin",
    secret_key="minioadmin123",
    secure=False
)

# Download file
local_path = f"/tmp/{filename}"
minio_client.fget_object(bucket, filename, local_path)

# Load text from PDF
loader = PyMuPDFLoader(local_path)
documents = loader.load()

# Print preview
for doc in documents[:3]:  # limit to first 3 chunks
    print(f"Content (trimmed): {doc.page_content[:200]}")
