from langchain_openai import ChatOpenAI
from app.utils.vectorstore import get_vectorstore, get_caption_store
from typing import List
import logging

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

def write_section(section: dict) -> str:
    heading = section["heading"]
    goals = section["goals"]
    questions = section["questions"]

    context = get_context_for_questions(questions)
    if not context.strip():
        return f"(No relevant context found for section: {heading})"

    prompt = f"""
            You are a scientific writer. Write a detailed section titled "{heading}" with the following goals:

            {goals}

            Use only the CONTEXT below, which comes from academic PDFs. Do not add external knowledge.

            CONTEXT:
            {context}

            Write a clear and informative section (300–800 words) based on the questions:
            {questions}
            """
    return llm.invoke(prompt).content.strip()
