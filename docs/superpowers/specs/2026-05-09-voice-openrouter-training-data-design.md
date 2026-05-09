# Luganda AI Studio — Voice, OpenRouter & Training Data Design

> Created: 2026-05-09
> Status: Approved
> Scope: Three independent features + roadmap ordering

---

## 1. Overview

This spec covers three improvements to Luganda AI Studio:

1. **OpenRouter neural translation** — replace NLLB-200 as primary neural fallback with a cheap API model, keeping NLLB-200 as offline safety net
2. **Text-to-speech (TTS)** — speak translated Luganda aloud using Meta's MMS local model
3. **Training data cleanup + export** — clean the feedback pipeline and produce a publishable, HuggingFace-compatible dataset

These features are independent and can be built and shipped in sequence without affecting each other.

---

## 2. Constraints

| Constraint | Detail |
|---|---|
| GPU | RTX 3050 Laptop, 4 GB VRAM |
| Budget | Under $5/month API spend |
| Users | Eventually public-facing |
| Offline resilience | Neural translation must work without internet |
| API key timing | OpenRouter key not available yet — system must work without it |

---

## 3. Feature 1 — OpenRouter Neural Translation

### 3.1 Goal

Replace NLLB-200 as the primary neural translation fallback with a cheap OpenRouter API model. Keep NLLB-200 as a silent offline fallback.

### 3.2 Pipeline Position

```
Pass 1: Exact match          (confidence: 1.00)
Pass 2: Normalized match     (confidence: 0.98)
Pass 3: Partial match        (confidence: 0.85)
Pass 4: Semantic match       (confidence: variable, threshold 0.50)
Pass 4.5: OpenRouter API     (confidence: 0.75, match_type: "neural_api")   ← NEW
Pass 5: NLLB-200 local       (confidence: variable, match_type: "neural_local")
→ not_found
```

### 3.3 Behaviour When API Key Is Absent

- If `OPENROUTER_API_KEY` is not set, Pass 4.5 is skipped entirely
- No error is raised, no log warning on every request — one startup log line only
- Pipeline falls straight through to NLLB-200 as before

### 3.4 Timeout and Fallback

- Hard timeout: 8 seconds (configurable via `OPENROUTER_TIMEOUT_SECONDS`, default `8`)
- On timeout, non-200 response, or any exception: silently fall through to NLLB-200
- All fallbacks are invisible to the user — they receive a translation regardless

### 3.5 Model

- Default: `google/gemma-2-9b-it:free` (free tier, strong instruction following)
- Configurable via `OPENROUTER_MODEL` env var — swap without touching code

### 3.6 Prompt

```
System: You are a Luganda-English translator. Return only the translated text. No explanation, no punctuation changes, no added context.
User: Translate the following from {source_lang} to {target_lang}: {text}
```

### 3.7 Response Handling

- Parse response as plain text, strip whitespace
- Return `match_type: "neural_api"`, `confidence: 0.75`, `matched_collection: null`
- If response is empty or unparseable, fall through to NLLB-200

### 3.8 Cost Guard

- Default free-tier models cost $0
- `OPENROUTER_DAILY_LIMIT_USD` env var (default `0.10`) caps spend for paid models
- In-memory counter, resets on server restart — sufficient for personal/small-team use
- When limit hit: log a warning, skip OpenRouter, fall through to NLLB-200

### 3.9 Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | unset | Enables OpenRouter; skipped if absent |
| `OPENROUTER_MODEL` | `google/gemma-2-9b-it:free` | Model to use |
| `OPENROUTER_TIMEOUT_SECONDS` | `8` | Max wait before falling back |
| `OPENROUTER_DAILY_LIMIT_USD` | `0.10` | Spend cap for paid models |

### 3.10 Files Changed

| File | Action |
|---|---|
| `backend/services/translation/openrouter_service.py` | NEW |
| `backend/services/translation/service.py` | Add Pass 4.5 |
| `backend/core/config.py` | Add 4 env vars |

---

## 4. Feature 2 — Text-to-Speech (TTS) with Meta MMS

### 4.1 Goal

Allow users to hear Luganda translations spoken aloud using Meta's MMS TTS model for Luganda (`facebook/mms-tts-lug`). Local, no API cost, real Luganda voice.

### 4.2 Model

- `facebook/mms-tts-lug` via HuggingFace `transformers`
- Loaded with `VitsModel` + `VitsTokenizer`
- Size: ~few hundred MB, CPU-capable, no VRAM required
- Lazy-loaded on first TTS request (same pattern as NLLB-200)

### 4.3 Backend

**New route:** `POST /api/v1/tts`

Request:
```json
{ "text": "Oli otya", "lang": "lug" }
```

Response: WAV audio file as a `StreamingResponse` with `Content-Type: audio/wav`

- Model lazy-loads on first request
- Subsequent requests: ~1–2s on CPU
- No caching of audio files — generated on demand

### 4.4 Frontend

