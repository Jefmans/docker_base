from langchain_openai  import OpenAIEmbeddings  # or `from langchain_openai import OpenAIEmbeddings`
from app.models import TextChunkEmbedding
import os
from dotenv import load_dotenv
import logging
import tiktoken
from typing import List, Callable


MODEL = "text-embedding-3-small"
TOKEN_LIMIT = 300_000
TARGET_BATCH_TOKENS = 250_000  # stay below limit

load_dotenv()

logger = logging.getLogger(__name__)
embedding_model = OpenAIEmbeddings(
    model=MODEL,
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

# Initialize tokenizer for your embedding model
encoding = tiktoken.encoding_for_model(MODEL)

def estimate_tokens(text: str) -> int:
    return len(encoding.encode(text))

def embed_chunks_streamed(chunks: List[dict], save_fn: Callable[[List[TextChunkEmbedding]], None]):
    logger.info(f"⚡ Embedding {len(chunks)} chunks in token-capped batches")

    current_batch = []
    current_tokens = 0

    for chunk in chunks:
        chunk_tokens = estimate_tokens(chunk["text"])

        # Start new batch if this chunk would exceed limit
        if current_tokens + chunk_tokens > TARGET_BATCH_TOKENS:
            _process_batch(current_batch, save_fn)
            current_batch = []
            current_tokens = 0

        current_batch.append(chunk)
        current_tokens += chunk_tokens

    # Process any remaining batch
    if current_batch:
        _process_batch(current_batch, save_fn)

    logger.info(f"✅ All chunks embedded and saved")


def _process_batch(batch: List[dict], save_fn):
    logger.info(f"🔄 Embedding batch of {len(batch)} chunks")
    texts = [c["text"] for c in batch]

    try:
        vectors = embedding_model.embed_documents(texts)
    except Exception as e:
        logger.error(f"❌ Failed to embed batch: {e}")
        raise

    results = []
    for chunk, vector in zip(batch, vectors):
        results.append(TextChunkEmbedding(
            chunk_size=chunk["chunk_size"],
            chunk_index=chunk["chunk_index"],
            text=chunk["text"],
            pages=chunk["pages"],
            embedding=vector
        ))

    save_fn(results)
    logger.info(f"📦 Saved {len(results)} embedded chunks")
