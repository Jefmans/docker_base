from typing import List
from app.utils.vectorstore import get_vectorstore
from app.models.research_tree import ResearchScope

def search_chunks(
    query: str,
    top_k: int = 100,
    return_docs: bool = False,
    scope: ResearchScope | None = None,
) -> List[str]:
    vs = get_vectorstore()
    results = vs.similarity_search(
        query,
        k=top_k,
        filters=scope.search_filters() if scope else None,
    )

    if return_docs:
        return results  # Return full Document objects
    return [r.page_content for r in results]
