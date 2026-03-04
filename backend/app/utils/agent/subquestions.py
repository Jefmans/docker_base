from typing import List

from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel


class SubquestionList(BaseModel):
    questions: List[str]


def generate_subquestions_from_chunks(
    chunks: List[str],
    user_query: str,
    model_name: str = "gpt-4o",
    *,
    target_count: int = 6,
    context_chunk_limit: int = 12,
) -> List[str]:
    llm = ChatOpenAI(model=model_name, temperature=0)
    context = "\n\n".join(chunks[:context_chunk_limit])
    parser = PydanticOutputParser(pydantic_object=SubquestionList)
    min_count = max(3, min(target_count - 1, 6))

    prompt = PromptTemplate(
        template="""
            You are a scientific assistant. Based on the user query and scientific context below,
            generate between {min_count} and {target_count} detailed subquestions.

            Scale the number of subquestions to the breadth of the evidence.
            Narrow or sparse evidence should produce fewer subquestions.
            Broad or multi-document evidence can justify more.

            Only ask questions that are grounded in the context. Avoid filler and duplicates.
            Treat idiomatic, literary, dialectal, archaic, or figurative expressions carefully.
            Do not force a modern literal interpretation if the surrounding context does not clearly support it.
            If a phrase is ambiguous, prefer a subquestion that tests or clarifies the ambiguity instead of assuming one meaning.
            Return your result using this format:
            {format_instructions}

            === USER QUESTION ===
            {query}

            === CONTEXT ===
            {context}
            """,
        input_variables=["query", "context", "min_count", "target_count"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    chain = prompt | llm | parser

    try:
        result = chain.invoke(
            {
                "query": user_query,
                "context": context,
                "min_count": min_count,
                "target_count": target_count,
            }
        )
        deduped = list(dict.fromkeys(q.strip() for q in result.questions if q and q.strip()))
        return deduped[:target_count]
    except Exception as exc:
        print("Subquestion parsing failed:", exc)
        raise
