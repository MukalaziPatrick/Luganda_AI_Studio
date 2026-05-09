# backend/services/ingestion/loader.py

"""
Data Loader
============

Reads all dataset JSON files and converts them into standardised records
ready for embedding and storage in ChromaDB.

WHAT THIS FILE DOES:
  1. Opens each JSON file in the datasets/ folder
  2. Extracts every field from each entry (nothing is thrown away)
  3. Builds a rich "text" string that will be embedded by MiniLM
  4. Returns a standardised record dict for each entry

RECORD SHAPE (every record this loader returns):
  {
    "collection":  str,   # "vocabulary", "sentences", "grammar", "proverbs"
    "doc_id":      str,   # stable unique ID — never changes for same entry
    "text":        str,   # the text that gets embedded — rich and complete
    "metadata":    dict,  # all fields stored in ChromaDB for display
  }

YOUR ACTUAL JSON FILE STRUCTURE (animals.json example):
  {
    "metadata": { "category": "animals", "total_entries": 53, ... },
    "entries": [
      {
        "luganda": "Embwa",
        "english": "Dog",
        "category": "animals",
        "subcategory": "domestic",
        "part_of_speech": "noun",
        "notes": "...",
        "example_sentence_luganda": "Embwa yange erina abaana.",
        "example_sentence_english": "My dog has puppies.",
        "needs_review": false
      },
      ...
    ]
  }

STABLE IDs:
  Each record gets an ID based on: collection + filename + luganda text.
  This means the same entry always gets the same ID on every ingestion run.
  This prevents duplicate records in ChromaDB.

RICH EMBED TEXT:
  We combine all available fields so semantic search works from multiple angles:
    - Search "dog" → finds "Embwa" via english field
    - Search "Embwa" → finds "Dog" via luganda field
    - Search "domestic animal" → finds via subcategory
    - Search "puppies" → finds via example sentence
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from backend.core.config import settings

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_json(file_path: Path) -> Any:
    """
    Read a JSON file and return its contents.
    Returns None on any failure (missing file, bad JSON, etc.)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"File not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Bad JSON in {file_path.name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return None


def _safe_str(value: Any, fallback: str = "") -> str:
    """
    Convert any value to a clean string.
    Returns fallback if value is None, False, or empty.
    """
    if value is None or value is False:
        return fallback
    s = str(value).strip()
    return s if s else fallback


