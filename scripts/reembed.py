# scripts/reembed.py

"""
Re-embed Migration Script
==========================

Wipes all ChromaDB collections and re-ingests from source JSON files
using the new paraphrase-multilingual-MiniLM-L12-v2 embedding model.

BEFORE RUNNING:
  1. Stop the FastAPI server (Ctrl+C in the terminal running uvicorn)
  2. From the project root, run:

       python scripts/reembed.py

EXPECTED RUNTIME:
  5-15 minutes on i7-11800H
  (~470 MB model download on first run, then embedding ~2,500 records)

SAFE TO RE-RUN:
  If it fails mid-way, just run it again. Ingestion is idempotent.
"""

import sys
import socket
import logging
import time
from pathlib import Path

# ── Ensure project root is on path ───────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db.chroma_client import get_chroma_client
from backend.services.ingestion.loader import load_all_datasets
from backend.services.ingestion.indexer import index_records

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

COLLECTIONS = ["vocabulary", "sentences", "grammar", "proverbs"]


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _check_server_stopped() -> None:
    if _port_in_use(8000):
        print("\n WARNING: Something is running on port 8000.")
        print("   Stop the FastAPI server before re-embedding to avoid conflicts.")
        print("   Press Ctrl+C to abort, or Enter to continue anyway.")
        try:
            input()
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(0)


def _delete_collections(client) -> None:
    print("\n Deleting existing collections...")
    for name in COLLECTIONS:
        try:
            client.delete_collection(name)
            print(f"   Deleted: {name}")
        except Exception as e:
            print(f"   {name}: {e} (skipping -- may not exist)")


def _reindex(client) -> dict:
    print("\n Loading data from datasets/...")
    all_records = load_all_datasets()

    for col_name, records in all_records.items():
        status = f"{len(records)} records" if records else " 0 records"
        print(f"   - {col_name:<12}: {status}")

    total = sum(len(v) for v in all_records.values())
    if total == 0:
        print("\n No records loaded. Check datasets/ folder.")
        sys.exit(1)

    print(f"\n Embedding and indexing {total} records...")
    print("   (First run downloads ~470 MB model -- subsequent runs are faster)")

    return index_records(all_records)


def _print_summary(summary: dict, elapsed: float) -> None:
    print("\n" + "=" * 60)
    print("  RE-EMBED COMPLETE")
    print("=" * 60)
    print(f"\n   Time taken: {elapsed:.1f}s\n")
    total = 0
    for col_name, count in summary.items():
        icon = "OK" if count > 0 else "WARN"
        print(f"   [{icon}]  {col_name:<12}: {count} records")
        total += count
    print(f"\n   Total: {total} records")
    print("\n   Next steps:")
    print("   1. Start the server: uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload")
    print("   2. Open http://127.0.0.1:8000/app/search.html and test a search")
    print("   3. Run: pytest tests/ -v")
    print("=" * 60 + "\n")


def main():
    print("\n" + "=" * 60)
    print("  LUGANDA AI STUDIO -- RE-EMBED MIGRATION")
    print("  Model: paraphrase-multilingual-MiniLM-L12-v2")
    print("=" * 60)

    _check_server_stopped()

    client = get_chroma_client()
    start = time.time()

    _delete_collections(client)
    summary = _reindex(client)

    _print_summary(summary, time.time() - start)


if __name__ == "__main__":
    main()
