from langchain_openai import ChatOpenAI
from app.utils.vectorstore import get_vectorstore, get_caption_store
from typing import List
import logging
from app.models.research_tree import ResearchNode



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


# writer.py
from app.utils.agent.repo import get_node_questions, get_node_chunks, mark_questions_consumed
from app.db.db import SessionLocal

def write_section(node: ResearchNode):
    db = SessionLocal()
    try:
        q_objs = get_node_questions(db, node.id)
        questions = [q.text for q in q_objs]
        chunks = get_node_chunks(db, node.id)
        context = "\n\n".join(c.text for c in chunks[:20])

        goals = (node.goals or "").strip()

        prompt = f"""
        You are a scientific writer.
        Write a detailed section titled "{node.title}".

        {'Goals for this section:\n' + goals if goals else ''}

        QUESTIONS TO ADDRESS:
        {chr(10).join(f"- {q}" for q in questions)}

        CONTEXT (verbatim excerpts, cite indirectly):
        {context}

        Constraints:
        - Integrate answers to the questions.
        - Be accurate and neutral.
        - No extra headings; just the prose.
        """

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
