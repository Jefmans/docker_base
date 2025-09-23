import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from elasticsearch import Elasticsearch
from langchain_elasticsearch import ElasticsearchStore

# --- Models ---
class AgentQueryRequest(BaseModel):
    query: str
    top_k: int = 5

# --- Setup ---
es = Elasticsearch("http://elasticsearch:9200")
embedding_model = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)

vectorstore = ElasticsearchStore(
    es_connection=es,
    index_name="pdf_chunks",
    embedding=embedding_model,
    vector_field='vector',
    text_field = 'text',    
)

caption_store = ElasticsearchStore(
    es_connection=es,
    index_name="captions",
    embedding=embedding_model,
    vector_field='vector',
    text_field = 'text',    
)

router = APIRouter()

# --- Endpoint ---
@router.post("/query/agent")
async def query_agent(request: AgentQueryRequest):
    try:
        # Step 1: Retrieve initial context
        chunks = vectorstore.similarity_search(request.query, k=request.top_k)
        captions = caption_store.similarity_search(request.query, k=request.top_k)
        context = "\n\n".join([doc.page_content for doc in chunks + captions])

        # Step 2: Generate initial answer
        prompt = f"""You are a scientific assistant. Based on the following context, answer the user's question.

        === CONTEXT ===
        {context}

        === QUESTION ===
        {request.query}
        """
        initial_answer = llm.invoke(prompt).content.strip()

        # Step 3: Generate hypotheses/sub-questions
        followup_prompt = f"""
        Based on the original question and answer, generate 3 to 5 meaningful sub-questions or hypotheses to explore further.

        QUESTION: {request.query}
        ANSWER: {initial_answer}

        Respond with a JSON list of strings like:
        ["...", "...", "..."]
        """
        followup_raw = llm.invoke(followup_prompt).content
        try:
            sub_questions = json.loads(followup_raw)
        except:
            sub_questions = [q.strip("- ") for q in followup_raw.strip().split("\n") if q.strip()]

        # Step 4: Answer each sub-question
        sub_answers = []
        for q in sub_questions:
            docs = vectorstore.similarity_search(q, k=request.top_k)
            caption_docs = caption_store.similarity_search(q, k=request.top_k)
            combined_context = "\n\n".join([doc.page_content for doc in docs + caption_docs])
            sub_prompt = f"""
            Based on the following context, answer this sub-question:

            CONTEXT:
            {combined_context}

            QUESTION: {q}
            """
            answer = llm.invoke(sub_prompt).content.strip()
            sub_answers.append({"question": q, "answer": answer})

        # Step 5: Final synthesis
        synthesis_prompt = f"""
        You are a scientific agent. Combine the information below to give a final, structured answer to the original question.

        ORIGINAL QUESTION: {request.query}
        INITIAL ANSWER: {initial_answer}

        SUB-ANSWERS:
        {json.dumps(sub_answers, indent=2)}

        Return a concise yet complete answer.
        """
        final_answer = llm.invoke(synthesis_prompt).content.strip()

        return {
            "query": request.query,
            "initial_answer": initial_answer,
            "chunks": chunks,
            "captions": captions, 
            "sub_questions": sub_questions,
            "sub_answers": sub_answers,
            "final_answer": final_answer
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent failed: {str(e)}")
