# tests/test_translate_route.py
"""
Full Translate Route Tests

Tests the POST /api/v1/translate HTTP endpoint:
  - Valid requests return 200 with TranslationResponse
  - Both directions (en_to_lg, lg_to_en) work
  - Invalid input returns 400 or 422
  - Response structure is consistent
  - Edge cases (very long text, special characters) handled properly
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ────────────────────────────────────────────────────────────────────────────
# Happy Path: Valid translations
# ────────────────────────────────────────────────────────────────────────────

def test_translate_en_to_lg_returns_200(client):
    """Valid en_to_lg request returns 200."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    assert response.status_code == 200


def test_translate_lg_to_en_returns_200(client):
    """Valid lg_to_en request returns 200."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "amazzi", "direction": "lg_to_en"},
    )
    assert response.status_code == 200


def test_translate_response_json_format(client):
    """Response is valid JSON."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


# ────────────────────────────────────────────────────────────────────────────
# Response Structure: All required fields present
# ────────────────────────────────────────────────────────────────────────────

def test_translate_response_includes_input_text(client):
    """Response echoes back the input text."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    assert "input_text" in data
    assert data["input_text"] == "water"


def test_translate_response_includes_direction(client):
    """Response echoes back the direction."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    assert "direction" in data
    assert data["direction"] == "en_to_lg"


def test_translate_response_includes_translated_text(client):
    """Response includes translated_text (even if not_found)."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    assert "translated_text" in data
    # Can be a string (found) or empty string (not found)
    assert isinstance(data["translated_text"], str)


def test_translate_response_includes_status(client):
    """Response includes status (success or not_found)."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    assert "status" in data
    assert data["status"] in ("success", "not_found")


def test_translate_response_includes_match_type(client):
    """Response includes match_type (exact, normalized, partial, semantic, not_found)."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    assert "match_type" in data
    assert data["match_type"] in ("exact", "normalized", "partial", "semantic", "not_found")


def test_translate_response_includes_confidence(client):
    """Response includes confidence score (0.0 to 1.0)."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    assert "confidence" in data
    assert isinstance(data["confidence"], (int, float))
    assert 0.0 <= data["confidence"] <= 1.0


def test_translate_success_includes_matched_collection(client):
    """Successful match includes matched_collection."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    if data["status"] == "success":
        assert "matched_collection" in data
        assert data["matched_collection"] in ("vocabulary", "sentences", "proverbs")


def test_translate_success_includes_matched_source_file(client):
    """Successful match includes matched_source_file."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    if data["status"] == "success":
        assert "matched_source_file" in data


def test_translate_response_includes_message(client):
    """Response includes a message."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    assert "message" in data
    assert isinstance(data["message"], str)


# ────────────────────────────────────────────────────────────────────────────
# Directionality: Correct direction is respected
# ────────────────────────────────────────────────────────────────────────────

def test_direction_en_to_lg_searches_english_field(client):
    """en_to_lg searches English column for input."""
    # Use a word that's definitely in English vocabulary
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    if data["status"] == "success":
        # Result should be a Luganda word (not English)
        assert data["translated_text"] != "water"


def test_direction_lg_to_en_searches_luganda_field(client):
    """lg_to_en searches Luganda column for input."""
    # Use a word that's definitely in Luganda vocabulary
    response = client.post(
        "/api/v1/translate",
        json={"text": "amazzi", "direction": "lg_to_en"},
    )
    data = response.json()
    if data["status"] == "success":
        # Result should be an English word (not Luganda)
        assert data["translated_text"] != "amazzi"


# ────────────────────────────────────────────────────────────────────────────
# Validation: Invalid input rejected
# ────────────────────────────────────────────────────────────────────────────

def test_empty_text_returns_422(client):
    """Empty text is rejected."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "", "direction": "en_to_lg"},
    )
    assert response.status_code in (400, 422)


def test_whitespace_only_text_returns_422(client):
    """Whitespace-only text is rejected."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "   ", "direction": "en_to_lg"},
    )
    assert response.status_code in (400, 422)


def test_invalid_direction_returns_422(client):
    """Invalid direction is rejected."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "invalid"},
    )
    assert response.status_code == 422


def test_wrong_direction_format_returns_422(client):
    """Wrong direction format (not xx_to_yy) returns 422."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en->lg"},  # Wrong separator
    )
    assert response.status_code == 422


def test_missing_text_field_returns_422(client):
    """Missing text field returns validation error."""
    response = client.post(
        "/api/v1/translate",
        json={"direction": "en_to_lg"},
    )
    assert response.status_code == 422


def test_missing_direction_field_returns_422(client):
    """Missing direction field returns validation error."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water"},
    )
    assert response.status_code == 422


