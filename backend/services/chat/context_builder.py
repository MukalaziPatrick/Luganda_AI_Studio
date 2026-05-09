# backend/services/chat/context_builder.py

"""
Fetches relevant Luganda context from ChromaDB
before sending a message to Ollama.

This is the RAG (Retrieval Augmented Generation) step.
Instead of the model guessing about Luganda,
we give it real data from your knowledge base.
"""

from backend.db.chroma_client import get_chroma_client
from backend.services.ingestion.embedder import get_model
from backend.core.config import CHAT_CONTEXT_RESULTS
import logging

logger = logging.getLogger(__name__)


def build_context(user_message: str) -> dict:
    """
    Search ChromaDB collections for content relevant
    to the user's message.

    Returns a dict with:
      - context_text : formatted string to inject into prompt
      - sources      : list of raw matches for logging
    """
    try:
        client = get_chroma_client()
        model = get_model()

        # Embed the user's message
        query_embedding = model.encode(user_message).tolist()

        # Collections to search
        # CHANGED: added "documents" so PDF-ingested content is included in context
        collections_to_search = [
            "vocabulary",
            "sentences",
            "grammar",
            "documents",
        ]

        all_results = []

        for collection_name in collections_to_search:
            try:
                collection = client.get_collection(collection_name)
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=min(CHAT_CONTEXT_RESULTS, collection.count()),
                    include=["documents", "metadatas", "distances"]
                )

                if not results["documents"] or not results["documents"][0]:
                    continue

                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0]
                ):
                    # Convert ChromaDB cosine distance to score
                    score = (1 - dist / 2) * 100

                    # Only include results with meaningful relevance
                    if score >= 25:
                        all_results.append({
                            "collection": collection_name,
                            "document": doc,
                            "metadata": meta,
                            "score": round(score, 1)
                        })

            except Exception as e:
                logger.warning(f"Could not search collection '{collection_name}': {e}")
                continue

        # Sort by score, take top results
        all_results.sort(key=lambda x: x["score"], reverse=True)
        top_results = all_results[:CHAT_CONTEXT_RESULTS]

        if not top_results:
            return {
                "context_text": "",
                "sources": []
            }

        # Format into readable context block
        lines = ["--- Luganda Knowledge Base Context ---"]
        for r in top_results:
            meta = r["metadata"]
            lines.append(f"[{r['collection'].upper()}] {r['document']}")

            # Add example sentence if available
            if meta.get("example_sentence_luganda"):
                lines.append(
                    f"  Example: {meta['example_sentence_luganda']} "
                    f"→ {meta.get('example_sentence_english', '')}"
                )

        lines.append("--- End of Context ---")
        context_text = "\n".join(lines)

        return {
            "context_text": context_text,
            "sources": [r["document"] for r in top_results]
        }

    except Exception as e:
        logger.error(f"Context builder failed: {e}")
        return {
            "context_text": "",
            "sources": []
        }