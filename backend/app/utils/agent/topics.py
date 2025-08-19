# app/utils/agent/topics.py
from difflib import SequenceMatcher
from typing import List

def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()

def group_similar(items: List[str], threshold: float = 0.72) -> List[List[str]]:
    """
    Greedy single-pass clustering. Each item is added to the cluster it is most similar to
    (max similarity against any member of that cluster), if >= threshold; else start new cluster.
    """
    clusters: List[List[str]] = []
    for item in items:
        if not item or not item.strip():
            continue
        best_idx, best_score = -1, 0.0
        for i, cluster in enumerate(clusters):
            score = max(_sim(item, rep) for rep in cluster)
            if score > best_score:
                best_idx, best_score = i, score
        if best_idx != -1 and best_score >= threshold:
            clusters[best_idx].append(item)
        else:
            clusters.append([item])
    return clusters
