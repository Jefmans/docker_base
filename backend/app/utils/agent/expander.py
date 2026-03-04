import logging

from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.models.research_tree import ResearchNode, ResearchTree, Chunk, ResearchScope
from app.utils.agent.controller import should_deepen_node, get_novel_expansion_questions
from app.utils.agent.writer import write_section, write_summary, write_conclusion
from app.utils.agent.planning import (
    node_context_chunk_limit,
    node_retrieval_top_k,
    node_should_attempt_depth,
    node_subquestion_target,
)
from app.utils.agent.repo import upsert_chunks, attach_chunks_to_node, upsert_questions, attach_questions_to_node, update_node_fields
from app.db.db import SessionLocal  # add this import
import hashlib
from app.db.models.research_node_orm import ResearchNodeORM
from sqlalchemy import select
from app.db.models.question_orm import QuestionORM


logger = logging.getLogger(__name__)


def stable_chunk_id(text: str, meta_id: str | None = None) -> str:
    return meta_id or hashlib.sha1(text.encode("utf-8")).hexdigest()


def enrich_node_with_chunks_and_subquestions(node: ResearchNode, tree: ResearchTree, top_k: int | None = None):
    # 0) build a query
    queries = [node.title] + getattr(node, "questions", [])
    combined_query = " ".join(q for q in queries if q).strip() or node.title
    retrieval_top_k = top_k or node_retrieval_top_k(tree.plan, node)
    logger.info(
        "Enriching node '%s' level=%s retrieval_top_k=%s question_count=%s",
        node.title,
        node.level,
        retrieval_top_k,
        len(getattr(node, "questions", [])),
    )

    results = search_chunks(combined_query, top_k=retrieval_top_k, return_docs=True, scope=tree.scope)
    logger.info("Node '%s' retrieval returned %s docs", node.title, len(results))

    chunk_dicts = []
    for doc in results:
        # inside enrich_node_with_chunks_and_subquestions(...)
        chunk_id = stable_chunk_id(
            doc.page_content, 
            doc.metadata.get("id") or doc.metadata.get("_id")  # fall back to ES _id if needed
            )
        chunk_dicts.append({
            "id": chunk_id,
            "text": doc.page_content,
            "page": doc.metadata.get("page"),
            "source": doc.metadata.get("source"),
        })

    # ✅ de-dupe within this list BEFORE touching DB
    chunk_dicts = list({c["id"]: c for c in chunk_dicts}.values())        

    db = SessionLocal()
    try:
        upsert_chunks(db, chunk_dicts)
        attach_chunks_to_node(db, node.id, [c["id"] for c in chunk_dicts])

        subqs = generate_subquestions_from_chunks(
            [c["text"] for c in chunk_dicts],
            node.title,
            target_count=node_subquestion_target(tree.plan, node),
            context_chunk_limit=node_context_chunk_limit(tree.plan, node),
        )
        qids = upsert_questions(db, subqs, source="expansion")
        attach_questions_to_node(db, node.id, qids)
        logger.info(
            "Node '%s' attached %s chunks and generated %s expansion questions",
            node.title,
            len(chunk_dicts),
            len(subqs),
        )

        db.commit()
    finally:
        db.close()


# app/utils/agent/expander.py
def deepen_node_with_subquestions(
    node,
    questions: list[str],
    top_k=5,
    scope: ResearchScope | None = None,
):
    db = SessionLocal()
    try:
        for q in questions:
            results = search_chunks(q, top_k=top_k, return_docs=True, scope=scope)
            chunk_dicts = []
            for i, doc in enumerate(results):
                chunk_id = stable_chunk_id(doc.page_content, doc.metadata.get("id"))
                chunk_dicts.append({
                    "id": chunk_id,
                    "text": doc.page_content,
                    "page": doc.metadata.get("page"),
                    "source": doc.metadata.get("source"),
                })
            # de-dupe + insert + attach (your hardened helpers)
            upsert_chunks(db, chunk_dicts)
            attach_chunks_to_node(db, node.id, [c["id"] for c in chunk_dicts])
        db.commit()
    finally:
        db.close()


