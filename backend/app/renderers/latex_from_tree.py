# app/renderers/latex_from_tree.py
from __future__ import annotations
from typing import Any, Dict
from textwrap import dedent
import json
import re

from app.models.research_tree import ResearchTree, ResearchNode
from langchain_openai import ChatOpenAI

# Keep the LLM deterministic
_LLM = ChatOpenAI(model="gpt-4o", temperature=0)

_FORBIDDEN = [
    r'\\write18', r'\\input\{', r'\\include\{', r'\\openout', r'\\read',
    r'\\csname', r'\\catcode', r'\\def', r'\\newcommand',
]

def _sanitize(tex: str) -> str:
    for pat in _FORBIDDEN:
        tex = re.sub(pat, '', tex, flags=re.IGNORECASE)
    return tex.strip()

def _compact_tree(tree: ResearchTree, max_chunk_chars: int = 800) -> Dict[str, Any]:
    """
    Serialize the tree to a compact JSON the LLM can digest.
    We keep structure + prose + (optionally) a few source hints per node.
    """
    def node_to_dict(n: ResearchNode) -> Dict[str, Any]:
        # Keep main prose fields verbatim
        out = {
            "title": n.title,
            "rank": n.rank,
            "level": n.level,
            "display_rank": n.display_rank,
            "goals": (n.goals or ""),
            "content": (n.content or ""),
            "summary": (n.summary or ""),
            "conclusion": (n.conclusion or ""),
            "questions": list(n.questions or []),
            # Include some (source, page) pairs as hints — the LLM can footnote them
            "sources": [],
            "subnodes": [],
        }
        # If chunks are present in-memory, include a few source hints
        # (If not, this just stays empty and that’s fine.)
        hints = []
        for c in (n.chunks or [])[:8]:
            hints.append({"source": c.source or "", "page": c.page})
        out["sources"] = hints

        out["subnodes"] = [node_to_dict(sn) for sn in (n.subnodes or [])]
        return out

    return {
        "query": tree.query,
        "root": node_to_dict(tree.root_node),
    }

_PROMPT = """\
You are a LaTeX typesetter for scientific articles.

You will receive a JSON-serialized research tree with:
- A root node (the article), with nested section nodes (subsections).
- Each node has: title, rank/level, optional goals/content/summary/conclusion, optional questions,
  and optional (source,page) hints.

TASK:
Produce a single, compilable LaTeX document **including preamble** that renders this article.

STRICT RULES:
- Use this exact preamble (no extra packages, no changes):

\\documentclass[11pt]{article}
\\usepackage[utf8]{inputenc}
\\usepackage[T1]{fontenc}
\\usepackage{hyperref}
\\usepackage{geometry}
\\geometry{margin=1in}

- After \\begin{document}:
  - Title = root title (or fallback to the query if empty), then \\maketitle
  - Then render all sections from the tree, preserving hierarchy:
    level 1 -> \\section, level 2 -> \\subsection, level 3 -> \\subsubsection, level >=4 -> \\paragraph
  - For each node, render (if present) in this order:
    1) main prose from `content` (plain paragraphs)
    2) a short bolded “Summary:” line if `summary` present
    3) a short bolded “Conclusion:” line if `conclusion` present
    4) optionally a footnotesize “Sources:” line constructed from (source, page) hints (e.g. “Sources: Book A, p.12; Paper B, p.7.”)
- DO NOT use figures, tables, bibliographies, \\cite, \\includegraphics, or custom macros.
- Keep text as plain paragraphs (no itemize/enumerate).
- Escape LaTeX special characters if needed in prose.
- Never invent sources/pages—only use the given hints.

Now generate the full LaTeX document.

=== RESEARCH TREE JSON ===
{tree_json}
"""

def to_latex_via_llm(tree: ResearchTree) -> str:
    # Prefer the in-memory tree; if nodes don’t carry chunks, it’s fine — we render prose/structure anyway.
    data = _compact_tree(tree)
    # If the root title is empty, let the prompt tell the LLM to fallback to the query
    tree_json = json.dumps(data, ensure_ascii=False)

    tex = _LLM.invoke(
        dedent(_PROMPT).format(tree_json=tree_json)
    ).content

    return _sanitize(tex)
