from langchain_openai import ChatOpenAI
from app.utils.vectorstore import get_vectorstore, get_caption_store
from typing import List
import logging
from app.models.research_tree import ResearchNode
from textwrap import dedent
from app.utils.agent.repo import get_node_questions, get_node_chunks, mark_questions_consumed
from app.db.db import SessionLocal


logger = logging.getLogger(__name__)
llm = ChatOpenAI(model="gpt-4o", temperature=0)

def get_context_for_questions(questions: List[str], top_k: int = 5) -> str:
    vectorstore = get_vectorstore()
    caption_store = get_caption_store()
    chunks = []

    for q in questions:
        text_hits = vectorstore.similarity_search(q, k=top_k)
        cap_hits = caption_store.similarity_search(q, k=top_k)
        chunks.extend(text_hits + cap_hits)

    unique_texts = list({doc.page_content for doc in chunks})
    return "\n\n".join(unique_texts[:20])  # limit


def write_section(node: ResearchNode):
    db = SessionLocal()
    try:
        q_objs = get_node_questions(db, node.id)
        questions = [q.text for q in q_objs]
        chunks = get_node_chunks(db, node.id)
        context = "\n\n".join(c.text for c in chunks[:20])

        goals = (node.goals or "").strip()

        # Precompute blocks so we don't put backslashes inside f-string { ... } expressions
        goals_block = f"Goals for this section:\n{goals}\n\n" if goals else ""
        questions_block = "\n".join(f"- {q}" for q in questions)

        prompt = dedent(f"""
            You are a scientific writer.
            Write a detailed section titled "{node.title}".

            {goals_block}QUESTIONS TO ADDRESS:
            {questions_block}

            CONTEXT (verbatim excerpts, cite indirectly):
            {context}

            Constraints:
            - Integrate answers to the questions.
            - Be accurate and neutral.
            - No extra headings; just the prose.
        """).strip()

        node.content = llm.invoke(prompt).content.strip()
        node.mark_final()

        mark_questions_consumed(db, [q.id for q in q_objs])
        db.commit()
    finally:
        db.close()
    return node


def write_summary(node: ResearchNode) -> str:
    db = SessionLocal()
    try:
        chunks = get_node_chunks(db, node.id)
        context = "\n\n".join(c.text for c in chunks[:20])
    finally:
        db.close()
    if not context.strip():
        return f"(No summary available for: {node.title})"
    # ... same prompt as you had


    prompt = f"""
        You are a scientific assistant.
        Based on the CONTEXT, write a concluding paragraph for the section titled "{node.title}".

        CONTEXT:
        {context}

        The conclusion should briefly reflect on the key findings or implications of the section.
    """
    return llm.invoke(prompt).content.strip()


def write_conclusion(node: ResearchNode) -> str:
    db = SessionLocal()
    try:
        chunks = get_node_chunks(db, node.id)
        context = "\n\n".join(c.text for c in chunks[:20])
    finally:
        db.close()
    if not context.strip():
        return f"(No conclusion available for: {node.title})"

    prompt = f"""
        You are a scientific assistant.
        Based on the CONTEXT, write a concluding paragraph for the section titled "{node.title}".

        CONTEXT:
        {context}

        The conclusion should briefly reflect on the key findings or implications of the section.
    """
    return llm.invoke(prompt).content.strip()


# writer.py
from app.models.research_tree import ResearchTree
from textwrap import dedent

def write_executive_summary(tree: ResearchTree) -> str:
    llm_local = ChatOpenAI(model="gpt-4o", temperature=0)
    # Gather concise context from already written sections
    sections = []
    for n in tree.root_node.subnodes:
        if n.content:
            sections.append(f"- {n.title}: {n.content[:800]}")  # trim per section
    context = "\n".join(sections[:12])  # cap a bit

    prompt = dedent(f"""
        You are a scientific writer. Draft a crisp Executive Summary (6–10 sentences)
        of the article below. Be accurate, synthetic, and non-repetitive. Avoid headings.

        ARTICLE TITLE:
        {tree.root_node.title}

        SECTION EXCERPTS:
        {context}
    """).strip()
    return llm_local.invoke(prompt).content.strip()


def write_overall_conclusion(tree: ResearchTree) -> str:
    llm_local = ChatOpenAI(model="gpt-4o", temperature=0)
    bullets = []
    for n in tree.root_node.subnodes:
        if n.summary:
            bullets.append(f"- {n.title}: {n.summary}")
        elif n.conclusion:
            bullets.append(f"- {n.title}: {n.conclusion}")
        elif n.content:
            bullets.append(f"- {n.title}: {n.content[:400]}")
    context = "\n".join(bullets[:14])

    prompt = dedent(f"""
        You are a scientific writer. Using the following findings, write an Overall Conclusion
        (1–2 solid paragraphs) that synthesizes the main insights and limitations, and points to
        future directions. Avoid new claims not supported by the findings.

        TITLE:
        {tree.root_node.title}

        FINDINGS:
        {context}
    """).strip()
    return llm_local.invoke(prompt).content.strip()
