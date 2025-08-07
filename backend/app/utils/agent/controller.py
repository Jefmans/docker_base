from difflib import SequenceMatcher

def question_similarity(q1, q2):
    return SequenceMatcher(None, q1.lower(), q2.lower()).ratio()

from app.utils.agent.repo import get_node_questions
from difflib import SequenceMatcher
from app.db.db import SessionLocal

def should_deepen_node(node, similarity_threshold=0.8, min_novel=2):
    db = SessionLocal()
    try:
        assigned = [q.text for q in get_node_questions(db, node.id)]
        generated = getattr(node, "generated_questions_texts", [])  # or pass them in
        existing = [q.lower().strip() for q in assigned]

        novel = 0
        for nq in generated:
            if all(SequenceMatcher(None, nq.lower().strip(), e).ratio() < similarity_threshold for e in existing):
                novel += 1
        return novel >= min_novel
    finally:
        db.close()
