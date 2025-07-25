from typing import List
from app.utils.vectorstore import get_vectorstore

def search_chunks_for_query(query: str, top_k: int = 100) -> List[str]:
    vs = get_vectorstore()  # your existing LangChain Elastic setup
    results = vs.similarity_search(query, k=top_k)
    return [r.page_content for r in results]