- Speaker button (`🔊`) appears next to translation result on `translate.html`
- Speaker button appears next to flashcard/answer text on `teach.html`
- Clicking calls `POST /api/v1/tts`, plays returned WAV via inline `<audio>` element
- Button shows spinner while request is in flight
- Button disables during playback to prevent double-fires
- Re-enables when audio ends

### 4.5 First-Use Toast

- On the first TTS request of a browser session, a toast appears:
  > *"Loading Luganda voice for the first time — this takes ~10 seconds. It'll be instant after that."*
- Shown once per session, tracked via `sessionStorage`
- Auto-dismisses after 6 seconds
- Does not block audio playback — toast and loading happen in parallel

### 4.6 Files Changed

| File | Action |
|---|---|
| `backend/services/tts/mms_tts_service.py` | NEW |
| `backend/api/routes/tts.py` | NEW |
| `backend/main.py` | Add TTS router |
| `frontend/translate.html` | Add speaker button + toast logic |
| `frontend/teach.html` | Add speaker button |
| `frontend/styles.css` | Speaker button styles, toast styles |

---

## 5. Feature 3 — Training Data Cleanup + Export

### 5.1 Goal

Clean the existing feedback pipeline and produce a date-stamped, HuggingFace-compatible export suitable for publishing and future LoRA fine-tuning.

### 5.2 Cleaning Rules (applied in order)

| Rule | Action |
|---|---|
| Minimum length | Drop pair if `source` OR `target` is under 3 characters (checked independently) |
| Blank target | Drop pair if `expected_output` is null or empty string |
| Identical pair | Drop pair if `source` and `target` are identical after normalization |
| Deduplication | For duplicate `(source_text, direction)` pairs, keep the most recent |
| Whitespace | Strip leading/trailing whitespace from both fields |

### 5.3 Export Schema

Each line of `dataset_export_YYYY-MM-DD.jsonl`:

```json
{
  "source": "hello",
  "target": "Oli otya",
  "direction": "en_to_lg",
  "match_type": "correction",
  "verified": true,
  "submitted_at": "2026-04-19T10:23:00Z"
}
```

- `verified: true` = user-submitted correction
- `verified: false` = auto-generated (from pipeline, not human-reviewed)
- Schema is HuggingFace dataset compatible

### 5.4 Export Script

**New script:** `scripts/export_dataset.py`

- Reads `data/feedback/feedback_log.jsonl` + `data/training/training_pairs.jsonl`
- Applies cleaning rules
- Writes `data/training/dataset_export_YYYY-MM-DD.jsonl` (date = run date)
- Prints a summary report:
  ```
  Total input pairs:     412
  Duplicates dropped:     38
  Too short (< 3 chars):   4
  Blank targets dropped:  11
  Identical pairs dropped: 2
  Final export count:    357
  Verified pairs:        201
  Output: data/training/dataset_export_2026-05-09.jsonl
  ```

### 5.5 Changes to `process_feedback.py`

- Apply same minimum-length and blank-target checks before ingesting corrections into ChromaDB
- Prevents dirty data from entering the knowledge base in the first place

### 5.6 Files Changed

| File | Action |
|---|---|
| `scripts/export_dataset.py` | NEW |
| `scripts/process_feedback.py` | Add cleaning pass |

---

## 6. Roadmap

Build order with rationale:

| # | Feature | Effort | Risk | Rationale |
|---|---|---|---|---|
| 1 | Training data cleanup + export | Small | None | Zero risk, do before data volume grows, foundation for publishing |
| 2 | OpenRouter integration | Medium | Low | Biggest quality win, pipeline slot exists, graceful fallback |
| 3 | TTS with Meta MMS | Medium | Low | High user delight, self-contained, doesn't touch translation pipeline |
| 4 | Minimal admin tools (stats + health) | Small | None | Required before public launch |
| 5 | Annotation review UI | Medium | Low | Needed once real users submit corrections at volume |
| 6 | Evaluation suite | Medium | Low | Measure accuracy baseline before public launch |

### Deliberately Deferred

| Item | Reason |
|---|---|
| OpenRouter API key | Wired and ready — add key when available |
| LoRA fine-tuning | Only viable at 500+ verified correction pairs |
| Full admin collection browser | Useful but not urgent |
| Speech-to-text input | No suitable Luganda STT model exists yet |

---

## 7. Testing Notes

### OpenRouter
- With key absent: confirm pipeline falls through to NLLB-200, no errors
- With key present: translate a word not in ChromaDB, confirm `match_type: "neural_api"` in response
- Simulate timeout: confirm NLLB-200 result returned, no 500 error

### TTS
- First call: confirm toast appears, audio plays after ~10s
- Second call same session: confirm no toast, audio plays faster
- `teach.html`: confirm speaker button appears on flashcard and quiz answer

### Training Data Export
- Run `export_dataset.py` on existing data
- Confirm summary counts are correct
- Open output JSONL and verify schema matches spec
- Confirm entries under 3 chars on either side are absent
