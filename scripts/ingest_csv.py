# scripts/ingest_csv.py

"""
CSV Ingestor for Luganda AI Studio — Phase 4
==============================================

Reads CSV files containing Luganda-English pairs and ingests them
into ChromaDB via the existing ingestion pipeline.

Handles any CSV with columns named 'luganda' and 'english' (case-insensitive).
Column order does not matter. Extra columns (notes, category, difficulty, etc.)
are carried through automatically.

Usage:
  python scripts/ingest_csv.py --file my_vocab.csv
  python scripts/ingest_csv.py --dir data/csv/
  python scripts/ingest_csv.py --file my_vocab.csv --dry-run
  python scripts/ingest_csv.py --stats

Input:
  CSV file with at minimum two columns named 'luganda' and 'english'.
  Separator is auto-detected (comma, semicolon, or tab).

  Example:
    luganda,english,notes
    Embwa,Dog,Common animal
    Enjovu,Elephant,Large animal

  Column aliases accepted:
    Luganda column : luganda, lg, lug
    English column : english, en, eng

Output:
  Saves cleaned JSON to data/datasets/<filename>_csv.json
  Then ingests into ChromaDB using the existing pipeline.
  Logs every run to data/datasets/ingestion_log.jsonl
"""

import argparse
import csv
import json
import logging
import sys
from datetime import date, datetime, timezone
from io import StringIO
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

# ── Paths ─────────────────────────────────────────────────────────────────────
CSV_DIR      = PROJECT_ROOT / "data" / "csv"
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"
LOG_FILE     = DATASETS_DIR / "ingestion_log.jsonl"

# ── Column name aliases ───────────────────────────────────────────────────────
LUGANDA_ALIASES = {"luganda", "lg", "lug", "luganda_text", "lg_text"}
ENGLISH_ALIASES = {"english", "en", "eng", "english_text", "en_text", "translation"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(value) -> str:
    """Strip whitespace from a cell value. Return empty string for None."""
    if value is None:
        return ""
    return str(value).strip()


def _detect_separator(raw_text: str) -> str:
    """
    Auto-detect CSV separator by counting occurrences of common delimiters
    in the first line.
    """
    first_line = raw_text.split("\n")[0] if "\n" in raw_text else raw_text
    counts = {
        ",":  first_line.count(","),
        "\t": first_line.count("\t"),
        ";":  first_line.count(";"),
    }
    return max(counts, key=counts.get)


def _find_columns(header_row: list[str]) -> tuple[int, int]:
    """
    Find the column indices for luganda and english in the header row.
    Returns (luganda_idx, english_idx) or raises ValueError.
    """
    normalized = [col.strip().lower() for col in header_row]

    lg_idx = next(
        (i for i, h in enumerate(normalized) if h in LUGANDA_ALIASES),
        None,
    )
    en_idx = next(
        (i for i, h in enumerate(normalized) if h in ENGLISH_ALIASES),
        None,
    )

    if lg_idx is None:
        raise ValueError(
            f"Could not find a Luganda column. "
            f"Expected one of: {sorted(LUGANDA_ALIASES)}. "
            f"Found headers: {header_row}"
        )
    if en_idx is None:
        raise ValueError(
            f"Could not find an English column. "
            f"Expected one of: {sorted(ENGLISH_ALIASES)}. "
            f"Found headers: {header_row}"
        )

    return lg_idx, en_idx


def _categorize(english: str, luganda: str) -> str:
    """1-2 words → vocabulary.  3+ words → sentences."""
    return "vocabulary" if max(len(english.split()), len(luganda.split())) <= 2 else "sentences"


# ── Core: parse one CSV file ──────────────────────────────────────────────────

def parse_csv_file(filepath: Path) -> list[dict]:
    """
    Read a CSV file and return a list of entry dicts ready for ingestion.

    Each dict has at minimum: luganda, english
    Extra columns (notes, category, difficulty, etc.) are passed through.

    Returns empty list and logs a warning on any failure.
    """
    try:
        raw = filepath.read_text(encoding="utf-8-sig")  # utf-8-sig strips BOM
    except UnicodeDecodeError:
        try:
            raw = filepath.read_text(encoding="latin-1")
            logger.warning(f"  {filepath.name}: read with latin-1 fallback encoding")
        except Exception as e:
            logger.error(f"  {filepath.name}: could not read file — {e}")
            return []

    sep = _detect_separator(raw)
    sep_name = {"," : "comma", "\t": "tab", ";": "semicolon"}.get(sep, sep)
    logger.info(f"  Detected separator: {sep_name}")

    try:
        reader = csv.DictReader(StringIO(raw), delimiter=sep)
        rows = list(reader)
    except Exception as e:
        logger.error(f"  {filepath.name}: CSV parse failed — {e}")
        return []

    if not rows:
        logger.warning(f"  {filepath.name}: file is empty")
        return []

    # Identify column aliases
    sample_keys = list(rows[0].keys())
    try:
        lg_idx, en_idx = _find_columns(sample_keys)
    except ValueError as e:
        logger.error(f"  {filepath.name}: {e}")
        return []

    lg_col = sample_keys[lg_idx]
    en_col = sample_keys[en_idx]
    logger.info(f"  Luganda column: '{lg_col}' | English column: '{en_col}'")

    # Optional extra columns
    optional_cols = [
        k for k in sample_keys
        if k.lower() not in LUGANDA_ALIASES | ENGLISH_ALIASES
    ]
    if optional_cols:
        logger.info(f"  Extra columns carried through: {optional_cols}")

    entries = []
    skipped = 0

    for row_num, row in enumerate(rows, start=2):  # start=2: row 1 is header
        luganda = _clean(row.get(lg_col, ""))
        english = _clean(row.get(en_col, ""))

        if not luganda or not english:
            skipped += 1
            continue

        entry = {
            "luganda":      luganda,
            "english":      english,
            "category":     "imported",
            "subcategory":  filepath.stem,
            "needs_review": True,
            "data_type":    _categorize(english, luganda),
        }

        # Carry through optional columns
        for col in optional_cols:
            val = _clean(row.get(col, ""))
            if val:
                # Normalize common column names to our standard fields
                col_lower = col.lower()
                if col_lower in ("notes", "note", "description"):
                    entry["notes"] = val
                elif col_lower in ("difficulty", "level"):
                    entry["difficulty"] = val
                elif col_lower in ("category", "cat", "type"):
                    entry["category"] = val
                elif col_lower in ("part_of_speech", "pos", "grammar"):
                    entry["part_of_speech"] = val
                else:
                    entry[col_lower] = val

        entries.append(entry)

    logger.info(f"  Parsed {len(entries)} entries, skipped {skipped} incomplete rows")
    return entries


# ── Core: ingest one file ─────────────────────────────────────────────────────

def process_file(filepath: Path, dry_run: bool) -> dict:
    """
    Parse a single CSV file, convert to JSON, and ingest into ChromaDB.
    Returns a counts dict.
    """
    logger.info(f"\nProcessing: {filepath.name}")
    entries = parse_csv_file(filepath)

    if not entries:
        logger.warning(f"  No valid entries found in {filepath.name} — skipping")
        return {}

    # Save as JSON to data/datasets/ so it's part of the permanent record
    output = {
        "metadata": {
            "source":        filepath.stem,
            "category":      "csv_import",
            "date_added":    str(date.today()),
            "source_file":   filepath.name,
            "total_entries": len(entries),
            "auto_imported": True,
            "needs_review":  True,
        },
        "entries": entries,
    }

    json_filename = f"{filepath.stem}_csv.json"
    json_path = DATASETS_DIR / json_filename
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"  JSON saved: {json_path.name}")

    # Group by collection
    records_by_collection: dict[str, list] = {}
    import hashlib
    for entry in entries:
        col = entry.get("data_type", "vocabulary")
        if col not in records_by_collection:
            records_by_collection[col] = []

        luganda = entry["luganda"]
        english = entry["english"]
        text    = f"{luganda} — {english}"
        if entry.get("notes"):
            text += f" | {entry['notes']}"

        doc_id = hashlib.md5(
            f"{col}|{filepath.stem}|{luganda[:100]}".encode("utf-8")
        ).hexdigest()

        metadata = {k: v for k, v in entry.items() if k != "data_type"}
        metadata["source_file"] = filepath.name

        records_by_collection[col].append({
            "collection": col,
            "doc_id":     doc_id,
            "text":       text,
            "metadata":   metadata,
        })

    for col, recs in records_by_collection.items():
        logger.info(f"  → {col}: {len(recs)} records")

    total = sum(len(r) for r in records_by_collection.values())

    if dry_run:
        logger.info(f"  [DRY RUN] Would ingest {total} records")
        return {}

    # Ingest
    from backend.services.ingestion.indexer import index_records
    counts = index_records(records_by_collection)
    logger.info(f"  Ingested: {counts}")

    # Log
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source":    filepath.stem,
        "file":      filepath.name,
        "counts":    counts,
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return counts


