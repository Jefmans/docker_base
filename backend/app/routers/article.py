from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Optional, List
from uuid import uuid4
from app.db.db import SessionLocal
from app.repositories.research_tree_repo import ResearchTreeRepository
from app.models.research_tree import ResearchTree, ResearchNode
from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.outline import generate_outline_from_tree
from app.utils.agent.finalizer import finalize_article_from_tree
from app.renderers.latex_deterministic import to_latex_deterministic
from app.utils.agent.expander import process_node_recursively

router = APIRouter(prefix="/agent", tags=["agent"])

class ArticleRequest(BaseModel):
    query: str
    doc_ids: Optional[List[str]] = None
    mode: Optional[str] = "quick"  # "quick" | "full"
    top_k: int = 10

class ArticleStartResponse(BaseModel):
    session_id: str
    mode: str

class ArticleStatusResponse(BaseModel):
    phase: str
    progress: int
    message: Optional[str] = None

class ArticleResponse(BaseModel):
    session_id: str
    title: str
    article_markdown: str

@router.post("/article", response_model=ArticleStartResponse)
def start_article(req: ArticleRequest):
    # Create session + seed root node with top chunks (optional)
    session_id = str(uuid4())
    top_chunks = search_chunks(req.query, top_k=req.top_k)  # you can scope by doc_ids inside search_chunks
    root = ResearchNode(title=req.query)
    tree = ResearchTree(query=req.query, root_node=root)

    # Save minimal tree; your repo.save persists node structure
    db = SessionLocal()
    try:
        ResearchTreeRepository(db).save(tree, session_id)
        db.commit()
    finally:
        db.close()

    # QUICK mode could do a synchronous fast pass here; FULL mode handled by background/task in real setup
    return ArticleStartResponse(session_id=session_id, mode=req.mode or "quick")

@router.get("/{session_id}/status", response_model=ArticleStatusResponse)
def get_article_status(session_id: str):
    # If you add jobs, report real phase/progress. For now, say 'done' if tree exists.
    try:
        db = SessionLocal()
        repo = ResearchTreeRepository(db)
        repo.load(session_id)  # throws if not found
        return ArticleStatusResponse(phase="done", progress=100)
    except Exception:
        return ArticleStatusResponse(phase="unknown", progress=0, message="Session not found")
    finally:
        db.close()

@router.get("/{session_id}/article", response_model=ArticleResponse)
def get_article(session_id: str):
    db = SessionLocal()
    try:
        repo = ResearchTreeRepository(db)
        tree = repo.load(session_id)

        # Minimal pipeline (quick): outline → write each top-level once
        outline = generate_outline_from_tree(tree)
        tree.root_node.title = outline.title or tree.query
        tree.root_node.subnodes = [ResearchNode(title=s.heading, goals=s.goals or "") for s in outline.sections]
        tree.assign_rank_and_level()

        # Simple write per section (no deepening) using your existing recursive
        for n in tree.root_node.subnodes:
            process_node_recursively(n, tree, top_k=8)

        # Finalize to markdown
        article_md = finalize_article_from_tree(tree)
        return ArticleResponse(session_id=session_id, title=tree.root_node.title, article_markdown=article_md)
    finally:
        db.close()

@router.get("/{session_id}/export/pdf")
def export_pdf(session_id: str):
    # Deterministic LaTeX export
    db = SessionLocal()
    try:
        repo = ResearchTreeRepository(db)
        tree = repo.load(session_id)
        latex = to_latex_deterministic(tree)
    finally:
        db.close()

    import tempfile, subprocess
    with tempfile.TemporaryDirectory() as tmp:
        tex = f"{tmp}/doc.tex"; pdf = f"{tmp}/doc.pdf"
        with open(tex, "w") as f: f.write(latex)
        subprocess.run(["pdflatex", "-interaction=nonstopmode", tex], cwd=tmp, check=False)
        with open(pdf, "rb") as f: pdf_bytes = f.read()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=article.pdf"}
    )
