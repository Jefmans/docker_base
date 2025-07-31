from typing import List, Optional, Dict, Set
from pydantic import BaseModel
from app.utils.agent.outline import OutlineSection



class Chunk(BaseModel):
    id: str
    text: str
    page: Optional[int]
    source: Optional[str]
    embedding: Optional[List[float]] = None


class ResearchNode(BaseModel):
    title: str
    questions: List[str] = []
    generated_questions: List[str] = []  # New: track subquestions
    chunks: List[Chunk] = []
    chunk_ids: Set[str] = set()  # New: track used chunk IDs

    content: Optional[str] = None
    summary: Optional[str] = None
    conclusion: Optional[str] = None
    is_final: bool = False

    parent: Optional["ResearchNode"] = None
    subnodes: List["ResearchNode"] = []

    @staticmethod
    def from_outline_section(section: OutlineSection) -> "ResearchNode":
        return ResearchNode(
            title=section.heading,
            questions=section.questions,
            subnodes=[
                ResearchNode.from_outline_section(sub)
                for sub in section.subsections
            ]
        )

    class Config:
        arbitrary_types_allowed = True
        # underscore_attrs_are_private = True
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
    def node_from_outline_section(section: OutlineSection) -> ResearchNode:
        node = ResearchNode(
            title=section.heading,
            questions=section.questions,
            generated_questions=[],
            chunks=[],
            is_final=False,
        )
        # Recursively add subsections
        for sub in section.subsections or []:
            node.add_subnode(ResearchTree.node_from_outline_section(sub))
        return node


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

        return f"\"\"\n\\documentclass{{article}}\n\\usepackage[utf8]{{inputenc}}\n\\usepackage{{hyperref}}\n\\title{{{escape_latex(self.query)}}}\n\\begin{{document}}\n\\maketitle\n\n{body}\n\n\\end{{document}}\n\"\""


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
