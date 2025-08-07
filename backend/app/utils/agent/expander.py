from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.models.research_tree import ResearchNode, ResearchTree, Chunk
from app.utils.agent.controller import should_deepen_node
from app.utils.agent.writer import write_section, write_summary, write_conclusion


from app.utils.agent.repo import upsert_chunks, attach_chunks_to_node, upsert_questions, attach_questions_to_node
from app.db.db import SessionLocal  # add this import


def enrich_node_with_chunks_and_subquestions(node: ResearchNode, tree: ResearchTree, top_k: int = 10):
    # 0) build a query
    queries = [node.title] + getattr(node, "questions", [])
    combined_query = " ".join(q for q in queries if q).strip() or node.title

    results = search_chunks(combined_query, top_k=top_k, return_docs=True)

    chunk_dicts = []
    for i, doc in enumerate(results):
        chunk_id = doc.metadata.get("id", f"{hash(doc.page_content)}_{i}")
        chunk_dicts.append({
            "id": chunk_id,
            "text": doc.page_content,
            "page": doc.metadata.get("page"),
            "source": doc.metadata.get("source"),
        })

    db = SessionLocal()
    try:
        upsert_chunks(db, chunk_dicts)
        attach_chunks_to_node(db, node.id, [c["id"] for c in chunk_dicts])

        subqs = generate_subquestions_from_chunks([c["text"] for c in chunk_dicts], node.title)
        qids = upsert_questions(db, subqs, source="expansion")
        attach_questions_to_node(db, node.id, qids)

        # make these visible to controller.should_deepen_node
        node.generated_questions_texts = subqs
        db.commit()
    finally:
        db.close()




from app.db.db import SessionLocal

def deepen_node_with_subquestions(node, tree, top_k=5):
    db = SessionLocal()
    try:
        for q in getattr(node, "generated_questions_texts", []):
            results = search_chunks(q, top_k=top_k, return_docs=True)
            chunk_dicts = []
            for i, doc in enumerate(results):
                chunk_id = doc.metadata.get("id", f"{hash(doc.page_content)}_{i}")
                chunk_dicts.append({
                    "id": chunk_id,
                    "text": doc.page_content,
                    "page": doc.metadata.get("page"),
                    "source": doc.metadata.get("source"),
                })
            upsert_chunks(db, chunk_dicts)
            attach_chunks_to_node(db, node.id, [c["id"] for c in chunk_dicts])
        db.commit()
    finally:
        db.close()




def process_node_recursively(node: ResearchNode, tree: ResearchTree, top_k: int = 10):
    # 1. Enrich with chunks and subquestions
    enrich_node_with_chunks_and_subquestions(node, tree, top_k=top_k)

    # 2. Deepen if necessary (i.e. add new chunks via subquestions)
    if should_deepen_node(node):
        deepen_node_with_subquestions(node, tree, top_k=top_k)

    # 3. Write section content
    write_section(node)
    node.summary = write_summary(node)
    node.conclusion = write_conclusion(node)
    

    # 4. Recurse through subnodes
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