# ── Stats ─────────────────────────────────────────────────────────────────────

def show_stats():
    from backend.db.chroma_client import chroma_client
    print("\nChromaDB Collection Stats:")
    print("-" * 40)
    total = 0
    try:
        for col in chroma_client.list_collections():
            name  = col.name if hasattr(col, "name") else str(col)
            count = col.count() if hasattr(col, "count") else chroma_client.get_collection(name).count()
            print(f"  {name:<18}: {count:>6} records")
            total += count
    except Exception as e:
        logger.error(f"Stats failed: {e}")
        return
    print(f"  {'TOTAL':<18}: {total:>6} records\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest CSV vocabulary files into Luganda AI Studio ChromaDB"
    )
    parser.add_argument("--file",    type=str, help="Path to a single CSV file")
    parser.add_argument("--dir",     type=str, help=f"Directory of CSV files (default: {CSV_DIR})")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to ChromaDB")
    parser.add_argument("--stats",   action="store_true", help="Show ChromaDB counts and exit")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    # Collect files to process
    if args.file:
        path = Path(args.file)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            logger.error(f"File not found: {path}")
            return
        files = [path]
    else:
        search_dir = Path(args.dir) if args.dir else CSV_DIR
        if not search_dir.exists():
            logger.info(f"CSV directory does not exist yet: {search_dir}")
            logger.info("Create it and place .csv files there, then re-run.")
            logger.info(f"  mkdir {search_dir}")
            return
        files = sorted(search_dir.glob("*.csv")) + sorted(search_dir.glob("*.tsv"))
        if not files:
            logger.info(f"No .csv or .tsv files found in {search_dir}")
            return

    logger.info(f"Found {len(files)} file(s) to process")

    if not args.dry_run:
        logger.info("\n--- Before ingestion ---")
        show_stats()

    grand_total = 0
    for filepath in files:
        counts = process_file(filepath, dry_run=args.dry_run)
        if counts:
            grand_total += sum(counts.values()) if isinstance(counts, dict) else 0

    logger.info(f"\n{'=' * 50}")
    if args.dry_run:
        logger.info("DRY RUN complete. No data was written.")
    else:
        logger.info("INGESTION COMPLETE.")
        logger.info("\n--- After ingestion ---")
        show_stats()


if __name__ == "__main__":
    main()
