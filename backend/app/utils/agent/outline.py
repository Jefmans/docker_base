from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from app.models.outline_model import Outline
from app.models.research_tree import ResearchTree


def _outline_style_guidance(output_style: str | None) -> str:
    key = (output_style or "scientific_article").strip().lower()
    if key in {"blog", "blogpost"}:
        return "Use an accessible blog structure with clear reader-friendly section titles."
    if key in {"newspaper", "news"}:
        return "Use a concise newspaper-style structure, prioritizing key facts and direct section titles."
    return "Use a formal scientific structure with precise, neutral section titles."


def generate_outline_from_tree(tree: ResearchTree) -> Outline:
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    parser = PydanticOutputParser(pydantic_object=Outline)

    all_chunk_texts = [c.text for n in tree.all_nodes() for c in n.chunks]
    all_chunk_texts = list(dict.fromkeys(all_chunk_texts))
    all_chunk_texts = all_chunk_texts[: tree.plan.root_context_chunks]

    subquestions = []
    for node in tree.all_nodes():
        subquestions.extend(node.questions or [])
    subquestions = list(dict.fromkeys(q.strip() for q in subquestions if q and q.strip()))
    subquestions = subquestions[: tree.plan.root_subquestion_target]

    target_sections = tree.plan.outline_target_sections
    if tree.plan.evidence_profile in {"narrow", "sparse"}:
        min_sections = max(1, target_sections - 2)
        max_sections = target_sections + 1
    elif tree.plan.evidence_profile == "moderate":
        min_sections = max(1, target_sections - 1)
        max_sections = target_sections + 2
    else:
        min_sections = max(2, target_sections - 1)
        max_sections = target_sections + 3

    prompt = PromptTemplate(
        template="""
            You are a scientific writer assistant. Create a full article outline for the question below
            using only the grounded subquestions and evidence.

            Scale the outline to the breadth of the evidence.
            Aim for around {target_sections} top-level sections.
            Keep the top-level section count between {min_sections} and {max_sections}.
            Do not force the same size every time.
            Use fewer sections if the evidence is narrow.
            Use more only if the evidence truly supports it.
            A single top-level section is allowed when evidence is sparse or highly focused.
            Keep each section to at most {max_subsections} subsections.
            Treat idiomatic, literary, dialectal, archaic, or figurative expressions carefully.
            Do not build sections around an unverified literal interpretation.
            If the meaning of a phrase is ambiguous, preserve that ambiguity in the outline instead of resolving it prematurely.
            Style requirement: {style_guidance}

            MAIN QUESTION:
            {query}

            EVIDENCE PROFILE:
            {evidence_profile}

            SUBQUESTIONS:
            {subquestions}

            CONTEXT:
            {all_chunks}

            {format_instructions}
            """,
        input_variables=[
            "query",
            "evidence_profile",
            "subquestions",
            "all_chunks",
            "target_sections",
            "min_sections",
            "max_sections",
            "max_subsections",
            "style_guidance",
        ],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    chain = prompt | llm | parser
    return chain.invoke(
        {
            "query": tree.query,
            "evidence_profile": tree.plan.evidence_profile,
            "subquestions": subquestions,
            "all_chunks": all_chunk_texts,
            "target_sections": target_sections,
            "min_sections": min_sections,
            "max_sections": max_sections,
            "max_subsections": tree.plan.outline_max_subsections,
            "style_guidance": _outline_style_guidance(tree.plan.output_style),
        }
    )
