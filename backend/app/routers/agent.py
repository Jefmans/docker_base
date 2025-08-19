from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from uuid import uuid4
from pydantic import BaseModel
from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.memory import save_session_chunks, get_session_chunks, save_section, save_research_tree
from app.utils.agent.session_memory_db import (
    save_session_chunks_db, get_session_chunks_db,
    save_section_db, get_all_sections_db,
    save_research_tree_db
)
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.utils.agent.outline import generate_outline_from_tree
from app.utils.agent.writer import write_section, write_summary, write_conclusion
import json
from app.utils.agent.finalizer import finalize_article_from_tree
from app.models.research_tree import ResearchTree, ResearchNode, Chunk
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from app.utils.agent.controller import should_deepen_node
from app.utils.agent.expander import enrich_node_with_chunks_and_subquestions, deepen_node_with_subquestions, process_node_recursively, export_tree_to_pdf
from app.db.db import SessionLocal, get_db
from sqlalchemy.orm import Session
from app.utils.agent.repo import upsert_questions, attach_questions_to_node, update_node_fields, get_node_chunks
from app.utils.agent.router_utils import choose_best_node_for_question
# app/routers/agent.py
from app.utils.agent.repo import get_node_questions
from app.db.models.question_orm import QuestionStatus
from app.utils.agent.repo import get_node_chunks
from app.models.research_tree import Chunk
# in /agent/query
from app.db.db import Session as SessionModel
from app.utils.agent.repo import upsert_chunks, attach_chunks_to_node
import hashlib




router = APIRouter()

class AgentQueryRequest(BaseModel):
    query: str = "What is a black hole ?"
    top_k: int = 5


@router.post("/agent/query")
async def start_query_session(request: AgentQueryRequest):
    user_query = request.query
    top_chunks = search_chunks(user_query, top_k=request.top_k)  # strings

    root_node = ResearchNode(title=user_query)  # no in-memory chunks needed
    tree = ResearchTree(query=user_query, root_node=root_node)

    session_id = str(uuid4())
    db = SessionLocal()
    try:
        # 1) create Session row (store original query)
        db.add(SessionModel(id=session_id, query=user_query, tree={}))
        db.flush()

        # 2) persist root node
        tree.save_to_db(db, session_id)

        # 3) upsert initial chunks and attach to root
        chunk_dicts = [{
            "id": hashlib.sha1(c.encode("utf-8")).hexdigest(),
            "text": c,
            "page": None,
            "source": None
        } for c in top_chunks]
        upsert_chunks(db, chunk_dicts)
        attach_chunks_to_node(db, tree.root_node.id, [c["id"] for c in chunk_dicts])

        db.commit()
    finally:
        db.close()

    return {"status": "success", "session_id": session_id, "query": user_query,
            "preview_chunks": top_chunks[:3]}




@router.post("/agent/subquestions")
def generate_subquestions(session_id: str):
    db = SessionLocal()
    tree = ResearchTree.load_from_db(db, session_id)  # you can still reuse this to get the nodes (ids/titles)
    if not tree:
        raise HTTPException(status_code=404, detail="ResearchTree not found")

    chunks = [c.text for c in tree.root_node.all_chunks()]  # if still JSON-based; or fetch via ORM for the root node
    subq = generate_subquestions_from_chunks(chunks, tree.query)

    qids = upsert_questions(db, subq, source="root_subq")

    # route them to nodes (implement choose_best_node_for_question)
    for qid, qtext in zip(qids, subq):
        best_node = choose_best_node_for_question(db, qtext, tree)  # see below
        attach_questions_to_node(db, best_node.id, [qid])

    db.commit()
    db.close()
    return {"session_id": session_id, "questions": subq, "count": len(qids)}


