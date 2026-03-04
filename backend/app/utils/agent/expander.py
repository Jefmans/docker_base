import hashlib
import logging

from sqlalchemy import select

from app.db.db import SessionLocal
from app.db.models.question_orm import QuestionORM
from app.db.models.research_node_orm import ResearchNodeORM
from app.models.research_tree import Chunk, ResearchNode, ResearchScope, ResearchTree
from app.utils.agent.controller import (
    build_node_evidence_profile,
    build_node_execution_plan,
    evaluate_node_refinement,
)
from app.utils.agent.planning import node_retrieval_top_k
from app.utils.agent.repo import (
    attach_chunks_to_node,
    attach_questions_to_node,
    update_node_fields,
    upsert_chunks,
    upsert_questions,
)
from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.utils.agent.writer import write_section


logger = logging.getLogger(__name__)


def stable_chunk_id(text: str, meta_id: str | None = None) -> str:
    return meta_id or hashlib.sha1(text.encode("utf-8")).hexdigest()


def _hydrate_node_in_memory(
    node: ResearchNode,
    chunk_dicts: list[dict],
    questions: list[str],
) -> None:
    node.questions = list(dict.fromkeys((node.questions or []) + questions))
    node.chunks = [
        Chunk(
            id=chunk["id"],
            text=chunk["text"],
            page=chunk.get("page"),
            source=chunk.get("source"),
        )
        for chunk in chunk_dicts
    ]
    node.chunk_ids = {chunk["id"] for chunk in chunk_dicts}


def enrich_node_with_chunks_and_subquestions(
    node: ResearchNode,
    tree: ResearchTree,
    top_k: int | None = None,
):
    queries = [node.title] + getattr(node, "questions", [])
    combined_query = " ".join(q for q in queries if q).strip() or node.title
    base_retrieval_top_k = top_k or node_retrieval_top_k(tree.plan, node)
    logger.info(
        "Enriching node '%s' level=%s retrieval_top_k=%s question_count=%s",
        node.title,
        node.level,
        base_retrieval_top_k,
        len(getattr(node, "questions", [])),
    )

    results = search_chunks(
        combined_query,
        top_k=base_retrieval_top_k,
        return_docs=True,
        scope=tree.scope,
    )
    logger.info("Node '%s' retrieval returned %s docs", node.title, len(results))

    chunk_dicts = []
    for doc in results:
        chunk_id = stable_chunk_id(
            doc.page_content,
            doc.metadata.get("id") or doc.metadata.get("_id"),
        )
        chunk_dicts.append(
            {
                "id": chunk_id,
                "text": doc.page_content,
                "page": doc.metadata.get("page"),
                "source": doc.metadata.get("source"),
            }
        )

    chunk_dicts = list({chunk["id"]: chunk for chunk in chunk_dicts}.values())
    evidence_profile = build_node_evidence_profile(node, chunk_dicts)
    execution_plan = build_node_execution_plan(node, tree.plan, evidence_profile)
    logger.info(
        "Node '%s' evidence density=%s unique_chunks=%s unique_sources=%s "
        "context_limit=%s subquestion_target=%s should_attempt_depth=%s",
        node.title,
        execution_plan.evidence_density,
        evidence_profile.unique_chunk_count,
        evidence_profile.unique_source_count,
        execution_plan.context_chunk_limit,
        execution_plan.subquestion_target,
        execution_plan.should_attempt_depth,
    )

    db = SessionLocal()
    try:
        upsert_chunks(db, chunk_dicts)
        attach_chunks_to_node(db, node.id, [chunk["id"] for chunk in chunk_dicts])

        subquestions = generate_subquestions_from_chunks(
            [chunk["text"] for chunk in chunk_dicts],
            node.title,
            target_count=execution_plan.subquestion_target,
            context_chunk_limit=execution_plan.context_chunk_limit,
        )
        question_ids = upsert_questions(db, subquestions, source="expansion")
        attach_questions_to_node(db, node.id, question_ids)
        _hydrate_node_in_memory(node, chunk_dicts, subquestions)
        logger.info(
            "Node '%s' attached %s chunks and generated %s expansion questions",
            node.title,
            len(chunk_dicts),
            len(subquestions),
        )

        db.commit()
    finally:
        db.close()

    return evidence_profile, execution_plan


