from fastapi import APIRouter, Request, HTTPException
from uuid import uuid4
from app.utils.agent.search_chunks import search_chunks_for_query
from app.utils.agent.memory import save_session_chunks
from pydantic import BaseModel
import logging


logger = logging.getLogger(__name__)
logger.info("START")

router = APIRouter()

class AgentQueryRequest(BaseModel):
    query: str = "What is a black hole ?"
    top_k: int = 5

@router.post("/agent/query")
async def start_query_session(request: AgentQueryRequest):
    user_query = request.query
    logger.info("HELLO WORLD")

    if not user_query:
        raise HTTPException(status_code=400, detail="Missing 'query' in request body.")

    try:
        # Search chunks in Elastic
        top_chunks = search_chunks_for_query(user_query, top_k=request.top_k)

        # Save in a new session
        session_id = str(uuid4())
        save_session_chunks(session_id, user_query, top_chunks)

        return {
            "status": "success",
            "session_id": session_id,
            "query": user_query,
            "preview_chunks": top_chunks[:3]  # optional preview
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
