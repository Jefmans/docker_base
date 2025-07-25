from typing import List
from langchain_openai import ChatOpenAI

def generate_subquestions_from_chunks(chunks: List[str], user_query: str, model_name: str = "gpt-4o") -> str:
    llm = ChatOpenAI(model=model_name, temperature=0)

    context = "\n\n".join(chunks[:20])  # Only top 20 chunks for safety
    prompt = f"""
You are a scientific research assistant. A user has asked the question: "{user_query}"

Based only on the real scientific context below (from books and articles), generate 5 to 10 important and well-formed scientific subquestions that would help answer the user's query in depth.

Only ask questions that can be addressed using the context. Do not invent questions that require external knowledge.

Respond with a JSON array of strings.

--- CONTEXT START ---
{context}
--- CONTEXT END ---
"""

    response = llm.invoke(prompt)
    return response.content.strip()
