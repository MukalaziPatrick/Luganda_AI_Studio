# backend/services/search_service.py

"""
Search Service for Luganda AI Studio
=====================================

Provides layered search with this priority order:

  1. EXACT MATCH       → score 100   (query == field value)
  2. NORMALIZED MATCH  → score 95    (after lowercasing + stripping punctuation)
  3. PREFIX MATCH      → score 85    (field starts with query)
  4. SUBSTRING MATCH   → score 65    (query appears inside field)
  5. SEMANTIC MATCH    → score 0–60  (ChromaDB vector similarity)

Results below MIN_SCORE (25) are hidden from the user.

Why this order matters:
  - Semantic-only search is great for meaning but bad for exact words.
  - If a user types "ssebo", they want "ssebo", not a vaguely related word.
  - Layering gives fast, accurate results for known words + fuzzy results
    for concepts and phrases.
"""

import re
import logging
import unicodedata
from typing import Any

from backend.db.chroma_client import get_chroma_client
from backend.services.ingestion.embedder import get_chroma_embedding_fn

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Collections that exist in ChromaDB
ALL_COLLECTIONS = ["vocabulary", "sentences", "grammar", "proverbs", "documents"]

# Minimum score to show a result to the user (0–100 scale)
MIN_SCORE = 25

# Score ceilings for each match tier (semantic is capped lower)
SCORE_EXACT      = 100
SCORE_NORMALIZED = 95
SCORE_PREFIX     = 85
SCORE_SUBSTRING  = 65
SCORE_SEMANTIC_MAX = 60   # semantic results are capped at 60 so exact wins

# How many results to fetch from ChromaDB before re-ranking
CHROMA_FETCH_K = 20


