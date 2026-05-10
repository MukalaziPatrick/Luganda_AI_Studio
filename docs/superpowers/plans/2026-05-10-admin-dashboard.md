# Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only admin dashboard at `/app/admin.html` that shows system health, collection counts, feedback stats, training data counts, and translation pipeline status.

**Architecture:** A single `GET /api/v1/admin/status` endpoint in a new `admin.py` route file aggregates data from ChromaDB, the feedback JSONL log, training JSONL files, and in-memory service state. The frontend is a static `admin.html` page that fetches this endpoint on load and renders five cards. `openrouter_service.py` is updated to track the timestamp of its last successful call.

**Tech Stack:** FastAPI, Python 3.10+, ChromaDB, httpx (TestClient), pytest, vanilla JS + CSS (matching existing app style)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/api/routes/admin.py` | CREATE | `GET /api/v1/admin/status` — aggregates all status data |
| `backend/services/translation/openrouter_service.py` | MODIFY | Add `last_call_at: Optional[str]` tracking on successful calls |
| `backend/main.py` | MODIFY | Register admin router at `/api/v1/admin` |
| `frontend/admin.html` | CREATE | Five-card dashboard UI, fetches `/api/v1/admin/status` on load |
| `frontend/index.html` | MODIFY | Add "Admin" nav link |
| `tests/__init__.py` | CREATE | Make tests a package |
| `tests/test_admin.py` | CREATE | Tests for the admin status endpoint |

---

### Task 1: Bootstrap test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

pytest and httpx are not in requirements.txt. The FastAPI TestClient uses `httpx` (already installed). Install pytest only.

- [ ] **Step 1: Install pytest**

```bash
pip install pytest
```

Expected output includes: `Successfully installed pytest-...`

- [ ] **Step 2: Create `tests/__init__.py`**

```python
```

(Empty file — makes `tests/` a Python package.)

- [ ] **Step 3: Create `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 4: Verify pytest discovers the fixture**

```bash
pytest tests/ --collect-only
```

