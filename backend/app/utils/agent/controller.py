from difflib import SequenceMatcher
from app.utils.agent.repo import get_node_questions
from app.db.db import SessionLocal
from app.db.models.question_orm import QuestionStatus




def question_similarity(q1, q2):
    return SequenceMatcher(None, q1.lower(), q2.lower()).ratio()


def should_deepen_node(node, similarity_threshold=0.8, min_novel=2):
    # Keep the name for compatibility, but use DB
    from app.db.db import SessionLocal
    db = SessionLocal()
    try:
        q_objs = get_node_questions(db, node.id)
        # Use whatever rule you prefer. Here: at least N assigned expansion questions.
        expansion_assigned = [
            q for q in q_objs if getattr(q, "source", None) == "expansion" and q.status == QuestionStatus.ASSIGNED
        ]
        return len(expansion_assigned) >= min_novel
    finally:
        db.close()
