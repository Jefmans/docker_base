from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.models.research_tree import ResearchNode, ResearchTree, Chunk
from app.utils.agent.controller import should_deepen_node
from app.utils.agent.writer import write_section, write_summary, write_conclusion


def enrich_node_with_chunks_and_subquestions(node: ResearchNode, tree: ResearchTree, top_k: int = 10):
    queries = [node.title] + node.questions
    combined_query = " ".join(queries)

    results = search_chunks(combined_query, top_k=top_k, return_docs=True)
    all_texts = []

    for i, doc in enumerate(results):
        chunk_id = doc.metadata.get("id", f"{hash(doc.page_content)}_{i}")  # Use ES ID if available

        if chunk_id not in tree.used_chunk_ids:
            chunk = Chunk(
                id=chunk_id,
                text=doc.page_content,
                page=doc.metadata.get("page"),
                source=doc.metadata.get("source"),
            )
            node.chunks.append(chunk)
            node.chunk_ids.add(chunk_id)
            tree.used_chunk_ids.add(chunk_id)
            all_texts.append(doc.page_content)

    if all_texts:
        subqs = generate_subquestions_from_chunks(all_texts, node.title)
        node.generated_questions = subqs
        tree.used_questions.update(q.strip().lower() for q in subqs)




def deepen_node_with_subquestions(node, tree, top_k=5):
    for q in node.generated_questions:
        results = search_chunks(q, top_k=top_k, return_docs=True)
        for i, doc in enumerate(results):
            chunk_id = doc.metadata.get("id", f"{hash(doc.page_content)}_{i}")
            if chunk_id not in tree.used_chunk_ids:
                chunk = Chunk(
                    id=chunk_id,
                    text=doc.page_content,
                    page=doc.metadata.get("page"),
                    source=doc.metadata.get("source"),
                )
                node.chunks.append(chunk)
                node.chunk_ids.add(chunk_id)
                tree.used_chunk_ids.add(chunk_id)





def process_node_recursively(node: ResearchNode, tree: ResearchTree, top_k: int = 10):
    # 1. Enrich with chunks and subquestions
    enrich_node_with_chunks_and_subquestions(node, tree, top_k=top_k)

    # 2. Deepen if necessary (i.e. add new chunks via subquestions)
    if should_deepen_node(node):
        deepen_node_with_subquestions(node, tree, top_k=top_k)

    # 3. Write section content
    section_data = {
        "heading": node.title,
        "goals": "",
        "questions": node.questions or [],
    }
    node.content = write_section(section_data)
    node.summary = write_summary(node)
    node.conclusion = write_conclusion(node)
    node.mark_final()

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