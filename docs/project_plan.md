# Luganda AI Studio — Project Plan

> Last updated from known project state.
> Update this file at the end of every completed phase.

---

## Project Goal

Build a practical, local-first Luganda AI application with three core features:

1. **Translate** — Luganda ↔ English with quality feedback
2. **Search** — semantic search across the Luganda knowledge base
3. **Teach** — interactive vocabulary and phrase learning mode

The system must be realistic for a Windows laptop with 16 GB RAM and 4 GB VRAM.
It must work with limited data now and improve as data grows.

---

## MVP Definition

The MVP is complete when all three of the following are true:

| Condition | Status |
|---|---|
| User can translate a word or phrase in both directions | ✅ Done |
| User can search the knowledge base and see results | ✅ Done |
| User can rate a translation and export session feedback | ✅ Done |
| Backend runs stably on local machine | ✅ Done |
| Frontend is accessible via browser at `/app/` | ✅ Done |

The MVP is **complete**. The project now moves into Phase 2.

---

## Phase Overview

```
Phase 1 — Foundation         ✅ COMPLETE
Phase 2 — Quality Loop       🔄 IN PROGRESS
Phase 3 — Teaching Mode      ⬜ PLANNED
Phase 4 — Data Pipeline      ⬜ PLANNED
Phase 5 — Admin Tools        ⬜ PLANNED
Phase 6 — Evaluation         ⬜ PLANNED
Phase 7 — Voice (optional)   ⬜ FUTURE
```

---

## Phase 1 — Foundation ✅ COMPLETE

**Goal:** Get a working backend and frontend serving real translations.

### Completed

- [x] FastAPI backend with Uvicorn
- [x] ChromaDB integration with 4 collections: vocabulary, sentences, grammar, proverbs
- [x] MiniLM embedding model for semantic search
- [x] 5-stage translation pipeline: exact → normalized → partial → semantic → not_found
- [x] Partial match improved to support multi-word input
- [x] `/api/v1/translate` endpoint working
- [x] `/api/v1/knowledge/search` endpoint working
- [x] `/api/v1/knowledge/stats` endpoint working
- [x] Static frontend served at `/app/` via FastAPI StaticFiles
- [x] `translate.html` — translation UI with direction toggle
- [x] `search.html` — semantic search with filter chips and result cards
- [x] `index.html` — dashboard / home page
- [x] Frontend API URLs fixed to match `/api/v1/` prefix
- [x] Frontend payload fixed: sends `direction: en_to_lg` not `source_lang/target_lang`
- [x] Frontend response parsing fixed: reads `translated_text` and `status` fields

---

## Phase 2 — Quality Loop 🔄 IN PROGRESS

**Goal:** Turn the translate page into a tool that actively improves the AI system.

### Completed

- [x] Result chips: direction, confidence %, match type, collection name
- [x] Feedback buttons: ✓ Correct / ✗ Wrong / 🔁 Needs Review
- [x] Expected output field: records what the correct translation should be
- [x] Session history: running log of all translations in the current session
- [x] Export JSON: downloads structured session data for dataset use

### Completed (Apr 17)

- [x] Feedback API endpoint — `POST /api/v1/feedback` saves verdicts to `data/feedback/feedback_log.jsonl`
- [x] Feedback storage — persists corrections as JSONL on disk (append-only, safe for frequent writes)
- [x] Frontend connected — translate.html sends verdicts to backend on every feedback click
- [x] Correction pair format — standard schema defined and used by `scripts/process_feedback.py`
- [x] Batch ingestion — `scripts/process_feedback.py` auto-ingests corrections into ChromaDB
- [x] Training data accumulation — corrections saved to `data/training/training_pairs.jsonl` for NLLB fine-tuning

### Remaining

- [x] Feedback review page — `frontend/reviews.html` built 2026-04-19. GET /api/v1/feedback endpoint added to feedback.py. Reviews nav link added to all pages.
- [x] Quality metrics — Session Summary card (Total/Correct/Wrong/Corrected) already live in translate.html. Confirmed complete.

---

## Phase 2 — Quality Loop ✅ COMPLETE
> Closed: 2026-04-19. All items done. See above.

---

## Phase 3 — Teaching Mode ✅ COMPLETE
> Confirmed complete: 2026-04-19. All tasks already built and working.

### Tasks

