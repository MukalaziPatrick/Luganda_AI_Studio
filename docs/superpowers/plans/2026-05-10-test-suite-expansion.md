# Test Suite Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ~18 new tests covering search service logic (unit) and knowledge HTTP routes (integration), bringing total from 14 to ~32 passing tests.

**Architecture:** Two new test files — `tests/test_search_service.py` for pure unit tests of `normalize()`, `lexical_score()`, `chroma_distance_to_score()`, `score_label()`; and `tests/test_knowledge_routes.py` for integration tests of `GET /api/v1/knowledge/search` and `GET /api/v1/knowledge/status` using the existing `TestClient` fixture against real local ChromaDB.

**Tech Stack:** pytest, FastAPI TestClient, real ChromaDB (no mocking)

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `tests/test_search_service.py` | Unit tests for pure search logic functions |
| Create | `tests/test_knowledge_routes.py` | Integration tests for knowledge HTTP routes |
| Read-only | `backend/services/search_service.py` | Source of functions under test |
| Read-only | `backend/api/routes/knowledge.py` | Source of routes under test |
| Read-only | `tests/conftest.py` | Provides the `client` fixture |

---

## Task 1: Unit tests for `normalize()`

**Files:**
- Create: `tests/test_search_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_search_service.py` with:

```python
# tests/test_search_service.py

from backend.services.search_service import (
    normalize,
    lexical_score,
    chroma_distance_to_score,
    score_label,
    SCORE_EXACT,
    SCORE_NORMALIZED,
    SCORE_PREFIX,
    SCORE_SUBSTRING,
    SCORE_SEMANTIC_MAX,
    MIN_SCORE,
)


# ── normalize() ───────────────────────────────────────────────────────────────

def test_normalize_empty_string():
    assert normalize("") == ""

def test_normalize_strips_punctuation():
    assert normalize("Ssebo!") == "ssebo"

def test_normalize_lowercases():
    assert normalize("Good Morning") == "good morning"

def test_normalize_collapses_whitespace():
    assert normalize("  good  morning  ") == "good morning"

def test_normalize_removes_trailing_whitespace():
    assert normalize("hello ") == "hello"

def test_normalize_handles_period():
    assert normalize("Good morning.") == "good morning"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_search_service.py -v
```

Expected: `ERROR` — import fails because file doesn't exist yet (or FAILED if file exists but imports are wrong). Confirm the error is an import error, not a logic error.

- [ ] **Step 3: Verify imports resolve (no implementation needed — functions already exist)**

The functions are already implemented in `backend/services/search_service.py`. Run again:

```bash
pytest tests/test_search_service.py::test_normalize_empty_string -v
```

Expected: `PASSED`

- [ ] **Step 4: Run all normalize tests**

```bash
pytest tests/test_search_service.py -v
```

Expected: All 6 normalize tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_search_service.py
git commit -m "test: add normalize() unit tests"
```

---

## Task 2: Unit tests for `lexical_score()`

**Files:**
- Modify: `tests/test_search_service.py`

- [ ] **Step 1: Append these tests to `tests/test_search_service.py`**

```python
# ── lexical_score() ───────────────────────────────────────────────────────────

def test_lexical_score_exact_match_returns_100():
    meta = {"luganda": "ssebo"}
    assert lexical_score("ssebo", meta) == SCORE_EXACT

def test_lexical_score_exact_match_case_insensitive():
    meta = {"luganda": "Ssebo"}
    assert lexical_score("ssebo", meta) == SCORE_EXACT

def test_lexical_score_normalized_match_returns_95():
    # Punctuation differs but normalized form matches
    meta = {"luganda": "ssebo!"}
    assert lexical_score("ssebo", meta) == SCORE_NORMALIZED

def test_lexical_score_prefix_match_returns_85():
    # Field starts with query
    meta = {"luganda": "ssebo wa"}
    assert lexical_score("ssebo", meta) == SCORE_PREFIX

def test_lexical_score_substring_match_returns_65():
    # Query appears inside field
    meta = {"english": "good morning friend"}
    assert lexical_score("morning", meta) == SCORE_SUBSTRING

def test_lexical_score_no_match_returns_none():
    meta = {"luganda": "enjovu", "english": "elephant"}
    assert lexical_score("water", meta) is None

def test_lexical_score_checks_all_metadata_fields():
    # Should find match in 'english' even when 'luganda' doesn't match
    meta = {"luganda": "enjovu", "english": "elephant"}
    assert lexical_score("elephant", meta) == SCORE_EXACT

def test_lexical_score_empty_metadata_returns_none():
    assert lexical_score("hello", {}) is None
```

- [ ] **Step 2: Run to verify**

```bash
pytest tests/test_search_service.py -k "lexical_score" -v
```

Expected: All 8 `PASSED`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_search_service.py
git commit -m "test: add lexical_score() unit tests"
```

---

## Task 3: Unit tests for `chroma_distance_to_score()` and `score_label()`

**Files:**
- Modify: `tests/test_search_service.py`

- [ ] **Step 1: Append these tests to `tests/test_search_service.py`**

