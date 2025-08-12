from typing import List, Optional, Dict, Set
from pydantic import BaseModel, Field
from app.models.outline_model import OutlineSection
from uuid import uuid4
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models.research_node_orm import ResearchNodeORM  # adjust path if needed
# add imports at the top of the file
from app.db.models.node_question_orm import NodeQuestionORM
from app.db.models.question_orm import QuestionORM
from app.db.models.node_chunk_orm import NodeChunkORM
from app.db.models.chunk_orm import ChunkORM



class Chunk(BaseModel):
    id: str
    text: str
    page: Optional[int]
    source: Optional[str]
    embedding: Optional[List[float]] = None

class ResearchNode(BaseModel):
    id: UUID = Field(default_factory=uuid4)  # ✅ Use UUID directly
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

    rank: Optional[int] = 0
    level: Optional[int] = 0

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


    @classmethod
    def from_orm_model(cls, orm_node: ResearchNodeORM) -> "ResearchNode":
        return cls(
            id=orm_node.id,
            title=orm_node.title,
            content=orm_node.content,
            summary=orm_node.summary,
            conclusion=orm_node.conclusion,
            rank=orm_node.rank,
            level=orm_node.level,
            is_final=orm_node.is_final,
            questions=[],
            generated_questions=[],
            chunks=[],
            chunk_ids=set(),
            subnodes=[]
        )


    @staticmethod
    def from_outline_section(section: OutlineSection, parent_rank: str = "") -> "ResearchNode":
        # Generate the new rank based on the parent rank and current level
        rank = f"{parent_rank}.{len(section.subsections) + 1}" if parent_rank else "1"

        node = ResearchNode(
            title=section.heading,
            questions=section.questions,
            rank=rank,  # Track the rank here
            subnodes=[ResearchNode.from_outline_section(sub, rank) for sub in section.subsections]
        )
        return node


    class Config:
        arbitrary_types_allowed = True


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

    def mark_final(self):
        self.is_final = True

    def needs_more_chunks(self, threshold: int = 3) -> bool:
        return len(self.chunks) < threshold

    def needs_expansion(self) -> bool:
        return not self.content or self.needs_more_chunks() or not self.summary
        

ResearchNode.update_forward_refs()

