from typing import List, Optional, Dict, Set
from pydantic import BaseModel, Field
from app.utils.agent.outline import OutlineSection
from uuid import uuid4

class Chunk(BaseModel):
    id: str
    text: str
    page: Optional[int]
    source: Optional[str]
    embedding: Optional[List[float]] = None

class ResearchNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    questions: List[str] = []
    generated_questions: List[str] = []
    chunks: List[Chunk] = []
    chunk_ids: Set[str] = set()

    content: Optional[str] = None
    summary: Optional[str] = None
    conclusion: Optional[str] = None
    is_final: bool = False

    parent: Optional["ResearchNode"] = None
    subnodes: List["ResearchNode"] = []

    rank: Optional[int] = None
    level: Optional[int] = None

    def __str__(self):
        return f"{self.title} : rank {self.rank} - level {self.level}"

    @property
    def display_rank(self) -> str:
        if not self.parent:
            return str(self.rank or 1)
        return f"{self.parent.display_rank}.{self.rank or 1}"

    @property
    def ranked_title(self):
        return f"{self.display_rank} {self.title}"

    @property
    def parent_title(self) -> Optional[str]:
        if self.parent:
            return f"{self.parent.title}"
        return None

    @staticmethod
    def from_outline_section(section: OutlineSection, parent_rank: str = "") -> "ResearchNode":
        rank = f"{parent_rank}.{len(section.subsections) + 1}" if parent_rank else "1"
        node = ResearchNode(
            title=section.heading,
            questions=section.questions,
            rank=rank,
            subnodes=[ResearchNode.from_outline_section(sub, rank) for sub in section.subsections]
        )
        return node

    def add_subnode(self, node: "ResearchNode"):
        node.parent = self
        self.subnodes.append(node)

    def walk(self) -> List["ResearchNode"]:
        nodes = [self]
        for sub in self.subnodes:
            nodes.extend(sub.walk())
        return nodes

    def mark_final(self):
        self.is_final = True

ResearchNode.update_forward_refs()

class ResearchTree(BaseModel):
    query: str
    root_node: ResearchNode
    used_questions: Set[str] = set()
    used_chunk_ids: Set[str] = set()

    def save_to_db(self, db, session_id: str):
        from app.db.models.research_node_orm import ResearchNodeORM
        def _save_node(node, parent_id=None):
            db_node = ResearchNodeORM(
                id=node.id,
                session_id=session_id,
                parent_id=parent_id,
                title=node.title,
                content=node.content,
                summary=node.summary,
                conclusion=node.conclusion,
                rank=node.rank,
                level=node.level,
                is_final=node.is_final,
            )
            db.add(db_node)
            db.flush()
            for child in node.subnodes:
                _save_node(child, parent_id=db_node.id)
        _save_node(self.root_node)
        db.commit()

    @staticmethod
    def load_from_db(db, session_id: str) -> "ResearchTree":
        from app.db.models.research_node_orm import ResearchNodeORM
        all_nodes = db.query(ResearchNodeORM).filter_by(session_id=session_id).all()
        node_map = {str(node.id): node for node in all_nodes}

        for node in all_nodes:
            if node.parent_id:
                parent = node_map[str(node.parent_id)]
                parent.children.append(node)

        root_orm = next((n for n in all_nodes if n.parent_id is None), None)
        if not root_orm:
            raise ValueError("No root node found")

        def _to_research_node(orm_node):
            node = ResearchNode(
                id=str(orm_node.id),
                title=orm_node.title,
                content=orm_node.content,
                summary=orm_node.summary,
                conclusion=orm_node.conclusion,
                rank=orm_node.rank,
                level=orm_node.level,
                is_final=orm_node.is_final,
                subnodes=[]
            )
            node.subnodes = [_to_research_node(child) for child in orm_node.children]
            for child in node.subnodes:
                child.parent = node
            return node

        root_node = _to_research_node(root_orm)
        return ResearchTree(root_node=root_node, query="")
