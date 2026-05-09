# scripts/ingest_pdf.py

"""
PDF Ingestor for Luganda AI Studio — Phase 4
=============================================

Extracts Luganda-English translation pairs from PDF files and ingests
them into ChromaDB via the existing ingestion pipeline.

Two extraction strategies (tried in order per page):

  1. TABLE MODE — best for vocabulary PDFs with two-column tables.
     Detects tables using pdfplumber, treats left col as one language
     and right col as the other.

  2. LINE PATTERN MODE — best for PDFs with one pair per line.
     Matches common patterns:
       "word — translation"
       "word: translation"
       "word\t translation"
       "word | translation"
       "word = translation"

Language direction is auto-detected: if the left-column text is shorter
on average it is assumed to be Luganda (words are often shorter than
English phrases). Use --direction to override.

Usage:
  python scripts/ingest_pdf.py --file vocab.pdf
  python scripts/ingest_pdf.py --dir data/pdfs/
  python scripts/ingest_pdf.py --file vocab.pdf --preview
  python scripts/ingest_pdf.py --file vocab.pdf --dry-run
  python scripts/ingest_pdf.py --stats

Requirements:
  pip install pdfplumber --break-system-packages

Optional (improves text quality):
  pip install pymupdf --break-system-packages
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import date, datetime, timezone
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
PDF_DIR      = PROJECT_ROOT / "data" / "pdfs"
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"
LOG_FILE     = DATASETS_DIR / "ingestion_log.jsonl"

# ── Line-pattern regexes ──────────────────────────────────────────────────────
# Matches: "word — translation", "word: translation", "word | translation",
#          "word = translation", "word\t translation"
LINE_PATTERNS = [
    re.compile(r"^(.+?)\s*[—–\-]{1,2}\s*(.+)$"),    # em dash, en dash, hyphen
    re.compile(r"^(.+?)\s*:\s*(.+)$"),                 # colon
    re.compile(r"^(.+?)\s*\|\s*(.+)$"),                # pipe
    re.compile(r"^(.+?)\s*=\s*(.+)$"),                 # equals
    re.compile(r"^(.+?)\t+(.+)$"),                     # tab
]

# Minimum character length to keep a pair (filter noise)
MIN_LEN = 2
MAX_LEN = 500


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Normalize whitespace and strip."""
    if not text:
        return ""
    text = " ".join(text.split())
    return text.strip()


def _is_noise(text: str) -> bool:
    """Return True if text looks like page noise (page numbers, headers, etc.)."""
    stripped = text.strip()
    if len(stripped) < MIN_LEN:
        return True
    if len(stripped) > MAX_LEN:
        return True
    # Pure numbers (page numbers)
    if stripped.isdigit():
        return True
    # All caps short strings (section headings like "CHAPTER 1")
    if stripped.isupper() and len(stripped.split()) == 1 and len(stripped) < 10:
        return True
    return False


def _detect_direction(left_texts: list[str], right_texts: list[str]) -> str:
    """
    Auto-detect which column is Luganda vs English.
    Luganda words tend to be shorter than English phrases.
    Returns "lg_en" (left=Luganda) or "en_lg" (left=English).
    """
    if not left_texts or not right_texts:
        return "lg_en"
    avg_left  = sum(len(t) for t in left_texts)  / len(left_texts)
    avg_right = sum(len(t) for t in right_texts) / len(right_texts)
    return "lg_en" if avg_left <= avg_right else "en_lg"


def _categorize(english: str, luganda: str) -> str:
    """vocabulary (≤2 words) or sentences (3+ words)."""
    return "vocabulary" if max(len(english.split()), len(luganda.split())) <= 2 else "sentences"


# ── Extraction: table mode ────────────────────────────────────────────────────

