# backend/app/utils/agent/session_memory_db.py

from typing import List, Dict
from app.models.research_tree import ResearchTree
from app.db import Session as SessionModel, SessionLocal
from sqlalchemy.orm import Session as DBSession
import uuid
import json

# --- Save basic query/chunks session state ---
def save_session_chunks_db(session_id: str, query: str, chunks: List[str]):
    with SessionLocal() as db:
        existing = db.query(SessionModel).filter_by(id=session_id).first()
        data = {
            "query": query,
            "chunks": chunks
        }
        if existing:
            existing.tree = data
        else:
            db.add(SessionModel(id=session_id, query=query, tree=data))
        db.commit()

# --- Load session state ---
def get_session_chunks_db(session_id: str) -> Dict:
    with SessionLocal() as db:
        record = db.query(SessionModel).filter_by(id=session_id).first()
        return record.tree if record else {}

# --- Save section content ---
def save_section_db(session_id: str, section_index: int, text: str):
    with SessionLocal() as db:
        record = db.query(SessionModel).filter_by(id=session_id).first()
        if not record:
            return
        tree_data = record.tree or {}
        tree_data.setdefault("sections", {})[section_index] = text
        record.tree = tree_data
        db.commit()

# --- Load all sections ---
def get_all_sections_db(session_id: str) -> List[str]:
    with SessionLocal() as db:
        record = db.query(SessionModel).filter_by(id=session_id).first()
        if not record:
            return []
        return list(record.tree.get("sections", {}).values())

# --- Save full ResearchTree ---
def save_research_tree_db(session_id: str, tree: ResearchTree):
    with SessionLocal() as db:
        existing = db.query(SessionModel).filter_by(id=session_id).first()
        if existing:
            existing.tree = tree.model_dump()
        else:
            db.add(SessionModel(id=session_id, query=tree.query, tree=tree.model_dump()))
        db.commit()

# --- Load ResearchTree ---
def get_research_tree_db(session_id: str) -> ResearchTree:
    with SessionLocal() as db:
        record = db.query(SessionModel).filter_by(id=session_id).first()
        if not record:
            return None
        return ResearchTree(**record.tree)
