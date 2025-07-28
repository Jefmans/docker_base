# core/agent/research_tree.py

from typing import List, Optional, Dict
from pydantic import BaseModel


class Chunk(BaseModel):
    id: str
    text: str
    page: Optional[int]
    source: Optional[str]
    embedding: Optional[List[float]] = None


class ResearchNode(BaseModel):
    title: str
    questions: List[str] = []
    chunks: List[Chunk] = []
    content: Optional[str] = None
    summary: Optional[str] = None
    conclusion: Optional[str] = None

    parent: Optional["ResearchNode"] = None
    subnodes: List["ResearchNode"] = []

    class Config:
        arbitrary_types_allowed = True
        underscore_attrs_are_private = True
        json_encoders = {
            "ResearchNode": lambda v: v.dict(exclude_none=True)
        }

    def add_subnode(self, node: "ResearchNode"):
        node.parent = self
        self.subnodes.append(node)

    def all_chunks(self) -> List[Chunk]:
        return self.chunks + [c for sn in self.subnodes for c in sn.all_chunks()]

    def all_questions(self) -> List[str]:
        return self.questions + [q for sn in self.subnodes for q in sn.all_questions()]

    def find_node_by_title(self, title: str) -> Optional["ResearchNode"]:
        if self.title == title:
            return self
        for sn in self.subnodes:
            result = sn.find_node_by_title(title)
            if result:
                return result
        return None


class ResearchTree(BaseModel):
    query: str
    root_node: ResearchNode

    class Config:
        arbitrary_types_allowed = True

    def deduplicate_chunks(self):
        seen_ids = set()
        def dedup(node: ResearchNode):
            unique = []
            for c in node.chunks:
                if c.id not in seen_ids:
                    unique.append(c)
                    seen_ids.add(c.id)
            node.chunks = unique
            for sn in node.subnodes:
                dedup(sn)
        dedup(self.root_node)

    def deduplicate_questions(self):
        seen = set()
        def dedup(node: ResearchNode):
            filtered = []
            for q in node.questions:
                qnorm = q.strip().lower()
                if qnorm not in seen:
                    filtered.append(q)
                    seen.add(qnorm)
            node.questions = filtered
            for sn in node.subnodes:
                dedup(sn)
        dedup(self.root_node)

    def generate_article(self, format: str = "markdown") -> str:
        if format == "markdown":
            return self._to_markdown()
        raise NotImplementedError(f"Format {format} not supported yet.")

    def _to_markdown(self) -> str:
        def walk(node: ResearchNode, level: int = 2) -> str:
            text = f"{'#' * level} {node.title}\n\n"
            if node.content:
                text += node.content.strip() + "\n\n"
            if node.summary:
                text += f"**Summary:** {node.summary.strip()}\n\n"
            if node.conclusion:
                text += f"**Conclusion:** {node.conclusion.strip()}\n\n"
            for sn in node.subnodes:
                text += walk(sn, level + 1)
            return text

        return f"# Research Article\n\n## Query\n{self.query}\n\n" + walk(self.root_node)

    def all_nodes(self) -> List[ResearchNode]:
        nodes = []
        def walk(node: ResearchNode):
            nodes.append(node)
            for sn in node.subnodes:
                walk(sn)
        walk(self.root_node)
        return nodes