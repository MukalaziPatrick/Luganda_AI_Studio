# scripts/ingest_dataset.py

"""
Universal Dataset Ingestor for Luganda AI Studio — Phase 1
============================================================

Reads cleaned JSON files from data/datasets/ and ingests them into ChromaDB.
Works with both downloaded datasets (from download_datasets.py) and any
manually created JSON files that follow the standard format.

Usage:
  python scripts/ingest_dataset.py                      # ingest all files in data/datasets/
  python scripts/ingest_dataset.py --file flores_sentences.json
  python scripts/ingest_dataset.py --dry-run             # preview without writing
  python scripts/ingest_dataset.py --stats               # show current ChromaDB counts

Expects JSON format:
  {
    "metadata": { "source": "...", "category": "...", ... },
    "entries": [
      { "luganda": "...", "english": "...", "category": "...", ... }
    ]
  }

This script uses the existing ingestion pipeline (embedder.py + indexer.py)
so all data goes through the same path as the original datasets.
"""

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Paths ────────────────────────────────────────────────────────────────────
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"
INGESTION_LOG = PROJECT_ROOT / "data" / "datasets" / "ingestion_log.jsonl"


def _safe_str(value, fallback=""):
    """Convert to clean string, handling None/False."""
    if value is None or value is False:
        return fallback
    s = str(value).strip()
    return s if s else fallback


def _make_stable_id(collection: str, source: str, luganda: str) -> str:
    """Generate stable MD5 ID matching the existing loader.py logic."""
    key = f"{collection}|{source}|{luganda[:100]}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def load_json_file(filepath: Path) -> tuple:
    """
    Load a JSON dataset file and return (metadata, entries).
    Returns (None, []) on failure.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read {filepath.name}: {e}")
        return None, []

    if isinstance(data, list):
        return {}, data
    elif isinstance(data, dict):
        metadata = data.get("metadata", {})
        entries = data.get("entries", [])
        if isinstance(entries, list):
            return metadata, entries

    logger.warning(f"{filepath.name}: unrecognized format")
    return None, []


def build_records(entries: list, source_name: str, filepath: Path) -> dict:
    """
    Convert raw entries into ChromaDB-ready records grouped by collection.

    Returns dict: { "vocabulary": [...], "sentences": [...] }
    """
    records_by_collection = {"vocabulary": [], "sentences": []}

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        luganda = _safe_str(entry.get("luganda"))
        english = _safe_str(entry.get("english"))

        if not luganda and not english:
            continue

        # Determine collection based on word count or explicit category
        explicit_cat = _safe_str(entry.get("data_type") or entry.get("category"))
        if explicit_cat in ("vocabulary", "sentences", "grammar", "proverbs"):
            collection = explicit_cat
        else:
            max_words = max(len(english.split()), len(luganda.split()))
            collection = "vocabulary" if max_words <= 2 else "sentences"

        # Ensure collection exists in our output dict
        if collection not in records_by_collection:
            records_by_collection[collection] = []

        # Build rich embed text
        parts = []
        if luganda and english:
            parts.append(f"{luganda} — {english}")
        elif luganda:
            parts.append(luganda)
        elif english:
            parts.append(english)

        subcategory = _safe_str(entry.get("subcategory"))
        category = _safe_str(entry.get("category"))
        if subcategory:
            parts.append(subcategory)
        if category and category != subcategory:
            parts.append(category)

        notes = _safe_str(entry.get("notes"))
        if notes:
            parts.append(notes)

        text = " | ".join(p for p in parts if p)
        doc_id = _make_stable_id(collection, source_name, luganda or english)

        # Build metadata
        needs_review = entry.get("needs_review", True)
        metadata = {
            "luganda": luganda,
            "english": english,
            "category": category or "imported",
            "subcategory": subcategory or source_name,
            "source_file": filepath.name,
            "data_type": collection,
            "needs_review": bool(needs_review),
            "import_source": source_name,
        }

        # Include optional fields if present
        for opt_field in ("difficulty", "part_of_speech", "context", "meaning", "tags"):
            val = _safe_str(entry.get(opt_field))
            if val:
                metadata[opt_field] = val

        records_by_collection[collection].append({
            "collection": collection,
            "doc_id": doc_id,
            "text": text,
            "metadata": metadata,
        })

    return records_by_collection


def ingest_records(records_by_collection: dict) -> dict:
    """
    Ingest records into ChromaDB using the existing indexer.
    Returns summary dict of counts.
    """
    from backend.services.ingestion.indexer import index_records
    return index_records(records_by_collection)


def log_ingestion(source_name: str, filepath: str, counts: dict):
    """Append an ingestion record to the log file."""
    from datetime import datetime, timezone

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source_name,
        "file": filepath,
        "counts": counts,
    }

    INGESTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(INGESTION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def show_stats():
    """Show current ChromaDB collection counts."""
    from backend.db.chroma_client import chroma_client

    print("\nChromaDB Collection Stats:")
    print("-" * 40)

    total = 0
    try:
        collections = chroma_client.list_collections()
        for col in collections:
            # In newer ChromaDB, col might be a Collection object or a name string
            if hasattr(col, 'name'):
                name = col.name
                count = col.count()
            else:
                name = str(col)
                c = chroma_client.get_collection(name)
                count = c.count()
            print(f"  {name:<16}: {count:>6} records")
            total += count
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return

    print(f"  {'TOTAL':<16}: {total:>6} records")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Ingest cleaned datasets into ChromaDB"
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Specific JSON file to ingest (filename only, looked up in data/datasets/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be ingested without writing to ChromaDB",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show current ChromaDB collection counts and exit",
    )

    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    # Find files to ingest
    if args.file:
        filepath = DATASETS_DIR / args.file
        if not filepath.exists():
            logger.error(f"File not found: {filepath}")
            logger.info(f"Available files in {DATASETS_DIR}:")
            for f in sorted(DATASETS_DIR.glob("*.json")):
                logger.info(f"  {f.name}")
            return
        files = [filepath]
    else:
        files = sorted(DATASETS_DIR.glob("*.json"))
        if not files:
            logger.info(f"No JSON files found in {DATASETS_DIR}")
            logger.info("Run download_datasets.py first to fetch data.")
            return

    logger.info(f"Found {len(files)} file(s) to ingest")

    # Show stats before
    if not args.dry_run:
        logger.info("\n--- Before ingestion ---")
        show_stats()

    # Process each file
    grand_total = 0

    for filepath in files:
        logger.info(f"\nProcessing: {filepath.name}")

        metadata, entries = load_json_file(filepath)
        if metadata is None:
            continue

        source_name = metadata.get("source", filepath.stem)
        logger.info(f"  Source: {source_name} | Entries: {len(entries)}")

        records_by_collection = build_records(entries, source_name, filepath)

        # Count
        for col_name, records in records_by_collection.items():
            if records:
                logger.info(f"  → {col_name}: {len(records)} records")

        total_records = sum(len(r) for r in records_by_collection.values())
        grand_total += total_records

        if args.dry_run:
            logger.info(f"  [DRY RUN] Would ingest {total_records} records")
            continue

        # Ingest
        if total_records > 0:
            counts = ingest_records(records_by_collection)
            log_ingestion(source_name, filepath.name, counts)
            logger.info(f"  Ingested: {counts}")

    logger.info(f"\n{'=' * 50}")
    if args.dry_run:
        logger.info(f"DRY RUN complete. {grand_total} records would be ingested.")
    else:
        logger.info(f"INGESTION COMPLETE. {grand_total} records processed.")
        logger.info("\n--- After ingestion ---")
        show_stats()


if __name__ == "__main__":
    main()