```python
# ── chroma_distance_to_score() ────────────────────────────────────────────────

def test_distance_zero_capped_at_semantic_max():
    # distance=0.0 → raw 100, capped at SCORE_SEMANTIC_MAX (60)
    assert chroma_distance_to_score(0.0) == SCORE_SEMANTIC_MAX

def test_distance_half_capped_at_semantic_max():
    # distance=0.5 → raw 75, capped at 60
    assert chroma_distance_to_score(0.5) == SCORE_SEMANTIC_MAX

def test_distance_one_returns_50():
    # distance=1.0 → raw 50, below cap → 50
    assert chroma_distance_to_score(1.0) == 50

def test_distance_1point6_returns_20():
    # distance=1.6 → raw 20, below MIN_SCORE but score function just returns it
    assert chroma_distance_to_score(1.6) == 20

def test_distance_two_returns_zero():
    # distance=2.0 → raw 0
    assert chroma_distance_to_score(2.0) == 0

def test_distance_below_min_score_is_not_filtered_by_function():
    # Filtering is the caller's responsibility; this function just converts
    score = chroma_distance_to_score(1.6)
    assert score < MIN_SCORE  # confirms caller must filter


# ── score_label() ─────────────────────────────────────────────────────────────

def test_score_label_100_is_exact():
    assert score_label(100) == "Exact match"

def test_score_label_95_is_exact():
    assert score_label(95) == "Exact match"

def test_score_label_85_is_strong():
    assert score_label(85) == "Strong match"

def test_score_label_60_is_good():
    assert score_label(60) == "Good match"

def test_score_label_40_is_related():
    assert score_label(40) == "Related"

def test_score_label_25_is_weak():
    assert score_label(25) == "Weak match"
```

- [ ] **Step 2: Run to verify**

```bash
pytest tests/test_search_service.py -k "distance or score_label" -v
```

Expected: All 12 `PASSED`.

- [ ] **Step 3: Run full service test file**

```bash
pytest tests/test_search_service.py -v
```

Expected: All tests in file `PASSED` (should be 26 total across Tasks 1–3).

- [ ] **Step 4: Commit**

```bash
git add tests/test_search_service.py
git commit -m "test: add chroma_distance_to_score() and score_label() unit tests"
```

---

## Task 4: Integration tests for `GET /api/v1/knowledge/search`

**Files:**
- Create: `tests/test_knowledge_routes.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_knowledge_routes.py`:

```python
# tests/test_knowledge_routes.py

import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ── GET /api/v1/knowledge/search ──────────────────────────────────────────────

def test_search_valid_query_returns_200(client):
    response = client.get("/api/v1/knowledge/search", params={"q": "hello"})
    assert response.status_code == 200

def test_search_response_has_required_keys(client):
    response = client.get("/api/v1/knowledge/search", params={"q": "hello"})
    data = response.json()
    assert "query" in data
    assert "collection" in data
    assert "total" in data
    assert "results" in data

def test_search_query_echoed_in_response(client):
    response = client.get("/api/v1/knowledge/search", params={"q": "ssebo"})
    data = response.json()
    assert data["query"] == "ssebo"

def test_search_empty_query_returns_400(client):
    response = client.get("/api/v1/knowledge/search", params={"q": ""})
    assert response.status_code in (400, 422)

def test_search_query_too_long_returns_422(client):
    long_query = "a" * 201
    response = client.get("/api/v1/knowledge/search", params={"q": long_query})
    assert response.status_code == 422

def test_search_top_k_limits_results(client):
    response = client.get("/api/v1/knowledge/search", params={"q": "hello", "top_k": 3})
    data = response.json()
    assert len(data["results"]) <= 3

def test_search_collection_filter_vocabulary(client):
    response = client.get(
        "/api/v1/knowledge/search",
        params={"q": "hello", "collection": "vocabulary"},
    )
    data = response.json()
    assert response.status_code == 200
    for result in data["results"]:
        assert result["metadata"].get("_collection") == "vocabulary"

def test_search_invalid_collection_returns_200_empty(client):
    response = client.get(
        "/api/v1/knowledge/search",
        params={"q": "hello", "collection": "nonexistent_collection"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["results"] == []
```

- [ ] **Step 2: Run to verify**

```bash
pytest tests/test_knowledge_routes.py -v
```

Expected: All 8 search tests `PASSED`. (ChromaDB must be running locally with data.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_knowledge_routes.py
git commit -m "test: add knowledge search route integration tests"
```

---

## Task 5: Integration tests for `GET /api/v1/knowledge/status`

**Files:**
- Modify: `tests/test_knowledge_routes.py`

- [ ] **Step 1: Append these tests to `tests/test_knowledge_routes.py`**

```python
# ── GET /api/v1/knowledge/status ──────────────────────────────────────────────

def test_status_returns_200(client):
    response = client.get("/api/v1/knowledge/status")
    assert response.status_code == 200

def test_status_has_required_keys(client):
    response = client.get("/api/v1/knowledge/status")
    data = response.json()
    assert "collections" in data
    assert "total_documents" in data

def test_status_contains_all_core_collections(client):
    response = client.get("/api/v1/knowledge/status")
    data = response.json()
    collections = data["collections"]
    for name in ("vocabulary", "sentences", "grammar", "proverbs"):
        assert name in collections, f"Missing collection: {name}"

def test_status_counts_are_non_negative_integers(client):
    response = client.get("/api/v1/knowledge/status")
    data = response.json()
    for name, count in data["collections"].items():
        assert isinstance(count, int), f"{name} count is not an int"
        assert count >= 0, f"{name} count is negative"

def test_status_total_documents_matches_sum(client):
    response = client.get("/api/v1/knowledge/status")
    data = response.json()
    expected_total = sum(v for v in data["collections"].values() if v >= 0)
    assert data["total_documents"] == expected_total
```

- [ ] **Step 2: Run all knowledge route tests**

```bash
pytest tests/test_knowledge_routes.py -v
```

Expected: All 13 tests `PASSED`.

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```bash
pytest tests/ -v
```

Expected: All tests pass. Count should be 14 (existing) + 26 (service) + 13 (routes) = ~32+ `PASSED` (exact count depends on Tasks 1–3).

- [ ] **Step 4: Commit**

```bash
git add tests/test_knowledge_routes.py
git commit -m "test: add knowledge status route integration tests"
```

---

## Done

All tasks complete when `pytest tests/ -v` shows 32+ passing tests with 0 failures.
