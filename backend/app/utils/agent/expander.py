from app.utils.agent.search_chunks import search_chunks
from app.utils.agent.subquestions import generate_subquestions_from_chunks
from app.models.research_tree import ResearchNode, ResearchTree, Chunk


def enrich_node_with_chunks_and_subquestions(node: ResearchNode, tree: ResearchTree, top_k: int = 5):
    queries = [node.title] + node.questions
    all_chunks = []

    for q in queries:
        results = search_chunks(q, top_k=top_k)
        for i, text in enumerate(results):
            chunk_id = f"{hash(q)}_{i}"
            if chunk_id not in tree.used_chunk_ids:
                chunk = Chunk(id=chunk_id, text=text)
                node.chunks.append(chunk)
                node.chunk_ids.add(chunk_id)
                tree.used_chunk_ids.add(chunk_id)
                all_chunks.append(text)

    if all_chunks:
        subqs = generate_subquestions_from_chunks(all_chunks, node.title)
        node.generated_questions = subqs
        tree.used_questions.update(q.strip().lower() for q in subqs)
