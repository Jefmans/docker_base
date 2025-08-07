from typing import List, Dict
from langchain_openai import ChatOpenAI

from pydantic import BaseModel, Field
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI



from typing import List, Optional
from pydantic import BaseModel

# from app.models.research_tree import ResearchTree, ResearchNode, Chunk


class OutlineSection(BaseModel):
    heading: str
    goals: Optional[str] = None
    questions: List[str] = []
    subsections: List["OutlineSection"] = []

    class Config:
        arbitrary_types_allowed = True

OutlineSection.update_forward_refs()



class Outline(BaseModel):
    title: str
    abstract: str
    sections: List[OutlineSection]




def generate_outline_from_tree(tree: ResearchTree) -> Outline:
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    parser = PydanticOutputParser(pydantic_object=Outline)

    all_chunks = [c.text for c in tree.root_node.all_chunks()]
    subquestions = list(tree.used_questions or [])
    query = tree.query
    # formatted_subq = "\n".join(f"- {q}" for q in subquestions)

    prompt = PromptTemplate(
        template="""
            You are a scientific writer assistant. Create a full outline for a scientific article based on the main question and subquestions below.

            MAIN QUESTION:
            {query}

            SUBQUESTIONS:
            {subquestions}

            CONTEXT:
            {all_chunks}

            {format_instructions}
            """,
        input_variables=["query", "formatted_subq", "all_chunks "],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )

    chain = prompt | llm | parser
    return chain.invoke({"query": query, "formatted_subq": subquestions, "all_chunks": all_chunks})


