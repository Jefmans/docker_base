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
    "why",
    "how",
    "when",
    "where",
    "which",
    "what",
    "waarom",
    "hoe",
    "wanneer",
    "waar",
    "welke",
    "wat",
    "vergelijk",
    "verschil",
    "oorzaak",
    "gevolg",
    "analyse",
    "verklaar",
}

_OUTPUT_STYLE_MAP = {
    "scientific": "scientific_article",
    "scientific_article": "scientific_article",
    "blog": "blogpost",
    "blogpost": "blogpost",
    "newspaper": "newspaper",
    "news": "newspaper",
}


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def normalize_output_style(value: str | None) -> str:
    if not value:
        return "scientific_article"
    return _OUTPUT_STYLE_MAP.get(value.strip().lower(), "scientific_article")


def estimate_query_complexity(query: str, scope: ResearchScope) -> int:
    tokens = re.findall(r"\w+", query.lower())
    token_count = len(tokens)
    distinct_terms = len(set(tokens))
    matched_terms = sum(1 for term in _COMPLEXITY_TERMS if term in tokens)
    clause_markers = [" and ", " or ", " en ", " of ", " versus ", " vs "]
    multi_clause = query.count("?") >= 2 or any(marker in f" {query.lower()} " for marker in clause_markers)

    score = 0
    if token_count >= 6:
        score += 1
    if token_count >= 12:
        score += 1
    if distinct_terms >= 6:
        score += 1
    if matched_terms >= 1:
        score += 1
    if matched_terms >= 3:
        score += 1
    if multi_clause:
        score += 1
    if scope.document_count >= 3:
        score += 1
    if scope.mode == "all":
        score += 1
    return _clamp(score, 0, 7)


