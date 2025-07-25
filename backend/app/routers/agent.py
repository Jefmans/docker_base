from fastapi import APIRouter, Request, HTTPException
from uuid import uuid4
from app.utils.agent.search_chunks import search_chunks_for_query
from app.utils.agent.memory import save_session_chunks

router = APIRouter()

@router.post("/agent/query")
async def start_query_session(request: Request):
    body = await request.json()
    user_query = body.get("query", "")

    if not user_query:
        raise HTTPException(status_code=400, detail="Missing 'query' in request body.")

    try:
        # Search chunks in Elastic
        top_chunks = search_chunks_for_query(user_query, top_k=100)

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
