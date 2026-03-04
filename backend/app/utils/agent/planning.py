import re

from app.models.research_tree import ResearchNode, ResearchPlan, ResearchScope


_COMPLEXITY_TERMS = {
    "compare",
    "contrast",
    "evaluate",
    "synthesize",
    "mechanism",
    "mechanisms",
    "pathway",
    "pathways",
    "limitations",
    "future",
    "implications",
    "tradeoff",
    "trade-offs",
    "application",
    "applications",
    "history",
    "evolution",
}


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def estimate_query_complexity(query: str, scope: ResearchScope) -> int:
    tokens = re.findall(r"\w+", query.lower())
    token_count = len(tokens)
    distinct_terms = len(set(tokens))
    matched_terms = sum(1 for term in _COMPLEXITY_TERMS if term in tokens)

    score = 1
    if token_count >= 9:
        score += 1
    if token_count >= 16:
        score += 1
    if distinct_terms >= 10:
        score += 1
    if matched_terms >= 2:
        score += 1
    if scope.document_count >= 3:
        score += 1
    if scope.mode == "all":
        score += 1
    return _clamp(score, 1, 6)


def build_research_plan(query: str, scope: ResearchScope, *, requested_top_k: int = 5) -> ResearchPlan:
    complexity = estimate_query_complexity(query, scope)
    document_count = max(scope.document_count, len(scope.filenames), 1)
    broad_scope = scope.mode in {"project", "all"} or document_count > 1

    root_top_k = _clamp(max(requested_top_k, 4 + complexity + min(document_count, 4)), 4, 18)
    root_context_chunks = _clamp(6 + complexity + min(document_count, 3), 6, 16)
    root_subquestion_target = _clamp(3 + complexity + (1 if broad_scope else 0), 4, 10)
    outline_target_sections = _clamp(2 + complexity + (1 if document_count >= 4 else 0), 3, 8)
    outline_max_subsections = _clamp(1 + (complexity // 2), 1, 4)
    section_top_k = _clamp(5 + complexity + min(document_count, 3), 5, 14)
    section_context_chunks = _clamp(8 + complexity + min(document_count, 4), 8, 20)
    section_subquestion_target = _clamp(2 + complexity, 3, 7)
    summary_context_sections = _clamp(4 + complexity + min(document_count, 2), 4, 12)
    desired_depth = 2 if complexity <= 2 and not broad_scope else 3
    if complexity >= 5 and broad_scope:
        desired_depth = 4

    evidence_profile = "broad" if broad_scope else "narrow"
    if complexity >= 5:
        section_length_hint = "4-6 substantial paragraphs"
    elif broad_scope or complexity >= 3:
        section_length_hint = "3-5 medium paragraphs"
    else:
        section_length_hint = "2-3 focused paragraphs"

    min_novel_questions_to_deepen = 2 if desired_depth <= 2 else 3

    return ResearchPlan(
        query_complexity=complexity,
        root_top_k=root_top_k,
        root_context_chunks=root_context_chunks,
        root_subquestion_target=root_subquestion_target,
        outline_target_sections=outline_target_sections,
        outline_max_subsections=outline_max_subsections,
        section_top_k=section_top_k,
        section_context_chunks=section_context_chunks,
        section_subquestion_target=section_subquestion_target,
        summary_context_sections=summary_context_sections,
        desired_depth=desired_depth,
        min_novel_questions_to_deepen=min_novel_questions_to_deepen,
        section_length_hint=section_length_hint,
        evidence_profile=evidence_profile,
    )


def node_retrieval_top_k(plan: ResearchPlan, node: ResearchNode) -> int:
    depth_penalty = max((node.level or 1) - 2, 0)
    question_bonus = min(len(node.questions or []), 3)
    return _clamp(plan.section_top_k + question_bonus - depth_penalty, 4, 16)


def node_context_chunk_limit(plan: ResearchPlan, node: ResearchNode) -> int:
    depth_penalty = max((node.level or 1) - 2, 0)
    question_bonus = min(len(node.questions or []), 4)
    return _clamp(plan.section_context_chunks + question_bonus - depth_penalty, 6, 24)


def node_subquestion_target(plan: ResearchPlan, node: ResearchNode) -> int:
    depth_penalty = max((node.level or 1) - 2, 0)
    question_bonus = 1 if len(node.questions or []) >= 3 else 0
    return _clamp(plan.section_subquestion_target + question_bonus - depth_penalty, 2, 8)


def node_should_attempt_depth(plan: ResearchPlan, node: ResearchNode) -> bool:
    return (node.level or 1) < plan.desired_depth

