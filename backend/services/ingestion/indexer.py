# backend/services/ingestion/indexer.py

"""
Indexer
========

Takes records from the Loader and upserts them into ChromaDB.

HOW IT WORKS:
  1. Receives a dict of { collection_name: [records] } from the loader
  2. For each collection, gets or creates it in ChromaDB
  3. Extracts doc_id, text, and metadata from each record
  4. Upserts in batches of 100

UPSERT vs INSERT:
  Upsert = insert if new, update if already exists.
  This means you can safely re-run ingestion at any time without
  creating duplicate records.

STABLE IDs (from loader.py):
  The loader generates a stable MD5 hash ID for each record based on:
    collection + filename + luganda text
  The indexer uses this ID directly from record["doc_id"].
  Do NOT regenerate IDs here — that would break the upsert logic.

CHROMADB METADATA RULES:
  ChromaDB only accepts these metadata value types: str, int, float, bool.
  Lists and nested dicts will cause errors.
  The sanitize_metadata() function converts everything to safe types.
"""

import logging
from typing import Any

from backend.db.chroma_client import get_chroma_client
from backend.services.ingestion.embedder import get_chroma_embedding_fn

logger = logging.getLogger(__name__)

# ── Collection Descriptions ───────────────────────────────────────────────────

COLLECTION_DESCRIPTIONS = {
    "vocabulary": "Luganda vocabulary words with English translations",
    "sentences":  "Luganda example sentences and phrases",
    "grammar":    "Luganda grammar rules and notes",
    "proverbs":   "Kiganda proverbs with meanings",
}

# Only these types are safe to store as ChromaDB metadata values
VALID_META_TYPES = (str, int, float, bool)


# ── Metadata Sanitiser ────────────────────────────────────────────────────────

def sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a metadata dict into ChromaDB-safe types.

    Rules:
      - str, int, float, bool  → kept as-is
      - list                   → joined as comma-separated string
      - dict                   → converted to string
      - None or False          → stored as empty string ""
      - Anything else          → converted to str

    Also removes any keys with empty string values that we don't
    want cluttering the metadata (optional — currently keeps them
    so the schema is consistent across all records).
    """
    safe = {}
    for key, value in metadata.items():
        if isinstance(value, VALID_META_TYPES):
            safe[key] = value
        elif isinstance(value, list):
            safe[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            safe[key] = str(value)
        elif value is None:
            safe[key] = ""
        else:
            safe[key] = str(value)
    return safe


# ── Main Indexer ───────────────────────────────────────────────────────────────

def index_records(
    records_by_collection: dict[str, list[dict[str, Any]]],
    batch_size: int = 100,
) -> dict[str, int]:
    """
    Index (upsert) all records into ChromaDB.

    Parameters
    ----------
    records_by_collection : dict
        Keys: collection names ("vocabulary", "sentences", etc.)
        Values: lists of record dicts from loader.py.

        Each record must have:
          - "doc_id"    : str  — stable unique ID from _make_stable_id()
          - "text"      : str  — the text to embed
          - "metadata"  : dict — fields to store alongside the embedding
          - "collection": str  — which collection this belongs to

    batch_size : int
        Records to upsert per batch. 100 is safe for 16GB RAM.
        Reduce to 50 if you see memory errors.

    Returns
    -------
    dict mapping collection_name → count of records successfully upserted.
    """
    client  = get_chroma_client()
    summary: dict[str, int] = {}

    for collection_name, records in records_by_collection.items():

        if not records:
            logger.info(f"'{collection_name}': no records to index — skipping.")
            summary[collection_name] = 0
            continue

        logger.info(f"'{collection_name}': indexing {len(records)} records...")

        # Get or create the ChromaDB collection
        # hnsw:space = "cosine" means distances range 0–2 (not 0–1)
        # This matches the score formula in search_service.py:
        #   score = (1 - distance / 2) * 100
        try:
            collection = client.get_or_create_collection(
                name=collection_name,
                embedding_function=get_chroma_embedding_fn(),
                metadata={
                    "description": COLLECTION_DESCRIPTIONS.get(collection_name, ""),
                    "hnsw:space":  "cosine",
                }
            )
        except Exception as e:
            logger.error(f"Could not get/create collection '{collection_name}': {e}")
            summary[collection_name] = 0
            continue

        total_upserted = 0
        total_skipped  = 0

        # Process in batches
        for batch_start in range(0, len(records), batch_size):
            batch = records[batch_start : batch_start + batch_size]

            ids       = []
            documents = []
            metadatas = []

            for record in batch:
                # ── Validate ──────────────────────────────────────────────
                text   = _safe_get_text(record)
                doc_id = record.get("doc_id", "").strip()
                meta   = record.get("metadata", {})

                if not text:
                    total_skipped += 1
                    logger.debug(f"Skipping record with empty text in '{collection_name}'")
                    continue

                if not doc_id:
                    total_skipped += 1
                    logger.warning(
                        f"Skipping record with no doc_id in '{collection_name}': "
                        f"luganda={meta.get('luganda', '?')}"
                    )
                    continue

                # ── Sanitise metadata ─────────────────────────────────────
                safe_meta = sanitize_metadata(meta)

                # Store collection name inside metadata so search results
                # can identify which collection a record came from.
                safe_meta["_collection"] = collection_name

                ids.append(doc_id)
                documents.append(text)
                metadatas.append(safe_meta)

            if not ids:
                continue

            # ── Upsert batch ──────────────────────────────────────────────
            try:
                collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                )
                total_upserted += len(ids)
                batch_num = batch_start // batch_size + 1
                logger.debug(f"  Batch {batch_num}: upserted {len(ids)} records")
            except Exception as e:
                batch_num = batch_start // batch_size + 1
                logger.error(
                    f"Batch {batch_num} failed for '{collection_name}': {e}",
                    exc_info=True,
                )

        logger.info(
            f"'{collection_name}': "
            f"{total_upserted} upserted, {total_skipped} skipped."
        )
        summary[collection_name] = total_upserted

    return summary


def _safe_get_text(record: dict) -> str:
    """
    Extract the 'text' field from a record safely.
    Returns empty string if missing or blank.
    """
    text = record.get("text", "")
    if not isinstance(text, str):
        text = str(text)
    return text.strip()


# ── Utility: Clear Collection ─────────────────────────────────────────────────

def clear_collection(collection_name: str) -> bool:
    """
    Delete all documents from a collection and recreate it empty.

    Use this only when you want to start completely fresh.
    WARNING: This permanently deletes all data in the collection.

    Returns True if successful, False if an error occurred.
    """
    client = get_chroma_client()
    try:
        client.delete_collection(collection_name)
        client.get_or_create_collection(
            name=collection_name,
            embedding_function=get_chroma_embedding_fn(),
            metadata={
                "description": COLLECTION_DESCRIPTIONS.get(collection_name, ""),
                "hnsw:space":  "cosine",
            }
        )
        logger.info(f"Collection '{collection_name}' cleared and recreated empty.")
        return True
    except Exception as e:
        logger.error(f"Failed to clear '{collection_name}': {e}")
        return False