# ── Text Normalisation ────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """
    Lowercase, remove punctuation, strip extra whitespace.
    Used to compare strings in a forgiving way.

    Example:
        "Ssebo!" → "ssebo"
        "Good morning." → "good morning"
    """
    if not text:
        return ""
    # Lowercase
    text = text.lower()
    # Remove diacritics (accents etc.) — keeps Luganda letters intact
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Remove punctuation except spaces
    text = re.sub(r"[^\w\s]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Score Helpers ─────────────────────────────────────────────────────────────

def chroma_distance_to_score(distance: float) -> int:
    """
    Convert ChromaDB cosine distance to a 0–100 score.

    ChromaDB cosine distance range: 0 (identical) to 2 (opposite).
    Formula: score = (1 - distance/2) * 100
    Then cap at SCORE_SEMANTIC_MAX so semantic never beats exact matches.

    Examples:
        distance 0.0  → raw 100 → capped at 60
        distance 0.5  → raw 75  → capped at 60
        distance 0.8  → raw 60  → capped at 60
        distance 1.0  → raw 50  → returned as 50
        distance 1.4  → raw 30  → returned as 30
        distance 1.6  → raw 20  → below MIN_SCORE, will be hidden
    """
    raw = (1.0 - distance / 2.0) * 100.0
    score = min(raw, SCORE_SEMANTIC_MAX)
    return max(0, int(round(score)))


def score_label(score: int) -> str:
    """Return a human-readable label for a score value."""
    if score >= 95:
        return "Exact match"
    if score >= 80:
        return "Strong match"
    if score >= 60:
        return "Good match"
    if score >= 40:
        return "Related"
    return "Weak match"


# ── Exact / Prefix / Substring Matching ──────────────────────────────────────

def _get_text_fields(metadata: dict) -> list[str]:
    """
    Extract all searchable text fields from a metadata dict.
    Covers all field names used across vocabulary, sentences, grammar, proverbs.
    """
    candidates = [
        metadata.get("luganda", ""),
        metadata.get("english", ""),
        metadata.get("word", ""),
        metadata.get("phrase", ""),
        metadata.get("meaning", ""),
        metadata.get("translation", ""),
        metadata.get("notes", ""),
        metadata.get("note", ""),
        metadata.get("context", ""),
    ]
    return [str(c).strip() for c in candidates if c]


def lexical_score(query: str, metadata: dict) -> int | None:
    """
    Check for exact, normalized, prefix, or substring match.

    Returns a score (int) if a match is found, or None if no lexical match.

    This runs BEFORE semantic search. If this returns a score,
    we use it directly and give the result priority.
    """
    q_raw  = query.strip()
    q_norm = normalize(query)

    fields = _get_text_fields(metadata)

    for field in fields:
        f_raw  = field.strip()
        f_norm = normalize(field)

        # Tier 1: Exact match (case-insensitive)
        if q_raw.lower() == f_raw.lower():
            return SCORE_EXACT

        # Tier 2: Normalized match
        if q_norm and f_norm and q_norm == f_norm:
            return SCORE_NORMALIZED

        # Tier 3: Prefix match (field starts with query, or query starts with field)
        if q_norm and f_norm:
            if f_norm.startswith(q_norm) or q_norm.startswith(f_norm):
                return SCORE_PREFIX

        # Tier 4: Substring match
        if q_norm and f_norm and len(q_norm) >= 2:
            if q_norm in f_norm or f_norm in q_norm:
                return SCORE_SUBSTRING

    return None  # No lexical match found


# ── Main Search Function ──────────────────────────────────────────────────────

def search_knowledge(
    query: str,
    collection_filter: str = "all",
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """
    Search the knowledge base and return ranked results.

    Parameters
    ----------
    query : str
        The search query (word, phrase, or sentence).
    collection_filter : str
        "all" to search everything, or a specific collection name
        ("vocabulary", "sentences", "grammar", "proverbs").
    top_k : int
        Maximum number of results to return.

    Returns
    -------
    list of dicts, each with:
        - text       : str   — the stored document text
        - metadata   : dict  — all metadata fields
        - score      : int   — 0–100 quality score
        - score_label: str   — human-readable label
        - match_type : str   — "exact", "prefix", "substring", "semantic"
        - collection : str   — which collection this came from
        - distance   : float — raw ChromaDB distance (for debugging)
    """
    query = query.strip()
    if not query:
        return []

    client = get_chroma_client()

    # Determine which collections to search
    if collection_filter and collection_filter.lower() != "all":
        collections_to_search = [collection_filter.lower()]
    else:
        collections_to_search = ALL_COLLECTIONS

    raw_results: list[dict[str, Any]] = []

    for col_name in collections_to_search:
        try:
            collection = client.get_or_create_collection(
                col_name,
                embedding_function=get_chroma_embedding_fn(),
            )
        except Exception as e:
            logger.warning(f"Could not access collection '{col_name}': {e}")
            continue

        # Check how many documents are in this collection
        try:
            count = collection.count()
        except Exception:
            count = 0

        if count == 0:
            logger.debug(f"Collection '{col_name}' is empty, skipping.")
            continue

        # Query ChromaDB for semantic matches
        try:
            fetch_k = min(CHROMA_FETCH_K, count)
            results = collection.query(
                query_texts=[query],
                n_results=fetch_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"ChromaDB query failed for '{col_name}': {e}")
            continue

        # Unpack ChromaDB response
        # results["documents"][0] is a list of document texts
        # results["metadatas"][0] is a list of metadata dicts
        # results["distances"][0] is a list of float distances
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            meta = meta or {}
            # Inject collection name into metadata so frontend can use it
            meta["_collection"] = col_name

            # Try lexical (exact/prefix/substring) match first
            lex_score = lexical_score(query, meta)

            if lex_score is not None:
                # We got a lexical match — determine the label
                if lex_score >= SCORE_EXACT:
                    mtype = "exact"
                elif lex_score >= SCORE_NORMALIZED:
                    mtype = "exact"
                elif lex_score >= SCORE_PREFIX:
                    mtype = "prefix"
                else:
                    mtype = "substring"

                raw_results.append({
                    "text":        doc or "",
                    "metadata":    meta,
                    "score":       lex_score,
                    "score_label": score_label(lex_score),
                    "match_type":  mtype,
                    "collection":  col_name,
                    "distance":    round(dist, 4),
                })
            else:
                # Fall back to semantic score
                sem_score = chroma_distance_to_score(dist)

                if sem_score < MIN_SCORE:
                    # Skip — result is too weak to show
                    logger.debug(
                        f"Hiding weak result (score={sem_score}) from '{col_name}': "
                        f"distance={dist:.3f}"
                    )
                    continue

                raw_results.append({
                    "text":        doc or "",
                    "metadata":    meta,
                    "score":       sem_score,
                    "score_label": score_label(sem_score),
                    "match_type":  "semantic",
                    "collection":  col_name,
                    "distance":    round(dist, 4),
                })

    # ── Deduplicate ───────────────────────────────────────────────────────────
    # If the same item appears in multiple collections (shouldn't happen but
    # just in case), keep the one with the highest score.
    seen_texts: dict[str, dict] = {}
    for item in raw_results:
        key = (item["text"], item["collection"])
        if key not in seen_texts or item["score"] > seen_texts[key]["score"]:
            seen_texts[key] = item

    deduped = list(seen_texts.values())

    # ── Sort: highest score first ─────────────────────────────────────────────
    deduped.sort(key=lambda x: x["score"], reverse=True)

    # ── Return top_k ─────────────────────────────────────────────────────────
    return deduped[:top_k]
