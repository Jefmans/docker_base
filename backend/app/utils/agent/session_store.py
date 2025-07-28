# backend/app/utils/agent/session_store.py

from sqlalchemy.orm import Session as DBSession
from app.db import Session as SessionModel
from app.models.research_tree import ResearchTree
import uuid

# --- Save tree ---
def save_research_tree_db(db: DBSession, session_id: str, tree: ResearchTree):
    db_session = db.query(SessionModel).filter_by(id=session_id).first()
    if db_session:
        db_session.tree = tree.model_dump()
    else:
        db_session = SessionModel(
            id=session_id,
            query=tree.query,
            tree=tree.model_dump()
        )
        db.add(db_session)
    db.commit()

# --- Load tree ---
def load_research_tree_db(db: DBSession, session_id: str) -> ResearchTree:
    db_session = db.query(SessionModel).filter_by(id=session_id).first()
    if not db_session:
        return None
    return ResearchTree(**db_session.tree)

# Optional: create new session ID

def create_session_id() -> str:
    return str(uuid.uuid4())
