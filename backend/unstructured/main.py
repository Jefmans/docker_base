from fastapi import FastAPI, UploadFile, File
from unstructured.partition.pdf import partition_pdf
import fitz
import io

app = FastAPI()

@app.post("/parse/")
async def parse_file(file: UploadFile = File(...)):
    content = await file.read()
    doc = fitz.open(stream=content, filetype="pdf")
    new_doc = fitz.open()

    for i in range(min(5, len(doc))):
        new_doc.insert_pdf(doc, from_page=i, to_page=i)

    buf = io.BytesIO()
    new_doc.save(buf)
    buf.seek(0)
    doc.close()
    new_doc.close()

    elements = partition_pdf(file=buf)
    text = "\n".join(e.text for e in elements if e.text)

    return {
        "char_count": len(text),
        "preview": text[:500]
    }
