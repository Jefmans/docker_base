from fastapi import FastAPI, HTTPException
from app.utils.pdf_reader import read_pdf_from_minio

app = FastAPI()
app = FastAPI(root_path="/pdfworker")

@app.post("/extract/{filename}")
def extract_pdf(filename: str):
    try:
        docs = read_pdf_from_minio(filename)
        return {
            "filename": filename,
            "chunks": len(docs),
            "preview": docs[0].page_content[:200] if docs else "No content"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
