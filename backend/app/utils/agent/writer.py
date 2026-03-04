import logging
from textwrap import dedent
from typing import List

from langchain_openai import ChatOpenAI

from app.db.db import SessionLocal
from app.models.research_tree import ResearchNode, ResearchTree
from app.utils.agent.repo import get_node_chunks, get_node_questions, mark_questions_consumed
from app.utils.vectorstore import get_caption_store, get_vectorstore


logger = logging.getLogger(__name__)
llm = ChatOpenAI(model="gpt-4o", temperature=0)


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


def write_section(
    node: ResearchNode,
    *,
    context_chunk_limit: int = 12,
    length_hint: str = "2-4 compact paragraphs",
):
    db = SessionLocal()
    try:
        q_objs = get_node_questions(db, node.id)
        questions = [q.text for q in q_objs]
        chunks = get_node_chunks(db, node.id)
        context = "\n\n".join(c.text for c in chunks[:context_chunk_limit])

        goals = (node.goals or "").strip()
        goals_block = f"Goals for this section:\n{goals}\n\n" if goals else ""
        questions_block = "\n".join(f"- {question}" for question in questions) or "- Address the section title directly."

        prompt = dedent(
            f"""
            You are a scientific writer.
            Write a section titled "{node.title}".

            {goals_block}QUESTIONS TO ADDRESS:
            {questions_block}

            CONTEXT (verbatim excerpts, cite indirectly):
            {context}

            Constraints:
            - Integrate the strongest relevant evidence from the context.
            - Adapt the section length to the evidence. Target roughly {length_hint}.
            - If the evidence is limited, stay concise instead of padding.
            - If the evidence is rich and multi-faceted, cover the distinct angles clearly.
            - Be accurate and neutral.
            - No extra headings; just the prose.
            """
        ).strip()

        node.content = llm.invoke(prompt).content.strip()
        node.mark_final()

        mark_questions_consumed(db, [q.id for q in q_objs])
        db.commit()
    finally:
        db.close()
    return node


def write_summary(node: ResearchNode, *, context_chunk_limit: int = 12) -> str:
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

        CONTEXT:
        {context}

        The summary should extract the main findings only.
        """
    ).strip()
    return llm.invoke(prompt).content.strip()


def write_conclusion(node: ResearchNode, *, context_chunk_limit: int = 12) -> str:
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

        CONTEXT:
        {context}

        The conclusion should reflect on implications, limitations, or takeaways without repeating the full section.
        """
    ).strip()
    return llm.invoke(prompt).content.strip()


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
        Target {sentence_hint}. Match the actual breadth of the material instead of forcing a fixed size.
        Be accurate, synthetic, and non-repetitive. Avoid headings.

        ARTICLE TITLE:
        {tree.root_node.title}

        SECTION EXCERPTS:
        {context}
        """
    ).strip()
    return llm_local.invoke(prompt).content.strip()


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
        Target about {paragraph_hint}. Match the scope of the evidence instead of forcing a generic ending.
        Synthesize the main insights and limitations, and point to future directions when supported.
        Avoid new claims not grounded in the findings.

        TITLE:
        {tree.root_node.title}

        FINDINGS:
        {context}
        """
    ).strip()
    return llm_local.invoke(prompt).content.strip()
