from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from itertools import combinations
from textwrap import dedent
from typing import Iterable

from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.db.models.research_node_orm import ResearchNodeORM
from app.models.research_tree import ResearchNode, ResearchTree


logger = logging.getLogger(__name__)

_OVERLAP_LLM = ChatOpenAI(model="gpt-4o-mini", temperature=0, timeout=90)
_TOKEN_RE = re.compile(r"\w+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "is", "are", "was", "were", "be",
    "de", "het", "een", "en", "of", "van", "te", "op", "in", "is", "zijn", "was", "waren", "met", "dat",
}
_STYLE_GUIDANCE = {
    "scientific_article": "Use a formal scientific style and keep claims explicitly evidence-grounded.",
    "blogpost": "Use a concise blog style with clear takeaways and no unnecessary jargon.",
    "newspaper": "Use concise newspaper style and prioritize key facts first.",
}


@dataclass(frozen=True)
class OverlapDecision:
    parent_title: str
    primary_title: str
    secondary_title: str
    action: str  # keep | rewrite_secondary | prune_secondary
    reason: str
    similarity: float
    chunk_overlap: float

    def to_dict(self) -> dict:
        return asdict(self)


def _tokenize(text: str) -> set[str]:
    tokens = {token for token in _TOKEN_RE.findall((text or "").lower()) if len(token) >= 3}
    return {token for token in tokens if token not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    seq_ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    token_ratio = _jaccard(_tokenize(a), _tokenize(b))
    return (0.55 * seq_ratio) + (0.45 * token_ratio)


def _chunk_overlap_ratio(a: ResearchNode, b: ResearchNode) -> float:
    chunk_ids_a = set(a.chunk_ids or set())
    chunk_ids_b = set(b.chunk_ids or set())
    if not chunk_ids_a or not chunk_ids_b:
        return 0.0
    return len(chunk_ids_a & chunk_ids_b) / max(min(len(chunk_ids_a), len(chunk_ids_b)), 1)


def _node_strength(node: ResearchNode) -> float:
    chunk_count = len(node.chunk_ids or [])
    question_count = len(node.questions or [])
    source_count = len({chunk.source for chunk in (node.chunks or []) if chunk.source})
    content_len = len((node.content or "").strip())
    length_bonus = 1 if content_len >= 900 else 0
    return (2.0 * chunk_count) + question_count + source_count + length_bonus


def _choose_primary_secondary(a: ResearchNode, b: ResearchNode) -> tuple[ResearchNode, ResearchNode]:
    strength_a = _node_strength(a)
    strength_b = _node_strength(b)
    if strength_a > strength_b:
        return a, b
    if strength_b > strength_a:
        return b, a
    rank_a = a.rank or 10_000
    rank_b = b.rank or 10_000
    return (a, b) if rank_a <= rank_b else (b, a)


def _is_weak_secondary(primary: ResearchNode, secondary: ResearchNode) -> bool:
    primary_strength = _node_strength(primary)
    secondary_strength = _node_strength(secondary)
    return secondary_strength < max(3.0, primary_strength * 0.75)


def _normalize_output_style(output_style: str | None) -> str:
    key = (output_style or "scientific_article").strip().lower()
    if key in {"blog", "blogpost"}:
        return "blogpost"
    if key in {"newspaper", "news"}:
        return "newspaper"
    return "scientific_article"


def _rewrite_secondary_to_reduce_overlap(
    *,
    root_query: str,
    output_style: str,
    length_hint: str,
    primary: ResearchNode,
    secondary: ResearchNode,
) -> str:
    style_key = _normalize_output_style(output_style)
    style_guidance = _STYLE_GUIDANCE.get(style_key, _STYLE_GUIDANCE["scientific_article"])
    secondary_questions = "\n".join(f"- {question}" for question in (secondary.questions or [])) or "- (none)"
    secondary_context = "\n\n".join(chunk.text for chunk in (secondary.chunks or [])[:10])

    prompt = dedent(
        f"""
        You are an editor reducing overlap between sibling sections.
        Keep only what is unique and still relevant to the root question.

        ROOT QUESTION:
        {root_query}

        PRIMARY SECTION (already covered):
        Title: {primary.title}
        Content:
        {primary.content or "(empty)"}

        SECONDARY SECTION (revise this one):
        Title: {secondary.title}
        Questions:
        {secondary_questions}

        SECONDARY EVIDENCE:
        {secondary_context or "(no evidence available)"}

        Constraints:
        - Remove points already covered by the primary section.
        - Keep only unique angles that still answer the root question.
        - If nothing unique remains, return exactly: __PRUNE__
        - Output style: {style_guidance}
        - Length target: {length_hint}
        - No heading, only section body text.
        """
    ).strip()

    rewritten = _OVERLAP_LLM.invoke(prompt).content.strip()
    return rewritten


def _prune_node_content(node: ResearchNode) -> None:
    node.content = None
    node.summary = None
    node.conclusion = None
    node.is_final = True


def _set_node_content(node: ResearchNode, content: str) -> None:
    node.content = content.strip()
    node.summary = None
    node.conclusion = None
    node.is_final = True


def _resolve_parent_sibling_overlap(
    parent: ResearchNode,
    *,
    root_query: str,
    output_style: str,
    length_hint: str,
) -> tuple[list[OverlapDecision], set[str]]:
    decisions: list[OverlapDecision] = []
    changed_node_ids: set[str] = set()
    siblings = [child for child in (parent.subnodes or []) if (child.content or "").strip()]
    if len(siblings) < 2:
        return decisions, changed_node_ids

    for left, right in combinations(siblings, 2):
        left_content = (left.content or "").strip()
        right_content = (right.content or "").strip()
        if not left_content or not right_content:
            continue

        similarity = _text_similarity(left_content, right_content)
        chunk_overlap = _chunk_overlap_ratio(left, right)
        if similarity < 0.57 and chunk_overlap < 0.50:
            continue

        primary, secondary = _choose_primary_secondary(left, right)
        secondary_before = (secondary.content or "").strip()
        reason = f"similarity={similarity:.2f}, chunk_overlap={chunk_overlap:.2f}"

        if similarity >= 0.82 and _is_weak_secondary(primary, secondary):
            _prune_node_content(secondary)
            changed_node_ids.add(str(secondary.id))
            decisions.append(
                OverlapDecision(
                    parent_title=parent.title,
                    primary_title=primary.title,
                    secondary_title=secondary.title,
                    action="prune_secondary",
                    reason=f"high overlap and weaker secondary ({reason})",
                    similarity=similarity,
                    chunk_overlap=chunk_overlap,
                )
            )
            continue

        rewritten = _rewrite_secondary_to_reduce_overlap(
            root_query=root_query,
            output_style=output_style,
            length_hint=length_hint,
            primary=primary,
            secondary=secondary,
        )
        if rewritten == "__PRUNE__" or not rewritten.strip():
            _prune_node_content(secondary)
            changed_node_ids.add(str(secondary.id))
            decisions.append(
                OverlapDecision(
                    parent_title=parent.title,
                    primary_title=primary.title,
                    secondary_title=secondary.title,
                    action="prune_secondary",
                    reason=f"rewrite indicated no unique content ({reason})",
                    similarity=similarity,
                    chunk_overlap=chunk_overlap,
                )
            )
            continue

        rewritten_similarity = _text_similarity(primary.content or "", rewritten)
        improved = rewritten_similarity <= max(0.72, similarity - 0.06)
        if not improved and _is_weak_secondary(primary, secondary):
            _prune_node_content(secondary)
            changed_node_ids.add(str(secondary.id))
            decisions.append(
                OverlapDecision(
                    parent_title=parent.title,
                    primary_title=primary.title,
                    secondary_title=secondary.title,
                    action="prune_secondary",
                    reason=f"rewrite did not sufficiently reduce overlap ({reason})",
                    similarity=similarity,
                    chunk_overlap=chunk_overlap,
                )
            )
            continue

        if rewritten.strip() != secondary_before:
            _set_node_content(secondary, rewritten)
            changed_node_ids.add(str(secondary.id))
            decisions.append(
                OverlapDecision(
                    parent_title=parent.title,
                    primary_title=primary.title,
                    secondary_title=secondary.title,
                    action="rewrite_secondary",
                    reason=(
                        f"overlap reduced from {similarity:.2f} to {rewritten_similarity:.2f}; "
                        f"chunk_overlap={chunk_overlap:.2f}"
                    ),
                    similarity=similarity,
                    chunk_overlap=chunk_overlap,
                )
            )

    return decisions, changed_node_ids


def reduce_tree_overlap(
    tree: ResearchTree,
    *,
    root_query: str,
    output_style: str,
    length_hint: str,
) -> tuple[list[OverlapDecision], list[ResearchNode]]:
    decisions: list[OverlapDecision] = []
    changed_node_ids: set[str] = set()
    node_map = {str(node.id): node for node in tree.all_nodes()}

    def walk(parent: ResearchNode) -> None:
        local_decisions, local_changed_ids = _resolve_parent_sibling_overlap(
            parent,
            root_query=root_query,
            output_style=output_style,
            length_hint=length_hint,
        )
        decisions.extend(local_decisions)
        changed_node_ids.update(local_changed_ids)

        for child in parent.subnodes or []:
            walk(child)

    walk(tree.root_node)
    changed_nodes = [node_map[node_id] for node_id in changed_node_ids if node_id in node_map]
    return decisions, changed_nodes


def persist_overlap_changes(db: Session, changed_nodes: Iterable[ResearchNode]) -> None:
    for node in changed_nodes:
        db.query(ResearchNodeORM).filter(ResearchNodeORM.id == node.id).update(
            {
                ResearchNodeORM.content: node.content,
                ResearchNodeORM.summary: node.summary,
                ResearchNodeORM.conclusion: node.conclusion,
                ResearchNodeORM.is_final: node.is_final,
            },
            synchronize_session=False,
        )
    db.flush()

