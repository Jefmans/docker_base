from app.models.research_tree import ResearchTree

def finalize_article_from_tree(tree: ResearchTree) -> str:
    title = tree.root_node.title or "Untitled Article"
    abstract = tree.root_node.content.strip() if tree.root_node.content else ""

    parts = [f"# {title}\n"]
    if abstract:
        parts.append(f"**Abstract:** {abstract}\n")

    def walk(node, level: int = 2):
        lines = [f"{'#' * level} {node.title}\n"]
        if node.content:
            lines.append(node.content.strip() + "\n")
        if node.summary:
            lines.append(f"**Summary:** {node.summary.strip()}\n")
        if node.conclusion:
            lines.append(f"**Conclusion:** {node.conclusion.strip()}\n")
        for sub in node.subnodes:
            lines.extend(walk(sub, level + 1))
        return lines

    for section in tree.root_node.subnodes:
        parts.extend(walk(section, level=2))

    parts.append("## Conclusion\n\n(Conclusion not generated. Add manually if needed.)")
    return "\n".join(parts).strip()
