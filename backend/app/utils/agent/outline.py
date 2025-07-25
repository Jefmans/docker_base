from typing import List, Dict
from langchain_openai import ChatOpenAI

def generate_outline(subquestions: List[str], query: str) -> Dict:
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    joined_subs = "\n".join(f"- {q}" for q in subquestions)
    prompt = f"""
You are a scientific assistant. Based on the main query and subquestions below, create an outline for a scientific article.

MAIN QUESTION: {query}

SUBQUESTIONS:
{joined_subs}

Respond in JSON format:
{{
  "title": "...",
  "abstract": "...",
  "sections": [
    {{
      "heading": "...",
      "goals": "...",
      "questions": [...]
    }},
    ...
  ]
}}
"""
    return llm.invoke(prompt).content
