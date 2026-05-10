# backend/services/ingestion/embedder.py

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_model_name = "paraphrase-multilingual-MiniLM-L12-v2"

_model = None
_chroma_embedding_fn = None


def get_chroma_embedding_fn():
    """
    Return a ChromaDB-compatible embedding function using the multilingual model.

    Pass this to get_or_create_collection() so ChromaDB uses the same model
    for both ingestion and search — no mismatch possible. Cached after first call.
    """
    global _chroma_embedding_fn
    if _chroma_embedding_fn is None:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        _chroma_embedding_fn = SentenceTransformerEmbeddingFunction(model_name=_model_name)
    return _chroma_embedding_fn


def get_model():
    """Load and return the sentence-transformers model (lazy)."""
    global _model

    if _model is not None:
        return _model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is not installed.\n"
            "Install it with: pip install sentence-transformers"
        )

    logger.info(f"Loading embedding model: {_model_name}")
    logger.info("(This may take a moment the first time — model will be cached)")

    _model = SentenceTransformer(_model_name)
    logger.info("Embedding model loaded successfully.")
    return _model


def get_embedding_model():
    """Alias for get_model(). Used by translation/service.py — kept for compatibility."""
    return get_model()


def embed_texts(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """Generate embeddings for a list of text strings."""
    if not texts:
        return []

    model = get_model()

    logger.info(f"Embedding {len(texts)} texts in batches of {batch_size}...")

    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
    )

    logger.info(f"Embedding complete. Shape: {embeddings.shape}")

    return embeddings.tolist()


def embed_single(text: str) -> list[float]:
    """Embed a single text string."""
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text.")

    results = embed_texts([text])
    return results[0]
