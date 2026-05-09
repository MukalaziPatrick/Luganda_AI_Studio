# backend/services/translation/service.py

"""
Translation service — Phase 2 (NLLB-200 neural fallback added).

Root cause of 500 error (historical):
- ChromaDB 1.5.5 .get() with include=["metadatas"] returns a dict
  where metadatas can be None if the collection query fails silently.
- The exception was swallowed, causing the function to return None.
- FastAPI then crashed trying to serialize None as a TranslationResponse.

Fixes applied:
- Added safe null checks at every step of the scan
- Added explicit error logging inside _scan_collection so failures surface
- Guaranteed that translate() ALWAYS returns a TranslationResponse object
- Added a top-level safety net at the end of translate() as final fallback
- Simplified ChromaDB .get() call to avoid version compatibility issues
"""

import logging
from typing import Optional

from backend.db.chroma_client import chroma_client
from backend.services.ingestion.embedder import get_embedding_model
from backend.services.translation.nllb_service import nllb_translator
from backend.services.translation.schemas import TranslationRequest, TranslationResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------- #
# Constants
# ---------------------------------------------------------------------- #

COLLECTIONS_TO_SEARCH = ["vocabulary", "sentences", "proverbs"]

# MiniLM cosine distance: 0 = identical, 2 = opposite.
# similarity = 1 - distance
# 0.50 means we accept matches where the vectors are reasonably close.
SEMANTIC_THRESHOLD = 0.50

# How many records to pull per collection scan.
# Our full dataset is 492 records — 1000 is a safe ceiling.
SCAN_LIMIT = 1000


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #

def _normalize(text: str) -> str:
    """Lowercase, strip whitespace, strip trailing punctuation."""
    return text.strip().lower().rstrip(".,!?;:")


def _get_source_field(direction: str) -> str:
    """Field we search AGAINST — the language the user typed in."""
    return "english" if direction == "en_to_lg" else "luganda"


def _get_target_field(direction: str) -> str:
    """Field we return AS the translation."""
    return "luganda" if direction == "en_to_lg" else "english"


# ---------------------------------------------------------------------- #
# Core: scan a collection and find the best match
# ---------------------------------------------------------------------- #