def deepen_node_with_subquestions(
    node,
    questions: list[str],
    top_k=5,
    scope: ResearchScope | None = None,
):
    db = SessionLocal()
    try:
        for question in questions:
            results = search_chunks(question, top_k=top_k, return_docs=True, scope=scope)
            chunk_dicts = []
            for doc in results:
                chunk_id = stable_chunk_id(doc.page_content, doc.metadata.get("id"))
                chunk_dicts.append(
                    {
                        "id": chunk_id,
                        "text": doc.page_content,
                        "page": doc.metadata.get("page"),
                        "source": doc.metadata.get("source"),
                    }
                )
            upsert_chunks(db, chunk_dicts)
            attach_chunks_to_node(db, node.id, [chunk["id"] for chunk in chunk_dicts])
        db.commit()
    finally:
        db.close()


def process_node_recursively(node: ResearchNode, tree: ResearchTree, top_k: int | None = None):
    logger.info(
        "Processing node '%s' level=%s subnodes=%s",
        node.title,
        node.level,
        len(node.subnodes),
    )

    evidence_profile, execution_plan = enrich_node_with_chunks_and_subquestions(
        node,
        tree,
        top_k=top_k,
    )

    did_deepen = False
    if execution_plan.should_attempt_depth:
        db = SessionLocal()
        try:
            refinement = evaluate_node_refinement(
                node,
                db,
                evidence=evidence_profile,
                min_novel=execution_plan.min_novel_questions_to_deepen,
            )
        finally:
            db.close()

        if refinement.should_deepen and refinement.novel_questions:
            deepen_node_with_subquestions(
                node,
                refinement.novel_questions,
                top_k=execution_plan.retrieval_top_k,
                scope=tree.scope,
            )
            did_deepen = True
            logger.info(
                "Node '%s' deepened with %s novel questions",
                node.title,
                len(refinement.novel_questions),
            )
        else:
            logger.info(
                "Node '%s' skipped deepening after refinement: %s",
                node.title,
                refinement.reason,
            )
    else:
        logger.info(
            "Node '%s' skipped deepening should_attempt_depth=%s evidence_density=%s",
            node.title,
            execution_plan.should_attempt_depth,
            execution_plan.evidence_density,
        )

    write_section(
        node,
        context_chunk_limit=execution_plan.context_chunk_limit,
        length_hint=execution_plan.section_length_hint,
    )

    db = SessionLocal()
    try:
        update_node_fields(
            db,
            node.id,
            content=node.content,
            is_final=True,
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
        with open(tex_path, "w") as handle:
            handle.write(tex)
        subprocess.run(["pdflatex", "-interaction=nonstopmode", tex_path], cwd=tmpdir)
        with open(pdf_path, "rb") as handle:
            return handle.read()


def create_subnodes_from_clusters(
    node: ResearchNode,
    clusters_q: list[list[str]],
    cluster_title_fn,
    db=None,
):
    """
    For each cluster of question texts, create a child node under `node` and
    attach those questions to the new child. Titles come from cluster_title_fn.
    """
    local_db = db or SessionLocal()
    try:
        parent_orm = local_db.execute(
            select(ResearchNodeORM).where(ResearchNodeORM.id == node.id)
        ).scalar_one_or_none()
        if not parent_orm:
            return
        session_id = parent_orm.session_id

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
            local_db.flush()

            question_ids = [q_to_id.get(question.strip().lower()) for question in cluster]
            question_ids = [question_id for question_id in question_ids if question_id]
            attach_questions_to_node(local_db, child_orm.id, question_ids)

        local_db.commit()
    finally:
        if db is None:
            local_db.close()


def title_from_cluster(cluster: list[str]) -> str:
    candidate = min(cluster, key=len)
    title = candidate.strip().rstrip("?.:;").capitalize()
    return title[:120]