def _extract_entries(data: Any, filename: str) -> list[dict]:
    """
    Extract the list of entries from a JSON file.

    Handles two structures:

    Structure 1 — list at root:
        [ {"luganda": "...", ...}, {"luganda": "...", ...} ]

    Structure 2 — dict with "entries" key (your actual format):
        {
          "metadata": { ... },
          "entries": [ {"luganda": "...", ...}, ... ]
        }

    If neither structure is found, logs a warning and returns [].
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        # Check for "entries" key first — this is your actual format
        if "entries" in data and isinstance(data["entries"], list):
            return data["entries"]

        # Fallback: find the first list-of-dicts value in the dict
        # This handles any other wrapper key like "items", "words", etc.
        for key, value in data.items():
            if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                logger.debug(f"{filename}: no 'entries' key found, using key '{key}' instead")
                return value

    logger.warning(
        f"{filename}: could not find an entries list. "
        f"Expected a list at root or a dict with an 'entries' key."
    )
    return []


def _make_stable_id(collection: str, filename: str, luganda: str) -> str:
    """
    Generate a stable, unique document ID using an MD5 hash.

    Based on: collection + filename + first 100 chars of luganda text.

    WHY THIS MATTERS:
      Counter-based IDs like "vocab_0", "vocab_1" change whenever you
      add or remove entries. That breaks upsert — ChromaDB thinks each
      run is a new set of records and creates duplicates.

      Hash-based IDs are always the same for the same input data,
      so upsert correctly finds and updates existing records.

    Example:
      collection="vocabulary", file="animals.json", luganda="Embwa"
      → "a3f9b1c2d4e5f6a7b8c9d0e1f2a3b4c5"
    """
    key = f"{collection}|{filename}|{luganda[:100]}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# ── Vocabulary Loader ─────────────────────────────────────────────────────────

def load_vocabulary_files() -> list[dict]:
    """
    Load all vocabulary JSON files from datasets/vocabulary/.

    ALL fields captured per entry:
      luganda, english, category, subcategory, part_of_speech,
      notes, example_sentence_luganda, example_sentence_english,
      needs_review

    Embed text combines all fields for rich semantic search.
    """
    vocab_files = [
        "animals.json",
        "body_parts.json",
        "food_and_drink.json",
        "transport.json",
        "family.json",
        "numbers.json",
    ]

    records = []
    vocab_dir = settings.datasets_dir / "vocabulary"

    for filename in vocab_files:
        file_path = vocab_dir / filename
        data = _read_json(file_path)
        if data is None:
            continue

        entries = _extract_entries(data, filename)
        loaded_count = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            luganda = _safe_str(entry.get("luganda"))
            english = _safe_str(entry.get("english"))

            # Skip entries with no luganda word — they are useless for search
            if not luganda:
                logger.debug(f"{filename}: skipping entry with no 'luganda' field")
                continue

            # Collect all available fields
            category     = _safe_str(entry.get("category", filename.replace(".json", "")))
            subcategory  = _safe_str(entry.get("subcategory"))
            pos          = _safe_str(entry.get("part_of_speech"))
            notes        = _safe_str(entry.get("notes"))
            ex_luganda   = _safe_str(entry.get("example_sentence_luganda"))
            ex_english   = _safe_str(entry.get("example_sentence_english"))
            needs_review = bool(entry.get("needs_review", False))

            # ── Build rich embed text ──────────────────────────────────────
            # More content = better semantic search from multiple angles.
            # Format: "Embwa — Dog | domestic animals | Example: ... (translation)"
            parts = [f"{luganda} — {english}"]

            if subcategory and category:
                parts.append(f"{subcategory} {category}")
            elif category:
                parts.append(category)

            if notes:
                parts.append(notes)

            if ex_luganda and ex_english:
                parts.append(f"Example: {ex_luganda} ({ex_english})")
            elif ex_luganda:
                parts.append(f"Example: {ex_luganda}")

            text   = " | ".join(p for p in parts if p)
            doc_id = _make_stable_id("vocabulary", filename, luganda)

            records.append({
                "collection": "vocabulary",
                "doc_id":     doc_id,
                "text":       text,
                "metadata": {
                    # Core translation fields (used by search + translation service)
                    "luganda":  luganda,
                    "english":  english,
                    # Classification
                    "category":       category,
                    "subcategory":    subcategory,
                    "part_of_speech": pos,
                    # Extra content shown in search results
                    "notes":                    notes,
                    "example_sentence_luganda": ex_luganda,
                    "example_sentence_english": ex_english,
                    # Provenance + quality flags
                    "source_file":  filename,
                    "data_type":    "vocabulary",
                    "needs_review": needs_review,
                },
            })
            loaded_count += 1

        logger.info(f"Vocabulary: {loaded_count} entries loaded from {filename}")

    return records


# ── Sentences Loader ──────────────────────────────────────────────────────────

def load_sentence_files() -> list[dict]:
    """
    Load all sentence JSON files from datasets/sentences/.

    Fields captured: luganda, english, context, difficulty, tags.
    """
    sentence_files = [
        "daily_life.json",
        "greetings.json",
    ]

    records = []
    sentences_dir = settings.datasets_dir / "sentences"

    for filename in sentence_files:
        file_path = sentences_dir / filename
        data = _read_json(file_path)
        if data is None:
            continue

        entries = _extract_entries(data, filename)
        loaded_count = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            # Try multiple field name variants
            luganda = _safe_str(
                entry.get("luganda") or entry.get("phrase") or entry.get("sentence")
            )
            english = _safe_str(
                entry.get("english") or entry.get("translation")
            )

            if not luganda:
                continue

            context    = _safe_str(entry.get("context") or entry.get("notes"))
            difficulty = _safe_str(entry.get("difficulty"))
            tags_raw   = entry.get("tags") or []
            tags_str   = (
                ", ".join(str(t) for t in tags_raw)
                if isinstance(tags_raw, list)
                else _safe_str(tags_raw)
            )

            # Embed text
            parts = [f"{luganda} — {english}"]
            if context:
                parts.append(context)
            if difficulty:
                parts.append(f"difficulty: {difficulty}")
            if tags_str:
                parts.append(tags_str)

            text   = " | ".join(p for p in parts if p)
            doc_id = _make_stable_id("sentences", filename, luganda)

            records.append({
                "collection": "sentences",
                "doc_id":     doc_id,
                "text":       text,
                "metadata": {
                    "luganda":     luganda,
                    "english":     english,
                    "context":     context,
                    "difficulty":  difficulty,
                    "tags":        tags_str,
                    "source_file": filename,
                    "data_type":   "sentence",
                },
            })
            loaded_count += 1

        logger.info(f"Sentences: {loaded_count} entries loaded from {filename}")

    return records


# ── Grammar Loader ────────────────────────────────────────────────────────────

def load_grammar_files() -> list[dict]:
    """
    Load all grammar JSON files from datasets/grammar/.

    Grammar entries have varied field names across files, so we try
    multiple field name variants for each piece of data.
    """
    grammar_files = [
        "vowels.json",
        "consonants.json",
        "word_classes.json",
        "verb_tenses.json",
    ]

    records = []
    grammar_dir = settings.datasets_dir / "grammar"

    for filename in grammar_files:
        file_path = grammar_dir / filename
        data = _read_json(file_path)
        if data is None:
            continue

        entries = _extract_entries(data, filename)
        loaded_count = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            # Grammar files use varying field names — try them all
            title = _safe_str(
                entry.get("title") or entry.get("name") or entry.get("tense")
            )
            description = _safe_str(
                entry.get("description") or entry.get("explanation") or entry.get("notes")
            )
            ex_luganda = _safe_str(
                entry.get("example_luganda") or entry.get("luganda")
            )
            ex_english = _safe_str(
                entry.get("example_english") or entry.get("english")
            )
            rule_id = _safe_str(entry.get("id"))

            # Build embed text
            parts = []
            if title:
                parts.append(title)
            if description:
                parts.append(description)
            if ex_luganda and ex_english:
                parts.append(f"Example: {ex_luganda} — {ex_english}")
            elif ex_luganda:
                parts.append(f"Example: {ex_luganda}")

            text = " | ".join(p for p in parts if p)
            if not text:
                continue

            # Use explicit rule ID if available, otherwise hash
            doc_id = rule_id if rule_id else _make_stable_id(
                "grammar", filename, title or text[:50]
            )

            records.append({
                "collection": "grammar",
                "doc_id":     doc_id,
                "text":       text,
                "metadata": {
                    "luganda":         ex_luganda,
                    "english":         ex_english,
                    "title":           title,
                    "description":     description,
                    "example_luganda": ex_luganda,
                    "example_english": ex_english,
                    "source_file":     filename,
                    "data_type":       "grammar",
                },
            })
            loaded_count += 1

        logger.info(f"Grammar: {loaded_count} entries loaded from {filename}")

    return records


# ── Proverbs Loader ───────────────────────────────────────────────────────────

def load_proverb_files() -> list[dict]:
    """
    Load all proverb JSON files from datasets/proverbs/.

    Fields captured: luganda, english, meaning, tags/theme.
    """
    proverb_files = [
        "kiganda_proverbs.json",
    ]

    records = []
    proverbs_dir = settings.datasets_dir / "proverbs"

    for filename in proverb_files:
        file_path = proverbs_dir / filename
        data = _read_json(file_path)
        if data is None:
            continue

        entries = _extract_entries(data, filename)
        loaded_count = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            luganda = _safe_str(entry.get("luganda") or entry.get("proverb"))
            english = _safe_str(entry.get("english") or entry.get("translation"))
            meaning = _safe_str(entry.get("meaning") or entry.get("interpretation"))

            if not luganda:
                continue

            tags_raw = entry.get("tags") or entry.get("theme") or []
            tags_str = (
                ", ".join(str(t) for t in tags_raw)
                if isinstance(tags_raw, list)
                else _safe_str(tags_raw)
            )

            # Embed text — meaning is especially important for proverb search
            parts = [f"{luganda} — {english}"]
            if meaning:
                parts.append(f"Meaning: {meaning}")
            if tags_str:
                parts.append(tags_str)

            text   = " | ".join(p for p in parts if p)
            doc_id = _make_stable_id("proverbs", filename, luganda)

            records.append({
                "collection": "proverbs",
                "doc_id":     doc_id,
                "text":       text,
                "metadata": {
                    "luganda":     luganda,
                    "english":     english,
                    "meaning":     meaning,
                    "tags":        tags_str,
                    "source_file": filename,
                    "data_type":   "proverb",
                },
            })
            loaded_count += 1

        logger.info(f"Proverbs: {loaded_count} entries loaded from {filename}")

    return records


# ── Master Loader ─────────────────────────────────────────────────────────────

def load_all_datasets() -> dict[str, list[dict]]:
    """
    Load all datasets and group them by collection name.

    Returns:
        {
            "vocabulary": [ ...records ],
            "sentences":  [ ...records ],
            "grammar":    [ ...records ],
            "proverbs":   [ ...records ],
        }

    Each record has: collection, doc_id, text, metadata.
    Called by run_ingestion.py to kick off the full pipeline.
    """
    logger.info("Starting full dataset load...")

    all_records: dict[str, list[dict]] = {
        "vocabulary": load_vocabulary_files(),
        "sentences":  load_sentence_files(),
        "grammar":    load_grammar_files(),
        "proverbs":   load_proverb_files(),
    }

    total = sum(len(v) for v in all_records.values())
    logger.info("Dataset load complete:")
    for collection, records in all_records.items():
        logger.info(f"  {collection:<12}: {len(records)} records")
    logger.info(f"  {'TOTAL':<12}: {total} records")

    return all_records
