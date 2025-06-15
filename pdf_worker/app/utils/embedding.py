from openai import OpenAIEmbeddings  # or `from langchain_openai import OpenAIEmbeddings`
from app.models import TextChunkEmbedding
import os
from dotenv import load_dotenv

load_dotenv()
embedding_model = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=os.getenv("OPENAI_API_KEY"))

def embed_chunks(chunks: List[dict]) -> List[TextChunkEmbedding]:
    texts = [chunk["text"] for chunk in chunks]
    vectors = embedding_model.embed_documents(texts)

    results = []
    for chunk, vector in zip(chunks, vectors):
        results.append(TextChunkEmbedding(
            chunk_size=chunk["chunk_size"],
            chunk_index=chunk["chunk_index"],
            text=chunk["text"],
            pages=chunk["pages"],
            embedding=vector
        ))
    return results
