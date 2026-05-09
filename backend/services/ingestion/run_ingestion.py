# backend/services/ingestion/run_ingestion.py

"""
Run Ingestion
==============

This is the script you run to load all your Luganda data into ChromaDB.

HOW TO RUN:
  From your project root (D:\\projects\\Luganda_AI_Studio), run:

      python -m backend.services.ingestion.run_ingestion

  Or with options:

      # Only re-index vocabulary
      python -m backend.services.ingestion.run_ingestion --collection vocabulary

      # Wipe a collection first, then re-index
      python -m backend.services.ingestion.run_ingestion --clear

      # Just check what's currently in ChromaDB
      python -m backend.services.ingestion.run_ingestion --status

WHAT IT DOES:
  1. Reads all JSON files from datasets/
  2. Converts them to standardised records
  3. Upserts records into the matching ChromaDB collection

SAFE TO RE-RUN:
  You can run this as many times as you want.
  It uses upsert (not insert), so it won't create duplicates.
  When you add new JSON files or fix existing ones, just re-run this.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# ── Make sure the project root is on the Python path ─────────────────────────
# This allows running as: python -m backend.services.ingestion.run_ingestion
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.ingestion.loader  import load_all_datasets
from backend.services.ingestion.indexer import index_records, clear_collection
from backend.db.chroma_client           import get_chroma_client


# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ── Status Check ─────────────────────────────────────────────────────────────

def print_status() -> None:
    """Print how many documents are currently in each ChromaDB collection."""
    client = get_chroma_client()
    collections = ["vocabulary", "sentences", "grammar", "proverbs"]

    print("\n" + "=" * 50)
    print("  CHROMADB STATUS")
    print("=" * 50)

    total = 0
    for col_name in collections:
        try:
            col   = client.get_or_create_collection(col_name)
            count = col.count()
            total += count
            bar   = "█" * min(count, 40) if count > 0 else "░ (empty)"
            print(f"  {col_name:<12} {count:>5} docs  {bar}")
        except Exception as e:
            print(f"  {col_name:<12} ERROR: {e}")

    print(f"{'─' * 50}")
    print(f"  {'TOTAL':<12} {total:>5} docs")
    print("=" * 50 + "\n")


# ── Main Ingestion ────────────────────────────────────────────────────────────

def run(
    collection_filter: str | None = None,
    clear: bool = False,
) -> None:
    """
    Run the full ingestion pipeline.

    Parameters
    ----------
    collection_filter : str or None
        If set, only ingest this collection ("vocabulary", "sentences", etc.)
        If None, ingest all collections.
    clear : bool
        If True, wipe the collection(s) first before indexing.
        Use this to fix corrupted or outdated data.
    """
    start_time = time.time()

    print("\n" + "=" * 60)
    print("  LUGANDA AI STUDIO — DATA INGESTION")
    print("=" * 60)

    # Step 1: Load all data from JSON files
    print("\n📂 Step 1: Loading data from datasets/...")
    all_records = load_all_datasets()

    # If filtering by collection, remove the rest
    if collection_filter:
        col = collection_filter.lower()
        all_records = {col: all_records.get(col, [])}
        print(f"   Filter: only processing '{col}'")

    # Print what was loaded
    print("\n   Records found:")
    for col_name, records in all_records.items():
        status = f"{len(records)} records" if records else "⚠️  0 records (check your JSON files)"
        print(f"   • {col_name:<12}: {status}")

    total_loaded = sum(len(v) for v in all_records.values())
    if total_loaded == 0:
        print("\n⚠️  No records were loaded. Check that your datasets/ folder has JSON files.")
        print("   Expected locations:")
        print("   • datasets/vocabulary/*.json")
        print("   • datasets/sentences/*.json")
        print("   • datasets/grammar/*.json")
        print("   • datasets/proverbs/*.json")
        return

    # Step 2: Optionally clear collections first
    if clear:
        print("\n🗑️  Step 2: Clearing existing data (--clear was set)...")
        for col_name in all_records.keys():
            success = clear_collection(col_name)
            status  = "✅ cleared" if success else "❌ failed"
            print(f"   • {col_name}: {status}")
    else:
        print("\n⏭️  Step 2: Skipping clear (using upsert — safe to re-run)")

    # Step 3: Index records into ChromaDB
    print(f"\n🔄 Step 3: Indexing {total_loaded} records into ChromaDB...")
    print("   (ChromaDB will embed the text using MiniLM — this may take a moment)")

    summary = index_records(all_records)

    # Step 4: Show results
    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("  INGESTION COMPLETE")
    print("=" * 60)
    print(f"\n   Time taken: {elapsed:.1f} seconds\n")

    total_indexed = 0
    for col_name, count in summary.items():
        icon = "✅" if count > 0 else "⚠️ "
        print(f"   {icon}  {col_name:<12}: {count} records indexed")
        total_indexed += count

    print(f"\n   Total indexed: {total_indexed} records")

    if total_indexed == 0:
        print("\n   ⚠️  Nothing was indexed. Possible causes:")
        print("   1. Your JSON files may be empty or have wrong field names.")
        print("   2. ChromaDB connection may have failed.")
        print("   Check the logs above for specific errors.")
    else:
        print("\n   ✅ Data is ready. You can now search at:")
        print("      http://127.0.0.1:8000/app/search.html")

    print("=" * 60 + "\n")


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Luganda AI Studio — Data Ingestion Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full ingestion (safe to re-run anytime)
  python -m backend.services.ingestion.run_ingestion

  # Only re-index vocabulary
  python -m backend.services.ingestion.run_ingestion --collection vocabulary

  # Clear vocabulary then re-index it fresh
  python -m backend.services.ingestion.run_ingestion --collection vocabulary --clear

  # Check what is currently in ChromaDB
  python -m backend.services.ingestion.run_ingestion --status
        """,
    )

    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        choices=["vocabulary", "sentences", "grammar", "proverbs"],
        help="Only process this collection (default: all)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        default=False,
        help="Clear the collection(s) before indexing (WARNING: deletes existing data)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        default=False,
        help="Only show current ChromaDB status (no indexing)",
    )

    args = parser.parse_args()

    if args.status:
        print_status()
    else:
        run(
            collection_filter=args.collection,
            clear=args.clear,
        )


if __name__ == "__main__":
    main()
