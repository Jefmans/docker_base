from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.models.research_tree import ResearchNode, ResearchTree, Chunk
from app.utils.agent.controller import should_deepen_node
from app.utils.agent.writer import write_section, write_summary, write_conclusion


from app.utils.agent.repo import upsert_chunks, attach_chunks_to_node, upsert_questions, attach_questions_to_node
from app.db.db import SessionLocal  # add this import

# utils/agent/expander.py (top)
import hashlib

def stable_chunk_id(text: str, meta_id: str | None = None) -> str:
    return meta_id or hashlib.sha1(text.encode("utf-8")).hexdigest()




def enrich_node_with_chunks_and_subquestions(node: ResearchNode, tree: ResearchTree, top_k: int = 10):
    # 0) build a query
    queries = [node.title] + getattr(node, "questions", [])
    combined_query = " ".join(q for q in queries if q).strip() or node.title

    results = search_chunks(combined_query, top_k=top_k, return_docs=True)

    chunk_dicts = []
    for doc in results:
        # inside enrich_node_with_chunks_and_subquestions(...)
        chunk_id = stable_chunk_id(doc.page_content, doc.metadata.get("id"))
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

        subqs = generate_subquestions_from_chunks([c["text"] for c in chunk_dicts], node.title)
        qids = upsert_questions(db, subqs, source="expansion")
        attach_questions_to_node(db, node.id, qids)

        db.commit()
    finally:
        db.close()




from app.db.db import SessionLocal

# app/utils/agent/expander.py
def deepen_node_with_subquestions(node, questions: list[str], top_k=5):
    db = SessionLocal()
    try:
        for q in questions:
            results = search_chunks(q, top_k=top_k, return_docs=True)
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




# utils/agent/expander.py
from app.utils.agent.repo import update_node_fields
from app.db.db import SessionLocal

def process_node_recursively(node: ResearchNode, tree: ResearchTree, top_k: int = 10):
    enrich_node_with_chunks_and_subquestions(node, tree, top_k=top_k)
    if should_deepen_node(node):
        deepen_node_with_subquestions(node, tree, top_k=top_k)

    # Generate text
    write_section(node)
    node.summary = write_summary(node)
    node.conclusion = write_conclusion(node)

    # Persist
    db = SessionLocal()
    try:
        update_node_fields(db, node.id,
                           content=node.content,
                           summary=node.summary,
                           conclusion=node.conclusion,
                           is_final=True)
        db.commit()
    finally:
        db.close()

    for subnode in node.subnodes:
        process_node_recursively(subnode, tree, top_k=top_k)


        

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
        

# app/utils/agent/expander.py (new function)
from app.models.research_tree import ResearchNode
from app.utils.agent.repo import attach_questions_to_node, attach_chunks_to_node
from app.db.db import SessionLocal
from app.db.models.research_node_orm import ResearchNodeORM

def create_subnodes_from_clusters(node: ResearchNode, clusters_q: list[list[str]],
                                  cluster_title_fn, db=None):
    """
    cluster_title_fn: callable(list[str]) -> str   # produce a title for each cluster
    clusters_q are lists of question texts (you can also build clusters from chunks similarly)
    """
    local_db = db or SessionLocal()
    try:
        # get DB ids for these question texts
        from sqlalchemy import func
        from app.db.models.question_orm import QuestionORM
        q_to_id = {q.text.lower(): q.id for q in local_db.query(QuestionORM).all()}  # or fetch only needed ones

        # existing children count to assign rank
        current_children_count = len(node.subnodes)

        for i, cluster in enumerate(clusters_q, start=1):
            if not cluster:
                continue
            title = cluster_title_fn(cluster)

            # create child node
            child_orm = ResearchNodeORM(
                session_id=node.parent.id if node.parent else None,  # your save_to_db handles session_id; alternatively pass it in
                parent_id=node.id,
                title=title,
                goals=None,
                content=None,
                summary=None,
                conclusion=None,
                rank=current_children_count + i,
                level=(node.level or 1) + 1,
                is_final=False,
            )
            local_db.add(child_orm)
            local_db.flush()

            # attach questions in this cluster to the new child
            qids = [q_to_id[q.strip().lower()] for q in cluster if q.strip().lower() in q_to_id]
            attach_questions_to_node(local_db, child_orm.id, qids)

            # OPTIONAL: re-attach relevant chunks to child too
            # A simple heuristic: any chunk whose text mentions >=1 key phrase from cluster
            # You can refine with retrieval or keyword matching.

        local_db.commit()
    finally:
        if db is None:
            local_db.close()


def title_from_cluster(cluster: list[str]) -> str:
    # Heuristic: use the shortest question, strip punctuation, sentence-case it.
    candidate = min(cluster, key=len)
    t = candidate.strip().rstrip("?.:;").capitalize()
    return t[:120]  # guard length
