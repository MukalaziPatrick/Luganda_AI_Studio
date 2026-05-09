# scripts/download_datasets.py

"""
Dataset Downloader for Luganda AI Studio — Phase 1
====================================================

Downloads and cleans publicly available Luganda-English parallel datasets.

Priority order (from training-plan.md):
  1. Flores-200  — 1,000 high-quality benchmark sentences
  2. JW300       — ~30,000 Luganda-English sentence pairs
  3. OPUS        — Additional parallel corpora

Usage:
  python scripts/download_datasets.py --source flores
  python scripts/download_datasets.py --source jw300
  python scripts/download_datasets.py --source all
  python scripts/download_datasets.py --list          # show available sources

Output:
  Cleaned JSON files in data/datasets/ ready for ingestion.
  Format matches the existing Luganda AI Studio schema.

IMPORTANT:
  All imported data is marked needs_review: true.
  Run a spot-check of 50 entries before trusting bulk imports.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

# Add project root to path so we can import backend modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Output directory ─────────────────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / "data" / "datasets"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── Deduplication ────────────────────────────────────────────────────────────

def load_existing_pairs(datasets_dir: Path) -> set:
    """
    Scan all existing JSON dataset files and collect (english_lower, luganda_lower)
    pairs to avoid importing duplicates.
    """
    existing = set()

    # Scan datasets/ folder (existing data)
    for json_file in datasets_dir.rglob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            entries = []
            if isinstance(data, list):
                entries = data
            elif isinstance(data, dict) and "entries" in data:
                entries = data["entries"]

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                en = (entry.get("english") or "").strip().lower()
                lg = (entry.get("luganda") or "").strip().lower()
                if en and lg:
                    existing.add((en, lg))

        except Exception:
            continue

    return existing


def normalize_text(text: str) -> str:
    """Clean a text string: strip whitespace, normalize encoding."""
    if not text:
        return ""
    # Strip whitespace, normalize multiple spaces
    text = " ".join(text.strip().split())
    return text


def categorize_entry(english: str, luganda: str) -> str:
    """
    Categorize as vocabulary or sentences based on word count.
    1-2 words → vocabulary
    3+ words  → sentences
    """
    # Use the longer of the two texts for word count
    max_words = max(len(english.split()), len(luganda.split()))
    return "vocabulary" if max_words <= 2 else "sentences"


def save_dataset(entries: list, source_name: str, category: str) -> Path:
    """Save a cleaned dataset as JSON matching the Luganda AI Studio format."""
    output = {
        "metadata": {
            "source": source_name,
            "category": category,
            "date_added": str(date.today()),
            "total_entries": len(entries),
            "auto_imported": True,
            "needs_review": True,
        },
        "entries": entries,
    }

    filename = f"{source_name}_{category}.json"
    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(entries)} {category} entries to {filepath}")
    return filepath


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE: Flores-200
# ══════════════════════════════════════════════════════════════════════════════

def _hf_load_pair(dataset_id: str, token=None, per_language_config=True) -> list:
    """
    Helper: extract eng_Latn + lug_Latn pairs from a HuggingFace flores dataset.

    Handles two common layouts:

    Layout A — per-language configs (e.g. openlanguagedata/flores_plus):
        load_dataset(id, "eng_Latn") → rows with field "sentence"
        load_dataset(id, "lug_Latn") → rows with field "sentence"
        Zipped by row index.

    Layout B — single "default" config, all languages as columns
        (e.g. cqchangm/flores200):
        load_dataset(id) → rows with fields "eng_Latn", "lug_Latn", etc.

    Raises on any failure so callers can fall through to the next source.
    """
    from datasets import load_dataset

    kwargs = {}
    if token:
        kwargs["token"] = token

    pairs = []

    if per_language_config:
        # Layout A: separate config per language
        ds_en = load_dataset(dataset_id, "eng_Latn", **kwargs)
        ds_lg = load_dataset(dataset_id, "lug_Latn", **kwargs)
        for split_name in ["dev", "devtest"]:
            if split_name not in ds_en or split_name not in ds_lg:
                logger.warning(f"  [{dataset_id}] split '{split_name}' missing — skipping")
                continue
            en_rows = list(ds_en[split_name])
            lg_rows = list(ds_lg[split_name])
            count = min(len(en_rows), len(lg_rows))
            for i in range(count):
                en = normalize_text(en_rows[i].get("sentence", ""))
                lg = normalize_text(lg_rows[i].get("sentence", ""))
                if en and lg:
                    pairs.append((en, lg))
            logger.info(f"  {split_name}: {count} pairs")
    else:
        # Layout B: single default config, language columns in each row
        ds = load_dataset(dataset_id, **kwargs)
        for split_name in ["dev", "devtest"]:
            if split_name not in ds:
                logger.warning(f"  [{dataset_id}] split '{split_name}' missing — skipping")
                continue
            count = 0
            for row in ds[split_name]:
                # Column names are the language codes directly
                en = normalize_text(row.get("eng_Latn", ""))
                lg = normalize_text(row.get("lug_Latn", ""))
                if en and lg:
                    pairs.append((en, lg))
                    count += 1
            logger.info(f"  {split_name}: {count} pairs")

    return pairs


def download_flores():
    """
    Download Flores-200 / Flores+ dev and devtest sets for English-Luganda.

    Tries sources in this order:
      1. cqchangm/flores200        — public mirror, no auth needed
      2. openlanguagedata/flores_plus — gated; needs HF_TOKEN env variable
         Get a free token: https://huggingface.co/settings/tokens
         Accept dataset terms: https://huggingface.co/datasets/openlanguagedata/flores_plus
         Then set the env var:  set HF_TOKEN=hf_xxxxxxxxxxxx   (Windows)

    Requires: pip install datasets --break-system-packages
    """
    logger.info("=" * 60)
    logger.info("FLORES: Downloading English-Luganda benchmark sentences")
    logger.info("=" * 60)

    try:
        from datasets import load_dataset  # noqa: F401 — check installed
    except ImportError:
        logger.error("HuggingFace 'datasets' library not installed.")
        logger.error("Run: pip install datasets --break-system-packages")
        return []

    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")

    pairs = []

    # ── Source 1: cqchangm/flores200 — extract from cached TAR archive ─────────
    # This dataset is a TAR of the original flores200 text files (one file per
    # language, one sentence per line). We download via huggingface_hub then
    # extract eng_Latn + lug_Latn ourselves instead of using load_dataset.
    try:
        import tarfile
        import tempfile
        from huggingface_hub import hf_hub_download

        logger.info("Downloading cqchangm/flores200 TAR archive (public, no auth)...")
        tar_path = hf_hub_download(
            repo_id="cqchangm/flores200",
            filename="flores200_dataset.tar.gz",
            repo_type="dataset",
        )
        logger.info(f"  Archive cached at: {tar_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger.info("  Extracting archive...")
            with tarfile.open(tar_path, "r:gz") as tf:
                tf.extractall(tmpdir)

            tmpdir_path = Path(tmpdir)

            # Find the extracted folder (usually flores200_dataset/)
            candidates = list(tmpdir_path.rglob("eng_Latn.devtest"))
            if not candidates:
                raise FileNotFoundError("eng_Latn.devtest not found inside TAR")

            base = candidates[0].parent.parent  # e.g. .../flores200_dataset/

            for split_name, ext in [("devtest", "devtest"), ("dev", "dev")]:
                en_file = base / split_name / f"eng_Latn.{ext}"
                lg_file = base / split_name / f"lug_Latn.{ext}"

                if not en_file.exists() or not lg_file.exists():
                    logger.warning(f"  {split_name}: files not found — skipping")
                    continue

                en_lines = en_file.read_text(encoding="utf-8").strip().split("\n")
                lg_lines = lg_file.read_text(encoding="utf-8").strip().split("\n")
                count = min(len(en_lines), len(lg_lines))

                for i in range(count):
                    en = normalize_text(en_lines[i])
                    lg = normalize_text(lg_lines[i])
                    if en and lg:
                        pairs.append((en, lg))

                logger.info(f"  {split_name}: {count} pairs loaded")

        if pairs:
            logger.info(f"Flores total raw pairs: {len(pairs)}")
            return pairs
        logger.warning("cqchangm/flores200 TAR extraction returned 0 pairs.")

    except Exception as e:
        logger.warning(f"cqchangm/flores200 TAR extraction failed: {e}")

    # ── Source 2: openlanguagedata/flores_plus (gated — needs HF_TOKEN) ───────
    if hf_token:
        try:
            logger.info("Trying openlanguagedata/flores_plus (authenticated)...")
            pairs = _hf_load_pair("openlanguagedata/flores_plus", token=hf_token)
            if pairs:
                logger.info(f"Flores total raw pairs: {len(pairs)}")
                return pairs
            logger.warning("flores_plus returned 0 pairs.")
        except Exception as e:
            logger.warning(f"flores_plus (authenticated) failed: {e}")
    else:
        logger.warning("HF_TOKEN not set — skipping openlanguagedata/flores_plus.")
        logger.warning("")
        logger.warning("  To unlock this source:")
        logger.warning("  1. Create a free account at https://huggingface.co")
        logger.warning("  2. Accept dataset terms: https://huggingface.co/datasets/openlanguagedata/flores_plus")
        logger.warning("  3. Create a token: https://huggingface.co/settings/tokens")
        logger.warning("  4. In this terminal run:")
        logger.warning("       set HF_TOKEN=hf_your_token_here")
        logger.warning("  5. Re-run: python scripts/download_datasets.py --source flores")
        logger.warning("")

    logger.info("Flores total raw pairs: 0")
    return []  # CHANGED: tries cqchangm mirror first, then authenticated flores_plus


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE: OPUS / JW300 (via Hugging Face datasets)
# ══════════════════════════════════════════════════════════════════════════════

def download_jw300():
    """
    Download JW300 English-Luganda parallel corpus.

    This tries the Hugging Face datasets library first.
    If not installed, falls back to direct OPUS download.
    """
    logger.info("=" * 60)
    logger.info("JW300: Downloading English-Luganda parallel corpus")
    logger.info("=" * 60)

    # Try Hugging Face datasets first
    try:
        from datasets import load_dataset

        logger.info("Loading JW300 via Hugging Face datasets library...")
        ds = load_dataset("opus_jw300", lang1="en", lang2="lg", split="train", trust_remote_code=True)

        all_pairs = []
        for row in ds:
            translation = row.get("translation", {})
            en = normalize_text(translation.get("en", ""))
            lg = normalize_text(translation.get("lg", ""))
            if en and lg and len(en) > 2 and len(lg) > 2:
                all_pairs.append((en, lg))

        logger.info(f"JW300 via HuggingFace: {len(all_pairs)} pairs loaded")
        return all_pairs

    except ImportError:
        logger.info("Hugging Face 'datasets' library not installed.")
        logger.info("Install with: pip install datasets --break-system-packages")
        logger.info("Skipping JW300 for now.")
        return []

    except Exception as e:
        logger.error(f"JW300 download failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ══════════════════════════════════════════════════════════════════════════════

SOURCES = {
    "flores": {
        "name": "Flores-200",
        "description": "1,000 high-quality benchmark sentences from Facebook Research",
        "download_fn": download_flores,
    },
    "jw300": {
        "name": "JW300",
        "description": "~30,000 English-Luganda pairs from Jehovah's Witnesses publications",
        "download_fn": download_jw300,
    },
}


def run_download(source_key: str, existing_pairs: set):
    """Download, clean, deduplicate, and save a single source."""
    source = SOURCES[source_key]
    logger.info(f"\nProcessing source: {source['name']}")
    logger.info(f"Description: {source['description']}")

    # Download raw pairs
    raw_pairs = source["download_fn"]()
    if not raw_pairs:
        logger.warning(f"No data retrieved from {source['name']}. Skipping.")
        return

    logger.info(f"Raw pairs from {source['name']}: {len(raw_pairs)}")

    # Deduplicate against existing data
    new_pairs = []
    dup_count = 0
    for en, lg in raw_pairs:
        key = (en.lower(), lg.lower())
        if key in existing_pairs:
            dup_count += 1
            continue
        existing_pairs.add(key)  # prevent intra-source duplicates too
        new_pairs.append((en, lg))

    logger.info(f"After deduplication: {len(new_pairs)} new, {dup_count} duplicates removed")

    if not new_pairs:
        logger.info("No new entries to add. All were duplicates.")
        return

    # Categorize and build entries
    vocab_entries = []
    sentence_entries = []

    for en, lg in new_pairs:
        cat = categorize_entry(en, lg)
        entry = {
            "luganda": lg,
            "english": en,
            "category": "imported",
            "subcategory": source_key,
            "difficulty": "intermediate",
            "needs_review": True,
        }

        if cat == "vocabulary":
            vocab_entries.append(entry)
        else:
            sentence_entries.append(entry)

    # Save
    saved_files = []
    if vocab_entries:
        fp = save_dataset(vocab_entries, source_key, "vocabulary")
        saved_files.append(fp)
    if sentence_entries:
        fp = save_dataset(sentence_entries, source_key, "sentences")
        saved_files.append(fp)

    logger.info(
        f"{source['name']} complete: "
        f"{len(vocab_entries)} vocabulary + {len(sentence_entries)} sentences = "
        f"{len(vocab_entries) + len(sentence_entries)} total new entries"
    )

    return saved_files


def main():
    parser = argparse.ArgumentParser(
        description="Download and clean Luganda-English datasets for Phase 1"
    )
    parser.add_argument(
        "--source",
        choices=list(SOURCES.keys()) + ["all"],
        default="flores",
        help="Which dataset to download (default: flores)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available sources and exit",
    )

    args = parser.parse_args()

    if args.list:
        print("\nAvailable dataset sources:")
        print("-" * 50)
        for key, info in SOURCES.items():
            print(f"  {key:<10} — {info['description']}")
        print(f"\n  all        — Download all sources")
        print(f"\nUsage: python scripts/download_datasets.py --source flores")
        return

    # Load existing data for deduplication
    datasets_dir = PROJECT_ROOT / "datasets"
    logger.info("Scanning existing datasets for deduplication...")
    existing = load_existing_pairs(datasets_dir)
    # Also scan data/datasets/ in case prior imports are there
    existing.update(load_existing_pairs(OUTPUT_DIR))
    logger.info(f"Found {len(existing)} existing translation pairs")

    # Run downloads
    sources_to_run = list(SOURCES.keys()) if args.source == "all" else [args.source]

    for src in sources_to_run:
        run_download(src, existing)

    logger.info("\n" + "=" * 60)
    logger.info("DOWNLOAD COMPLETE")
    logger.info(f"Output directory: {OUTPUT_DIR}")
    logger.info("Next step: python scripts/ingest_dataset.py")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
