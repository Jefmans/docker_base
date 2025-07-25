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


from app.utils.agent.memory import get_session_chunks
from app.utils.agent.subquestions import generate_subquestions_from_chunks

@router.post("/agent/subquestions")
def generate_subquestions(session_id: str):
    session = get_session_chunks(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    query = session["query"]
    chunks = session["chunks"]
    subq = generate_subquestions_from_chunks(chunks, query)

    return {
        "session_id": session_id,
        "query": query,
        "subquestions": subq
    }


from app.utils.agent.outline import generate_outline

@router.post("/agent/outline")
def create_outline(session_id: str):
    session = get_session_chunks(session_id)
    if not session or "query" not in session or "chunks" not in session:
        raise HTTPException(status_code=404, detail="Session not found")

    subq = generate_subquestions_from_chunks(session["chunks"], session["query"])
    outline = generate_outline(subq, session["query"])

    return {
        "session_id": session_id,
        "outline": outline.dict()  # FastAPI handles this gracefully
    }


from app.utils.agent.writer import write_section
from app.utils.agent.memory import save_section
from app.utils.agent.outline import Outline  # Pydantic model
import json

@router.post("/agent/section/{section_id}")
def write_section_by_id(session_id: str, section_id: int):
    session = get_session_chunks(session_id)
    print(session)
    if not session or "outline" not in session:
        raise HTTPException(status_code=404, detail="Session or outline missing")

    outline_data = session["outline"]
    if isinstance(outline_data, str):
        outline_data = json.loads(outline_data)  # support old string-based storage

    try:
        outline = Outline(**outline_data)
        section = outline.sections[section_id]
        generated_text = write_section(section.dict())
        save_section(session_id, section_id, generated_text)

        return {
            "session_id": session_id,
            "section_id": section_id,
            "heading": section.heading,
            "text": generated_text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