def _extract_from_tables(page, direction: str | None) -> list[tuple[str, str]]:
    """
    Extract pairs from tables on a single pdfplumber page.
    Returns list of (luganda, english) tuples.
    """
    pairs = []

    tables = page.extract_tables()
    if not tables:
        return pairs

    for table in tables:
        if not table:
            continue

        # Filter to rows with at least 2 non-empty cells
        valid_rows = []
        for row in table:
            if row is None:
                continue
            cells = [_clean(str(c)) if c else "" for c in row]
            filled = [c for c in cells if c and not _is_noise(c)]
            if len(filled) >= 2:
                valid_rows.append(cells)

        if not valid_rows:
            continue

        # Use first two meaningful columns
        # Detect direction from column content if not forced
        col0_texts = [r[0] for r in valid_rows if len(r) > 0 and r[0]]
        col1_texts = [r[1] for r in valid_rows if len(r) > 1 and r[1]]

        eff_direction = direction or _detect_direction(col0_texts, col1_texts)

        for row in valid_rows:
            if len(row) < 2:
                continue
            c0 = _clean(row[0]) if row[0] else ""
            c1 = _clean(row[1]) if row[1] else ""

            if not c0 or not c1:
                continue
            if _is_noise(c0) or _is_noise(c1):
                continue

            if eff_direction == "lg_en":
                pairs.append((c0, c1))   # (luganda, english)
            else:
                pairs.append((c1, c0))   # swap

    return pairs


# ── Extraction: line pattern mode ────────────────────────────────────────────

def _extract_from_lines(page, direction: str | None) -> list[tuple[str, str]]:
    """
    Extract pairs from plain text lines using delimiter patterns.
    Returns list of (luganda, english) tuples.
    """
    text = page.extract_text()
    if not text:
        return []

    pairs = []
    lines = text.split("\n")

    left_parts  = []
    right_parts = []

    for line in lines:
        line = _clean(line)
        if not line or _is_noise(line):
            continue

        matched = False
        for pattern in LINE_PATTERNS:
            m = pattern.match(line)
            if m:
                left  = _clean(m.group(1))
                right = _clean(m.group(2))
                if left and right and not _is_noise(left) and not _is_noise(right):
                    left_parts.append(left)
                    right_parts.append(right)
                    matched = True
                    break

        if not matched:
            continue

    # Detect direction across all collected pairs
    eff_direction = direction or _detect_direction(left_parts, right_parts)

    for left, right in zip(left_parts, right_parts):
        if eff_direction == "lg_en":
            pairs.append((left, right))
        else:
            pairs.append((right, left))

    return pairs


# ── Core: parse one PDF ───────────────────────────────────────────────────────