Expected: `0 errors`, no collection failures. (No tests yet — that's fine.)

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: bootstrap pytest infrastructure"
```

---

### Task 2: Add `last_call_at` tracking to OpenRouterTranslator

**Files:**
- Modify: `backend/services/translation/openrouter_service.py`

The admin endpoint needs to know when OpenRouter was last called successfully. We add a module-level `_last_call_at: Optional[str]` variable and set it on every successful translation.

- [ ] **Step 1: Write the failing test**

Create `tests/test_openrouter_tracking.py`:

```python
from backend.services.translation import openrouter_service as svc


def test_last_call_at_starts_as_none():
    # Reset state for isolation
    svc._last_call_at = None
    assert svc.get_last_call_at() is None


def test_get_last_call_at_returns_string_after_set():
    svc._last_call_at = "2026-05-10T12:00:00+00:00"
    assert svc.get_last_call_at() == "2026-05-10T12:00:00+00:00"
    svc._last_call_at = None  # clean up
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_openrouter_tracking.py -v
```

Expected: FAIL — `AttributeError: module has no attribute '_last_call_at'` or `get_last_call_at`

- [ ] **Step 3: Update `backend/services/translation/openrouter_service.py`**

Add below the existing `_daily_spend_usd` line:

```python
from datetime import datetime, timezone
from typing import Optional

# In-memory timestamp of last successful OpenRouter call. None until first call.
_last_call_at: Optional[str] = None


def get_last_call_at() -> Optional[str]:
    """Return ISO 8601 timestamp of last successful OpenRouter call, or None."""
    return _last_call_at
```

Then inside the `translate` method, after the `logger.info(f"[OpenRouter] '{text}' → '{translated}'")` line, add:

```python
global _last_call_at
_last_call_at = datetime.now(timezone.utc).isoformat()
```

**Full updated file** — replace the entire file content:

```python
# backend/services/translation/openrouter_service.py

"""
OpenRouter neural translation — Pass 4.5 in the translation pipeline.

Used between semantic search and NLLB-200.
Skipped entirely if OPENROUTER_API_KEY is not set.

On any failure (timeout, HTTP error, bad response, spend limit):
  returns None → pipeline falls through to NLLB-200.

Confidence returned: 0.75
Match type: "neural_api"
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_LANG_NAMES = {
    "en_to_lg": ("English", "Luganda"),
    "lg_to_en": ("Luganda", "English"),
}

# In-memory daily spend counter. Resets on server restart.
_daily_spend_usd: float = 0.0

# In-memory timestamp of last successful OpenRouter call. None until first call.
_last_call_at: Optional[str] = None


def get_last_call_at() -> Optional[str]:
    """Return ISO 8601 timestamp of last successful OpenRouter call, or None."""
    return _last_call_at


class OpenRouterTranslator:
    """Thin wrapper around the OpenRouter chat completions API."""

    def is_enabled(self) -> bool:
        return bool(settings.openrouter_api_key)

    def translate(self, text: str, direction: str) -> Optional[str]:
        """
        Translate `text` using OpenRouter.
        Returns the translated string, or None if unavailable/failed.
        """
        global _daily_spend_usd, _last_call_at

        if not self.is_enabled():
            return None

        if _daily_spend_usd >= settings.openrouter_daily_limit_usd:
            logger.warning(
                f"[OpenRouter] Daily spend limit "
                f"${settings.openrouter_daily_limit_usd:.2f} reached. "
                f"Skipping — falling back to NLLB-200."
            )
            return None

        source_lang, target_lang = _LANG_NAMES.get(direction, ("English", "Luganda"))

        payload = {
            "model": settings.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Luganda-English translator. "
                        "Return only the translated text. "
                        "No explanation, no punctuation changes, no added context."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Translate the following from {source_lang} to {target_lang}: {text}"
                    ),
                },
            ],
        }

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=settings.openrouter_timeout_seconds) as client:
                response = client.post(_OPENROUTER_URL, json=payload, headers=headers)

                if response.status_code != 200:
                    logger.warning(
                        f"[OpenRouter] HTTP {response.status_code} — "
                        f"falling back to NLLB-200."
                    )
                    return None

                data = response.json()

                usage = data.get("usage", {})
                cost = usage.get("cost", 0.0)
                if cost:
                    _daily_spend_usd += cost

                choices = data.get("choices") or []
                if not choices:
                    logger.warning("[OpenRouter] Empty choices in response — falling back to NLLB-200.")
                    return None

                translated = (
                    choices[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )

                if not translated:
                    logger.warning("[OpenRouter] Empty translation in response — falling back to NLLB-200.")
                    return None

                logger.info(f"[OpenRouter] '{text}' → '{translated}'")
                _last_call_at = datetime.now(timezone.utc).isoformat()
                return translated

        except httpx.TimeoutException:
            logger.warning(
                f"[OpenRouter] Timeout after {settings.openrouter_timeout_seconds}s "
                f"— falling back to NLLB-200."
            )
            return None
        except Exception as e:
            logger.warning(f"[OpenRouter] Error: {e} — falling back to NLLB-200.")
            return None


openrouter_translator = OpenRouterTranslator()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_openrouter_tracking.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/translation/openrouter_service.py tests/test_openrouter_tracking.py
git commit -m "feat: track last_call_at timestamp in openrouter_service"
```

---

### Task 3: Create the admin status endpoint

**Files:**
- Create: `backend/api/routes/admin.py`
- Create: `tests/test_admin.py`

The endpoint collects all status data and returns it in one JSON response. Each section is wrapped in a try/except so a failure in one area doesn't break the whole response.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admin.py`:

```python
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_admin_status_returns_200():
    response = client.get("/api/v1/admin/status")
    assert response.status_code == 200


def test_admin_status_has_required_sections():
    response = client.get("/api/v1/admin/status")
    data = response.json()
    assert "system" in data
    assert "collections" in data
    assert "feedback" in data
    assert "training" in data
    assert "pipeline" in data


def test_admin_system_section_has_required_keys():
    response = client.get("/api/v1/admin/status")
    system = response.json()["system"]
    assert "api_status" in system
    assert "chroma_connected" in system
    assert "openrouter_key_set" in system
    assert "tts_deps_installed" in system
    assert "chroma_disk_mb" in system
    assert system["api_status"] == "ok"


def test_admin_collections_section_has_required_keys():
    response = client.get("/api/v1/admin/status")
    cols = response.json()["collections"]
    for name in ("vocabulary", "sentences", "grammar", "proverbs", "documents", "total"):
        assert name in cols


def test_admin_feedback_section_has_required_keys():
    response = client.get("/api/v1/admin/status")
    fb = response.json()["feedback"]
    for key in ("total_submissions", "last_submission_at", "correct", "wrong", "needs_review"):
        assert key in fb


def test_admin_training_section_has_required_keys():
    response = client.get("/api/v1/admin/status")
    tr = response.json()["training"]
    for key in ("training_pairs", "correction_pairs", "last_export"):
        assert key in tr


def test_admin_pipeline_section_has_required_keys():
    response = client.get("/api/v1/admin/status")
    pl = response.json()["pipeline"]
    for key in ("nllb_loaded", "openrouter_key_set", "openrouter_last_call_at"):
        assert key in pl
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_admin.py -v
```

Expected: All tests FAIL with 404 (route not registered yet)

- [ ] **Step 3: Create `backend/api/routes/admin.py`**

```python
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

_COLLECTIONS = ["vocabulary", "sentences", "grammar", "proverbs", "documents"]


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
                col = client.get_or_create_collection(name)
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
            "openrouter_key_set": bool(settings.openrouter_api_key),
            "openrouter_last_call_at": get_last_call_at(),
        },
    }
```

- [ ] **Step 4: Register the router in `backend/main.py`**

Add the import and `include_router` call. Open `backend/main.py` and make these two changes:

Change the imports line from:
```python
from backend.api.routes import health, knowledge, translate, teach, feedback, chat, tts
```
To:
```python
from backend.api.routes import health, knowledge, translate, teach, feedback, chat, tts, admin
```

Add after the existing `app.include_router(tts.router, ...)` line:
```python
app.include_router(admin.router,    prefix="/api/v1/admin",    tags=["Admin"])
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_admin.py -v
```

Expected: All 7 tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/admin.py backend/main.py tests/test_admin.py
git commit -m "feat: add GET /api/v1/admin/status endpoint"
```

---

### Task 4: Build `frontend/admin.html`

**Files:**
- Create: `frontend/admin.html`

Static page that fetches `/api/v1/admin/status` on load and populates five cards. Uses the same CSS tokens as `reviews.html`.

- [ ] **Step 1: Create `frontend/admin.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Admin — Luganda AI Studio</title>
  <link rel="manifest" href="/app/manifest.json" />
  <meta name="theme-color" content="#0c1710" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,600;0,9..144,700;1,9..144,400&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet" />

  <style>
    :root {
      --bg:            #0c1710;
      --bg-card:       #111f15;
      --bg-surface:    #182a1d;
      --border:        #243529;
      --green-deep:    #1a6b35;
      --green-mid:     #27924a;
      --green-light:   #52c46e;
      --amber:         #d99b2a;
      --amber-light:   #f0b93c;
      --red:           #c9503e;
      --text-primary:  #deeee2;
      --text-secondary:#7a9e84;
      --text-muted:    #3e5c46;
      --font-display:  'Fraunces', Georgia, serif;
      --font-body:     'DM Sans', sans-serif;
      --radius:        14px;
      --radius-sm:     8px;
      --space-2: 8px; --space-3: 12px; --space-4: 16px;
      --space-5: 20px; --space-6: 24px; --space-8: 32px;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: var(--font-body); background: var(--bg); color: var(--text-primary); min-height: 100vh; padding: var(--space-6); }
    h1 { font-family: var(--font-display); font-size: 2rem; font-weight: 600; margin-bottom: var(--space-2); }
    .subtitle { color: var(--text-secondary); margin-bottom: var(--space-8); font-size: 0.9rem; }
    nav { margin-bottom: var(--space-8); display: flex; gap: var(--space-4); flex-wrap: wrap; }
    nav a { color: var(--text-secondary); text-decoration: none; font-size: 0.9rem; padding: var(--space-2) var(--space-3); border-radius: var(--radius-sm); border: 1px solid var(--border); transition: color 0.18s, border-color 0.18s; }
    nav a:hover { color: var(--text-primary); border-color: var(--green-mid); }
    nav a.active { color: var(--green-light); border-color: var(--green-mid); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: var(--space-6); }
    .card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--space-6); }
    .card-title { font-family: var(--font-display); font-size: 1.1rem; font-weight: 600; margin-bottom: var(--space-4); color: var(--text-primary); }
    .pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 99px; font-size: 0.8rem; font-weight: 500; }
    .pill.ok   { background: #0d2a18; color: var(--green-light); border: 1px solid #1a5c30; }
    .pill.fail { background: #2a1208; color: #e07060; border: 1px solid #5c2010; }
    .pill.warn { background: #1c1205; color: var(--amber-light); border: 1px solid #5a3e10; }
    .status-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) 0; border-bottom: 1px solid var(--border); }
    .status-row:last-child { border-bottom: none; }
    .status-label { color: var(--text-secondary); font-size: 0.88rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    th { text-align: left; color: var(--text-muted); font-weight: 500; padding: var(--space-2) 0; border-bottom: 1px solid var(--border); }
    td { padding: var(--space-2) 0; border-bottom: 1px solid var(--border); color: var(--text-secondary); }
    td:last-child { text-align: right; color: var(--text-primary); font-weight: 500; }
    tfoot td { color: var(--green-light); font-weight: 600; border-top: 1px solid var(--border); border-bottom: none; }
    .stat-row { display: flex; justify-content: space-between; align-items: center; padding: var(--space-2) 0; border-bottom: 1px solid var(--border); font-size: 0.88rem; }
    .stat-row:last-child { border-bottom: none; }
    .stat-val { color: var(--text-primary); font-weight: 500; }
    .refresh-btn { margin-top: var(--space-8); padding: var(--space-2) var(--space-5); background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-secondary); font-family: var(--font-body); font-size: 0.88rem; cursor: pointer; transition: color 0.18s, border-color 0.18s; }
    .refresh-btn:hover { color: var(--text-primary); border-color: var(--green-mid); }
    .error-msg { color: #e07060; font-size: 0.88rem; margin-top: var(--space-4); }
    .loading { color: var(--text-muted); font-size: 0.88rem; }
  </style>
</head>
<body>

  <nav>
    <a href="/app/index.html">Dashboard</a>
    <a href="/app/translate.html">Translate</a>
    <a href="/app/search.html">Search</a>
    <a href="/app/teach.html">Teach</a>
    <a href="/app/reviews.html">Reviews</a>
    <a href="/app/admin.html" class="active">Admin</a>
  </nav>

  <h1>Admin Dashboard</h1>
  <p class="subtitle">System status — read-only view. Refresh the page to update.</p>

  <div id="error" class="error-msg" style="display:none"></div>
  <div id="loading" class="loading">Loading status…</div>

  <div class="grid" id="grid" style="display:none">

    <!-- Card 1: System Health -->
    <div class="card">
      <div class="card-title">System Health</div>
      <div class="status-row">
        <span class="status-label">API</span>
        <span class="pill ok">● Online</span>
      </div>
      <div class="status-row">
        <span class="status-label">ChromaDB</span>
        <span id="chroma-pill" class="pill">…</span>
      </div>
      <div class="status-row">
        <span class="status-label">OpenRouter key</span>
        <span id="or-key-pill" class="pill">…</span>
      </div>
      <div class="status-row">
        <span class="status-label">TTS dependencies</span>
        <span id="tts-pill" class="pill">…</span>
      </div>
      <div class="status-row">
        <span class="status-label">ChromaDB disk usage</span>
        <span id="chroma-disk" class="stat-val">…</span>
      </div>
    </div>

    <!-- Card 2: Collections -->
    <div class="card">
      <div class="card-title">Collections</div>
      <table>
        <thead><tr><th>Collection</th><th>Records</th></tr></thead>
        <tbody id="collections-body"></tbody>
        <tfoot><tr><td>Total</td><td id="collections-total">…</td></tr></tfoot>
      </table>
    </div>

    <!-- Card 3: Feedback Summary -->
    <div class="card">
      <div class="card-title">Feedback Summary</div>
      <div class="stat-row"><span class="status-label">Total submissions</span><span id="fb-total" class="stat-val">…</span></div>
      <div class="stat-row"><span class="status-label">Last submission</span><span id="fb-last" class="stat-val">…</span></div>
      <div class="stat-row"><span class="status-label">✓ Correct</span><span id="fb-correct" class="stat-val">…</span></div>
      <div class="stat-row"><span class="status-label">✗ Wrong</span><span id="fb-wrong" class="stat-val">…</span></div>
      <div class="stat-row"><span class="status-label">🔁 Needs Review</span><span id="fb-review" class="stat-val">…</span></div>
    </div>

    <!-- Card 4: Training Data -->
    <div class="card">
      <div class="card-title">Training Data</div>
      <div class="stat-row"><span class="status-label">Training pairs</span><span id="tr-pairs" class="stat-val">…</span></div>
      <div class="stat-row"><span class="status-label">Correction pairs</span><span id="tr-corrections" class="stat-val">…</span></div>
      <div class="stat-row"><span class="status-label">Last export</span><span id="tr-export" class="stat-val">…</span></div>
    </div>

    <!-- Card 5: Translation Pipeline -->
    <div class="card">
      <div class="card-title">Translation Pipeline</div>
      <div class="status-row">
        <span class="status-label">NLLB model loaded</span>
        <span id="nllb-pill" class="pill">…</span>
      </div>
      <div class="status-row">
        <span class="status-label">OpenRouter key set</span>
        <span id="or-pill2" class="pill">…</span>
      </div>
      <div class="status-row">
        <span class="status-label">OpenRouter last call</span>
        <span id="or-last" class="stat-val">…</span>
      </div>
    </div>

  </div>

  <button class="refresh-btn" onclick="location.reload()">↺ Refresh</button>

  <script>
    function pill(ok, yesLabel = 'Yes', noLabel = 'No') {
      const cls = ok ? 'ok' : 'fail';
      const dot = ok ? '●' : '●';
      const label = ok ? yesLabel : noLabel;
      return `<span class="pill ${cls}">${dot} ${label}</span>`;
    }

    function fmt(ts) {
      if (!ts) return '—';
      try {
        return new Date(ts).toLocaleString();
      } catch { return ts; }
    }

    async function load() {
      try {
        const res = await fetch('/api/v1/admin/status');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const d = await res.json();

        document.getElementById('loading').style.display = 'none';
        document.getElementById('grid').style.display = 'grid';

        // System
        document.getElementById('chroma-pill').outerHTML = pill(d.system.chroma_connected, 'Connected', 'Disconnected');
        document.getElementById('or-key-pill').outerHTML = pill(d.system.openrouter_key_set, 'Set', 'Not set');
        document.getElementById('tts-pill').outerHTML    = pill(d.system.tts_deps_installed, 'Installed', 'Missing');
        document.getElementById('chroma-disk').textContent = d.system.chroma_disk_mb + ' MB';

        // Collections
        const cols = ['vocabulary','sentences','grammar','proverbs','documents'];
        const tbody = document.getElementById('collections-body');
        tbody.innerHTML = cols.map(c =>
          `<tr><td>${c}</td><td style="text-align:right">${d.collections[c] ?? '—'}</td></tr>`
        ).join('');
        document.getElementById('collections-total').textContent = d.collections.total ?? '—';

        // Feedback
        document.getElementById('fb-total').textContent   = d.feedback.total_submissions;
        document.getElementById('fb-last').textContent    = fmt(d.feedback.last_submission_at);
        document.getElementById('fb-correct').textContent = d.feedback.correct;
        document.getElementById('fb-wrong').textContent   = d.feedback.wrong;
        document.getElementById('fb-review').textContent  = d.feedback.needs_review;

        // Training
        document.getElementById('tr-pairs').textContent       = d.training.training_pairs;
        document.getElementById('tr-corrections').textContent = d.training.correction_pairs;
        document.getElementById('tr-export').textContent      = d.training.last_export ?? '—';

        // Pipeline
        document.getElementById('nllb-pill').outerHTML  = pill(d.pipeline.nllb_loaded, 'Loaded', 'Not loaded');
        document.getElementById('or-pill2').outerHTML   = pill(d.pipeline.openrouter_key_set, 'Set', 'Not set');
        document.getElementById('or-last').textContent  = fmt(d.pipeline.openrouter_last_call_at);

      } catch (err) {
        document.getElementById('loading').style.display = 'none';
        const el = document.getElementById('error');
        el.style.display = 'block';
        el.textContent = 'Failed to load status: ' + err.message;
      }
    }

    load();
  </script>
</body>
</html>
```

- [ ] **Step 2: Open the app in a browser and verify all 5 cards render**

Start the server:
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open: `http://127.0.0.1:8000/app/admin.html`

Check:
- All 5 cards visible
- System Health: ChromaDB shows "Connected", API shows "Online"
- Collections: rows for vocabulary, sentences, grammar, proverbs, documents with real counts
- Feedback/Training cards show numbers (0 is fine if no data yet)
- Pipeline: NLLB shows "Not loaded" (expected — lazy loaded), OpenRouter key shows current state
- No JS errors in browser console

- [ ] **Step 3: Commit**

```bash
git add frontend/admin.html
git commit -m "feat: add admin dashboard frontend"
```

---

### Task 5: Add Admin nav link to `index.html`

**Files:**
- Modify: `frontend/index.html`

Add an "Admin" link to the navigation section alongside the existing page links. Search for the nav section — it contains links to Translate, Search, Teach, Reviews.

- [ ] **Step 1: Find the nav links in `index.html`**

Open `frontend/index.html` and find the navigation section. It will contain anchor tags pointing to `translate.html`, `search.html`, `teach.html`, `reviews.html`. Add an Admin link after the Reviews link:

```html
<a href="/app/admin.html">Admin</a>
```

The exact surrounding HTML will vary — add the link in the same style as the others. Do not change any other part of `index.html`.

- [ ] **Step 2: Verify in browser**

Open `http://127.0.0.1:8000/app/index.html` and confirm the Admin link appears and navigates to the dashboard.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: add Admin nav link to index.html"
```

---

## Self-Review Checklist

### Spec coverage

| Spec requirement | Task |
|---|---|
| `GET /api/v1/admin/status` endpoint | Task 3 |
| `system` section with health pills | Task 3 + Task 4 |
| `collections` section with counts | Task 3 + Task 4 |
| `feedback` section with verdicts | Task 3 + Task 4 |
| `training` section with pair counts | Task 3 + Task 4 |
| `pipeline` section with NLLB + OpenRouter | Task 3 + Task 4 |
| `openrouter_last_call_at` tracking | Task 2 |
| `frontend/admin.html` five-card layout | Task 4 |
| Nav link in `index.html` | Task 5 |
| Graceful degradation on error | Task 3 (`try/except` per section) |
| No auth required | ✅ No auth added |
| Read-only (no ingestion trigger) | ✅ No write endpoints |

### Placeholder scan

No TBDs, TODOs, or vague steps. All code is complete.

### Type consistency

- `get_last_call_at()` defined in Task 2, imported in Task 3 `admin_status()` — matches.
- `_nllb_loaded()` accesses `nllb_translator._model` — matches the `NLLBTranslator.__init__` pattern seen in `nllb_service.py`.
- All response keys in `admin_status()` match the spec JSON shape exactly.