class ResearchTree(BaseModel):
    query: str
    root_node: ResearchNode
    used_questions: Set[str] = set()
    used_chunk_ids: Set[str] = set()
    
    class Config:
        arbitrary_types_allowed = True

    def add_subnode(self, parent_title: str, subnode_data: dict):
        parent_node = self.root_node.find_node_by_title(parent_title)
        if parent_node:
            subnode = ResearchNode(**subnode_data)
            parent_node.add_subnode(subnode)

    def deduplicate_all(self):
        self._deduplicate_chunks()
        self._deduplicate_questions()

    def _deduplicate_chunks(self):
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
        self.used_chunk_ids = seen_ids

    def _deduplicate_questions(self):
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
        self.used_questions = seen
        
    @staticmethod
    def node_from_outline_section(
        section: OutlineSection
    ) -> ResearchNode:
        node = ResearchNode(
            title=section.heading,
            questions=section.questions,
            subnodes=[
                ResearchTree.node_from_outline_section(sub)
                for sub in section.subsections or []
            ]
        )
        return node


    
    def assign_rank_and_level(self):
        def _assign(node: ResearchNode, parent: Optional[ResearchNode], level: int):
            node.parent = parent
            node.level = level
            for i, sub in enumerate(node.subnodes):
                sub.rank = i + 1
                _assign(sub, node, level + 1)

        self.root_node.rank = 1
        self.root_node.level = 1
        self.root_node.parent = None
        _assign(self.root_node, None, 0)





    def to_markdown(self) -> str:
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

    def to_html(self) -> str:
        def walk(node: ResearchNode, level: int = 2) -> str:
            text = f"<h{level}>{node.title}</h{level}>\n"
            if node.content:
                text += f"<p>{node.content.strip()}</p>\n"
            if node.summary:
                text += f"<p><strong>Summary:</strong> {node.summary.strip()}</p>\n"
            if node.conclusion:
                text += f"<p><strong>Conclusion:</strong> {node.conclusion.strip()}</p>\n"
            for sn in node.subnodes:
                text += walk(sn, level + 1)
            return text

        return f"<h1>Research Article</h1>\n<h2>Query</h2><p>{self.query}</p>\n" + walk(self.root_node)

    def all_nodes(self) -> List[ResearchNode]:
        nodes = []
        def walk(node: ResearchNode):
            nodes.append(node)
            for sn in node.subnodes:
                walk(sn)
        walk(self.root_node)
        return nodes

    def model_dump_jsonable(self):
        def clean_node(node):
            return {
                "title": node.title,
                "rank": node.rank,
                "level": node.level,
                "parent_rank":node.parent.rank if node.parent else None,
                "parent_level":node.parent.level if node.parent else None,
                "display_rank": node.display_rank, # ✅ computed property
                # "ranked_title": node.ranked_title,  # ✅ computed property
                "questions": node.questions,
                "generated_questions": node.generated_questions,
                "chunks": [c.dict() for c in node.chunks],
                "chunk_ids": list(node.chunk_ids),
                "content": node.content,
                "summary": node.summary,
                "conclusion": node.conclusion,
                "is_final": node.is_final,
                "subnodes": [clean_node(sn) for sn in node.subnodes]
            }

        return {
            "query": self.query,
            "root_node": clean_node(self.root_node),
            "used_questions": list(self.used_questions),
            "used_chunk_ids": list(self.used_chunk_ids)
    }

    def to_latex(self) -> str:
        def escape_latex(text: str) -> str:
            replacements = {
                "&": "\\&", "%": "\\%", "$": "\\$", "#": "\\#",
                "_": "\\_", "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}",
                "^": "\\textasciicircum{}", "\\": "\\textbackslash{}",
            }
            for key, val in replacements.items():
                text = text.replace(key, val)
            return text

        def walk(node, level: int = 1) -> str:
            parts = []
            section_cmd = ["section", "subsection", "subsubsection", "paragraph"]
            cmd = section_cmd[min(level, len(section_cmd)-1)]

            parts.append(f"\\{cmd}{{{escape_latex(node.title)}}}\n")
            if node.content:
                parts.append(escape_latex(node.content) + "\n")
            if node.summary:
                parts.append(f"\\textbf{{Summary}}: {escape_latex(node.summary)}\n")
            if node.conclusion:
                parts.append(f"\\textbf{{Conclusion}}: {escape_latex(node.conclusion)}\n")

            for chunk in node.chunks:
                if chunk.source and chunk.page is not None:
                    parts.append(f"\\textit{{[source: {escape_latex(chunk.source)}, page {chunk.page}]}}\n")

            for sub in node.subnodes:
                parts.append(walk(sub, level + 1))
            return "\n".join(parts)

        body = walk(self.root_node)
        return f"\\documentclass{{article}}\n\\usepackage[utf8]{{inputenc}}\n\\title{{{escape_latex(self.query)}}}\n\\begin{{document}}\n\\maketitle\n\n{body}\n\n\\end{{document}}"

    def to_latex_styled(self) -> str:
        import re

        def escape_latex(text: str) -> str:
            replacements = {
                "&": "\\&", "%": "\\%", "$": "\\$", "#": "\\#",
                "_": "\\_", "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}",
                "^": "\\textasciicircum{}", "\\": "\\textbackslash{}",
            }
            for key, val in replacements.items():
                text = text.replace(key, val)
            return text

        def clean_text(text: str) -> str:
            return text.replace("\\", "").replace("\n", " ").strip()

        def walk(node, level=1) -> str:
            parts = []
            # Clean and strip title
            title_raw = clean_text(node.title)
            print('title raw: ', title_raw)
            title_clean = re.sub(r"^\d+(?:\.\d+)*\s*", "", title_raw)  # Remove 0.1.2 prefix
            print('title clean 1: ', title_clean)
            title_clean = re.sub(r"^\\+", "", title_clean)  # Remove starting backslashes
            print('title clean 2: ', title_clean)
            title_clean = title_clean.replace("\\", "")
            print('title clean 3: ', title_clean)
            title = escape_latex(title_clean)
            print('title: ', title)

            section_cmd = ["section", "subsection", "subsubsection", "paragraph"]
            cmd = section_cmd[min(level, len(section_cmd)-1)]
            parts.append(f"\\{cmd}{{{title}}}\n")

            if node.content:
                content_clean = escape_latex(clean_text(node.content))
                parts.append(content_clean + "\n")
            if node.summary:
                summary_clean = escape_latex(clean_text(node.summary))
                parts.append(f"\\textbf{{Summary}}: {summary_clean}\n")
            if node.conclusion:
                conclusion_clean = escape_latex(clean_text(node.conclusion))
                parts.append(f"\\textbf{{Conclusion}}: {conclusion_clean}\n")

            for chunk in node.chunks:
                if chunk.source and chunk.page is not None:
                    src = escape_latex(chunk.source)
                    parts.append(f"\\textit{{[source: {src}, page {chunk.page}]}}\n")

            for sub in node.subnodes:
                parts.append(walk(sub, level + 1))

            return "\n".join(parts)

        body = walk(self.root_node)
        return f"""
    \\documentclass{{article}}
    \\usepackage[utf8]{{inputenc}}
    \\usepackage{{hyperref}}
    \\usepackage{{geometry}}
    \\usepackage{{titlesec}}
    \\geometry{{margin=1in}}
    \\titleformat{{\\section}}{{\\Large\\bfseries}}{{\\thesection}}{{1em}}{{}}
    \\title{{{escape_latex(self.query)}}}
    \\begin{{document}}
    \\maketitle
    \\tableofcontents
    \\newpage

    {body}
    \\end{{document}}
    """

    def save_to_db(self, db, session_id: str):
        from app.db.models.research_node_orm import ResearchNodeORM

        def _save_or_update_node(node: ResearchNode, parent_id=None):
            # Check if the node exists
            db_node = db.query(ResearchNodeORM).filter_by(id=node.id).first()

            if db_node:
                # ✅ Update existing fields
                db_node.title = node.title
                db_node.content = node.content
                db_node.summary = node.summary
                db_node.conclusion = node.conclusion
                db_node.rank = node.rank
                db_node.level = node.level
                db_node.is_final = node.is_final
                db_node.parent_id = parent_id
            else:
                # ✅ Create new node
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

            # Recurse into subnodes
            for child in node.subnodes:
                _save_or_update_node(child, parent_id=db_node.id)

        _save_or_update_node(self.root_node)
        db.commit()



    @classmethod
    def load_from_db(cls, db: Session, session_id: str) -> "ResearchTree":
        try:
            session_uuid = session_id
        except ValueError:
            raise ValueError("Invalid session_id format; must be a valid UUID")

        root_orm = (
            db.query(ResearchNodeORM)
            .filter(ResearchNodeORM.session_id == session_uuid,
                    ResearchNodeORM.parent_id == None)  # noqa: E711
            .first()
        )
        if not root_orm:
            raise ValueError("No root node found")

        all_orm_nodes = (
            db.query(ResearchNodeORM)
            .filter(ResearchNodeORM.session_id == session_uuid)
            .all()
        )

        # Build id → node map
        node_map = {}
        for orm_node in all_orm_nodes:
            node = ResearchNode.from_orm_model(orm_node)
            node_map[node.id] = node

        # Link children
        for orm_node in all_orm_nodes:
            if orm_node.parent_id:
                parent = node_map[orm_node.parent_id]
                parent.subnodes.append(node_map[orm_node.id])

        # 🔥 HYDRATE QUESTIONS & CHUNKS FROM ORM
        node_ids = list(node_map.keys())

        # Questions (bulk)
        q_rows = (
            db.query(NodeQuestionORM.node_id, QuestionORM.text)
            .join(QuestionORM, QuestionORM.id == NodeQuestionORM.question_id)
            .filter(NodeQuestionORM.node_id.in_(node_ids))
            .all()
        )
        # group per node
        q_by_node = {}
        for nid, qtext in q_rows:
            q_by_node.setdefault(nid, []).append(qtext)

        # Chunks (bulk)
        c_rows = (
            db.query(NodeChunkORM.node_id, ChunkORM.id, ChunkORM.text, ChunkORM.page, ChunkORM.source)
            .join(ChunkORM, ChunkORM.id == NodeChunkORM.chunk_id)
            .filter(NodeChunkORM.node_id.in_(node_ids))
            .all()
        )
        c_by_node = {}
        for nid, cid, ctext, cpage, csrc in c_rows:
            c_by_node.setdefault(nid, []).append(Chunk(id=cid, text=ctext, page=cpage, source=csrc))

        # Set hydrated data on each node
        for nid, node in node_map.items():
            node.questions = q_by_node.get(nid, [])
            node.chunks = c_by_node.get(nid, [])
            node.chunk_ids = {c.id for c in node.chunks}

        root_node = node_map[root_orm.id]
        return cls(query=root_node.title, root_node=root_node)
