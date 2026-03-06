from app.models.research_tree import ResearchTree

def finalize_article_from_tree(tree: ResearchTree) -> str:
    title = tree.root_node.title or "Untitled Article"
    abstract = tree.root_node.content.strip() if tree.root_node.content else ""
    exec_summary = (tree.root_node.summary or "").strip()
    overall = (tree.root_node.conclusion or "").strip()

    parts = [f"# {title}\n"]

    if exec_summary:
        parts.append(f"**Executive Summary**\n\n{exec_summary}\n")

    if abstract:
        parts.append(f"**Abstract**\n\n{abstract}\n")

    def walk(node, level: int = 2):
        child_lines = []
        for sub in node.subnodes:
            child_lines.extend(walk(sub, level + 1))

        has_local_content = any(
            [
                bool((node.content or "").strip()),
                bool((node.summary or "").strip()),
                bool((node.conclusion or "").strip()),
            ]
        )
        if not has_local_content and not child_lines:
            return []

        lines = [f"{'#' * level} {node.title}\n"]
        if node.content:
            lines.append(node.content.strip() + "\n")
        if node.summary:
            lines.append(f"**Section Summary:** {node.summary.strip()}\n")
        if node.conclusion:
            lines.append(f"**Section Conclusion:** {node.conclusion.strip()}\n")
        lines.extend(child_lines)
        return lines

    for section in tree.root_node.subnodes:
        parts.extend(walk(section, level=2))

    if overall:
        parts.append(f"## Overall Conclusion\n\n{overall}\n")
    else:
        parts.append("## Overall Conclusion\n\n(Conclusion not generated.)\n")

    return "\n".join(parts).strip()

