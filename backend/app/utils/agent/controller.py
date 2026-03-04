from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List

from app.db.models.node_question_orm import NodeQuestionORM
from app.db.models.question_orm import QuestionORM, QuestionStatus
from app.db.models.research_node_orm import ResearchNodeORM
from app.models.research_tree import ResearchNode, ResearchPlan
from app.utils.agent.planning import (
    node_context_chunk_limit,
    node_retrieval_top_k,
    node_should_attempt_depth,
    node_subquestion_target,
)
from app.utils.agent.repo import get_node_questions


@dataclass(frozen=True)
class NodeEvidenceProfile:
    retrieved_chunk_count: int
    unique_chunk_count: int
    unique_source_count: int
    unique_page_count: int
    question_count: int
    duplicate_ratio: float
    evidence_density: str
    has_meaningful_support: bool


@dataclass(frozen=True)
class NodeExecutionPlan:
    retrieval_top_k: int
    context_chunk_limit: int
    subquestion_target: int
    min_novel_questions_to_deepen: int
    section_length_hint: str
    should_attempt_depth: bool
    evidence_density: str


@dataclass(frozen=True)
class NodeRefinementDecision:
    should_deepen: bool
    novel_questions: List[str]
    reason: str


def _similar(a: str, b: str, thresh: float) -> bool:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio() >= thresh


def _is_novel(candidate: str, against: List[str], thresh: float) -> bool:
    return all(not _similar(candidate, ex, thresh) for ex in against)


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def build_node_evidence_profile(node: ResearchNode, chunk_dicts: list[dict]) -> NodeEvidenceProfile:
    chunk_count = len(chunk_dicts)
    unique_ids = {chunk.get("id") for chunk in chunk_dicts if chunk.get("id")}
    unique_sources = {chunk.get("source") for chunk in chunk_dicts if chunk.get("source")}
    unique_pages = {
        (chunk.get("source"), chunk.get("page"))
        for chunk in chunk_dicts
        if chunk.get("page") is not None
    }

    unique_chunk_count = len(unique_ids) or chunk_count
    duplicate_ratio = 0.0
    if chunk_count:
        duplicate_ratio = max(chunk_count - unique_chunk_count, 0) / chunk_count

    if unique_chunk_count >= 10 or (unique_chunk_count >= 8 and len(unique_sources) >= 2):
        evidence_density = "rich"
    elif unique_chunk_count >= 5 or len(unique_pages) >= 4:
        evidence_density = "moderate"
    else:
        evidence_density = "sparse"

    has_meaningful_support = unique_chunk_count >= 3 or (
        len(unique_sources) >= 2 and unique_chunk_count >= 2
    )

    return NodeEvidenceProfile(
        retrieved_chunk_count=chunk_count,
        unique_chunk_count=unique_chunk_count,
        unique_source_count=len(unique_sources),
        unique_page_count=len(unique_pages),
        question_count=len(node.questions or []),
        duplicate_ratio=duplicate_ratio,
        evidence_density=evidence_density,
        has_meaningful_support=has_meaningful_support,
    )


def build_node_execution_plan(
    node: ResearchNode,
    plan: ResearchPlan,
    evidence: NodeEvidenceProfile,
) -> NodeExecutionPlan:
    base_retrieval_top_k = node_retrieval_top_k(plan, node)
    base_context_limit = node_context_chunk_limit(plan, node)
    base_subquestion_target = node_subquestion_target(plan, node)
    base_should_attempt_depth = node_should_attempt_depth(plan, node)

    if evidence.evidence_density == "rich":
        retrieval_top_k = _clamp(base_retrieval_top_k + 2, 3, 24)
        context_limit = _clamp(base_context_limit + 2, 4, 26)
        subquestion_target = _clamp(base_subquestion_target + 1, 1, 9)
        min_novel = _clamp(max(1, plan.min_novel_questions_to_deepen), 1, 6)
        length_hint = "3-5 evidence-rich paragraphs"
        should_attempt_depth = base_should_attempt_depth and evidence.has_meaningful_support
    elif evidence.evidence_density == "moderate":
        retrieval_top_k = base_retrieval_top_k
        context_limit = base_context_limit
        subquestion_target = base_subquestion_target
        min_novel = max(1, plan.min_novel_questions_to_deepen)
        length_hint = plan.section_length_hint
        should_attempt_depth = base_should_attempt_depth and evidence.has_meaningful_support
    else:
        retrieval_top_k = _clamp(base_retrieval_top_k - 1, 3, 20)
        context_limit = _clamp(base_context_limit - 2, 3, 22)
        subquestion_target = _clamp(base_subquestion_target - 1, 1, 6)
        min_novel = 1
        length_hint = "1-2 short evidence-grounded paragraphs"
        should_attempt_depth = (
            base_should_attempt_depth
            and evidence.has_meaningful_support
            and evidence.unique_chunk_count >= 3
        )

    return NodeExecutionPlan(
        retrieval_top_k=retrieval_top_k,
        context_chunk_limit=context_limit,
        subquestion_target=subquestion_target,
        min_novel_questions_to_deepen=min_novel,
        section_length_hint=length_hint,
        should_attempt_depth=should_attempt_depth,
        evidence_density=evidence.evidence_density,
    )


