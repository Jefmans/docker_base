from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.db import get_db
from app.utils.document_scope import resolve_research_scope
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
        try:
            scope = resolve_research_scope(
                db,
                document_id=request.document_id,
                project_id=request.project_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if scope.mode == "project" and not scope.filenames:
            return {
                "scope": scope.model_dump(),
                "text_chunks": [],
                "captions": [],
            }

        text_results = vectorstore.similarity_search_with_score(
            query=request.query,
            k=request.top_k,
            filters=scope.search_filters(),
        )
        caption_results = caption_store.similarity_search_with_score(
            query=request.query,
            k=request.top_k,
            filters=scope.search_filters(),
        )

        return {
            "scope": scope.model_dump(),
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


