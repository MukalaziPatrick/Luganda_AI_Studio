# Training Data Cleanup + Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cleaning pass to `process_feedback.py` and create `scripts/export_dataset.py` that produces a date-stamped, HuggingFace-compatible JSONL file of verified translation pairs.

**Architecture:** Two independent changes — a guard added to the existing feedback ingestor, and a new standalone export script. No backend or frontend changes. Zero risk to existing functionality.

**Tech Stack:** Python 3.10+, pathlib, json, argparse (all already in use)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/process_feedback.py` | Modify | Add cleaning guard before ingestion |
| `scripts/export_dataset.py` | Create | Read training files, clean, write dated export |

---

### Task 1: Add cleaning guard to `process_feedback.py`

**Files:**
- Modify: `scripts/process_feedback.py`

The `ingest_correction` function currently returns `False` only when `input_text` or `expected` is empty. We need to also drop pairs where either side is under 3 characters, or where source and target are identical after normalization.

Add a `_is_valid_pair` helper and call it in both `ingest_correction` and `append_training_pair`.

- [ ] **Step 1: Add `_is_valid_pair` helper after `_safe_str`**

Open `scripts/process_feedback.py`. After the `_safe_str` function (line 63), add:

```python
def _is_valid_pair(source: str, target: str) -> bool:
    """Return False if the pair should be dropped from training data."""
    if len(source.strip()) < 3 or len(target.strip()) < 3:
        return False
    if source.strip().lower() == target.strip().lower():
        return False
    return True
```

- [ ] **Step 2: Apply guard in `ingest_correction`**

In `ingest_correction`, find the block (around line 125):
```python
    if not input_text or not expected:
        return False
```

Replace with:
```python
    if not input_text or not expected:
        return False
    if not _is_valid_pair(input_text, expected):
        logger.debug(f"Skipping invalid pair: '{input_text}' / '{expected}'")
        return False
```

- [ ] **Step 3: Apply guard in `append_training_pair`**

In `append_training_pair`, find the block (around line 178):
```python
    if not input_text or not expected:
        return
```

Replace with:
```python
    if not input_text or not expected:
        return
    if not _is_valid_pair(input_text, expected):
        return
```

- [ ] **Step 4: Verify the script still runs**

```bash
python scripts/process_feedback.py --stats
```

Expected: stats table prints without error. No translation changes — this only affects future ingestion.

- [ ] **Step 5: Commit**

```bash
git add scripts/process_feedback.py
git commit -m "feat: add minimum-length and identical-pair guard to feedback ingestor"
```

---

### Task 2: Create `scripts/export_dataset.py`

**Files:**
- Create: `scripts/export_dataset.py`

- [ ] **Step 1: Create the file**

Create `scripts/export_dataset.py` with this content:

```python
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
    if len(source.strip()) < 3 or len(target.strip()) < 3:
        return False
    if source.strip().lower() == target.strip().lower():
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

    # Deduplicate by (source, direction) — keep most recent (last seen)
    seen: dict[tuple, dict] = {}
    for record in valid:
        key = (record["source"].lower(), record["direction"])
        seen[key] = record  # later entries overwrite earlier ones

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
```

- [ ] **Step 2: Run a dry-run to verify it works**

```bash
python scripts/export_dataset.py --dry-run
```

Expected output (counts will vary):
```
Export Summary
----------------------------------------
  Total input records:       <N>
  Dropped (invalid/short):   <N>
  Dropped (duplicate):       <N>
  Final export count:        <N>
  Verified pairs:            <N>

  [DRY RUN] No file written.
```

No error should be raised even if some source files are empty or missing.

- [ ] **Step 3: Run the real export**

```bash
python scripts/export_dataset.py
```

Expected: prints summary and writes `data/training/dataset_export_YYYY-MM-DD.jsonl` (today's date).

- [ ] **Step 4: Verify the output file**

Open the file and check:
- Each line is valid JSON
- Each record has: `source`, `target`, `direction`, `match_type`, `verified`, `submitted_at`
- No `source` or `target` under 3 characters
- No identical source/target pairs

```bash
python -c "
import json
from pathlib import Path
from datetime import date

path = Path('data/training') / f'dataset_export_{date.today().isoformat()}.jsonl'
records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
print(f'Records: {len(records)}')
print(f'Keys in first record: {list(records[0].keys()) if records else \"(empty)\"}')
short = [r for r in records if len(r[\"source\"]) < 3 or len(r[\"target\"]) < 3]
print(f'Short pairs (should be 0): {len(short)}')
"
```

Expected:
```
Records: <N>
Keys in first record: ['source', 'target', 'direction', 'match_type', 'verified', 'submitted_at']
Short pairs (should be 0): 0
```

- [ ] **Step 5: Commit**

```bash
git add scripts/export_dataset.py
git commit -m "feat: add export_dataset.py with cleaning, dedup, and dated JSONL output"
```