def build_research_plan(
    query: str,
    scope: ResearchScope,
    *,
    requested_top_k: int = 5,
    output_style: str | None = None,
) -> ResearchPlan:
    complexity = estimate_query_complexity(query, scope)
    document_count = max(scope.document_count, len(scope.filenames), 1)
    broad_scope = scope.mode in {"project", "all"} or document_count > 1
    normalized_output_style = normalize_output_style(output_style)

    # root_top_k is the candidate retrieval budget (broad recall pass)
    root_top_k = _clamp(max(requested_top_k, 18 + (2 * complexity) + min(document_count, 8)), 12, 40)
    # root_context_chunks is the post-filtered evidence budget sent to LLM steps
    root_context_chunks = _clamp(int(root_top_k * 0.5), 5, 20)
    root_subquestion_target = _clamp(1 + (complexity // 2) + (1 if broad_scope else 0), 1, 10)
    outline_target_sections = _clamp(
        1 + (complexity // 2) + (1 if document_count >= 4 else 0) + (1 if broad_scope and complexity >= 2 else 0),
        1,
        9,
    )
    outline_max_subsections = _clamp(1 + (complexity // 3) + (1 if broad_scope and complexity >= 4 else 0), 1, 6)
    section_top_k = _clamp(max(5, int(root_top_k * 0.65)) + (1 if broad_scope else 0), 5, 28)
    section_context_chunks = _clamp(int(section_top_k * 0.75), 4, 24)
    section_subquestion_target = _clamp(1 + (complexity // 2) + (1 if broad_scope and complexity >= 3 else 0), 1, 7)
    summary_context_sections = _clamp(outline_target_sections + (1 if broad_scope else 0), 2, 16)

    desired_depth = 2
    if broad_scope or complexity >= 2:
        desired_depth = 3
    if complexity >= 5 and broad_scope:
        desired_depth = 4

    evidence_profile = "broad" if broad_scope else "narrow"
    if complexity >= 6:
        section_length_hint = "4-6 substantial paragraphs"
    elif broad_scope or complexity >= 3:
        section_length_hint = "3-5 medium paragraphs"
    else:
        section_length_hint = "2-3 focused paragraphs"

    min_novel_questions_to_deepen = 1 if complexity <= 2 else (2 if desired_depth <= 2 else 3)

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
        output_style=normalized_output_style,
    )


def refine_research_plan_from_initial_chunks(plan: ResearchPlan, chunk_dicts: list[dict]) -> ResearchPlan:
    unique_chunk_ids = {chunk.get("id") for chunk in chunk_dicts if chunk.get("id")}
    unique_sources = {chunk.get("source") for chunk in chunk_dicts if chunk.get("source")}
    unique_pages = {
        (chunk.get("source"), chunk.get("page"))
        for chunk in chunk_dicts
        if chunk.get("page") is not None
    }

    unique_chunk_count = len(unique_chunk_ids) or len(chunk_dicts)
    unique_source_count = len(unique_sources)
    unique_page_count = len(unique_pages)
    normalized_snippets = {
        re.sub(r"\s+", " ", str(chunk.get("text", "")).lower()).strip()[:180]
        for chunk in chunk_dicts
        if chunk.get("text")
    }
    snippet_diversity = len([snippet for snippet in normalized_snippets if len(snippet) >= 60])
    high_quality_count = sum(
        1
        for chunk in chunk_dicts
        if isinstance(chunk.get("text"), str) and len(chunk["text"].strip()) >= 220
    )
    effective_evidence = max(
        0,
        min(
            unique_chunk_count,
            max(high_quality_count, 1) + 2,
            max(snippet_diversity, 1) + 2,
        ),
    )

    evidence_richness = effective_evidence + min(unique_source_count, 3) + (1 if unique_page_count >= 6 else 0)
    selected_context = _clamp(
        int(max(effective_evidence, 1) * 0.8) + min(unique_source_count, 2),
        3,
        20,
    )
    updates: dict[str, object] = {
        "root_context_chunks": selected_context,
    }

    if evidence_richness <= 5:
        updates["root_subquestion_target"] = _clamp(plan.root_subquestion_target - 1, 1, 10)
        updates["outline_target_sections"] = _clamp(plan.outline_target_sections - 1, 1, 8)
        updates["section_top_k"] = _clamp(plan.section_top_k - 2, 4, 24)
        updates["section_context_chunks"] = _clamp(plan.section_context_chunks - 2, 4, 20)
        updates["section_subquestion_target"] = _clamp(plan.section_subquestion_target - 1, 1, 7)
        updates["summary_context_sections"] = _clamp(plan.summary_context_sections - 1, 2, 12)
        updates["section_length_hint"] = "1-2 short evidence-grounded paragraphs"
        updates["desired_depth"] = 2
        updates["min_novel_questions_to_deepen"] = 1
        updates["evidence_profile"] = "sparse"
    elif evidence_richness >= 11:
        updates["root_subquestion_target"] = _clamp(plan.root_subquestion_target + 2, 2, 10)
        updates["outline_target_sections"] = _clamp(plan.outline_target_sections + 1, 2, 9)
        updates["section_top_k"] = _clamp(plan.section_top_k + 3, 5, 28)
        updates["section_context_chunks"] = _clamp(plan.section_context_chunks + 3, 4, 24)
        updates["section_subquestion_target"] = _clamp(plan.section_subquestion_target + 1, 1, 7)
        updates["summary_context_sections"] = _clamp(plan.summary_context_sections + 1, 2, 12)
        updates["section_length_hint"] = (
            "3-5 medium paragraphs" if plan.query_complexity >= 2 else "2-4 focused paragraphs"
        )
        updates["desired_depth"] = _clamp(plan.desired_depth + 1, 2, 4)
        updates["min_novel_questions_to_deepen"] = 1
        updates["evidence_profile"] = "rich" if unique_source_count >= 2 or unique_page_count >= 6 else "moderate"
    else:
        diversity_bonus = 1 if unique_source_count >= 2 or snippet_diversity >= 8 else 0
        updates["root_subquestion_target"] = _clamp(
            2 + (effective_evidence // 3) + diversity_bonus,
            1,
            10,
        )
        updates["outline_target_sections"] = _clamp(
            1 + (effective_evidence // 4) + diversity_bonus,
            1,
            9,
        )
        updates["section_subquestion_target"] = _clamp(
            1 + (effective_evidence // 5) + diversity_bonus,
            1,
            7,
        )
        updates["section_top_k"] = _clamp(
            max(plan.section_top_k, selected_context + 2 + diversity_bonus),
            5,
            28,
        )
        updates["section_context_chunks"] = _clamp(
            max(plan.section_context_chunks, selected_context + diversity_bonus),
            4,
            24,
        )
        updates["min_novel_questions_to_deepen"] = 1 if effective_evidence >= 6 else plan.min_novel_questions_to_deepen
        updates["evidence_profile"] = "moderate" if unique_page_count >= 3 else plan.evidence_profile

    return plan.model_copy(update=updates)


def node_retrieval_top_k(plan: ResearchPlan, node: ResearchNode) -> int:
    depth_penalty = max((node.level or 1) - 2, 0)
    question_bonus = min(len(node.questions or []), 3)
    return _clamp(plan.section_top_k + question_bonus - depth_penalty, 3, 24)


def node_context_chunk_limit(plan: ResearchPlan, node: ResearchNode) -> int:
    depth_penalty = max((node.level or 1) - 2, 0)
    question_bonus = min(len(node.questions or []), 4)
    return _clamp(plan.section_context_chunks + question_bonus - depth_penalty, 4, 24)


def node_subquestion_target(plan: ResearchPlan, node: ResearchNode) -> int:
    depth_penalty = max((node.level or 1) - 2, 0)
    question_bonus = 1 if len(node.questions or []) >= 3 else 0
    return _clamp(plan.section_subquestion_target + question_bonus - depth_penalty, 1, 8)


def node_should_attempt_depth(plan: ResearchPlan, node: ResearchNode) -> bool:
    return (node.level or 1) < plan.desired_depth
