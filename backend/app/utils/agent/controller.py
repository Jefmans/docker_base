from difflib import SequenceMatcher

def question_similarity(q1, q2):
    return SequenceMatcher(None, q1.lower(), q2.lower()).ratio()

def should_deepen_node(node, similarity_threshold=0.8, min_novel=2):
    novel_count = 0
    existing = [q.strip().lower() for q in node.questions]

    for new_q in node.generated_questions:
        if all(question_similarity(new_q, old_q) < similarity_threshold for old_q in existing):
            novel_count += 1

    return novel_count >= min_novel
