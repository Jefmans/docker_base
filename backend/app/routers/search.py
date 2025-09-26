from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.utils.vectorstore import get_vectorstore

router = APIRouter(tags=["search"])

class SearchScope(BaseModel):
    doc_ids: Optional[List[str]] = None
    include_captions: Optional[bool] = True

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    scope: Optional[SearchScope] = None

class SourceMeta(BaseModel):
    doc_id: Optional[str] = None
    title: Optional[str] = None
    page: Optional[int] = None
    image_filename: Optional[str] = None

class SearchHit(BaseModel):
    text: str
    score: float
    source: SourceMeta

class SearchResponse(BaseModel):
    text_chunks: List[SearchHit]
    captions: List[SearchHit]

@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    try:
        text_vs   = get_vectorstore(index_name="pdf_chunks")
        caption_vs = get_vectorstore(index_name="captions")

        # Optional filter by doc_ids (depends on how you index metadata in ES)
        # If you store doc_id in metadata, you can pass a filter in your vectorstore impl.

        text_results = text_vs.similarity_search_with_score(req.query, k=req.top_k)
        cap_results  = caption_vs.similarity_search_with_score(req.query, k=req.top_k) if (not req.scope or req.scope.include_captions) else []

        def pack(items):
            out = []
            for (doc, score) in items:
                md = dict(doc.metadata or {})
                out.append(SearchHit(
                    text=doc.page_content,
                    score=float(score),
                    source=SourceMeta(
                        doc_id=md.get("document_id") or md.get("doc_id"),
                        title=md.get("title"),
                        page=md.get("page"),
                        image_filename=md.get("filename") if md.get("kind") == "image" else None
                    )
                ))
            return out

        return SearchResponse(text_chunks=pack(text_results), captions=pack(cap_results))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {e}")
