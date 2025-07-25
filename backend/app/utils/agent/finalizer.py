from app.utils.agent.outline import Outline
import json

def finalize_article(session_data: dict) -> str:
    if "outline" not in session_data or "query" not in session_data:
        return "❌ Missing outline or query."

    outline = Outline(**session_data["outline"]) if isinstance(session_data["outline"], dict) else Outline(**json.loads(session_data["outline"]))
    session_id = session_data["session_id"]
    all_sections = session_data.get("sections") or {}

    stitched = f"# {outline.title}\n\n"
    stitched += f"**Abstract:** {outline.abstract}\n\n"

    for i, section in enumerate(outline.sections):
        text = all_sections.get(i, "").strip()
        if not text:
            continue
        stitched += f"## {section.heading}\n\n{text}\n\n"

    stitched += "## Conclusion\n\n(Conclusion not generated. Add manually if needed.)"

    return stitched.strip()