- [x] `teach.html` — full flash card mode (3D flip, Got It / Try Again, Review Missed)
- [x] `teach.html` — quiz mode (4-option multiple choice, correct/wrong highlight, notes display)
- [x] `/api/v1/teach/cards` — returns shuffled vocabulary cards from ChromaDB with fallback
- [x] `/api/v1/teach/quiz` — returns one question with 4 options, exclude= param to avoid repeats
- [x] `/api/v1/teach/quiz/answer` — validates answer, returns encouraging message
- [x] `/api/v1/teach/progress` GET + POST — persists cumulative session stats to disk
- [x] Progress bar, session score screen, keyboard shortcuts (Space/Enter/arrows)
- [x] Reviews nav link added to sidebar (2026-04-19)

---

## Phase 4 — Data Pipeline ✅ COMPLETE
> Closed: 2026-04-19. CSV ingestor and PDF parser built. All pipeline tasks done.

**Goal:** Make it easy to add new Luganda data and keep collections growing.

### Current Data Situation

| Source | Format | Status |
|---|---|---|
| Initial vocabulary | JSON / CSV | Loaded into ChromaDB |
| PDF documents | PDF | Not yet parsed |
| User corrections | JSONL on disk | Auto-ingested by `scripts/process_feedback.py` |
| Grammar notes | Manual | Partially loaded |
| Flores-200 | Downloaded JSON | Ready to ingest via `scripts/ingest_dataset.py` |
| JW300 | Downloaded JSON | Ready to ingest via `scripts/download_datasets.py` |

### Tasks

- [x] Dataset downloader — `scripts/download_datasets.py` fetches Flores-200 and JW300
- [x] Universal JSON ingestor — `scripts/ingest_dataset.py` loads any JSON into ChromaDB
- [x] Correction ingestor — `scripts/process_feedback.py` ingests user corrections
- [x] Deduplication — download script deduplicates against existing 464 pairs
- [x] Ingestion CLI — `python scripts/ingest_dataset.py --file mydata.json`
- [x] Ingestion log — `data/datasets/ingestion_log.jsonl` records every run
- [x] CSV ingestor — `scripts/ingest_csv.py`. Auto-detects separator, column aliases, optional columns. Built 2026-04-19
- [x] PDF parser — `scripts/ingest_pdf.py`. Table mode + line pattern mode, auto direction detection. Built 2026-04-19

### Target Data Volumes

| Collection | Current (est.) | Target Phase 4 |
|---|---|---|
| vocabulary | ~200 pairs | 1,000+ pairs |
| sentences | ~100 pairs | 500+ pairs |
| grammar | ~50 entries | 200+ entries |
| proverbs | ~50 entries | 150+ entries |

---

## Phase 5 — Admin Tools ⬜ NEXT

**Goal:** Give the developer visibility and control over the system without touching code.

### Tasks

- [ ] Stats page — show record counts per collection with last-updated timestamp
- [ ] Collection browser — list entries in each collection with search
- [ ] Correction review — view submitted corrections, approve or reject
- [ ] Ingestion trigger — button to run ingestor from the UI
- [ ] System health — show backend status, model load time, ChromaDB size

---

## Phase 6 — Evaluation ⬜ PLANNED

**Goal:** Measure how good the translation system actually is.

### Tasks

- [ ] Build a test set — 100 English → Luganda pairs with known correct answers
- [ ] Build an eval script — runs all test pairs, scores exact / partial / wrong
- [ ] Track accuracy over time — compare scores before and after data additions
- [ ] Flag systematic failures — which words / patterns always fail

---

## Phase 7 — Voice (Optional) ⬜ FUTURE

**Goal:** Add spoken Luganda input and output.

### Constraints

- Requires an audio model that fits in 4 GB VRAM or runs on CPU
- No suitable Luganda TTS model confirmed yet
- Whisper (OpenAI) can do speech-to-text but has no Luganda training

### Status

Deferred. Do not plan implementation until Phase 4 data targets are met.

---

## Next Tasks — Immediate Priority

These are the next three actions in order:

### Task 1 — Run Phase 1: Download and Ingest Datasets ✅ SCRIPTS READY

**What:** Run the download and ingestion scripts to go from 464 → 5,000+ translation pairs.

**How to run:**
```bash
python scripts/download_datasets.py --source flores
python scripts/download_datasets.py --source jw300
python scripts/ingest_dataset.py --dry-run
python scripts/ingest_dataset.py
```

**Status:** Scripts built and tested. Awaiting execution on local machine.

---

### Task 2 — NLLB-200 Neural Translation Fallback

**What:** Add `facebook/nllb-200-distilled-600M` as a fallback when the search pipeline returns not_found.