@router.post("/agent/outline")
def create_outline(session_id: str):
    db = SessionLocal()
    try:
        tree = ResearchTree.load_from_db(db, session_id)
        outline = generate_outline_from_tree(tree)  # returns DTO
        tree.apply_outline(outline, db, session_id)
        db.commit()
        return {"session_id": session_id, "node_count": len(tree.root_node.subnodes)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Outline failed: {e}")
    finally:
        db.close()


@router.post("/agent/section/{section_id}")
def write_section_by_id(session_id: str, section_id: int):
    db = SessionLocal()
    try:
        tree = ResearchTree.load_from_db(db, session_id)
        if not tree:
            raise HTTPException(status_code=404, detail="ResearchTree not found")

        if section_id < 0 or section_id >= len(tree.root_node.subnodes):
            raise HTTPException(status_code=400, detail="Invalid section_id")

        node = tree.root_node.subnodes[section_id]

        # Generate content (writer already reads questions/chunks from DB)
        write_section(node)

        update_node_fields(db, node.id, content=node.content, is_final=True)
        db.commit()

        return {
            "session_id": session_id,
            "section_id": section_id,
            "heading": node.title,
            "text": node.content
        }
    finally:
        db.close()



@router.post("/agent/expand/{section_id}")
def expand_section(session_id: str, section_id: int, top_k: int = 5):
    # tree = get_research_tree_db(session_id)
    db = SessionLocal()
    tree = ResearchTree.load_from_db(db, session_id)
    if not tree:
        raise HTTPException(status_code=404, detail="ResearchTree not found")

    if section_id < 0 or section_id >= len(tree.root_node.subnodes):
        raise HTTPException(status_code=400, detail="Invalid section_id")

    node = tree.root_node.subnodes[section_id]

    # remember what we had before
    before_ids = set(getattr(node, "chunk_ids", set()))

    # enrich (writes to DB)
    enrich_node_with_chunks_and_subquestions(node, tree, top_k=top_k)

    # ⬇️ REFRESH from DB so in-memory node reflects new attachments
    orm_chunks = get_node_chunks(db, node.id)
    node.chunks = [Chunk(id=c.id, text=c.text, page=c.page, source=c.source) for c in orm_chunks]
    node.chunk_ids = {c.id for c in orm_chunks}

    new_chunks = [c for c in node.chunks if c.id not in before_ids]

    return {
        "status": "expanded",
        "section": node.title,
        "new_chunks": [c.text[:100] for c in new_chunks],
        "questions": node.questions
    }


# app/routers/agent.py
from app.utils.agent.repo import get_node_questions, get_node_chunks
from app.utils.agent.topics import group_similar
from app.utils.agent.controller import should_deepen_node
from app.utils.agent.expander import create_subnodes_from_clusters, deepen_node_with_subquestions

@router.post("/agent/deepen/{section_id}")
def deepen_section(session_id: str, section_id: int, top_k: int = 5):
    db = SessionLocal()
    try:
        tree = ResearchTree.load_from_db(db, session_id)
        if not tree:
            raise HTTPException(status_code=404, detail="ResearchTree not found")

        if section_id < 0 or section_id >= len(tree.root_node.subnodes):
            raise HTTPException(status_code=400, detail="Invalid section_id")

        node = tree.root_node.subnodes[section_id]

        # 1) collect candidate items to form topics
        q_objs = get_node_questions(db, node.id)
        expansion_q = [q.text for q in q_objs if getattr(q, "source", "").lower() == "expansion"]
        if not expansion_q:
            return {"status": "skipped", "reason": "No expansion questions on this node — run /expand first"}

        # 2) group into topics
        clusters = group_similar(expansion_q, threshold=0.72)

        # 3) decide if we should deepen
        existing_child_titles = [c.title for c in node.subnodes]
        if not should_deepen_node(node, clusters, existing_child_titles,
                                  min_items=2, title_sim_thresh=0.7, min_clusters=1):
            return {"status": "skipped", "reason": "No sufficiently novel topic clusters to justify subnodes"}

        # 4) create subnodes from topic clusters
        def title_from_cluster(cluster):
            cand = min(cluster, key=len)
            return cand.strip().rstrip("?.:;").capitalize()[:120]

        create_subnodes_from_clusters(node, clusters, title_from_cluster, db=db)

        # 5) (Optional) move relevant chunks down to the children
        # A simple approach: for each child title, fetch chunks for the parent,
        # attach chunks that keyword-match the child title/cluster terms to that child, and (optionally) leave them also on parent or detach from parent.

        return {
            "status": "deepened",
            "created_subnodes": [title_from_cluster(c) for c in clusters if len(c) >= 2]
        }
    finally:
        db.close()



@router.post("/agent/section/complete/{section_id}")
def complete_section(session_id: str, section_id: int):
    # tree = get_research_tree_db(session_id)
    db = SessionLocal()
    tree = ResearchTree.load_from_db(db, session_id)
    if not tree:
        raise HTTPException(status_code=404, detail="ResearchTree not found")

    if section_id < 0 or section_id >= len(tree.root_node.subnodes):
        raise HTTPException(status_code=400, detail="Invalid section_id")

    node = tree.root_node.subnodes[section_id]
    node.summary = write_summary(node)
    node.conclusion = write_conclusion(node)
    # save_research_tree_db(session_id, tree)

    return {
        "status": "success",
        "section_id": section_id,
        "summary": node.summary,
        "conclusion": node.conclusion
    }


@router.post("/agent/complete_tree")
def complete_full_tree(session_id: str, top_k: int = 10):
    # tree = get_research_tree_db(session_id)
    db = SessionLocal()
    tree = ResearchTree.load_from_db(db, session_id)
    if not tree:
        raise HTTPException(status_code=404, detail="ResearchTree not found")

    process_node_recursively(tree.root_node, tree, top_k=top_k)
    # save_research_tree_db(session_id, tree)

    return {
        "status": "complete",
        "title": tree.root_node.title,
        "outline_depth": len(tree.root_node.subnodes),
        "summary": tree.root_node.summary,
        "conclusion": tree.root_node.conclusion,
    }


@router.post("/agent/article/finalize")
def finalize_article_route(session_id: str):
    # tree = get_research_tree_db(session_id)
    db = SessionLocal()
    tree = ResearchTree.load_from_db(db, session_id)    
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
        outline = generate_outline_from_tree(tree)  # if you want to base it on the current tree

        # STEP 5: Attach outline to tree
        tree.root_node.title = outline.title or request.query
        tree.root_node.questions = [q for s in outline.sections for q in s.questions]
        tree.root_node.subnodes = [
            ResearchTree.node_from_outline_section(s) for s in outline.sections
        ]

        # STEP 6: Write content per section
        section_outputs = []
        for i, node in enumerate(tree.root_node.subnodes):
            write_section(node)
            
            section_outputs.append({
                "heading": node.title,
                "text": node.content
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
    # tree = get_research_tree_db(session_id)
    db = SessionLocal()
    tree = ResearchTree.load_from_db(db, session_id)
    if not tree:
        raise HTTPException(status_code=404, detail="Session or tree not found")

    return JSONResponse(content=tree.model_dump_jsonable())


@router.get("/agent/export/pdf_latex")
def export_pdf_via_latex(session_id: str):
    # tree = get_research_tree_db(session_id)
    db = SessionLocal()
    tree = ResearchTree.load_from_db(db, session_id)    
    if not tree:
        raise HTTPException(status_code=404, detail="Session not found")

    pdf_bytes = export_tree_to_pdf(tree)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=article.pdf"}
    )


@router.get("/agent/export/tree_content")
def export_tree_content(session_id: str):
    try:
        db = SessionLocal()
        tree = ResearchTree.load_from_db(db, session_id)
        db.close()
    except ValueError:
        raise HTTPException(status_code=404, detail="Tree not found in DB")

    def serialize_node(node):
        return {
            "title": node.title,
            "goals": node.goals,                     
            "questions": list(node.questions or []), 
            "content": node.content,
            "summary": node.summary,
            "conclusion": node.conclusion,
            "rank": node.rank,
            "level": node.level,
            "parent_rank":node.parent.rank if node.parent else None,
            "parent_level":node.parent.level if node.parent else None,
            "display_rank": node.display_rank,
            "parent_title": node.parent_title,
            "node_id": str(node.id),
            # "parent_id": node.parent_id,
            # "ranked_title": node.ranked_title, 
            "subnodes": [serialize_node(sub) for sub in node.subnodes],
        }

    return {
        "query": tree.query,
        "root_node": serialize_node(tree.root_node)
    }


