# app/renderers/article_renderer.py
from app.models.research_tree import ResearchTree

class ArticleRenderer:
    @staticmethod
    def to_markdown(tree: ResearchTree) -> str:
        def walk(node, level: int = 2) -> str:
            text = f"{'#' * level} {node.title}\n\n"
            if node.content:
                text += node.content.strip() + "\n\n"
            # no per-node summary/conclusion
            for sn in node.subnodes:
                text += walk(sn, level + 1)
            return text

        parts = [f"# {tree.root_node.title or 'Research Article'}\n"]

        # Executive Summary (root.summary) — if present
        if tree.root_node.summary:
            parts.append(f"**Executive Summary**\n\n{tree.root_node.summary.strip()}\n")

        # Abstract from root.content if you use it as abstract, optional
        if tree.root_node.content:
            parts.append(f"**Abstract**\n\n{tree.root_node.content.strip()}\n")

        # Sections
        for sn in tree.root_node.subnodes:
            parts.append(walk(sn, level=2))

        # Overall Conclusion (root.conclusion) — if present
        if tree.root_node.conclusion:
            parts.append(f"## Overall Conclusion\n\n{tree.root_node.conclusion.strip()}\n")

        return "\n".join(parts).strip()

    @staticmethod
    def to_html(tree: ResearchTree) -> str:
        def walk(node, level: int = 2) -> str:
            html = [f"<h{level}>{node.title}</h{level}>"]
            if node.content:
                html.append(f"<p>{node.content.strip()}</p>")
            # no per-node summary/conclusion
            for sn in node.subnodes:
                html.append(walk(sn, level + 1))
            return "\n".join(html)

        parts = [f"<h1>{tree.root_node.title or 'Research Article'}</h1>"]

        if tree.root_node.summary:
            parts.append(f"<h2>Executive Summary</h2>\n<p>{tree.root_node.summary.strip()}</p>")

        if tree.root_node.content:
            parts.append(f"<h2>Abstract</h2>\n<p>{tree.root_node.content.strip()}</p>")

        for sn in tree.root_node.subnodes:
            parts.append(walk(sn, level=2))

        if tree.root_node.conclusion:
            parts.append(f"<h2>Overall Conclusion</h2>\n<p>{tree.root_node.conclusion.strip()}</p>")

        return "\n".join(parts)
