from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.db import get_db
from app.db.models.document_orm import Document
from app.db.models.project_orm import Project
from app.utils.vectorstore import get_vectorstore


vectorstore = get_vectorstore(index_name="pdf_chunks")
caption_store = get_vectorstore(index_name="captions")

# FastAPI router
router = APIRouter()

# Request model
class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    document_id: UUID | None = None
    project_id: UUID | None = None


@router.post("/query/")
async def query(request: QueryRequest, db: Session = Depends(get_db)):
    try:
        if request.document_id and request.project_id:
            raise HTTPException(status_code=400, detail="Choose document_id or project_id, not both")

        filters = None
        scope = {"mode": "all", "document_id": None, "project_id": None}

        if request.document_id:
            document = db.get(Document, request.document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found")
            filters = {"source_pdf": document.filename}
            scope = {
                "mode": "document",
                "document_id": str(document.id),
                "project_id": str(document.project_id) if document.project_id else None,
            }
        elif request.project_id:
            project = db.get(Project, request.project_id)
            if project is None:
                raise HTTPException(status_code=404, detail="Project not found")

            filenames = [
                filename
                for (filename,) in (
                    db.query(Document.filename)
                    .filter(Document.project_id == project.id)
                    .all()
                )
            ]
            if not filenames:
                return {
                    "scope": {
                        "mode": "project",
                        "document_id": None,
                        "project_id": str(project.id),
                    },
                    "text_chunks": [],
                    "captions": [],
                }

            filters = {"source_pdf": filenames}
            scope = {
                "mode": "project",
                "document_id": None,
                "project_id": str(project.id),
            }

        text_results = vectorstore.similarity_search_with_score(
            query=request.query,
            k=request.top_k,
            filters=filters,
        )
        caption_results = caption_store.similarity_search_with_score(
            query=request.query,
            k=request.top_k,
            filters=filters,
        )

        return {
            "scope": scope,
            "text_chunks": [
                {
                    "text": doc.page_content, 
                    "score": score, 
                    "metadata": dict(doc.metadata or {})
                }
            for (doc, score) in text_results
            ],
            "captions": [
                {
                "text": doc.page_content,
                "score": score,
                "metadata": dict(doc.metadata or {})
                }
            for (doc, score) in caption_results
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Query error: {str(e)}")


