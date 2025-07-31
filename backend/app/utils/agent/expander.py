from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.models.research_tree import ResearchNode, ResearchTree, Chunk



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
