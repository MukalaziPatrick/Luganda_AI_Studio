# backend/api/routes/knowledge.py

"""
Knowledge API Routes
=====================

Provides:
  GET /api/v1/knowledge/search   — search the knowledge base
  GET /api/v1/knowledge/status   — how many items are in each collection

Collections searched:
  vocabulary, sentences, grammar, proverbs  — JSON datasets
  documents                                  — PDF chunks (from run_pdf_ingestion.py)

The actual search logic lives in:
  backend/services/search_service.py
"""

import logging
from fastapi import APIRouter, HTTPException, Query

from backend.services.search_service import search_knowledge, ALL_COLLECTIONS
from backend.db.chroma_client import get_chroma_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Documents collection is populated by run_pdf_ingestion.py
# It is included in status but searched via the same search_knowledge() function
ALL_COLLECTIONS_WITH_DOCS = ALL_COLLECTIONS + ["documents"]


# ── Search Endpoint ────────────────────────────────────────────────────────────

@router.get("/search")  # CHANGED: was "/knowledge/search" → doubled to /api/v1/knowledge/knowledge/search
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    top_k: int = Query(default=10, ge=1, le=50, description="Max results to return"),
    collection: str = Query(default="all", description="Filter by collection name"),
):
    """
    Search the Luganda knowledge base.

    Uses layered matching:
    1. Exact word match  → score 100
    2. Normalized match  → score 95
    3. Prefix match      → score 85
    4. Substring match   → score 65
    5. Semantic match    → score 25-60 (hidden if below 25)

    Returns results sorted best-first.
    Searches all collections including PDF documents.
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    logger.info(f"Search request: q='{query}' collection='{collection}' top_k={top_k}")

    try:
        results = search_knowledge(
            query=query,
            collection_filter=collection,
            top_k=top_k,
        )
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

    logger.info(f"Search returned {len(results)} results for: '{query}'")

    return {
        "query":      query,
        "collection": collection,
        "total":      len(results),
        "results":    results,
    }


# ── Status Endpoint ────────────────────────────────────────────────────────────

@router.get("/status")  # CHANGED: was "/knowledge/status" → doubled to /api/v1/knowledge/knowledge/status
async def knowledge_status():
    """
    Return the count of items in each ChromaDB collection.
    Includes both JSON collections and the PDF documents collection.
    """
    client = get_chroma_client()
    status = {}

    for col_name in ALL_COLLECTIONS_WITH_DOCS:
        try:
            col = client.get_or_create_collection(col_name)
            status[col_name] = col.count()
        except Exception as e:
            logger.warning(f"Could not count '{col_name}': {e}")
            status[col_name] = -1

    total = sum(v for v in status.values() if v >= 0)

    return {
        "collections":     status,
        "total_documents": total,
    }
