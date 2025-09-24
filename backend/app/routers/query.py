import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
# from langchain_community.vectorstores import ElasticsearchStore
from langchain_openai import OpenAIEmbeddings
from elasticsearch import Elasticsearch
from langchain_elasticsearch import ElasticsearchStore


# Elasticsearch connection
es = Elasticsearch("http://elasticsearch:9200")

# LangChain embedding model
embedding_model = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

# Vector store
vectorstore = ElasticsearchStore(
    es_connection=es,
    index_name="pdf_chunks",  # Replace with your real index
    embedding=embedding_model,
    vector_query_field='vector',
    query_field = 'text',
)

caption_store = ElasticsearchStore(
    es_connection=es,
    index_name="captions",
    embedding=embedding_model,
    vector_query_field='vector',
    query_field = 'text',    
)

# FastAPI router
router = APIRouter()

# Request model
class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

# Route
# @router.post("/query/")
# async def query(request: QueryRequest):
#     try:
#         results = vectorstore.similarity_search(
#             query=request.query,
#             k=request.top_k
#         )
#         return {"results": [r.page_content for r in results]}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"❌ Query error: {str(e)}")
@router.post("/query/")
async def query(request: QueryRequest):
    try:
        text_results = vectorstore.similarity_search_with_score(query=request.query, k=request.top_k)
        caption_results = caption_store.similarity_search_with_score(query=request.query, k=request.top_k)

        return {
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
                    # "caption": r.caption,
                    # "score": score,
                    # "metadata": r.metadata  # will include minio_path
                    "r" : r
                }
                for r  in caption_results
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"❌ Query error: {str(e)}")


