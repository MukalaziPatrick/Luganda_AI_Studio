# scripts/export_dataset.py

"""
Export cleaned, HuggingFace-compatible training data from accumulated feedback.

Reads:
  data/feedback/feedback_log.jsonl
  data/training/training_pairs.jsonl
  data/training/corrections.jsonl

Cleans:
  - Drop pairs where source OR target < 3 characters
  - Drop pairs where expected_output is null or empty
  - Drop pairs where source == target (after normalization)
  - Deduplicate by (source, direction) — keep most recent
  - Strip leading/trailing whitespace from source and target

Writes:
  data/training/dataset_export_YYYY-MM-DD.jsonl

Usage:
  python scripts/export_dataset.py
  python scripts/export_dataset.py --dry-run
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FEEDBACK_FILE    = PROJECT_ROOT / "data" / "feedback" / "feedback_log.jsonl"
TRAINING_FILE    = PROJECT_ROOT / "data" / "training" / "training_pairs.jsonl"
CORRECTIONS_FILE = PROJECT_ROOT / "data" / "training" / "corrections.jsonl"
OUTPUT_DIR       = PROJECT_ROOT / "data" / "training"


def _is_valid_pair(source: str, target: str) -> bool:
    s = source.strip()
    t = target.strip()
    if len(s) < 3 or len(t) < 3:
        return False
    if s.lower() == t.lower():
        return False
    return True


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def _to_export_record(raw: dict, verified: bool) -> dict | None:
    """Normalise a raw record into the export schema. Returns None if invalid."""
    # Support both feedback_log schema and training_pairs schema
    source = (
        raw.get("source")
        or raw.get("input_text")
        or ""
    ).strip()
    target = (
        raw.get("target")
        or raw.get("expected_output")
        or ""
    ).strip()
    direction = raw.get("direction", "en_to_lg")
    submitted_at = raw.get("submitted_at") or raw.get("timestamp") or datetime.now(timezone.utc).isoformat()

    if not source or not target:
        return None
    if not _is_valid_pair(source, target):
        return None

    return {
        "source": source,
        "target": target,
        "direction": direction,
        "match_type": "correction" if verified else "auto",
        "verified": verified,
        "submitted_at": submitted_at,
    }


def export(dry_run: bool = False) -> None:
    stats = {
        "input_total": 0,
        "dropped_invalid": 0,
        "dropped_duplicate": 0,
        "final_count": 0,
        "verified_count": 0,
    }

    raw_records: list[tuple[dict, bool]] = []  # (record, is_verified)

    # Load feedback_log — verified corrections (verdict=wrong + expected_output)
    for r in _load_jsonl(FEEDBACK_FILE):
        if r.get("verdict") == "wrong" and r.get("expected_output"):
            raw_records.append((r, True))

    # Load corrections.jsonl — verified
    for r in _load_jsonl(CORRECTIONS_FILE):
        raw_records.append((r, True))

    # Load training_pairs.jsonl — unverified (auto-generated)
    for r in _load_jsonl(TRAINING_FILE):
        raw_records.append((r, False))

    stats["input_total"] = len(raw_records)

    # Normalise and validate
    valid: list[dict] = []
    for raw, verified in raw_records:
        record = _to_export_record(raw, verified)
        if record is None:
            stats["dropped_invalid"] += 1
        else:
            valid.append(record)

    # Deduplicate by (source, direction) — verified always beats unverified;
    # within the same verified status, last seen wins (most recent).
    seen: dict[tuple, dict] = {}
    for record in valid:
        key = (record["source"].lower(), record["direction"])
        existing = seen.get(key)
        if existing is None or (record["verified"] and not existing["verified"]):
            seen[key] = record

    deduped = list(seen.values())
    stats["dropped_duplicate"] = len(valid) - len(deduped)
    stats["final_count"] = len(deduped)
    stats["verified_count"] = sum(1 for r in deduped if r["verified"])

    # Report
    print("\nExport Summary")
    print("-" * 40)
    print(f"  Total input records:       {stats['input_total']}")
    print(f"  Dropped (invalid/short):   {stats['dropped_invalid']}")
    print(f"  Dropped (duplicate):       {stats['dropped_duplicate']}")
    print(f"  Final export count:        {stats['final_count']}")
    print(f"  Verified pairs:            {stats['verified_count']}")

    if dry_run:
        print("\n  [DRY RUN] No file written.")
        return

    output_path = OUTPUT_DIR / f"dataset_export_{date.today().isoformat()}.jsonl"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        print(f"  WARNING: Overwriting existing export: {output_path.name}")

    with open(output_path, "w", encoding="utf-8") as f:
        for record in deduped:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\n  Output: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Export cleaned training dataset")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    export(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
