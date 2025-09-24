from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from uuid import uuid4
from pydantic import BaseModel
from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.utils.agent.outline import generate_outline_from_tree
from app.utils.agent.writer import write_section, write_summary, write_conclusion
from app.utils.agent.finalizer import finalize_article_from_tree
from app.models.research_tree import ResearchTree, ResearchNode, Chunk
from app.utils.agent.expander import enrich_node_with_chunks_and_subquestions, create_subnodes_from_clusters
from app.utils.agent.repo import upsert_questions, attach_questions_to_node, update_node_fields, get_node_chunks, upsert_chunks, attach_chunks_to_node, get_node_questions
from app.utils.agent.router_utils import choose_best_node_for_question, get_top_level_section_or_400
import hashlib
from app.db.db import SessionLocal 
from app.repositories.research_tree_repo import ResearchTreeRepository
from app.renderers.article_renderer import ArticleRenderer
from app.mappers.outline_to_tree import node_from_outline_section



router = APIRouter()

class AgentQueryRequest(BaseModel):
    query: str = "What is a black hole ?"
    top_k: int = 5


@router.post("/agent/query")
async def start_query_session(request: AgentQueryRequest):
    user_query = request.query
    top_chunks = search_chunks(user_query, top_k=request.top_k)

    root_node = ResearchNode(title=user_query)
    tree = ResearchTree(query=user_query, root_node=root_node)

    session_id = str(uuid4())
    db = SessionLocal()
    try:
        # create Session row + persist root via repo
        repo = ResearchTreeRepository(db)
        repo.save(tree, session_id)

        # upsert initial chunks and attach to root (unchanged)
        chunk_dicts = [{
            "id": hashlib.sha1(c.encode("utf-8")).hexdigest(),
            "text": c, "page": None, "source": None
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
    try:
        repo = ResearchTreeRepository(db)
        tree = repo.load(session_id)

        if not tree:
            raise HTTPException(status_code=404, detail="ResearchTree not found")

        # Gather all chunk texts across the hydrated tree
        chunks = [c.text for n in tree.all_nodes() for c in n.chunks]
        # (optional) de-dup to keep the prompt lean
        chunks = list(dict.fromkeys(chunks))
        
        subq = generate_subquestions_from_chunks(chunks, tree.query)

        qids = upsert_questions(db, subq, source="root_subq")

        # route them to nodes (implement choose_best_node_for_question)
        for qid, qtext in zip(qids, subq):
            best_node = choose_best_node_for_question(db, qtext, tree)  # see below
            attach_questions_to_node(db, best_node.id, [qid])

        db.commit()
    finally:
        db.close()
    return {"session_id": session_id, "questions": subq, "count": len(qids)}


@router.post("/agent/outline")
def create_outline(session_id: str):
    db = SessionLocal()
    try:
        repo = ResearchTreeRepository(db)
        tree = repo.load(session_id)
        outline = generate_outline_from_tree(tree)

        # apply outline in-memory
        tree.root_node.subnodes = [node_from_outline_section(s) for s in outline.sections]
  
        if outline.title:
            tree.root_node.title = outline.title
        tree.assign_rank_and_level()

        # persist structure
        repo.save(tree, session_id)

        # attach outline questions using your existing helpers
        from app.utils.agent.repo import upsert_questions, attach_questions_to_node
        def attach_all(section, node):
            if getattr(section, "questions", None):
                qids = upsert_questions(db, section.questions, source="outline")
                attach_questions_to_node(db, node.id, qids)
            for ssub, nsub in zip(section.subsections or [], node.subnodes or []):
                attach_all(ssub, nsub)
        for s, n in zip(outline.sections, tree.root_node.subnodes):
            attach_all(s, n)

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
        repo = ResearchTreeRepository(db)
        tree = repo.load(session_id)
        if not tree:
            raise HTTPException(status_code=404, detail="ResearchTree not found")

        node = get_top_level_section_or_400(tree, section_id)

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
    try:
        repo = ResearchTreeRepository(db)
        tree = repo.load(session_id)
        if not tree:
            raise HTTPException(status_code=404, detail="ResearchTree not found")

        node = get_top_level_section_or_400(tree, section_id)

        # remember what we had before
        before_ids = set(getattr(node, "chunk_ids", set()))

        # enrich (writes to DB)
        enrich_node_with_chunks_and_subquestions(node, tree, top_k=top_k)

        # ⬇️ REFRESH from DB so in-memory node reflects new attachments
        orm_chunks = get_node_chunks(db, node.id)
        node.chunks = [Chunk(id=c.id, text=c.text, page=c.page, source=c.source) for c in orm_chunks]
        node.chunk_ids = {c.id for c in orm_chunks}
        
        q_objs = get_node_questions(db, node.id)
        node.questions = [q.text for q in q_objs]

        new_chunks = [c for c in node.chunks if c.id not in before_ids]

        return {
            "status": "expanded",
            "section": node.title,
            "new_chunks": [c.text[:100] for c in new_chunks],
            "total_chunks": len(node.chunks),
            "questions": node.questions
        }
    finally:
        db.close()


@router.post("/agent/deepen/{section_id}")
def deepen_section(session_id: str, section_id: int, top_k: int = 5):
    from app.utils.agent.controller import get_novel_expansion_questions
    from app.utils.agent.topics import group_similar

    db = SessionLocal()
    try:
        repo = ResearchTreeRepository(db)
        tree = repo.load(session_id)
        if not tree:
            raise HTTPException(status_code=404, detail="ResearchTree not found")

        node = get_top_level_section_or_400(tree, section_id)

        # 1) Take only *novel* expansion questions (vs local/global + child titles)
        novel_expansion = get_novel_expansion_questions(
            node, db, q_sim_thresh=0.80, title_sim_thresh=0.70
        )
        print("NEW QUESTIONS", novel_expansion)
        if len(novel_expansion) < 2:
            return {"status": "skipped", "reason": "Not enough novel expansion questions"}

        # 2) Group into topic clusters
        clusters = group_similar(novel_expansion, threshold=0.72)
        big_enough = [c for c in clusters if len(c) >= 2]
        if not big_enough:
            return {"status": "skipped", "reason": "No clusters with at least 2 related questions"}

        # 3) Title heuristic for each cluster
        def title_from_cluster(cluster):
            cand = min(cluster, key=len)
            return cand.strip().rstrip("?.:;").capitalize()[:120]

        # 4) Create subnodes (persisted)
        create_subnodes_from_clusters(node, big_enough, title_from_cluster, db=db)

        return {
            "status": "deepened",
            "created_subnodes": [title_from_cluster(c) for c in big_enough]
        }
    finally:
        db.close()


@router.post("/agent/section/complete/{section_id}")
def complete_section(session_id: str, section_id: int):
    # tree = get_research_tree_db(session_id)
    db = SessionLocal()
    try:
        repo = ResearchTreeRepository(db)
        tree = repo.load(session_id)
        if not tree:
            raise HTTPException(status_code=404, detail="ResearchTree not found")

        node = get_top_level_section_or_400(tree, section_id)

        node.summary = write_summary(node)
        node.conclusion = write_conclusion(node)
        # save_research_tree_db(session_id, tree)
        # persist into DB so the tree is source-of-truth
        update_node_fields(db, node.id, summary=node.summary, conclusion=node.conclusion, is_final=True)
        db.commit()    

        return {
            "status": "success",
            "section_id": section_id,
            "summary": node.summary,
            "conclusion": node.conclusion
        }
    finally:
        db.close()


# @router.post("/agent/complete_tree")
# def complete_full_tree(session_id: str, top_k: int = 10):
#     # tree = get_research_tree_db(session_id)
#     db = SessionLocal()
#     repo = ResearchTreeRepository(db)
#     tree = repo.load(session_id)
#     if not tree:
#         raise HTTPException(status_code=404, detail="ResearchTree not found")

#     process_node_recursively(tree.root_node, tree, top_k=top_k)
#     # save_research_tree_db(session_id, tree)

#     return {
#         "status": "complete",
#         "title": tree.root_node.title,
#         "outline_depth": len(tree.root_node.subnodes),
#         "summary": tree.root_node.summary,
#         "conclusion": tree.root_node.conclusion,
#     }


# @router.post("/agent/article/finalize")
# def finalize_article_route(session_id: str):
#     # tree = get_research_tree_db(session_id)
#     db = SessionLocal()
#     repo = ResearchTreeRepository(db)
#     tree = repo.load(session_id)
#     if not tree:
#         raise HTTPException(status_code=404, detail="ResearchTree not found")

#     article = finalize_article_from_tree(tree)

#     return {
#         "session_id": session_id,
#         "title": tree.root_node.title or "Untitled Article",
#         "article": article
#     }


@router.post("/agent/full_run")
def full_run(request: AgentQueryRequest):
    try:
        # STEP 1: create session + persist root node in DB
        session_id = str(uuid4())
        user_query = request.query
        top_chunks = search_chunks(user_query, top_k=request.top_k)

        # Build root ResearchTree
        root_node = ResearchNode(title=request.query)
        tree = ResearchTree(query=user_query, root_node=root_node)

        db = SessionLocal()

        try:
            # create Session row
            # db.add(SessionModel(id=session_id, query=user_query, tree={}))
            # db.flush()

            # persist root node
            repo = ResearchTreeRepository(db)
            repo.save(tree, session_id)

            # upsert initial chunks and attach to root
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

        # STEP 2: subquestions + outline
        # subq = generate_subquestions_from_chunks(top_chunks, user_query)
        # reload to ensure the root has the initial attached chunks in memory
        db = SessionLocal()
        try:
            repo = ResearchTreeRepository(db)
            tree_for_subq = repo.load(session_id)
            root_chunks_text = [c.text for c in tree_for_subq.root_node.chunks]
        finally:
            db.close()
        subq = generate_subquestions_from_chunks(root_chunks_text, user_query)
        # outline = generate_outline_from_tree(tree)
        # Use hydrated tree for the outline
        db = SessionLocal()
        try:
            repo = ResearchTreeRepository(db)
            tree_for_outline = repo.load(session_id)
        finally:
            db.close()
        outline = generate_outline_from_tree(tree_for_outline)

        # Apply outline to DB-backed tree
        db = SessionLocal()
        try:
            repo = ResearchTreeRepository(db)
            tree = repo.load(session_id)  # reload to ensure ORM ids
            tree.root_node.subnodes = [node_from_outline_section(s) for s in outline.sections]
            if outline.title:
                tree.root_node.title = outline.title
            tree.assign_rank_and_level()
            repo.save(tree, session_id)

            # attach outline questions
            from app.utils.agent.repo import upsert_questions, attach_questions_to_node
            def _attach_all(section, node):
                if getattr(section, "questions", None):
                    qids = upsert_questions(db, section.questions, source="outline")
                    attach_questions_to_node(db, node.id, qids)
                for ssub, nsub in zip(section.subsections or [], node.subnodes or []):
                    _attach_all(ssub, nsub)
            for s, n in zip(outline.sections, tree.root_node.subnodes):
                _attach_all(s, n)
            db.commit()
        finally:
            db.close()

        # STEP 3: write each top-level section and persist
        section_outputs = []
        db = SessionLocal()
        try:
            repo = ResearchTreeRepository(db)
            tree = repo.load(session_id)
            for node in tree.root_node.subnodes:
                write_section(node)
                update_node_fields(db, node.id, content=node.content, is_final=True)
                section_outputs.append({"heading": node.title, "text": node.content})
            db.commit()
        finally:
            db.close()

        # STEP 4: final synthesis (in-memory from the latest tree)
        db = SessionLocal()
        try:
            repo = ResearchTreeRepository(db)
            tree = repo.load(session_id)
            article = finalize_article_from_tree(tree)
        finally:
            db.close()

        return {
            "session_id": session_id,
            "title": tree.root_node.title or user_query,
            "abstract": tree.root_node.content or "",
            "outline": [s.dict() for s in outline.sections],
            "sections": section_outputs,
            "article": article
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent/tree/{session_id}")
def get_tree(session_id: str):
    db = SessionLocal()
    repo = ResearchTreeRepository(db)
    tree = repo.load(session_id)
    db.close()
    return JSONResponse(content=tree.model_dump_jsonable())



@router.get("/agent/export/pdf_latex")
def export_pdf_via_latex(session_id: str):
    import subprocess, tempfile
    db = SessionLocal()
    repo = ResearchTreeRepository(db)
    tree = repo.load(session_id)
    db.close()

    latex = ArticleRenderer.to_latex(tree)
    with tempfile.TemporaryDirectory() as tmp:
        tex = f"{tmp}/doc.tex"
        pdf = f"{tmp}/doc.pdf"
        with open(tex, "w") as f: f.write(latex)
        subprocess.run(["pdflatex", "-interaction=nonstopmode", tex], cwd=tmp, check=False)
        with open(pdf, "rb") as f: pdf_bytes = f.read()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=article.pdf"}
    )



@router.get("/agent/export/tree_content")
def export_tree_content(session_id: str):
    try:
        db = SessionLocal()
        repo = ResearchTreeRepository(db)
        tree = repo.load(session_id)
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


