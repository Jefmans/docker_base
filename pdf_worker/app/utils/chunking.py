from typing import List, Dict
from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_text_by_lengths(
    text_pages: List[str],
    chunk_sizes: List[int] = [200, 800],
    overlap_pct: float = 0.2
) -> Dict[int, List[Dict]]:
    """
    Returns dict of chunk size → list of chunks, with each chunk storing:
    - text
    - chunk_index
    - source_page(s)
    """
    full_text = "\n".join(text_pages)
    results = {}

    for size in chunk_sizes:
        overlap = int(size * overlap_pct)
        splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
        chunks = splitter.create_documents([full_text])

        enriched = []
        for i, chunk in enumerate(chunks):
            enriched.append({
                "chunk_index": i,
                "text": chunk.page_content,
                "metadata": chunk.metadata
            })
        results[size] = enriched

    return results
