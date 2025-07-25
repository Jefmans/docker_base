from typing import Dict, List

_session_store: Dict[str, Dict] = {}

def save_session_chunks(session_id: str, query: str, chunks: List[str]):
    _session_store[session_id] = {
        "query": query,
        "chunks": chunks
    }

def get_session_chunks(session_id: str) -> Dict:
    return _session_store.get(session_id, {})
