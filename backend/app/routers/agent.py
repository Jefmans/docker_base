from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from uuid import uuid4
from pydantic import BaseModel
from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.memory import save_session_chunks, get_session_chunks, save_section, save_research_tree
from app.utils.agent.session_memory_db import (
    save_session_chunks_db, get_session_chunks_db,
    save_section_db, get_all_sections_db,
    save_research_tree_db, get_research_tree_db
)
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.utils.agent.outline import generate_outline, Outline
from app.utils.agent.writer import write_section
import json
from app.utils.agent.finalizer import finalize_article_from_tree
from app.models.research_tree import ResearchTree, ResearchNode, Chunk
from app.utils.agent.memory import get_research_tree
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder




router = APIRouter()

class AgentQueryRequest(BaseModel):
    query: str = "What is a black hole ?"
    top_k: int = 5



@router.post("/agent/query")
async def start_query_session(request: AgentQueryRequest):
    user_query = request.query
    if not user_query:
        raise HTTPException(status_code=400, detail="Missing 'query' in request body.")

    try:
        top_chunks = search_chunks(user_query, top_k=request.top_k)

        # Convert chunks (currently strings) to Chunk objects — improve later
        chunk_objs = [Chunk(id=str(i), text=c, page=None, source=None) for i, c in enumerate(top_chunks)]

        root_node = ResearchNode(title=user_query, chunks=chunk_objs)
        tree = ResearchTree(query=user_query, root_node=root_node)

        session_id = str(uuid4())
        save_research_tree_db(session_id, tree)

        return {
            "status": "success",
            "session_id": session_id,
            "query": user_query,
            "preview_chunks": top_chunks[:3]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/agent/subquestions")
def generate_subquestions(session_id: str):
    tree = get_research_tree_db(session_id)
    if not tree:
        raise HTTPException(status_code=404, detail="ResearchTree not found")

    chunks = [c.text for c in tree.root_node.all_chunks()]
    subq = generate_subquestions_from_chunks(chunks, tree.query)

    return {
        "session_id": session_id,
        "query": tree.query,
        "subquestions": subq
    }


@router.post("/agent/outline")
def create_outline(session_id: str):
    tree = get_research_tree_db(session_id)
    if not tree:
        raise HTTPException(status_code=404, detail="ResearchTree not found")

    # Step 1: Get all chunks
    chunks = [c.text for c in tree.root_node.all_chunks()]

    # Step 2: Generate outline from LLM
    outline = generate_outline(chunks, tree.query)

    # Step 3: Build full node structure from outline
    tree.root_node.subnodes = [
        ResearchTree.node_from_outline_section(section) for section in outline.sections
    ]

    # ✅ NEW: attach outline metadata (optional, but nice)
    tree.root_node.title = outline.title or tree.root_node.title
    tree.root_node.questions = [q for sec in outline.sections for q in sec.questions]

    # ✅ NEW: Save outline inside the session (DB version)
    session = get_session_chunks_db(session_id)
    session["outline"] = outline.dict()

    # Save back to database
    save_research_tree_db(session_id, tree)

    return {
        "session_id": session_id,
        "outline": outline.dict(),
        "node_count": len(tree.root_node.subnodes),
        # "tree": tree.model_dump()
    }



@router.post("/agent/section/{section_id}")
def write_section_by_id(session_id: str, section_id: int):
    # Step 1: Load full ResearchTree from DB
    tree = get_research_tree_db(session_id)
    if not tree:
        raise HTTPException(status_code=404, detail="ResearchTree not found")

    # Step 2: Get top-level section node from root
    if section_id < 0 or section_id >= len(tree.root_node.subnodes):
        raise HTTPException(status_code=400, detail="Invalid section_id")

    node = tree.root_node.subnodes[section_id]

    # Step 3: Prepare section dictionary for writing
    section_data = {
        "heading": node.title,
        "goals": "",  # You can optionally extract or store `goals` in the node
        "questions": node.questions or [],
    }

    # Step 4: Generate content
    generated_text = write_section(section_data)

    # Step 5: Save content into the node
    node.content = generated_text
    node.mark_final()

    # Step 6: Save updated tree back to DB
    save_research_tree_db(session_id, tree)

    return {
        "session_id": session_id,
        "section_id": section_id,
        "heading": node.title,
        "text": generated_text
    }





from app.utils.agent.finalizer import finalize_article_from_tree

@router.post("/agent/article/finalize")
def finalize_article_route(session_id: str):
    tree = get_research_tree_db(session_id)
    if not tree:
        raise HTTPException(status_code=404, detail="ResearchTree not found")

    article = finalize_article_from_tree(tree)

    return {
        "session_id": session_id,
        "title": tree.root_node.title or "Untitled Article",
        "article": article
    }



@router.post("/agent/full_run")
def full_run(request: AgentQueryRequest):
    try:
        # STEP 1: Generate session ID
        session_id = str(uuid4())

        # STEP 2: Search top-k chunks
        top_chunks = search_chunks(request.query, top_k=request.top_k)
        chunk_objs = [Chunk(id=str(i), text=c, page=None, source=None) for i, c in enumerate(top_chunks)]

        # STEP 3: Build root ResearchTree
        root_node = ResearchNode(title=request.query, chunks=chunk_objs)
        tree = ResearchTree(query=request.query, root_node=root_node)

        # STEP 4: Generate subquestions and outline
        subq = generate_subquestions_from_chunks(top_chunks, request.query)
        outline = generate_outline(subq, request.query)

        # STEP 5: Attach outline to tree
        tree.root_node.title = outline.title or request.query
        tree.root_node.questions = [q for s in outline.sections for q in s.questions]
        tree.root_node.subnodes = [
            ResearchTree.node_from_outline_section(s) for s in outline.sections
        ]

        # STEP 6: Write content per section
        section_outputs = []
        for i, node in enumerate(tree.root_node.subnodes):
            section_data = {
                "heading": node.title,
                "goals": "",  # if you want to use `goals`, add it to ResearchNode
                "questions": node.questions
            }
            text = write_section(section_data)
            node.content = text
            node.mark_final()
            section_outputs.append({
                "heading": node.title,
                "text": text
            })

        # STEP 7: Save full tree to DB
        save_research_tree_db(session_id, tree)

        # STEP 8: Finalize article from tree
        article = finalize_article_from_tree(tree)

        return {
            "session_id": session_id,
            "title": tree.root_node.title,
            "abstract": tree.root_node.content or "",
            "outline": [s.dict() for s in outline.sections],
            "sections": section_outputs,
            "article": article
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/agent/tree/{session_id}")
def get_tree(session_id: str):
    tree = get_research_tree_db(session_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Session or tree not found")

    return JSONResponse(content=tree.model_dump_jsonable())

