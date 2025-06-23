from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from elasticsearch import Elasticsearch
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# === Configuration ===
ES_URL = os.getenv("ELASTICSEARCH_HOST", "http://elasticsearch:9200")
embedding_model = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=os.getenv("OPENAI_API_KEY"))
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
es = Elasticsearch(ES_URL)

CHUNK_INDEX = "pdf_chunks"
CAPTION_INDEX = "captions"

# === Schemas ===
class QueryRequest(BaseModel):
    query: str
    top_k: int = 10
    chunk_sizes: List[int] = [400, 800]
    use_llm: bool = True


class SearchResult(BaseModel):
    type: str  # "text" or "caption"
    text: str
    pages: List[int]
    score: float
    chunk_size: Optional[int] = None
    source_pdf: Optional[str] = None


class QueryResponse(BaseModel):
    results: List[SearchResult]
    answer: Optional[str] = None


# === Internal Logic ===
def search_index(index: str, query_vector: List[float], size: int = 10):
    return es.search(
        index=index,
        body={
            "size": size,
            "query": {
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                        "params": {"query_vector": query_vector}
                    }
                }
            }
        }
    )


# === Main Endpoint ===
@router.post("/query/", response_model=QueryResponse)
def query_semantic_search(req: QueryRequest):
    try:
        # Step 1: Embed query
        query_vector = embedding_model.embed_query(req.query)

        # Step 2: Search text chunks (per size)
        results: List[SearchResult] = []
        for size in req.chunk_sizes:
            res = search_index(CHUNK_INDEX, query_vector, size=req.top_k)
            for hit in res["hits"]["hits"]:
                source = hit["_source"]
                results.append(SearchResult(
                    type="text",
                    text=source["text"],
                    pages=[source["pages"]] if isinstance(source["pages"], int) else source["pages"],
                    score=hit["_score"],
                    chunk_size=source.get("chunk_size"),
                    source_pdf=source.get("filename")
                ))

        # Step 3: Search captions
        caption_hits = search_index(CAPTION_INDEX, query_vector, size=req.top_k)
        for hit in caption_hits["hits"]["hits"]:
            source = hit["_source"]
            results.append(SearchResult(
                type="caption",
                text=source["caption"],
                pages=[source["page_number"]],
                score=hit["_score"],
                source_pdf=source.get("source_pdf")
            ))

        # Step 4: Sort and trim
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        top_hits = sorted_results[:req.top_k]

        # Step 5: Generate LLM answer (optional)
        answer = None
        if req.use_llm:
            context = "\n\n".join([f"[Page {','.join(map(str, r.pages))}]\n{r.text}" for r in top_hits])
            prompt = f"""Answer the following question based only on the provided context. Mention page numbers where appropriate.

                            Question: {req.query}

                            Context:
                            {context}
                    """
            try:
                answer = llm.invoke(prompt).content
            except Exception as e:
                logger.warning(f"LLM failed: {e}")
                answer = "LLM failed to generate an answer."

        return QueryResponse(results=top_hits, answer=answer)

    except Exception as e:
        logger.error(f"❌ Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
