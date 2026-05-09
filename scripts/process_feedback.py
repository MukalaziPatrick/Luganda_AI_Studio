# scripts/process_feedback.py

"""
Feedback Processor for Luganda AI Studio — Phase 3
=====================================================

Reads user feedback from data/feedback/feedback_log.jsonl and:

1. Auto-ingests corrections into ChromaDB (instant improvement)
   - Only entries with verdict="wrong" AND expected_output provided
   - Creates new translation pairs in the appropriate collection
   - Marks all as needs_review: true

2. Accumulates training data for future NLLB-200 fine-tuning
   - Saves verified correction pairs to data/training/corrections.jsonl
   - When 500+ pairs accumulate, prints readiness message

Usage:
  python scripts/process_feedback.py              # process all unprocessed feedback
  python scripts/process_feedback.py --dry-run    # preview without writing
  python scripts/process_feedback.py --stats      # show feedback statistics
  python scripts/process_feedback.py --reset      # clear processed markers (reprocess all)

Safety:
  - All corrections marked needs_review: true
  - Processing is idempotent (uses processed markers)
  - Corrections logged separately for audit
"""

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
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
FEEDBACK_FILE = PROJECT_ROOT / "data" / "feedback" / "feedback_log.jsonl"
PROCESSED_FILE = PROJECT_ROOT / "data" / "feedback" / "processed_ids.json"
CORRECTIONS_FILE = PROJECT_ROOT / "data" / "training" / "corrections.jsonl"
TRAINING_PAIRS_FILE = PROJECT_ROOT / "data" / "training" / "training_pairs.jsonl"
AUDIT_LOG = PROJECT_ROOT / "data" / "feedback" / "auto_ingestion_log.jsonl"


def _safe_str(value, fallback=""):
    if value is None or value is False:
        return fallback
    s = str(value).strip()
    return s if s else fallback


def load_feedback() -> list:
    """Load all feedback records from the JSONL file."""
    if not FEEDBACK_FILE.exists():
        logger.info(f"No feedback file found at {FEEDBACK_FILE}")
        return []

    records = []
    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                logger.warning(f"Bad JSON at line {line_num}: {e}")

    return records


def load_processed_ids() -> set:
    """Load set of already-processed feedback IDs."""
    if not PROCESSED_FILE.exists():
        return set()
    try:
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_processed_ids(ids: set):
    """Save processed IDs to disk."""
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, indent=2)


def _make_correction_id(direction: str, input_text: str, expected: str) -> str:
    """Stable ID for a correction entry."""
    key = f"correction|{direction}|{input_text[:100]}|{expected[:100]}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def ingest_correction(record: dict) -> bool:
    """
    Ingest a single correction into ChromaDB.

    Creates a new entry where:
    - The input_text is stored as the source language field
    - The expected_output is stored as the target language field
    """
    from backend.services.ingestion.indexer import index_records

    direction = record.get("direction", "en_to_lg")
    input_text = _safe_str(record.get("input_text"))
    expected = _safe_str(record.get("expected_output"))

    if not input_text or not expected:
        return False

    # Determine language fields based on direction
    if direction == "en_to_lg":
        english = input_text
        luganda = expected
    else:
        english = expected
        luganda = input_text

    # Determine collection by word count
    max_words = max(len(english.split()), len(luganda.split()))
    collection = "vocabulary" if max_words <= 2 else "sentences"

    doc_id = _make_correction_id(direction, input_text, expected)

    # Build embed text
    text = f"{luganda} — {english} | user_correction"

    record_for_chroma = {
        "collection": collection,
        "doc_id": doc_id,
        "text": text,
        "metadata": {
            "luganda": luganda,
            "english": english,
            "category": "user_correction",
            "subcategory": "feedback",
            "source_file": "feedback_corrections",
            "data_type": collection,
            "needs_review": True,
            "import_source": "user_feedback",
            "correction_date": datetime.now(timezone.utc).isoformat(),
        },
    }

    try:
        counts = index_records({collection: [record_for_chroma]})
        return counts.get(collection, 0) > 0
    except Exception as e:
        logger.error(f"ChromaDB ingestion failed: {e}")
        return False


def append_training_pair(record: dict):
    """
    Append a correction pair to the training data accumulation files.
    Format ready for NLLB-200 fine-tuning.
    """
    direction = record.get("direction", "en_to_lg")
    input_text = _safe_str(record.get("input_text"))
    expected = _safe_str(record.get("expected_output"))

    if not input_text or not expected:
        return

    # Corrections file — full record for audit
    CORRECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    correction = {
        "timestamp": record.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "feedback_id": record.get("id"),
        "input_text": input_text,
        "original_output": record.get("translated_text"),
        "expected_output": expected,
        "direction": direction,
    }
    with open(CORRECTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(correction, ensure_ascii=False) + "\n")

    # Training pairs file — minimal format for NLLB fine-tuning
    if direction == "en_to_lg":
        source, target = input_text, expected
    else:
        source, target = expected, input_text
        direction = "en_to_lg"  # normalize to en→lg for training

    training_pair = {
        "source": source,
        "target": target,
        "direction": direction,
    }
    with open(TRAINING_PAIRS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(training_pair, ensure_ascii=False) + "\n")


