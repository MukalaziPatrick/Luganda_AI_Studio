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


# ── lexical_score() ───────────────────────────────────────────────────────────

def test_lexical_score_exact_match_returns_100():
    meta = {"luganda": "ssebo"}
    assert lexical_score("ssebo", meta) == SCORE_EXACT

def test_lexical_score_exact_match_case_insensitive():
    meta = {"luganda": "Ssebo"}
    assert lexical_score("ssebo", meta) == SCORE_EXACT

def test_lexical_score_normalized_match_returns_95():
    meta = {"luganda": "ssebo!"}
    assert lexical_score("ssebo", meta) == SCORE_NORMALIZED

def test_lexical_score_prefix_match_returns_85():
    meta = {"luganda": "ssebo wa"}
    assert lexical_score("ssebo", meta) == SCORE_PREFIX

def test_lexical_score_substring_match_returns_65():
    meta = {"english": "good morning friend"}
    assert lexical_score("morning", meta) == SCORE_SUBSTRING

def test_lexical_score_no_match_returns_none():
    meta = {"luganda": "enjovu", "english": "elephant"}
    assert lexical_score("water", meta) is None

def test_lexical_score_checks_all_metadata_fields():
    meta = {"luganda": "enjovu", "english": "elephant"}
    assert lexical_score("elephant", meta) == SCORE_EXACT

def test_lexical_score_empty_metadata_returns_none():
    assert lexical_score("hello", {}) is None
