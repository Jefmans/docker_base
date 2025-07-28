from typing import List
from langchain_openai import ChatOpenAI
import json

from pydantic import BaseModel
from typing import List

class SubquestionList(BaseModel):
    questions: List[str]



from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnableMap
from langchain_openai import ChatOpenAI
import json

def generate_subquestions_from_chunks(chunks: List[str], user_query: str, model_name: str = "gpt-4o") -> List[str]:
    llm = ChatOpenAI(model=model_name, temperature=0)

    # Limit chunk length to avoid context overflow
    context = "\n\n".join(chunks[:20])

    parser = PydanticOutputParser(pydantic_object=SubquestionList)

    prompt = PromptTemplate(
        template="""
            You are a scientific assistant. Based on the user query and real scientific context below, generate a list of 5–10 detailed subquestions.

            Only ask questions that are grounded in the context. Return your result using this format:
            {format_instructions}

            === USER QUESTION ===
            {query}

            === CONTEXT ===
            {context}
            """,
        input_variables=["query", "context"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )

    chain = prompt | llm | parser

    try:
        result = chain.invoke({"query": user_query, "context": context})
        return result.questions
    except Exception as e:
        print("❌ Subquestion parsing failed:", e)
        raise
