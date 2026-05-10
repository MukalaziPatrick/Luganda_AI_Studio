# Test Suite Expansion — Design Spec
**Date:** 2026-05-10
**Scope:** Search service unit tests + knowledge route integration tests

---

## Goal

Expand the existing 14-test suite to cover the two recently modified files:
- `backend/services/search_service.py` — layered matching logic
- `backend/api/routes/knowledge.py` — search and status HTTP routes

## Approach

Two new test files following the existing pattern:
- Unit tests for pure logic (no DB)
- Integration tests for HTTP routes (real ChromaDB via TestClient)

---

## File 1: `tests/test_search_service.py`

Pure unit tests. No ChromaDB, no network. Runs in milliseconds.

### `normalize()`
- Empty string → returns `""`
- Punctuation stripped: `"Ssebo!"` → `"ssebo"`
- Whitespace collapsed: `"  good  morning  "` → `"good morning"`
- Lowercased

### `lexical_score()`
- Exact match (case-insensitive) → 100
- Normalized match (punctuation differs) → 95
- Prefix match (field starts with query) → 85
- Substring match (query inside field) → 65
- No match → `None`

### `chroma_distance_to_score()`
- Distance `0.0` → capped at 60 (SCORE_SEMANTIC_MAX)
- Distance `0.5` → capped at 60
- Distance `1.0` → 50
- Distance `1.6` → 20 (below MIN_SCORE=25, caller responsible for filtering)
- Distance `2.0` → 0

### `score_label()`
- Score 100 → `"Exact match"`
- Score 85 → `"Strong match"`
- Score 60 → `"Good match"`
- Score 40 → `"Related"`
- Score 25 → `"Weak match"`

---

## File 2: `tests/test_knowledge_routes.py`

Integration tests using FastAPI `TestClient` + real local ChromaDB.
Uses the existing `client` fixture from `conftest.py`.

### Search route — `GET /api/v1/knowledge/search`

| Test | Expected |
|---|---|
| Valid query `?q=hello` | 200, keys: `query`, `collection`, `total`, `results` |
| Empty query `?q=` | 400 |
| Query >200 chars | 422 |
| `top_k=3` | `len(results) <= 3` |
| `collection=vocabulary` | All results have `metadata._collection == "vocabulary"` |
| `collection=invalid_name` | 200, `total == 0`, `results == []` |

### Status route — `GET /api/v1/knowledge/status`

| Test | Expected |
|---|---|
| Route returns 200 | Response OK |
| Response has required keys | `collections` and `total_documents` present |
| All 4 collections present | `vocabulary`, `sentences`, `grammar`, `proverbs` in `collections` |
| All counts are integers ≥ 0 | No negative or missing values |

---

## What Is Not Covered

- Translation pipeline degradation tests (out of scope for this expansion)
- `documents` (PDF) collection — excluded; only populated by manual ingestion script
- Performance / load testing

---

## Success Criteria

- All new tests pass with `pytest tests/ -v`
- No mocking of ChromaDB — integration tests use the real local instance
- New test count: 14 existing + ~18 new = ~32 total
