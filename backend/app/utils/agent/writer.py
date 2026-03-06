import logging
import re
from textwrap import dedent
from typing import List

from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.db.db import SessionLocal
from app.models.research_tree import ResearchNode, ResearchTree
from app.utils.agent.repo import get_node_chunks, get_node_questions, mark_questions_consumed
from app.utils.vectorstore import get_caption_store, get_vectorstore


logger = logging.getLogger(__name__)
LLM_TIMEOUT_SECONDS = 120
llm = ChatOpenAI(model="gpt-4o", temperature=0, timeout=LLM_TIMEOUT_SECONDS)
alignment_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, timeout=90)

_STYLE_GUIDANCE = {
    "scientific_article": (
        "Use a formal, evidence-led, neutral scientific style with precise wording, "
        "explicit uncertainty, and no rhetorical flourish."
    ),
    "blogpost": (
        "Use an accessible blog style: clear explanations, short concrete paragraphs, "
        "engaging but factual tone, and minimal jargon."
    ),
    "newspaper": (
        "Use a concise newspaper style: lead with the key point, short paragraphs, "
        "objective tone, and direct language."
    ),
}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "is", "are", "was", "were", "be",
    "de", "het", "een", "en", "of", "van", "te", "op", "in", "is", "zijn", "was", "waren", "met", "dat",
}


class SectionAlignmentVerdict(BaseModel):
    aligned: bool = Field(description="True when the section is still in line with the root question.")
    reason: str = Field(default="", description="Short reason for the verdict.")


def get_context_for_questions(questions: List[str], top_k: int = 5, context_limit: int = 12) -> str:
    vectorstore = get_vectorstore()
    caption_store = get_caption_store()
    chunks = []

    for question in questions:
        text_hits = vectorstore.similarity_search(question, k=top_k)
        cap_hits = caption_store.similarity_search(question, k=top_k)
        chunks.extend(text_hits + cap_hits)

    unique_texts = list({doc.page_content for doc in chunks})
    return "\n\n".join(unique_texts[:context_limit])


def _normalize_output_style(output_style: str | None) -> str:
    if not output_style:
        return "scientific_article"
    key = output_style.strip().lower()
    if key in {"scientific", "scientific_article"}:
        return "scientific_article"
    if key in {"blog", "blogpost"}:
        return "blogpost"
    if key in {"newspaper", "news"}:
        return "newspaper"
    return "scientific_article"


def _style_instruction(output_style: str | None) -> str:
    return _STYLE_GUIDANCE[_normalize_output_style(output_style)]


def _keyword_tokens(text: str) -> set[str]:
    tokens = {token for token in re.findall(r"\w+", (text or "").lower()) if len(token) >= 3}
    return {token for token in tokens if token not in _STOPWORDS}


def _fallback_section_alignment(root_query: str, node_title: str, questions: list[str]) -> tuple[bool, str]:
    query_tokens = _keyword_tokens(root_query)
    section_tokens = _keyword_tokens(node_title)
    for question in questions:
        section_tokens.update(_keyword_tokens(question))

    if not query_tokens:
        return True, "fallback: empty query token set"

    overlap = query_tokens & section_tokens
    overlap_ratio = len(overlap) / max(len(query_tokens), 1)
    aligned = len(overlap) >= 1 or overlap_ratio >= 0.2
    reason = (
        f"fallback lexical overlap={len(overlap)}/{len(query_tokens)} ratio={overlap_ratio:.2f}"
        if overlap
        else "fallback: no lexical overlap"
    )
    return aligned, reason