def process_node_recursively(node: ResearchNode, tree: ResearchTree, top_k: int | None = None):
    retrieval_top_k = node_retrieval_top_k(tree.plan, node)
    context_chunk_limit = node_context_chunk_limit(tree.plan, node)
    logger.info(
        "Processing node '%s' level=%s subnodes=%s",
        node.title,
        node.level,
        len(node.subnodes),
    )

    # 1) Expand the node (chunks + new expansion questions)
    enrich_node_with_chunks_and_subquestions(node, tree, top_k=retrieval_top_k)

    # 2) Decide whether to deepen using DB-based novelty
    should_attempt_depth = node_should_attempt_depth(tree.plan, node)
    did_deepen = False
    if should_attempt_depth and should_deepen_node(
        node,
        min_novel=tree.plan.min_novel_questions_to_deepen,
    ):
        from app.db.db import SessionLocal
        db = SessionLocal()
        try:
            novel_expansion = get_novel_expansion_questions(
                node, db, q_sim_thresh=0.80, title_sim_thresh=0.70
            )
        finally:
            db.close()

        if novel_expansion:
            deepen_node_with_subquestions(node, novel_expansion, top_k=retrieval_top_k, scope=tree.scope)
            did_deepen = True
            logger.info(
                "Node '%s' deepened with %s novel questions",
                node.title,
                len(novel_expansion),
            )
        else:
            logger.info("Node '%s' had no novel expansion questions", node.title)
    else:
        logger.info(
            "Node '%s' skipped deepening should_attempt_depth=%s",
            node.title,
            should_attempt_depth,
        )

    # 3) Generate text for this node (CONTENT ONLY)
    write_section(
        node,
        context_chunk_limit=context_chunk_limit,
        length_hint=tree.plan.section_length_hint,
    )

    # 4) Persist generated fields (no summary/conclusion here)
    db = SessionLocal()
    try:
        update_node_fields(
            db, node.id,
            content=node.content,
            is_final=True
        )
        db.commit()
        logger.info(
            "Persisted node '%s' content_len=%s did_deepen=%s",
            node.title,
            len((node.content or "").strip()),
            did_deepen,
        )
    finally:
        db.close()

    # 5) Recurse
    for subnode in node.subnodes:
        process_node_recursively(subnode, tree)
    logger.info("Finished node '%s'", node.title)


        
def export_tree_to_pdf(tree: ResearchTree, output_pdf="output.pdf"):
    import subprocess
    import tempfile
    tex = tree.to_latex_styled()

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = f"{tmpdir}/doc.tex"
        pdf_path = f"{tmpdir}/doc.pdf"
        with open(tex_path, "w") as f:
            f.write(tex)
        subprocess.run(["pdflatex", "-interaction=nonstopmode", tex_path], cwd=tmpdir)
        with open(pdf_path, "rb") as f:
            return f.read()
        

def create_subnodes_from_clusters(
    node: ResearchNode,
    clusters_q: list[list[str]],
    cluster_title_fn,
    db=None
):
    """
    For each cluster of question texts, create a child node under `node` and
    attach those questions to the new child. Titles come from cluster_title_fn.
    """
    local_db = db or SessionLocal()
    try:
        # Resolve parent ORM to get the correct session_id
        parent_orm = local_db.execute(
                select(ResearchNodeORM).where(ResearchNodeORM.id == node.id)
            ).scalar_one_or_none()
        if not parent_orm:
            return
        session_id = parent_orm.session_id

        # Map question text -> id (lowercased)
        q_rows = local_db.execute(select(QuestionORM.id, QuestionORM.text)).all()
        q_to_id = {text.lower(): qid for (qid, text) in q_rows}

        current_children_count = len(node.subnodes)

        for i, cluster in enumerate(clusters_q, start=1):
            if not cluster:
                continue
            title = cluster_title_fn(cluster)

            child_orm = ResearchNodeORM(
                session_id=session_id,
                parent_id=node.id,
                title=title,
                goals=None,
                content=None,
                summary=None,
                conclusion=None,
                rank=(current_children_count + i),
                level=(node.level or 1) + 1,
                is_final=False,
            )
            local_db.add(child_orm)
            local_db.flush()  # get id

            # attach questions for this cluster
            qids = [q_to_id.get(q.strip().lower()) for q in cluster]
            qids = [qid for qid in qids if qid]
            attach_questions_to_node(local_db, child_orm.id, qids)

        local_db.commit()
    finally:
        if db is None:
            local_db.close()


def title_from_cluster(cluster: list[str]) -> str:
    # Heuristic: use the shortest question, strip punctuation, sentence-case it.
    candidate = min(cluster, key=len)
    t = candidate.strip().rstrip("?.:;").capitalize()
    return t[:120]  # guard length