**Why:** After Phase 1 data scaling, this is the next biggest improvement. Any text not in the database can get an AI-generated translation instead of "not_found."

**Files affected:**
- `backend/services/translation/nllb_service.py` — NEW
- `backend/services/translation/service.py` — add neural fallback step
- `backend/api/routes/translate.py` — no changes (service handles it)

**Approval needed:** Yes — touches the translation pipeline.

---

### Task 3 — Teaching Mode Page

**What:** Create `frontend/teach.html` with a flashcard drill pulling from the vocabulary collection.

**Why:** Teaching mode is a core feature of the product and can be built with existing data.

**Files affected:**
- `frontend/teach.html` — NEW
- `backend/api/routes/teach.py` — NEW (cards endpoint)
- `backend/main.py` — add teach router

**Approval needed:** Yes — new backend route and new frontend page.

---

## Test Flow — How to Verify the System Is Working

Run these steps after any change to confirm nothing is broken.

### 1. Backend Health

```
GET http://127.0.0.1:8000/api/v1/health
Expected: { "status": "ok" }
```

### 2. Translation — Success Case

```
POST http://127.0.0.1:8000/api/v1/translate
Body: { "text": "hello", "direction": "en_to_lg" }
Expected: status = "success", translated_text is not null
```

### 3. Translation — Not Found Case

```
POST http://127.0.0.1:8000/api/v1/translate
Body: { "text": "xyzxyzxyz", "direction": "en_to_lg" }
Expected: status = "not_found", translated_text is null
```

### 4. Search — Results Returned

```
GET http://127.0.0.1:8000/api/v1/knowledge/search?q=water&top_k=5&collection=all
Expected: results array with at least 1 item, each has text + metadata + distance
```

### 5. Search — Empty Result

```
GET http://127.0.0.1:8000/api/v1/knowledge/search?q=xyzxyzxyz&top_k=5&collection=all
Expected: results = [], total_results = 0
```

### 6. Stats

```
GET http://127.0.0.1:8000/api/v1/knowledge/stats
Expected: collections dict with counts for vocabulary, sentences, grammar, proverbs
```

### 7. Frontend — Translate Page

```
Open: http://127.0.0.1:8000/app/translate.html
- Type "water" → click Translate
- Result should appear with confidence chip and match type
- Click ✓ Correct → button highlights green, "Saved to session" appears
- Scroll down → Session History shows the entry
- Click Export JSON → file downloads with entry inside
```

### 8. Frontend — Search Page

```
Open: http://127.0.0.1:8000/app/search.html
- Type "hello" → press Enter
- Results appear with Luganda text, English meaning, match % badge
- Click Vocabulary filter chip → results filter by collection
- Click Clear results → idle state returns
```

---

## Known Issues and Technical Debt

| Issue | Severity | Notes |
|---|---|---|
| ~~Session feedback lost on tab close~~ | ~~Medium~~ | ✅ Fixed — feedback.py saves to disk, translate.html sends to API |
| ~~No deduplication on ingestion~~ | ~~Medium~~ | ✅ Fixed — download_datasets.py deduplicates, indexer uses stable MD5 IDs |
| No test suite exists | Medium | Fix in Phase 6 |
| Frontend has no error boundary for JS crashes | Low | Handle gracefully in polish pass |
| ChromaDB `.get()` returns None if collection empty | Low | Already guarded in service.py |

---

## Decisions Log

| Date | Decision | Reason |
|---|---|---|
| Phase 1 | Use ChromaDB instead of Postgres | Simpler setup, works locally, good for vectors |
| Phase 1 | Use MiniLM for embeddings | Small model, runs on CPU, good enough for current data volume |
| Phase 1 | Frontend as static HTML | No build step, served directly by FastAPI, fastest to iterate |
| Phase 1 | Translation pipeline with 5 stages | Gives best result at each level before falling back |
| Phase 2 | Feedback stored in browser first | No backend complexity needed for MVP feedback loop |
| Phase 2 | Export as JSON not CSV | Richer structure, easier to re-ingest with metadata intact |
| Phase 2 | Feedback API saves to JSONL | Append-only format, safe for concurrent writes, easy to parse |
| Apr 17 | Three automation scripts for training plan | download_datasets.py, ingest_dataset.py, process_feedback.py |
| Apr 17 | Feedback corrections auto-ingest to ChromaDB | Instant improvement when users correct translations |
| Apr 17 | Training data accumulation for NLLB | corrections.jsonl + training_pairs.jsonl ready for Phase 3 fine-tuning |
