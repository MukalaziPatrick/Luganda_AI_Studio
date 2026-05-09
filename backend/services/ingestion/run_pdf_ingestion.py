# backend/services/ingestion/run_pdf_ingestion.py

"""
Run PDF Ingestion
==================

Loads all PDFs from datasets/raw_downloads/ into ChromaDB.
Stores them in a separate "documents" collection.

HOW TO RUN (from your project root):

  # Process all PDFs in datasets/raw_downloads/
  python -m backend.services.ingestion.run_pdf_ingestion

  # Process a single specific PDF
  python -m backend.services.ingestion.run_pdf_ingestion --file luganda_grammar.pdf

  # Wipe the documents collection first, then re-index all PDFs
  python -m backend.services.ingestion.run_pdf_ingestion --clear

  # Check how many document chunks are currently in ChromaDB
  python -m backend.services.ingestion.run_pdf_ingestion --status

SAFE TO RE-RUN:
  Uses upsert — running again will update existing chunks, not duplicate them.
  If you add new PDFs to raw_downloads/, just re-run this script.

PERFORMANCE ESTIMATE (your machine):
  Digital PDF (~20 pages): ~5-15 seconds
  Scanned PDF (~20 pages): ~2-5 minutes (OCR is slow)
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# ── Ensure project root is on path ────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.ingestion.pdf_loader import load_all_pdfs, load_pdf_file
from backend.services.ingestion.indexer    import index_records, clear_collection
from backend.db.chroma_client              import get_chroma_client

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

RAW_DOWNLOADS_DIR = PROJECT_ROOT / "datasets" / "raw_downloads"


# ── Status ────────────────────────────────────────────────────────────────────

def print_status() -> None:
    """Show how many document chunks are in ChromaDB."""
    client = get_chroma_client()

    print("\n" + "=" * 50)
    print("  DOCUMENTS COLLECTION STATUS")
    print("=" * 50)

    try:
        col   = client.get_or_create_collection("documents")
        count = col.count()
        bar   = "█" * min(count // 5, 40) if count > 0 else "░ (empty)"
        print(f"  documents    {count:>5} chunks  {bar}")
    except Exception as e:
        print(f"  documents    ERROR: {e}")

    # Also show what PDFs are in raw_downloads
    print(f"\n  PDFs in datasets/raw_downloads/:")
    pdf_files = sorted(RAW_DOWNLOADS_DIR.glob("*.pdf")) if RAW_DOWNLOADS_DIR.exists() else []
    if pdf_files:
        for f in pdf_files:
            size_kb = f.stat().st_size // 1024
            print(f"    • {f.name} ({size_kb} KB)")
    else:
        print("    (no PDF files found)")

    print("=" * 50 + "\n")


# ── Main Run ──────────────────────────────────────────────────────────────────

def run(
    single_file: str | None = None,
    clear: bool = False,
) -> None:
    """
    Run the full PDF ingestion pipeline.

    Parameters
    ----------
    single_file : str or None
        If set, only process this one PDF filename (not the full directory).
    clear : bool
        If True, wipe the documents collection before indexing.
    """
    start_time = time.time()

    print("\n" + "=" * 60)
    print("  LUGANDA AI STUDIO — PDF INGESTION")
    print("=" * 60)

    # ── Step 1: Find PDFs ──────────────────────────────────────────
    if single_file:
        pdf_path = RAW_DOWNLOADS_DIR / single_file
        if not pdf_path.exists():
            print(f"\n❌ File not found: {pdf_path}")
            print(f"   Make sure the file is in: {RAW_DOWNLOADS_DIR}")
            return
        print(f"\n📄 Processing single file: {single_file}")
    else:
        pdf_files = sorted(RAW_DOWNLOADS_DIR.glob("*.pdf")) if RAW_DOWNLOADS_DIR.exists() else []
        if not pdf_files:
            print(f"\n⚠️  No PDF files found in: {RAW_DOWNLOADS_DIR}")
            print("   Add your PDFs there and re-run this script.")
            return
        print(f"\n📂 Found {len(pdf_files)} PDF files:")
        for f in pdf_files:
            size_kb = f.stat().st_size // 1024
            print(f"   • {f.name} ({size_kb} KB)")

    # ── Step 2: Optionally clear ───────────────────────────────────
    if clear:
        print("\n🗑️  Clearing existing documents collection...")
        success = clear_collection("documents")
        print(f"   {'✅ Cleared' if success else '❌ Failed to clear'}")
    else:
        print("\n⏭️  Skipping clear (upsert mode — safe to re-run)")

    # ── Step 3: Load PDFs ──────────────────────────────────────────
    print("\n🔄 Step 3: Extracting text from PDFs...")
    print("   Digital PDFs: fast (seconds)")
    print("   Scanned PDFs: slow (minutes) — OCR in progress...\n")

    if single_file:
        records = load_pdf_file(RAW_DOWNLOADS_DIR / single_file)
    else:
        records = load_all_pdfs(RAW_DOWNLOADS_DIR)

    if not records:
        print("\n⚠️  No chunks were extracted.")
        print("   Possible reasons:")
        print("   1. PDFs are empty or password-protected")
        print("   2. OCR failed on scanned pages")
        print("   3. Pages were too short to create meaningful chunks")
        return

    print(f"\n   Extracted {len(records)} chunks total")

    # ── Step 4: Index into ChromaDB ────────────────────────────────
    print(f"\n💾 Step 4: Storing {len(records)} chunks in ChromaDB...")

    summary = index_records({"documents": records})
    indexed = summary.get("documents", 0)

    # ── Step 5: Results ────────────────────────────────────────────
    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("  PDF INGESTION COMPLETE")
    print("=" * 60)
    print(f"\n   Time taken  : {elapsed:.1f} seconds")
    print(f"   Chunks indexed: {indexed}")

    if indexed > 0:
        print("\n   ✅ PDFs are now searchable at:")
        print("      http://127.0.0.1:8000/app/search.html")
        print("      (Select the 'Documents' filter to see PDF results)")
    else:
        print("\n   ⚠️  Nothing was indexed. Check the logs above for errors.")

    print("=" * 60 + "\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Luganda AI Studio — PDF Ingestion Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all PDFs in datasets/raw_downloads/
  python -m backend.services.ingestion.run_pdf_ingestion

  # Process one specific PDF
  python -m backend.services.ingestion.run_pdf_ingestion --file luganda_grammar.pdf

  # Clear documents collection then re-index everything
  python -m backend.services.ingestion.run_pdf_ingestion --clear

  # Check current status
  python -m backend.services.ingestion.run_pdf_ingestion --status
        """,
    )

    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Process only this PDF filename (must be in datasets/raw_downloads/)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        default=False,
        help="Clear the documents collection before indexing",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        default=False,
        help="Show current ChromaDB document status only",
    )

    args = parser.parse_args()

    if args.status:
        print_status()
    else:
        run(
            single_file=args.file,
            clear=args.clear,
        )


if __name__ == "__main__":
    main()
