# backend/api/routes/admin.py

"""
Admin status endpoint.

GET /api/v1/admin/status
  Returns a single JSON object with system health, collection counts,
  feedback stats, training data counts, and pipeline status.

Each section is wrapped in try/except — a failure in one area
does not crash the whole response.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter

from backend.core.config import settings
from backend.db.chroma_client import get_chroma_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Paths to data files
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FEEDBACK_FILE = _PROJECT_ROOT / "data" / "feedback" / "feedback_log.jsonl"
_TRAINING_FILE = _PROJECT_ROOT / "data" / "training" / "training_pairs.jsonl"
_CORRECTIONS_FILE = _PROJECT_ROOT / "data" / "training" / "corrections.jsonl"
_TRAINING_DIR = _PROJECT_ROOT / "data" / "training"
_CHROMA_DIR = _PROJECT_ROOT / "data" / "chromadb"

_COLLECTIONS = ["vocabulary", "sentences", "grammar", "proverbs"]


def _chroma_disk_mb() -> float:
    """Return total size of the ChromaDB directory in MB."""
    try:
        total = sum(f.stat().st_size for f in _CHROMA_DIR.rglob("*") if f.is_file())
        return round(total / (1024 * 1024), 1)
    except Exception:
        return 0.0


def _tts_deps_installed() -> bool:
    """Return True if transformers and scipy are importable."""
    try:
        import transformers  # noqa: F401
        import scipy  # noqa: F401
        return True
    except ImportError:
        return False


def _collection_counts() -> Dict[str, Any]:
    """Return record counts per ChromaDB collection."""
    counts: Dict[str, Any] = {}
    try:
        client = get_chroma_client()
        for name in _COLLECTIONS:
            try:
                col = client.get_collection(name)
                counts[name] = col.count()
            except Exception:
                counts[name] = 0
        counts["total"] = sum(counts.values())
    except Exception as e:
        logger.warning(f"[admin] ChromaDB collection counts failed: {e}")
        for name in _COLLECTIONS:
            counts[name] = 0
        counts["total"] = 0
    return counts


def _chroma_connected() -> bool:
    """Return True if ChromaDB responds."""
    try:
        client = get_chroma_client()
        client.list_collections()
        return True
    except Exception:
        return False


def _feedback_stats() -> Dict[str, Any]:
    """Read feedback_log.jsonl and return summary counts."""
    result: Dict[str, Any] = {
        "total_submissions": 0,
        "last_submission_at": None,
        "correct": 0,
        "wrong": 0,
        "needs_review": 0,
    }
    if not _FEEDBACK_FILE.exists():
        return result
    try:
        records = []
        with open(_FEEDBACK_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        result["total_submissions"] = len(records)
        result["correct"] = sum(1 for r in records if r.get("verdict") == "correct")
        result["wrong"] = sum(1 for r in records if r.get("verdict") == "wrong")
        result["needs_review"] = sum(1 for r in records if r.get("verdict") == "needs_review")
        if records:
            result["last_submission_at"] = records[-1].get("timestamp")
    except Exception as e:
        logger.warning(f"[admin] Feedback stats failed: {e}")
    return result


def _count_jsonl_lines(path: Path) -> int:
    """Count non-empty lines in a JSONL file. Returns 0 if file missing."""
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _last_export_date() -> Optional[str]:
    """Return the date suffix of the most recent dataset_export_*.jsonl file."""
    try:
        exports = sorted(_TRAINING_DIR.glob("dataset_export_*.jsonl"))
        if not exports:
            return None
        # filename: dataset_export_YYYY-MM-DD.jsonl
        name = exports[-1].stem  # dataset_export_2026-05-10
        return name.replace("dataset_export_", "")
    except Exception:
        return None


def _nllb_loaded() -> bool:
    """Return True if the NLLB model singleton has been initialised."""
    try:
        from backend.services.translation.nllb_service import nllb_translator
        return nllb_translator._model is not None
    except Exception:
        return False


@router.get("/status")
async def admin_status() -> Dict[str, Any]:
    """
    Return aggregated system status for the admin dashboard.
    Each section degrades gracefully — failures return zeros/nulls.
    """
    from backend.services.translation.openrouter_service import get_last_call_at

    return {
        "system": {
            "api_status": "ok",
            "chroma_connected": _chroma_connected(),
            "openrouter_key_set": bool(settings.openrouter_api_key),
            "tts_deps_installed": _tts_deps_installed(),
            "chroma_disk_mb": _chroma_disk_mb(),
        },
        "collections": _collection_counts(),
        "feedback": _feedback_stats(),
        "training": {
            "training_pairs": _count_jsonl_lines(_TRAINING_FILE),
            "correction_pairs": _count_jsonl_lines(_CORRECTIONS_FILE),
            "last_export": _last_export_date(),
        },
        "pipeline": {
            "nllb_loaded": _nllb_loaded(),
            "openrouter_last_call_at": get_last_call_at(),
        },
    }