def _scan_collection(
    collection_name: str,
    source_field: str,
    target_field: str,
    input_text: str,
) -> Optional[dict]:
    """
    Pull all records from a collection and compare in Python.

    This is safe, simple, and avoids ChromaDB filter compatibility issues.
    With 500 records, this runs in milliseconds.

    Match priority:
    1. Exact match       — strip whitespace only, case preserved
    2. Normalized match  — both sides lowercased
    3. Partial match     — input word found inside stored value
                           e.g. "stomach" matches "Stomach / Belly"
    """
    try:
        col = chroma_client.get_collection(name=collection_name)

        # Simple .get() with no filters — just pull everything
        raw = col.get(include=["metadatas"])

        # Safety check — metadatas can be None if collection is empty
        if raw is None:
            logger.warning(f"[{collection_name}] col.get() returned None.")
            return None

        metadatas = raw.get("metadatas")
        if not metadatas:
            logger.warning(f"[{collection_name}] metadatas is empty or None.")
            return None

        logger.debug(
            f"[{collection_name}] Scanning {len(metadatas)} records | "
            f"source_field='{source_field}' | target_field='{target_field}'"
        )

        input_stripped = input_text.strip()
        input_normalized = _normalize(input_text)

        # ---------------------------------------------------------- #
        # Pass A — Exact match (strip only, case preserved)
        # ---------------------------------------------------------- #
        for meta in metadatas:
            if not isinstance(meta, dict):
                continue
            stored = meta.get(source_field, "")
            if not stored:
                continue
            if stored.strip() == input_stripped:
                translation = meta.get(target_field)
                if translation:
                    logger.debug(
                        f"[{collection_name}] EXACT: "
                        f"'{stored}' → '{translation}'"
                    )
                    return {
                        "translated_text": translation,
                        "match_type": "exact",
                        "confidence": 1.0,
                        "matched_collection": collection_name,
                        "matched_source_file": meta.get("source_file"),
                    }

        # ---------------------------------------------------------- #
        # Pass B — Normalized match (lowercase both sides)
        # ---------------------------------------------------------- #
        for meta in metadatas:
            if not isinstance(meta, dict):
                continue
            stored = meta.get(source_field, "")
            if not stored:
                continue
            if _normalize(stored) == input_normalized:
                translation = meta.get(target_field)
                if translation:
                    logger.debug(
                        f"[{collection_name}] NORMALIZED: "
                        f"'{stored}' → '{translation}'"
                    )
                    return {
                        "translated_text": translation,
                        "match_type": "normalized",
                        "confidence": 0.98,
                        "matched_collection": collection_name,
                        "matched_source_file": meta.get("source_file"),
                    }

        # ---------------------------------------------------------- #
        # Pass C — Partial match
        # "stomach" matches "Stomach / Belly"
        # "foot" matches "Foot"
        # New: "hello world" matches if "hello" OR "world" appears in stored value
        # Only runs if input has at least one word >= 3 characters
        # AND input is 1-2 words only. Sentences (3+ words) skip this
        # pass entirely and fall through to semantic search → NLLB.
        # Without this guard, ANY word in a sentence can false-match
        # a stored entry (e.g. "market" in a sentence hitting transport.json). # CHANGED
        # ---------------------------------------------------------- #
        if len(input_normalized) >= 3 and len(input_normalized.split()) <= 2:  # CHANGED
            input_words = input_normalized.split()  # Split input into words # IMPROVED
            for meta in metadatas:
                if not isinstance(meta, dict):
                    continue
                stored = meta.get(source_field, "")
                if not stored:
                    continue
                stored_normalized = _normalize(stored)
                # Split on slash and hyphen to get individual words
                stored_words = (
                    stored_normalized
                    .replace("/", " ")
                    .replace("-", " ")
                    .split()
                )
                # Check if ANY input word matches ANY stored word # IMPROVED
                if any(word in stored_words for word in input_words):  # IMPROVED
                    translation = meta.get(target_field)
                    if translation:
                        logger.debug(
                            f"[{collection_name}] PARTIAL: "
                            f"'{stored}' → '{translation}'"
                        )
                        return {
                            "translated_text": translation,
                            "match_type": "partial",
                            "confidence": 0.85,
                            "matched_collection": collection_name,
                            "matched_source_file": meta.get("source_file"),
                        }

    except Exception as e:
        # Log the full error so we can diagnose future issues
        logger.error(
            f"_scan_collection failed for '{collection_name}': {e}",
            exc_info=True,
        )

    return None


# ---------------------------------------------------------------------- #
# Semantic match
# ---------------------------------------------------------------------- #

def _try_semantic_match(
    collection_name: str,
    target_field: str,
    input_text: str,
) -> Optional[dict]:
    """
    Use MiniLM embeddings to find the semantically closest record.

    ChromaDB returns cosine distance (lower = more similar).
    similarity = 1 - distance
    We only accept results where similarity >= SEMANTIC_THRESHOLD.
    """
    try:
        model = get_embedding_model()
        embedding = model.encode([input_text])[0].tolist()

        col = chroma_client.get_collection(name=collection_name)

        results = col.query(
            query_embeddings=[embedding],
            n_results=1,
            include=["metadatas", "distances"],
        )

        if not results:
            return None

        metadatas = results.get("metadatas")
        distances = results.get("distances")

        if not metadatas or not distances:
            return None

        if len(metadatas[0]) == 0:
            return None

        meta = metadatas[0][0]
        distance = distances[0][0]
        similarity = round(1.0 - distance, 4)

        logger.debug(
            f"[{collection_name}] SEMANTIC: "
            f"distance={distance:.4f} similarity={similarity:.4f} "
            f"threshold={SEMANTIC_THRESHOLD}"
        )

        if similarity >= SEMANTIC_THRESHOLD:
            translation = meta.get(target_field)
            if translation:
                return {
                    "translated_text": translation,
                    "match_type": "semantic",
                    "confidence": similarity,
                    "matched_collection": collection_name,
                    "matched_source_file": meta.get("source_file"),
                }

    except Exception as e:
        logger.error(
            f"_try_semantic_match failed for '{collection_name}': {e}",
            exc_info=True,
        )

    return None


