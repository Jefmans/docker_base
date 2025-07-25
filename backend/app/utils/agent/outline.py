from typing import List, Dict
from langchain_openai import ChatOpenAI

from pydantic import BaseModel, Field
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI



class OutlineSection(BaseModel):
    heading: str
    goals: str
    questions: List[str]

class Outline(BaseModel):
    title: str
    abstract: str
    sections: List[OutlineSection]




def generate_outline(subquestions: List[str], query: str) -> Outline:
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    parser = PydanticOutputParser(pydantic_object=Outline)

    formatted_subq = "\n".join(f"- {q}" for q in subquestions)

    prompt = PromptTemplate(
        template="""
You are a scientific writer assistant. Create a full outline for a scientific article based on the main question and subquestions below.

MAIN QUESTION:
{query}

SUBQUESTIONS:
{formatted_subq}

{format_instructions}
""",
        input_variables=["query", "formatted_subq"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )

    chain = prompt | llm | parser
    return chain.invoke({"query": query, "formatted_subq": formatted_subq})