def parse_pdf_file(filepath: Path, direction: str | None = None) -> list[dict]:
    """
    Extract Luganda-English pairs from a PDF file.
    Tries table extraction first, falls back to line patterns.
    Returns list of entry dicts.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error(
            "pdfplumber is not installed.\n"
            "Run: pip install pdfplumber --break-system-packages"
        )
        return []

    pairs: list[tuple[str, str]] = []
    table_count  = 0
    pattern_count = 0

    logger.info(f"  Opening PDF: {filepath.name}")

    try:
        with pdfplumber.open(str(filepath)) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"  Pages: {total_pages}")

            for page_num, page in enumerate(pdf.pages, start=1):
                # Try tables first
                table_pairs = _extract_from_tables(page, direction)
                if table_pairs:
                    pairs.extend(table_pairs)
                    table_count += len(table_pairs)
                else:
                    # Fall back to line patterns
                    line_pairs = _extract_from_lines(page, direction)
                    pairs.extend(line_pairs)
                    pattern_count += len(line_pairs)

    except Exception as e:
        logger.error(f"  Failed to read {filepath.name}: {e}")
        return []

    logger.info(
        f"  Extracted {len(pairs)} pairs "
        f"(tables: {table_count}, line patterns: {pattern_count})"
    )

    if not pairs:
        logger.warning(
            "  No pairs extracted. "
            "The PDF may use embedded images (scanned) rather than text. "
            "OCR is not supported — please use a text-based PDF."
        )
        return []

    # Deduplicate within this file
    seen: set[tuple[str, str]] = set()
    entries = []
    dupes = 0

    for luganda, english in pairs:
        key = (luganda.lower(), english.lower())
        if key in seen:
            dupes += 1
            continue
        seen.add(key)

        entries.append({
            "luganda":      luganda,
            "english":      english,
            "category":     "imported",
            "subcategory":  filepath.stem,
            "data_type":    _categorize(english, luganda),
            "needs_review": True,
        })

    if dupes:
        logger.info(f"  Removed {dupes} duplicates within the file")

    logger.info(f"  Final unique entries: {len(entries)}")
    return entries


# ── Core: ingest one file ─────────────────────────────────────────────────────

def process_file(filepath: Path, direction: str | None, dry_run: bool, preview: bool) -> dict:
    """
    Parse a single PDF, save as JSON, and ingest into ChromaDB.
    Returns counts dict.
    """
    logger.info(f"\nProcessing: {filepath.name}")
    entries = parse_pdf_file(filepath, direction=direction)

    if not entries:
        logger.warning(f"  No entries extracted from {filepath.name}")
        return {}

    # Preview first 20 pairs
    if preview:
        print(f"\n  Preview — first {min(20, len(entries))} pairs from {filepath.name}:")
        print(f"  {'LUGANDA':<30} {'ENGLISH'}")
        print(f"  {'-'*30} {'-'*30}")
        for e in entries[:20]:
            print(f"  {e['luganda']:<30} {e['english']}")
        print()

    # Save as JSON
    output = {
        "metadata": {
            "source":        filepath.stem,
            "category":      "pdf_import",
            "date_added":    str(date.today()),
            "source_file":   filepath.name,
            "total_entries": len(entries),
            "auto_imported": True,
            "needs_review":  True,
        },
        "entries": entries,
    }

    json_filename = f"{filepath.stem}_pdf.json"
    json_path = DATASETS_DIR / json_filename
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"  JSON saved: {json_path.name}")

    # Group by collection and build ChromaDB records
    records_by_collection: dict[str, list] = {}
    for entry in entries:
        col = entry.get("data_type", "vocabulary")
        if col not in records_by_collection:
            records_by_collection[col] = []

        luganda = entry["luganda"]
        english = entry["english"]
        text    = f"{luganda} — {english}"

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
        "type":      "pdf",
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
        description="Extract and ingest Luganda-English pairs from PDF files"
    )
    parser.add_argument("--file",      type=str,   help="Path to a single PDF file")
    parser.add_argument("--dir",       type=str,   help=f"Directory of PDFs (default: {PDF_DIR})")
    parser.add_argument(
        "--direction",
        choices=["lg_en", "en_lg"],
        default=None,
        help=(
            "Column/line direction. lg_en = left/first is Luganda. "
            "en_lg = left/first is English. "
            "Default: auto-detect."
        ),
    )
    parser.add_argument("--preview", action="store_true", help="Show first 20 extracted pairs per file without ingesting")
    parser.add_argument("--dry-run", action="store_true", help="Parse and show counts but do not write to ChromaDB")
    parser.add_argument("--stats",   action="store_true", help="Show ChromaDB counts and exit")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    # Collect files
    if args.file:
        path = Path(args.file)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            logger.error(f"File not found: {path}")
            return
        files = [path]
    else:
        search_dir = Path(args.dir) if args.dir else PDF_DIR
        if not search_dir.exists():
            logger.info(f"PDF directory does not exist yet: {search_dir}")
            logger.info("Create it and place .pdf files there, then re-run.")
            logger.info(f"  mkdir {search_dir}")
            return
        files = sorted(search_dir.glob("*.pdf")) + sorted(search_dir.glob("*.PDF"))
        if not files:
            logger.info(f"No PDF files found in {search_dir}")
            return

    logger.info(f"Found {len(files)} PDF file(s) to process")

    if not args.dry_run and not args.preview:
        logger.info("\n--- Before ingestion ---")
        show_stats()

    grand_total = 0
    for filepath in files:
        counts = process_file(
            filepath,
            direction = args.direction,
            dry_run   = args.dry_run,
            preview   = args.preview,
        )
        if counts and isinstance(counts, dict):
            grand_total += sum(counts.values())

    logger.info(f"\n{'=' * 50}")
    if args.preview:
        logger.info("PREVIEW complete. No data was written.")
    elif args.dry_run:
        logger.info("DRY RUN complete. No data was written.")
    else:
        logger.info("INGESTION COMPLETE.")
        logger.info("\n--- After ingestion ---")
        show_stats()


if __name__ == "__main__":
    main()
