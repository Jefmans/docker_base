from typing import Dict, List
from app.models.research_tree import ResearchTree

_session_store: Dict[str, Dict] = {}

def save_session_chunks(session_id: str, query: str, chunks: List[str]):
    _session_store[session_id] = _session_store.get(session_id, {})
    _session_store[session_id].update({
        "query": query,
        "chunks": chunks
    })

def get_session_chunks(session_id: str) -> Dict:
    return _session_store.get(session_id, {})

def save_section(session_id: str, section_index: int, text: str):
    if session_id in _session_store:
        _session_store[session_id].setdefault("sections", {})[section_index] = text

def get_all_sections(session_id: str) -> List[str]:
    return list(_session_store.get(session_id, {}).get("sections", {}).values())




def save_research_tree(session_id: str, tree: ResearchTree):
    _session_store[session_id] = {"tree": tree.model_dump()}

def get_research_tree(session_id: str) -> ResearchTree:
    session = _session_store.get(session_id)
    if not session or "tree" not in session:
        return None
    return ResearchTree(**session["tree"])
