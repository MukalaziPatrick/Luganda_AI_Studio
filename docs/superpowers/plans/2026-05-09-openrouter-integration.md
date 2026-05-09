# OpenRouter Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenRouter as Pass 4.5 in the translation pipeline — tried before NLLB-200, skipped silently if `OPENROUTER_API_KEY` is not set, with an 8-second timeout and graceful fallback to NLLB-200 on any failure.

**Architecture:** A new `openrouter_service.py` wraps the OpenRouter HTTP API. `service.py` gains a single new pass between semantic search and NLLB-200. All config is env-var driven. No frontend changes.

**Tech Stack:** Python 3.10+, `httpx` (async-capable HTTP client), FastAPI (already in use), `python-dotenv` (already in use)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/services/translation/openrouter_service.py` | Create | HTTP call to OpenRouter, timeout, response parsing |
| `backend/services/translation/service.py` | Modify | Add Pass 4.5 between semantic and NLLB-200 |
| `backend/core/config.py` | Modify | Add 4 OpenRouter env vars to `settings` |
| `.env` (already exists or create) | Note | Where user adds `OPENROUTER_API_KEY` when ready |

---

### Task 1: Add OpenRouter env vars to `config.py`

**Files:**
- Modify: `backend/core/config.py`

- [ ] **Step 1: Add OpenRouter settings to `config.py`**

Open `backend/core/config.py`. At the end of the file, after the `settings = SimpleNamespace(...)` block, add:

```python
# ─── OpenRouter ───────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-2-9b-it:free")
OPENROUTER_TIMEOUT_SECONDS = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "8"))
OPENROUTER_DAILY_LIMIT_USD = float(os.getenv("OPENROUTER_DAILY_LIMIT_USD", "0.10"))
```

Also add these to the `settings` SimpleNamespace so they're accessible via `settings.openrouter_api_key` etc:

Find the `settings = SimpleNamespace(` block and add four lines inside it:

```python
settings = SimpleNamespace(
    app_name="Luganda AI Studio",
    app_version="1.0.0",
    chroma_dir=CHROMA_PATH,
    datasets_dir=DATASETS_DIR,
    imported_datasets_dir=IMPORTED_DATASETS_DIR,
    feedback_dir=FEEDBACK_DIR,
    training_dir=TRAINING_DIR,
    # OpenRouter
    openrouter_api_key=OPENROUTER_API_KEY,
    openrouter_model=OPENROUTER_MODEL,
    openrouter_timeout_seconds=OPENROUTER_TIMEOUT_SECONDS,
    openrouter_daily_limit_usd=OPENROUTER_DAILY_LIMIT_USD,
)
```

- [ ] **Step 2: Verify config loads**

```bash
python -c "from backend.core.config import settings; print(settings.openrouter_api_key or '(not set — correct)')"
```

Expected:
```
(not set — correct)
```

- [ ] **Step 3: Commit**

```bash
git add backend/core/config.py
git commit -m "feat: add OpenRouter env vars to config"
```

---

### Task 2: Create `openrouter_service.py`

**Files:**
- Create: `backend/services/translation/openrouter_service.py`

- [ ] **Step 1: Check that `httpx` is available**

```bash
python -c "import httpx; print(httpx.__version__)"
```

If this fails with `ModuleNotFoundError`:
```bash
pip install httpx
```

- [ ] **Step 2: Create the service file**

Create `backend/services/translation/openrouter_service.py`:

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
# Sufficient for personal/small-team use.
_daily_spend_usd: float = 0.0


class OpenRouterTranslator:
    """Thin wrapper around the OpenRouter chat completions API."""

    def is_enabled(self) -> bool:
        return bool(settings.openrouter_api_key)

    def translate(self, text: str, direction: str) -> Optional[str]:
        """
        Translate `text` using OpenRouter.
        Returns the translated string, or None if unavailable/failed.
        """
        global _daily_spend_usd

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

            # Track spend if the API reports it
            usage = data.get("usage", {})
            cost = usage.get("cost", 0.0)
            if cost:
                _daily_spend_usd += cost

            translated = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )

            if not translated:
                logger.warning("[OpenRouter] Empty response — falling back to NLLB-200.")
                return None

            logger.info(f"[OpenRouter] '{text}' → '{translated}'")
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

- [ ] **Step 3: Verify the module imports cleanly**

```bash
python -c "from backend.services.translation.openrouter_service import openrouter_translator; print('enabled:', openrouter_translator.is_enabled())"
```

Expected (with no key set):
```
enabled: False
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/translation/openrouter_service.py
git commit -m "feat: add OpenRouterTranslator service with timeout and spend guard"
```

---

### Task 3: Wire Pass 4.5 into `service.py`

**Files:**
- Modify: `backend/services/translation/service.py`

- [ ] **Step 1: Add the import**

Open `backend/services/translation/service.py`. Find the existing imports at the top:

```python
from backend.services.translation.nllb_service import nllb_translator
```

Add the OpenRouter import directly below it:

```python
from backend.services.translation.openrouter_service import openrouter_translator
```

- [ ] **Step 2: Add Pass 4.5 in the `translate` function**

Find the Pass 3 block in the `translate` function (around line 372):

```python
    # ------------------------------------------------------------------ #
    # Pass 3 — Neural fallback (NLLB-200)
    # ------------------------------------------------------------------ #
    # Only reached when all search passes return nothing.
    # NLLB can translate any text, so this should never fall through to
    # not_found unless the model itself fails to load or crashes.
    logger.info(f"[Pass 3] Attempting neural translation for '{input_text}'")

    neural_text = nllb_translator.translate(input_text, direction)
```

Replace that entire block with:

```python
    # ------------------------------------------------------------------ #
    # Pass 3 — OpenRouter API (primary neural fallback)
    # Skipped silently if OPENROUTER_API_KEY is not set.
    # Falls through to NLLB-200 on timeout, HTTP error, or empty response.
    # ------------------------------------------------------------------ #
    if openrouter_translator.is_enabled():
        logger.info(f"[Pass 3] Attempting OpenRouter translation for '{input_text}'")
        api_text = openrouter_translator.translate(input_text, direction)
        if api_text:
            logger.info(f"[OpenRouter] '{input_text}' → '{api_text}'")
            return TranslationResponse(
                input_text=input_text,
                direction=direction,
                translated_text=api_text,
                match_type="neural_api",
                confidence=0.75,
                matched_collection="openrouter",
                matched_source_file=None,
                status="success",
                message="AI-generated translation via OpenRouter. May need review.",
            )

    # ------------------------------------------------------------------ #
    # Pass 4 — Neural fallback (NLLB-200 local)
    # Only reached when OpenRouter is disabled or failed.
    # ------------------------------------------------------------------ #
    logger.info(f"[Pass 4] Attempting NLLB-200 translation for '{input_text}'")

    neural_text = nllb_translator.translate(input_text, direction)
```

Also update the existing `if neural_text:` return block — change `"nllb-200"` → `"nllb-200-local"` and the pass comment below it to `Pass 5`:

```python
    if neural_text:
        logger.info(f"[NLLB] '{input_text}' → '{neural_text}'")
        return TranslationResponse(
            input_text=input_text,
            direction=direction,
            translated_text=neural_text,
            match_type="neural_local",
            confidence=0.70,
            matched_collection="nllb-200-local",
            matched_source_file=None,
            status="success",
            message="AI-generated translation (local model). May need review.",
        )

    # ------------------------------------------------------------------ #
    # Pass 5 — Nothing found
    # ------------------------------------------------------------------ #
```

- [ ] **Step 3: Start the backend and verify it boots without errors**

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Expected: server starts, no import errors. Look for:
```
INFO:     Application startup complete.
```

- [ ] **Step 4: Test translation without API key (should still work via NLLB-200)**

With server running, in a separate terminal:

```bash
python -c "
import httpx, json
r = httpx.post('http://127.0.0.1:8000/api/v1/translate', json={'text': 'xyznotindb', 'direction': 'en_to_lg'})
print(json.dumps(r.json(), indent=2))
"
```

Expected: response with `match_type` of `neural_local` or `not_found` — NOT `neural_api` (since key is not set).

- [ ] **Step 5: Commit**

```bash
git add backend/services/translation/service.py
git commit -m "feat: add OpenRouter as Pass 3 neural fallback, NLLB-200 moves to Pass 4"
```

---

### Task 4: Create `.env` template

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create `.env.example`**

Create `.env.example` at the project root:

```bash
# OpenRouter — add your key here when ready
# Get a key at https://openrouter.ai/keys
# OPENROUTER_API_KEY=sk-or-...

# Optional: override the model (default: google/gemma-2-9b-it:free)
# OPENROUTER_MODEL=mistralai/mistral-7b-instruct:free

# Optional: timeout in seconds before falling back to NLLB-200 (default: 8)
# OPENROUTER_TIMEOUT_SECONDS=8

# Optional: daily spend cap in USD for paid models (default: 0.10)
# OPENROUTER_DAILY_LIMIT_USD=0.10
```

- [ ] **Step 2: Ensure `.env` is in `.gitignore`**

```bash
python -c "
from pathlib import Path
gi = Path('.gitignore')
content = gi.read_text() if gi.exists() else ''
if '.env' not in content:
    with open('.gitignore', 'a') as f:
        f.write('\n.env\n')
    print('.env added to .gitignore')
else:
    print('.env already in .gitignore')
"
```

- [ ] **Step 3: Commit**

```bash
git add .env.example .gitignore
git commit -m "docs: add .env.example with OpenRouter configuration template"
```