def is_section_aligned_with_query(
    node: ResearchNode,
    *,
    root_query: str,
    context_chunk_limit: int = 8,
) -> tuple[bool, str]:
    questions = list(node.questions or [])
    context = "\n\n".join(c.text for c in (node.chunks or [])[:context_chunk_limit])

    parser = PydanticOutputParser(pydantic_object=SectionAlignmentVerdict)
    prompt = PromptTemplate(
        template="""
            You are a strict relevance checker.
            Decide whether the proposed section is still in line with the original user question.

            Mark aligned=true only when the section directly answers the question
            or a necessary sub-question that clearly contributes to answering it.
            If the section drifts into side stories or weakly related material, aligned=false.

            ROOT QUESTION:
            {root_query}

            SECTION TITLE:
            {section_title}

            SECTION QUESTIONS:
            {section_questions}

            SECTION EVIDENCE EXCERPTS:
            {context}

            {format_instructions}
            """,
        input_variables=["root_query", "section_title", "section_questions", "context"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    try:
        chain = prompt | alignment_llm | parser
        verdict = chain.invoke(
            {
                "root_query": root_query,
                "section_title": node.title,
                "section_questions": "\n".join(f"- {q}" for q in questions) if questions else "- (none)",
                "context": context or "(no evidence loaded)",
            }
        )
        return bool(verdict.aligned), verdict.reason.strip() or "model verdict"
    except Exception:
        logger.exception("Alignment check failed for section '%s'; using fallback heuristic", node.title)
        return _fallback_section_alignment(root_query, node.title, questions)


def write_section(
    node: ResearchNode,
    *,
    root_query: str,
    output_style: str = "scientific_article",
    context_chunk_limit: int = 12,
    length_hint: str = "2-4 compact paragraphs",
):
    db = SessionLocal()
    try:
        q_objs = get_node_questions(db, node.id)
        questions = [q.text for q in q_objs]
        chunks = get_node_chunks(db, node.id)
        context = "\n\n".join(c.text for c in chunks[:context_chunk_limit])
        style_instruction = _style_instruction(output_style)

        goals = (node.goals or "").strip()
        goals_block = f"Goals for this section:\n{goals}\n\n" if goals else ""
        questions_block = "\n".join(f"- {question}" for question in questions) or "- Address the section title directly."

        prompt = dedent(
            f"""
            You are a scientific writer.
            Write a section titled "{node.title}".
            The original user question is: "{root_query}".
            Output style requirement: {style_instruction}

            {goals_block}QUESTIONS TO ADDRESS:
            {questions_block}

            CONTEXT (verbatim excerpts, cite indirectly):
            {context}

            Constraints:
            - Integrate the strongest relevant evidence from the context.
            - Keep the section tightly aligned with the original user question.
            - If evidence in context is off-topic for the original question, exclude it.
            - Adapt the section length to the evidence. Target roughly {length_hint}.
            - If the evidence is limited, stay concise instead of padding.
            - If the evidence is rich and multi-faceted, cover the distinct angles clearly.
            - Be accurate and neutral.
            - Treat idiomatic, literary, dialectal, archaic, or figurative expressions carefully.
            - Do not force a modern literal interpretation unless the surrounding context clearly supports it.
            - If a phrase is ambiguous, acknowledge the ambiguity instead of making an unsupported claim.
            - No extra headings; just the prose.
            """
        ).strip()

        logger.info(
            "Writing section '%s' style=%s with %s questions, %s chunks, context_limit=%s context_chars=%s",
            node.title,
            _normalize_output_style(output_style),
            len(questions),
            len(chunks),
            context_chunk_limit,
            len(context),
        )
        try:
            node.content = llm.invoke(prompt).content.strip()
            node.mark_final()
            logger.info("Finished section '%s' content_len=%s", node.title, len(node.content))
        except Exception:
            logger.exception("Section generation failed for '%s'", node.title)
            raise

        mark_questions_consumed(db, [q.id for q in q_objs])
        db.commit()
    finally:
        db.close()
    return node


def write_summary(
    node: ResearchNode,
    *,
    output_style: str = "scientific_article",
    context_chunk_limit: int = 12,
) -> str:
    db = SessionLocal()
    try:
        chunks = get_node_chunks(db, node.id)
        context = "\n\n".join(c.text for c in chunks[:context_chunk_limit])
    finally:
        db.close()

    if not context.strip():
        return f"(No summary available for: {node.title})"

    prompt = dedent(
        f"""
        You are a scientific assistant.
        Based on the CONTEXT, write a compact section summary for "{node.title}".
        Output style requirement: {_style_instruction(output_style)}

        CONTEXT:
        {context}

        The summary should extract the main findings only.
        Preserve ambiguity where the evidence is linguistically uncertain.
        """
    ).strip()
    logger.info("Writing summary for '%s' context_chars=%s", node.title, len(context))
    try:
        result = llm.invoke(prompt).content.strip()
        logger.info("Finished summary for '%s' len=%s", node.title, len(result))
        return result
    except Exception:
        logger.exception("Summary generation failed for '%s'", node.title)
        raise


def write_conclusion(
    node: ResearchNode,
    *,
    output_style: str = "scientific_article",
    context_chunk_limit: int = 12,
) -> str:
    db = SessionLocal()
    try:
        chunks = get_node_chunks(db, node.id)
        context = "\n\n".join(c.text for c in chunks[:context_chunk_limit])
    finally:
        db.close()

    if not context.strip():
        return f"(No conclusion available for: {node.title})"

    prompt = dedent(
        f"""
        You are a scientific assistant.
        Based on the CONTEXT, write a concluding paragraph for the section titled "{node.title}".
        Output style requirement: {_style_instruction(output_style)}

        CONTEXT:
        {context}

        The conclusion should reflect on implications, limitations, or takeaways without repeating the full section.
        Preserve ambiguity where the evidence is linguistically uncertain.
        """
    ).strip()
    logger.info("Writing conclusion for '%s' context_chars=%s", node.title, len(context))
    try:
        result = llm.invoke(prompt).content.strip()
        logger.info("Finished conclusion for '%s' len=%s", node.title, len(result))
        return result
    except Exception:
        logger.exception("Conclusion generation failed for '%s'", node.title)
        raise


def write_executive_summary(tree: ResearchTree) -> str:
    llm_local = ChatOpenAI(model="gpt-4o", temperature=0)
    sections = []
    for node in tree.root_node.subnodes:
        if node.content:
            sections.append(f"- {node.title}: {node.content[:800]}")
    context = "\n".join(sections[: tree.plan.summary_context_sections])
    sentence_hint = "6-10 sentences" if tree.plan.query_complexity >= 4 else "4-7 sentences"

    prompt = dedent(
        f"""
        You are a scientific writer. Draft an Executive Summary of the article below.
        Output style requirement: {_style_instruction(tree.plan.output_style)}
        Target {sentence_hint}. Match the actual breadth of the material instead of forcing a fixed size.
        Be accurate, synthetic, and non-repetitive. Avoid headings.
        Do not turn ambiguous or possibly idiomatic source language into confident literal claims.

        ARTICLE TITLE:
        {tree.root_node.title}

        SECTION EXCERPTS:
        {context}
        """
    ).strip()
    logger.info(
        "Writing executive summary title=%r excerpt_count=%s context_chars=%s",
        tree.root_node.title,
        len(sections[: tree.plan.summary_context_sections]),
        len(context),
    )
    try:
        result = llm_local.invoke(prompt).content.strip()
        logger.info("Finished executive summary len=%s", len(result))
        return result
    except Exception:
        logger.exception("Executive summary generation failed for title=%r", tree.root_node.title)
        raise


def write_overall_conclusion(tree: ResearchTree) -> str:
    llm_local = ChatOpenAI(model="gpt-4o", temperature=0)
    bullets = []
    for node in tree.root_node.subnodes:
        if node.summary:
            bullets.append(f"- {node.title}: {node.summary}")
        elif node.conclusion:
            bullets.append(f"- {node.title}: {node.conclusion}")
        elif node.content:
            bullets.append(f"- {node.title}: {node.content[:400]}")
    context = "\n".join(bullets[: max(tree.plan.summary_context_sections, 6)])
    paragraph_hint = "2 paragraphs" if tree.plan.query_complexity >= 4 else "1 focused paragraph"

    prompt = dedent(
        f"""
        You are a scientific writer. Using the following findings, write an Overall Conclusion.
        Output style requirement: {_style_instruction(tree.plan.output_style)}
        Target about {paragraph_hint}. Match the scope of the evidence instead of forcing a generic ending.
        Synthesize the main insights and limitations, and point to future directions when supported.
        Avoid new claims not grounded in the findings.
        Preserve ambiguity where the underlying language may be idiomatic, literary, dialectal, or archaic.

        TITLE:
        {tree.root_node.title}

        FINDINGS:
        {context}
        """
    ).strip()
    logger.info(
        "Writing overall conclusion title=%r finding_count=%s context_chars=%s",
        tree.root_node.title,
        len(bullets[: max(tree.plan.summary_context_sections, 6)]),
        len(context),
    )
    try:
        result = llm_local.invoke(prompt).content.strip()
        logger.info("Finished overall conclusion len=%s", len(result))
        return result
    except Exception:
        logger.exception("Overall conclusion generation failed for title=%r", tree.root_node.title)
        raise
