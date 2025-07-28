from typing import List
from app.utils.vectorstore import get_vectorstore

def search_chunks(query: str, top_k: int = 100) -> List[str]:
    vs = get_vectorstore()  # your existing LangChain Elastic setup
    results = vs.similarity_search(query, k=top_k)
    # print(results[0].dict())

    return [r.page_content for r in results]
