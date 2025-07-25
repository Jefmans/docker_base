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

from app.utils.agent.memory import save_session_chunks

...

@router.post("/agent/outline")
def create_outline(session_id: str):
    session = get_session_chunks(session_id)
    if not session or "query" not in session or "chunks" not in session:
        raise HTTPException(status_code=404, detail="Session not found")

    subq = generate_subquestions_from_chunks(session["chunks"], session["query"])
    outline = generate_outline(subq, session["query"])

    # ✅ Save it!
    session["outline"] = outline.dict()
    save_session_chunks(session_id, session["query"], session["chunks"])  # resave session with outline
    print(session)

    return {
        "session_id": session_id,
        "outline": outline.dict()
    }



from app.utils.agent.writer import write_section
from app.utils.agent.memory import save_section
from app.utils.agent.outline import Outline  # Pydantic model
import json

@router.post("/agent/section/{section_id}")
def write_section_by_id(session_id: str, section_id: int):
    session = get_session_chunks(session_id)
    # print(session)
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


from app.utils.agent.finalizer import finalize_article

@router.post("/agent/article/finalize")
def finalize_article_route(session_id: str):
    session = get_session_chunks(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Make sure session includes the sections
    session["session_id"] = session_id  # Needed for get_all_sections
    article_text = finalize_article(session)

    return {
        "session_id": session_id,
        "title": session.get("outline", {}).get("title", "Untitled Article"),
        "article": article_text
    }


from fastapi import BackgroundTasks
from app.utils.agent.search_chunks import search_chunks_for_query
from app.utils.agent.memory import save_session_chunks, get_session_chunks, save_section
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.utils.agent.outline import generate_outline, Outline
from app.utils.agent.writer import write_section
from app.utils.agent.finalizer import finalize_article
from uuid import uuid4

@router.post("/agent/full_run")
def full_run(request: AgentQueryRequest, background_tasks: BackgroundTasks = None):
    try:
        # STEP 1: Query & retrieve chunks
        session_id = str(uuid4())
        top_chunks = search_chunks_for_query(request.query, top_k=request.top_k)
        save_session_chunks(session_id, request.query, top_chunks)

        # STEP 2: Subquestions
        subq = generate_subquestions_from_chunks(top_chunks, request.query)

        # STEP 3: Outline
        outline = generate_outline(subq, request.query)
        session = get_session_chunks(session_id)
        session["outline"] = outline.dict()

        # STEP 4: Write each section
        section_outputs = []
        for i, section in enumerate(outline.sections):
            text = write_section(section.dict())
            save_section(session_id, i, text)
            section_outputs.append({
                "heading": section.heading,
                "text": text
            })

        # STEP 5: Finalize article
        session["session_id"] = session_id
        article = finalize_article(session)

        return {
            "session_id": session_id,
            "title": outline.title,
            "abstract": outline.abstract,
            "outline": [s.dict() for s in outline.sections],
            "sections": section_outputs,
            "article": article
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
