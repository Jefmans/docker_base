import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langchain_community.vectorstores import ElasticsearchStore
from langchain_openai import OpenAIEmbeddings
from elasticsearch import Elasticsearch

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
    index_name="your-index-name",  # Replace with your real index
    embedding=embedding_model,
)

# FastAPI router
router = APIRouter()

# Request model
class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

# Route
@router.post("/query/")
async def query(request: QueryRequest):
    try:
        results = vectorstore.similarity_search(
            query=request.query,
            k=request.top_k
        )
        return {"results": [r.page_content for r in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"❌ Query error: {str(e)}")