def get_novel_expansion_questions(
    node,
    db,
    q_sim_thresh: float,
    title_sim_thresh: float,
) -> List[str]:
    """
    Returns the subset of this node's ASSIGNED expansion questions that are:
    - novel vs. this node's non-expansion questions
    - novel vs. all other nodes' questions in the same session
    - not overlapping with existing child titles
    """
    q_objs = get_node_questions(db, node.id)

    expansion_q = [
        q.text for q in q_objs
        if q.status == QuestionStatus.ASSIGNED and (q.source or "").lower() == "expansion"
    ]
    if not expansion_q:
        return []

    local_existing = [
        q.text for q in q_objs
        if (q.source or "").lower() != "expansion"
    ]

    rn = db.query(ResearchNodeORM).filter(ResearchNodeORM.id == node.id).first()
    if not rn:
        return []

    other_q_texts = (
        db.query(QuestionORM.text)
        .join(NodeQuestionORM, NodeQuestionORM.question_id == QuestionORM.id)
        .join(ResearchNodeORM, ResearchNodeORM.id == NodeQuestionORM.node_id)
        .filter(
            ResearchNodeORM.session_id == rn.session_id,
            ResearchNodeORM.id != node.id,
        )
        .all()
    )
    global_existing = [text for (text,) in other_q_texts]

    child_titles = [child.title for child in getattr(node, "subnodes", []) or []]

    novel = []
    for candidate in expansion_q:
        if not _is_novel(candidate, local_existing, q_sim_thresh):
            continue
        if not _is_novel(candidate, global_existing, q_sim_thresh):
            continue
        if not _is_novel(candidate, child_titles, title_sim_thresh):
            continue
        novel.append(candidate)

    return novel


def evaluate_node_refinement(
    node,
    db,
    *,
    evidence: NodeEvidenceProfile | None = None,
    similarity_threshold: float = 0.80,
    min_novel: int = 1,
    title_similarity_threshold: float = 0.70,
) -> NodeRefinementDecision:
    if evidence is not None:
        if not evidence.has_meaningful_support:
            return NodeRefinementDecision(
                should_deepen=False,
                novel_questions=[],
                reason="insufficient evidence support",
            )
        if evidence.evidence_density == "sparse" and evidence.unique_chunk_count < 4:
            return NodeRefinementDecision(
                should_deepen=False,
                novel_questions=[],
                reason="evidence too sparse",
            )

    novel_expansion = get_novel_expansion_questions(
        node,
        db,
        q_sim_thresh=similarity_threshold,
        title_sim_thresh=title_similarity_threshold,
    )
    if len(novel_expansion) < min_novel:
        return NodeRefinementDecision(
            should_deepen=False,
            novel_questions=novel_expansion,
            reason="not enough novel questions",
        )

    return NodeRefinementDecision(
        should_deepen=True,
        novel_questions=novel_expansion,
        reason="novel expansion available",
    )


def should_deepen_node(
    node,
    similarity_threshold: float = 0.80,
    min_novel: int = 2,
    title_similarity_threshold: float = 0.70,
    evidence: NodeEvidenceProfile | None = None,
) -> bool:
    from app.db.db import SessionLocal

    db = SessionLocal()
    try:
        decision = evaluate_node_refinement(
            node,
            db,
            evidence=evidence,
            similarity_threshold=similarity_threshold,
            min_novel=min_novel,
            title_similarity_threshold=title_similarity_threshold,
        )
        return decision.should_deepen
    finally:
        db.close()
