from langchain_openai  import OpenAIEmbeddings  # or `from langchain_openai import OpenAIEmbeddings`
from app.models import TextChunkEmbedding
import os
from dotenv import load_dotenv
from typing import List
import logging


load_dotenv()

logger = logging.getLogger(__name__)
embedding_model = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

def embed_chunks(chunks: List[dict], batch_size: int = 100) -> List[TextChunkEmbedding]:
    """
    Embeds text chunks in safe batches (e.g., 100 at a time) to avoid OpenAI's token limit.
    """
    results = []
    logger.info(f"Embedding {len(chunks)} chunks in batches of {batch_size}")

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        texts = [chunk["text"] for chunk in batch]

        try:
            vectors = embedding_model.embed_documents(texts)
        except Exception as e:
            logger.error(f"❌ Error embedding batch {i}-{i+batch_size}: {e}")
            raise

        for chunk, vector in zip(batch, vectors):
            results.append(TextChunkEmbedding(
                chunk_size=chunk["chunk_size"],
                chunk_index=chunk["chunk_index"],
                text=chunk["text"],
                pages=chunk["pages"],
                embedding=vector
            ))

    logger.info(f"✅ Finished embedding {len(results)} chunks")
    return results



def embed_chunks_streaming(chunks: List[dict], save_fn, batch_size: int = 1):
    """
    Embed and save chunks one-by-one or in small batches, streaming-style.
    `save_fn` is a function to store the embeddings (e.g., to Elasticsearch).
    """
    logger.info(f"Streaming embedding for {len(chunks)} chunks...")

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        texts = [chunk["text"] for chunk in batch]

        try:
            vectors = embedding_model.embed_documents(texts)
        except Exception as e:
            logger.error(f"❌ Error embedding batch {i}-{i+batch_size}: {e}")
            raise

        embedded_batch = []
        for chunk, vector in zip(batch, vectors):
            embedding_record = TextChunkEmbedding(
                chunk_size=chunk["chunk_size"],
                chunk_index=chunk["chunk_index"],
                text=chunk["text"],
                pages=chunk["pages"],
                embedding=vector
            )
            embedded_batch.append(embedding_record)

        save_fn(embedded_batch)

    logger.info(f"✅ Done streaming {len(chunks)} chunks")