def log_auto_ingestion(record: dict, success: bool):
    """Log auto-ingestion attempt for audit."""
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "feedback_id": record.get("id"),
        "input_text": record.get("input_text"),
        "expected_output": record.get("expected_output"),
        "direction": record.get("direction"),
        "ingested_to_chromadb": success,
    }
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


def count_training_pairs() -> int:
    """Count accumulated training pairs."""
    if not TRAINING_PAIRS_FILE.exists():
        return 0
    count = 0
    with open(TRAINING_PAIRS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def show_stats():
    """Show feedback statistics."""
    records = load_feedback()
    processed = load_processed_ids()
    training_count = count_training_pairs()

    if not records:
        print("\nNo feedback records found.")
        print(f"Feedback file: {FEEDBACK_FILE}")
        return

    total = len(records)
    verdicts = {}
    with_expected = 0
    actionable = 0

    for r in records:
        v = r.get("verdict", "unknown")
        verdicts[v] = verdicts.get(v, 0) + 1
        if r.get("expected_output"):
            with_expected += 1
        if v == "wrong" and r.get("expected_output"):
            actionable += 1

    print("\nFeedback Statistics:")
    print("-" * 40)
    print(f"  Total records:       {total}")
    print(f"  Already processed:   {len(processed)}")
    print(f"  Unprocessed:         {total - len(processed)}")
    print()
    print("  Verdicts:")
    for v, c in sorted(verdicts.items()):
        print(f"    {v:<15}: {c}")
    print()
    print(f"  With expected output:  {with_expected}")
    print(f"  Actionable (wrong + expected): {actionable}")
    print()
    print(f"  Training pairs accumulated: {training_count}")
    if training_count >= 500:
        print("  ✓ READY FOR FINE-TUNING! Run: python scripts/finetune_nllb.py")
    else:
        print(f"  Need {500 - training_count} more pairs before fine-tuning")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Process user feedback: ingest corrections + accumulate training data"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to ChromaDB or training files",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show feedback statistics and exit",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear processed IDs and reprocess everything",
    )

    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    if args.reset:
        if PROCESSED_FILE.exists():
            PROCESSED_FILE.unlink()
            logger.info("Processed IDs cleared. All feedback will be reprocessed.")
        else:
            logger.info("No processed IDs file found — nothing to reset.")

    # Load feedback
    records = load_feedback()
    if not records:
        logger.info("No feedback to process.")
        return

    processed_ids = load_processed_ids()
    logger.info(f"Loaded {len(records)} total feedback records")
    logger.info(f"Already processed: {len(processed_ids)}")

    # Filter to unprocessed records with actionable corrections
    actionable = []
    skipped_already_processed = 0
    skipped_no_correction = 0

    for record in records:
        record_id = record.get("id")
        if not record_id:
            continue

        if record_id in processed_ids:
            skipped_already_processed += 1
            continue

        # Only process "wrong" verdicts with expected_output
        verdict = record.get("verdict", "")
        expected = _safe_str(record.get("expected_output"))

        if verdict == "wrong" and expected:
            actionable.append(record)
        else:
            # Mark as processed even if not actionable (so we don't re-check)
            processed_ids.add(record_id)
            skipped_no_correction += 1

    logger.info(f"Skipped (already processed): {skipped_already_processed}")
    logger.info(f"Skipped (no correction):     {skipped_no_correction}")
    logger.info(f"Actionable corrections:      {len(actionable)}")

    if not actionable:
        logger.info("No new corrections to process.")
        if not args.dry_run:
            save_processed_ids(processed_ids)
        return

    # Process corrections
    ingested_count = 0
    training_count = 0

    for record in actionable:
        record_id = record.get("id")
        input_text = _safe_str(record.get("input_text"))
        expected = _safe_str(record.get("expected_output"))

        logger.info(f"  Processing: '{input_text}' → '{expected}'")

        if args.dry_run:
            logger.info(f"    [DRY RUN] Would ingest to ChromaDB + add to training data")
            ingested_count += 1
            training_count += 1
        else:
            # Step 1: Ingest into ChromaDB
            success = ingest_correction(record)
            if success:
                ingested_count += 1
                logger.info(f"    ✓ Ingested to ChromaDB")
            else:
                logger.warning(f"    ✗ ChromaDB ingestion failed")

            # Step 2: Add to training data
            append_training_pair(record)
            training_count += 1
            logger.info(f"    ✓ Added to training data")

            # Step 3: Log for audit
            log_auto_ingestion(record, success)

        # Mark as processed
        processed_ids.add(record_id)

    # Save processed state
    if not args.dry_run:
        save_processed_ids(processed_ids)

    # Report
    total_training = count_training_pairs()

    logger.info(f"\n{'=' * 50}")
    logger.info(f"PROCESSING COMPLETE")
    logger.info(f"  Corrections processed:     {len(actionable)}")
    logger.info(f"  New entries in ChromaDB:    {ingested_count}")
    logger.info(f"  Training pairs added:       {training_count}")
    logger.info(f"  Total training pairs:       {total_training}")

    if total_training >= 500:
        logger.info(f"\n  ★ READY FOR FINE-TUNING!")
        logger.info(f"    Run: python scripts/finetune_nllb.py")
    else:
        logger.info(f"  Need {500 - total_training} more pairs before fine-tuning")

    logger.info(f"{'=' * 50}")


if __name__ == "__main__":
    main()