# ---------------------------------------------------------------------- #
# Main translation function
# ---------------------------------------------------------------------- #

def translate(request: TranslationRequest) -> TranslationResponse:
    """
    Main entry point. ALWAYS returns a TranslationResponse — never None.

    Pass order:
    1. Scan-based match across all collections (exact → normalized → partial)
    2. Semantic match across all collections (best score wins)
    3. Neural fallback via NLLB-200-distilled-600M (lazy-loaded on first use)
    4. Not found — only if the neural model itself fails
    """
    input_text = request.text.strip()
    direction = request.direction
    source_field = _get_source_field(direction)
    target_field = _get_target_field(direction)

    logger.info(
        f"Translate | '{input_text}' | {direction} | "
        f"{source_field} → {target_field}"
    )

    # ------------------------------------------------------------------ #
    # Pass 1 — Scan-based match
    # ------------------------------------------------------------------ #
    for collection in COLLECTIONS_TO_SEARCH:
        result = _scan_collection(
            collection_name=collection,
            source_field=source_field,
            target_field=target_field,
            input_text=input_text,
        )
        if result:
            logger.info(
                f"Match [{result['match_type']}] in "
                f"'{result['matched_collection']}' → "
                f"'{result['translated_text']}'"
            )
            return TranslationResponse(
                input_text=input_text,
                direction=direction,
                status="success",
                message=f"{result['match_type'].capitalize()} match found.",
                **result,
            )

    # ------------------------------------------------------------------ #
    # Pass 2 — Semantic match
    # ------------------------------------------------------------------ #
    best_semantic: Optional[dict] = None

    for collection in COLLECTIONS_TO_SEARCH:
        result = _try_semantic_match(
            collection_name=collection,
            target_field=target_field,
            input_text=input_text,
        )
        if result:
            if (
                best_semantic is None
                or result["confidence"] > best_semantic["confidence"]
            ):
                best_semantic = result

    if best_semantic:
        logger.info(
            f"Semantic match in '{best_semantic['matched_collection']}' | "
            f"confidence={best_semantic['confidence']} | "
            f"→ '{best_semantic['translated_text']}'"
        )
        return TranslationResponse(
            input_text=input_text,
            direction=direction,
            status="success",
            message=(
                f"Semantic match found "
                f"(confidence: {best_semantic['confidence']})."
            ),
            **best_semantic,
        )

    # ------------------------------------------------------------------ #
    # Pass 3 — Neural fallback (NLLB-200)
    # ------------------------------------------------------------------ #
    # Only reached when all search passes return nothing.
    # NLLB can translate any text, so this should never fall through to
    # not_found unless the model itself fails to load or crashes.
    logger.info(f"[Pass 3] Attempting neural translation for '{input_text}'")

    neural_text = nllb_translator.translate(input_text, direction)

    if neural_text:
        logger.info(f"[NLLB] '{input_text}' → '{neural_text}'")
        return TranslationResponse(
            input_text=input_text,
            direction=direction,
            translated_text=neural_text,
            match_type="neural",
            confidence=0.70,
            matched_collection="nllb-200",
            matched_source_file=None,
            status="success",
            message="AI-generated translation. May need review.",
        )

    # ------------------------------------------------------------------ #
    # Pass 4 — Nothing found (neural also failed)
    # ------------------------------------------------------------------ #
    logger.info(f"No match for '{input_text}' | direction={direction}")

    return TranslationResponse(
        input_text=input_text,
        direction=direction,
        translated_text=None,
        match_type="not_found",
        confidence=None,
        matched_collection=None,
        matched_source_file=None,
        status="not_found",
        message=(
            "No translation found in the current dataset. "
            "The dataset is growing and this word may be added in future."
        ),
    )