from dataclasses import dataclass, field
import os

from elasticsearch import Elasticsearch
from langchain_openai import OpenAIEmbeddings

from app.utils.search_index import build_filter_clauses


@dataclass
class StoredDocument:
    page_content: str
    metadata: dict = field(default_factory=dict)


class SimpleElasticsearchVectorStore:
    def __init__(self, *, index_name: str, vector_query_field: str = "vector", query_field: str = "text"):
        self.index_name = index_name
        self.vector_query_field = vector_query_field
        self.query_field = query_field
        self.es = Elasticsearch("http://elasticsearch:9200")
        self._embeddings = None

    @property
    def embeddings(self) -> OpenAIEmbeddings:
        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=os.getenv("OPENAI_API_KEY"),
            )
        return self._embeddings

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        *,
        filters: dict[str, object] | None = None,
    ) -> list[StoredDocument]:
        return [doc for doc, _score in self.similarity_search_with_score(query=query, k=k, filters=filters)]

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        *,
        filters: dict[str, object] | None = None,
    ) -> list[tuple[StoredDocument, float]]:
        vector = self.embeddings.embed_query(query)
        knn = {
            "field": self.vector_query_field,
            "query_vector": vector,
            "k": k,
            "num_candidates": max(25, k * 5),
        }
        clauses = build_filter_clauses(filters)
        if clauses:
            knn["filter"] = {"bool": {"filter": clauses}}
        response = self.es.search(
            index=self.index_name,
            size=k,
            knn=knn,
            source=True,
        )

        hits = response.get("hits", {}).get("hits", [])
        results: list[tuple[StoredDocument, float]] = []
        for hit in hits:
            source = dict(hit.get("_source") or {})
            text = source.pop(self.query_field, "")
            source.setdefault("id", hit.get("_id"))
            results.append((StoredDocument(page_content=text, metadata=source), float(hit.get("_score", 0.0))))
        return results


def get_vectorstore(index_name: str = "pdf_chunks") -> SimpleElasticsearchVectorStore:
    return SimpleElasticsearchVectorStore(index_name=index_name)


def get_caption_store() -> SimpleElasticsearchVectorStore:
    return get_vectorstore(index_name="captions")
