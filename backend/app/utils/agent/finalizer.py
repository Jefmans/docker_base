from langchain_openai import ChatOpenAI
from app.utils.agent.memory import get_session_chunks, get_all_sections
from app.utils.agent.outline import Outline
import json

llm = ChatOpenAI(model="gpt-4o", temperature=0)

def finalize_article(session_data: dict) -> str:
    if "outline" not in session_data or "query" not in session_data:
        return "❌ Missing outline or query."

    outline = Outline(**session_data["outline"]) if isinstance(session_data["outline"], dict) else Outline(**json.loads(session_data["outline"]))
    sections = get_all_sections(session_data["session_id"])

    if not sections:
        return "❌ No sections found to finalize."

    joined_sections = "\n\n".join(sections)

    prompt = f"""
You are a scientific editor. Combine the following article data into a polished, structured scientific article.

=== TITLE ===
{outline.title}

=== ABSTRACT ===
{outline.abstract}

=== SECTIONS ===
{joined_sections}

=== GOAL ===
We want a logically flowing, coherent, well-written article using only the content above. Add intro/conclusion/transitions if missing. Keep it formal and academic.
"""

    return llm.invoke(prompt).content.strip()
