import fitz  # PyMuPDF
from langchain_openai import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
import os
from dotenv import load_dotenv
from langchain.prompts import PromptTemplate
from app.models import DocumentMetadata

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# --- Metadata Extraction ---
def get_doc_info(file_path):
    doc = fitz.open(file_path)
    num_pages = len(doc)

    N = 10
    page_indices = list(range(min(N, num_pages))) + list(range(max(num_pages - N, 0), num_pages))

    year_pattern = r"(?:19|20)\d{2}"
    candidate_pages = []

    for i in page_indices:
        text = doc[i].get_text()
        candidate_pages.append(text)
    combined_text = "\n---\n".join(candidate_pages)


    logger.info(f"[get_doc_info] Pages selected: {page_indices}")
    logger.info(f"[get_doc_info] Combined text length: {len(combined_text)} characters")
    logger.info(f"[get_doc_info] Approx. token count: {len(combined_text) // 4} tokens")


    # Load API key
    load_dotenv()
    openai_api_key = os.getenv("OPENAI_API_KEY")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=openai_api_key)

    parser = PydanticOutputParser(pydantic_object=DocumentMetadata)
    prompt = PromptTemplate(
        template="Extract the metadata from this text:\n\n{text}\n\n{format_instructions}",
        input_variables=["text"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )

    chain = prompt | llm | parser

    try:
        result = chain.invoke({"text": combined_text})
    except Exception as e:
        print("❌ Parsing failed:", e)
        return None


    return result




