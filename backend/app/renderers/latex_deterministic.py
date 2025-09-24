from __future__ import annotations
from textwrap import dedent
from typing import Iterable
import re

from app.models.research_tree import ResearchTree, ResearchNode

# --- Escaping / sanitization ---

_LATEX_ESC_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

_FORBIDDEN_BODY = [
    r"\\documentclass", r"\\usepackage", r"\\input\{", r"\\include\{",
    r"\\write18", r"\\openout", r"\\read", r"\\csname", r"\\catcode",
    r"\\def", r"\\newcommand", r"\\includegraphics",
    r"\\begin\{figure\}", r"\\begin\{table\}", r"\\bibliography",
    r"\\addbibresource", r"\\begin\{thebibliography\}",
]

def _esc_text(s: str) -> str:
    """Escape LaTeX specials in plain text. Keep simple newlines."""
    if not s:
        return ""
    out = []
    for ch in s:
        out.append(_LATEX_ESC_MAP.get(ch, ch))
    return "".join(out)

def _sanitize_body(s: str) -> str:
    """Remove dangerous LaTeX primitives if they slipped into content."""
    if not s:
        return ""
    for pat in _FORBIDDEN_BODY:
        s = re.sub(pat, "", s, flags=re.IGNORECASE)
    return s

# --- Structure helpers ---

def _heading_cmd(level: int) -> str:
    if level <= 1: return "section"
    if level == 2: return "subsection"
    if level == 3: return "subsubsection"
    return "paragraph"

def _sources_line(node: ResearchNode, max_pairs: int = 8) -> str:
    pairs = []
    for c in (node.chunks or []):
        if c.source and (c.page is not None):
            pairs.append((str(c.source), int(c.page)))
    if not pairs:
        return ""
    # de-dup + stable-ish order
    pairs = sorted(set(pairs))[:max_pairs]
    items = "; ".join(f"{_esc_text(src)}, p.{pg}" for src, pg in pairs)
    return rf"\footnotesize\emph{{Sources: {items}.}}\normalsize"

# --- Rendering ---

def _render_node(node: ResearchNode) -> str:
    parts = []
    cmd = _heading_cmd(node.level or 1)
    parts.append(rf"\{cmd}{{{_esc_text(node.title or '')}}}" + "\n")

    if node.content:
        parts.append(_sanitize_body(_esc_text(node.content)) + "\n")

    # no per-node summary/conclusion

    sl = _sources_line(node)
    if sl:
        parts.append(sl + "\n")

    for child in (node.subnodes or []):
        parts.append(_render_node(child))

    return "".join(parts)

def to_latex_deterministic(tree: ResearchTree) -> str:
    title = tree.root_node.title or tree.query

    preamble = dedent(rf"""
    \documentclass[11pt]{{article}}
    \usepackage[utf8]{{inputenc}}
    \usepackage[T1]{{fontenc}}
    \usepackage{{hyperref}}
    \usepackage{{geometry}}
    \geometry{{margin=1in}}
    \title{{{_esc_text(title)}}}
    \date{{}}
    \begin{{document}}
    \maketitle
    """).strip("\n") + "\n"

    # Executive Summary (root only)
    exec_summary = tree.root_node.summary or ""
    exec_block = ""
    if exec_summary.strip():
        exec_block = "\\section*{Executive Summary}\n" + _sanitize_body(_esc_text(exec_summary)) + "\n\n"

    # Optional Abstract from root.content
    abstract_block = ""
    if (tree.root_node.content or "").strip():
        abstract_block = "\\section*{Abstract}\n" + _sanitize_body(_esc_text(tree.root_node.content)) + "\n\n"

    body = _render_node(tree.root_node)

    # Overall Conclusion (root only)
    overall = tree.root_node.conclusion or ""
    concl_block = ""
    if overall.strip():
        concl_block = "\n\\section*{Overall Conclusion}\n" + _sanitize_body(_esc_text(overall)) + "\n"

    end = "\\end{document}\n"
    return preamble + exec_block + abstract_block + body + concl_block + end