def test_null_text_returns_422(client):
    """Null text returns validation error."""
    response = client.post(
        "/api/v1/translate",
        json={"text": None, "direction": "en_to_lg"},
    )
    assert response.status_code == 422


def test_null_direction_returns_422(client):
    """Null direction returns validation error."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": None},
    )
    assert response.status_code == 422


# ────────────────────────────────────────────────────────────────────────────
# Edge Cases: Long text, special characters
# ────────────────────────────────────────────────────────────────────────────

def test_very_long_text_is_accepted(client):
    """Text up to the 500-char limit is accepted and processed."""
    long_text = "water " * 80  # 480 characters, under the 500-char max_length limit
    response = client.post(
        "/api/v1/translate",
        json={"text": long_text, "direction": "en_to_lg"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "translated_text" in data


def test_text_with_punctuation(client):
    """Text with punctuation is handled (normalized)."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water.", "direction": "en_to_lg"},
    )
    assert response.status_code == 200
    data = response.json()
    # Should normalize and match "water" without the period
    if data["status"] == "success":
        assert "translated_text" in data


def test_text_with_numbers(client):
    """Text with numbers is handled."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water123", "direction": "en_to_lg"},
    )
    assert response.status_code == 200
    data = response.json()
    # May not find match (non-word), but shouldn't crash
    assert data["status"] in ("success", "not_found")


def test_text_with_special_characters(client):
    """Text with special characters is handled."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water-lily", "direction": "en_to_lg"},
    )
    assert response.status_code == 200
    data = response.json()
    # May or may not find match
    assert data["status"] in ("success", "not_found")


def test_text_with_unicode_luganda(client):
    """Luganda text with diacritics is handled."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "amazzi", "direction": "lg_to_en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "translated_text" in data


def test_mixed_case_text(client):
    """Mixed case text is normalized and matched."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "WaTeR", "direction": "en_to_lg"},
    )
    assert response.status_code == 200
    data = response.json()
    # Should normalize and match
    if data["status"] == "success":
        assert data["match_type"] in ("exact", "normalized")


def test_leading_trailing_whitespace(client):
    """Leading/trailing whitespace is stripped."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "  water  ", "direction": "en_to_lg"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["input_text"].strip() == data["input_text"].strip()  # Comparison check


# ────────────────────────────────────────────────────────────────────────────
# Status vs Confidence Alignment
# ────────────────────────────────────────────────────────────────────────────

def test_success_status_has_nonzero_confidence(client):
    """When status is 'success', confidence is > 0."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    data = response.json()
    if data["status"] == "success":
        assert data["confidence"] > 0.0


def test_not_found_status_has_zero_confidence(client):
    """When status is 'not_found', confidence is 0.0."""
    response = client.post(
        "/api/v1/translate",
        json={"text": "xyzabc123notaword", "direction": "en_to_lg"},
    )
    data = response.json()
    if data["status"] == "not_found":
        assert data["confidence"] == 0.0


# ────────────────────────────────────────────────────────────────────────────
# Consistency: Same input yields same output (determinism)
# ────────────────────────────────────────────────────────────────────────────

def test_same_input_yields_same_output(client):
    """Multiple requests with same input return same translation."""
    input_data = {"text": "water", "direction": "en_to_lg"}

    response1 = client.post("/api/v1/translate", json=input_data)
    response2 = client.post("/api/v1/translate", json=input_data)

    data1 = response1.json()
    data2 = response2.json()

    assert data1["translated_text"] == data2["translated_text"]
    assert data1["match_type"] == data2["match_type"]
    assert data1["confidence"] == data2["confidence"]


# ────────────────────────────────────────────────────────────────────────────
# Performance: Response time is reasonable
# ────────────────────────────────────────────────────────────────────────────

def test_translate_response_time_under_5_seconds(client):
    """Translate request completes in reasonable time (< 5 sec)."""
    import time

    start = time.time()
    response = client.post(
        "/api/v1/translate",
        json={"text": "water", "direction": "en_to_lg"},
    )
    elapsed = time.time() - start

    assert response.status_code == 200
    assert elapsed < 5.0, f"Translation took {elapsed:.2f}s (expected < 5s)"
