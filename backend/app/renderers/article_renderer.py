# app/renderers/article_renderer.py
from app.models.research_tree import ResearchTree

class ArticleRenderer:
    @staticmethod
    def to_markdown(tree: ResearchTree) -> str:
        def walk(node, level: int = 2) -> str:
            text = f"{'#' * level} {node.title}\n\n"
            if node.content:
                text += node.content.strip() + "\n\n"
            if node.summary:
                text += f"**Summary:** {node.summary.strip()}\n\n"
            if node.conclusion:
                text += f"**Conclusion:** {node.conclusion.strip()}\n\n"
            for sn in node.subnodes:
                text += walk(sn, level + 1)
            return text

        return f"# Research Article\n\n## Query\n{tree.query}\n\n" + walk(tree.root_node)

    @staticmethod
    def to_html(tree: ResearchTree) -> str:
        def walk(node, level: int = 2) -> str:
            text = f"<h{level}>{node.title}</h{level}>\n"
            if node.content:
                text += f"<p>{node.content.strip()}</p>\n"
            if node.summary:
                text += f"<p><strong>Summary:</strong> {node.summary.strip()}</p>\n"
            if node.conclusion:
                text += f"<p><strong>Conclusion:</strong> {node.conclusion.strip()}</p>\n"
            for sn in node.subnodes:
                text += walk(sn, level + 1)
            return text

        return f"<h1>Research Article</h1>\n<h2>Query</h2><p>{tree.query}</p>\n" + walk(tree.root_node)

    @staticmethod
    def to_latex(tree: ResearchTree) -> str:
        def esc(s: str) -> str:
            for k, v in {
                "&": "\\&","%": "\\%","$": "\\$","#": "\\#","_": "\\_",
                "{": "\\{","}": "\\}","~": "\\textasciitilde{}",
                "^": "\\textasciicircum{}","\\": "\\textbackslash{}",
            }.items():
                s = s.replace(k, v)
            return s

        def walk(node, level: int = 1) -> str:
            cmds = ["section", "subsection", "subsubsection", "paragraph"]
            cmd = cmds[min(level, len(cmds) - 1)]
            out = [f"\\{cmd}{{{esc(node.title)}}}\n"]
            if node.content:
                out.append(esc(node.content) + "\n")
            if node.summary:
                out.append(f"\\textbf{{Summary}}: {esc(node.summary)}\n")
            if node.conclusion:
                out.append(f"\\textbf{{Conclusion}}: {esc(node.conclusion)}\n")

            # (optional) cite source+page lines from chunks
            for ch in node.chunks:
                if ch.source and ch.page is not None:
                    out.append(f"\\textit{{[source: {esc(ch.source)}, page {ch.page}]}}\n")

            for sn in node.subnodes:
                out.append(walk(sn, level + 1))
            return "\n".join(out)

        body = walk(tree.root_node)
        return (
            "\\documentclass{article}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{hyperref}\n"
            "\\title{"+esc(tree.query)+"}\n"
            "\\begin{document}\n\\maketitle\n"
            + body +
            "\n\\end{document}\n"
        )
