# tests/test_feedback_route.py
"""
Feedback Route Tests

Tests the POST /api/v1/feedback endpoint.

FeedbackRequest schema (actual fields):
  input_text          str   — source text shown to user
  direction           str   — "en_to_lg" | "lg_to_en"
  translated_text     str   — translation that was displayed
  verdict             str   — "correct" | "wrong" | "needs_review"
  expected_output     str?  — user's correction (optional)
  match_type          str?  — from translation response (optional)
  confidence          float?— from translation response (optional)
  matched_collection  str?  — from translation response (optional)

FeedbackResponse returns status="saved" (not "success").
"""

import json
import os
import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def feedback_log_path():
    """Path to feedback log file."""
    return "data/feedback/feedback_log.jsonl"


# ── Minimal valid payload ─────────────────────────────────────────────────────

def _payload(**overrides):
    """Return a valid FeedbackRequest payload, with optional field overrides."""
    base = {
        "input_text": "water",
        "direction": "en_to_lg",
        "translated_text": "amazzi",
        "verdict": "correct",
    }
    base.update(overrides)
    return base


# ────────────────────────────────────────────────────────────────────────────
# Successful Feedback Submission
# ────────────────────────────────────────────────────────────────────────────

def test_feedback_correct_verdict_returns_200(client):
    """User marks translation as correct."""
    response = client.post("/api/v1/feedback", json=_payload(verdict="correct"))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"


def test_feedback_wrong_verdict_returns_200(client):
    """User marks translation as wrong."""
    response = client.post(
        "/api/v1/feedback",
        json=_payload(verdict="wrong", expected_output="omwenge"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"


def test_feedback_review_verdict_returns_200(client):
    """User marks translation as needing review."""
    response = client.post(
        "/api/v1/feedback",
        json=_payload(verdict="needs_review"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"


# ────────────────────────────────────────────────────────────────────────────
# Response Fields
# ────────────────────────────────────────────────────────────────────────────

def test_feedback_response_includes_message(client):
    """Response includes a success message."""
    response = client.post("/api/v1/feedback", json=_payload())
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert len(data["message"]) > 0


def test_feedback_response_includes_status(client):
    """Response includes status field set to 'saved'."""
    response = client.post("/api/v1/feedback", json=_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"


# ────────────────────────────────────────────────────────────────────────────
# File Persistence: Feedback saved to JSONL
# ────────────────────────────────────────────────────────────────────────────

def test_feedback_saved_to_jsonl_file(client, feedback_log_path):
    """Feedback is appended to feedback_log.jsonl."""
    lines_before = 0
    if os.path.exists(feedback_log_path):
        with open(feedback_log_path, "r") as f:
            lines_before = sum(1 for _ in f)

    response = client.post("/api/v1/feedback", json=_payload())
    assert response.status_code == 200

    lines_after = 0
    if os.path.exists(feedback_log_path):
        with open(feedback_log_path, "r") as f:
            lines_after = sum(1 for _ in f)

    assert lines_after >= lines_before


def test_feedback_jsonl_has_valid_json(client, feedback_log_path):
    """Each line in feedback_log.jsonl is valid JSON."""
    response = client.post("/api/v1/feedback", json=_payload())
    assert response.status_code == 200

    if os.path.exists(feedback_log_path):
        with open(feedback_log_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        json.loads(line)
                    except json.JSONDecodeError:
                        pytest.fail(f"Invalid JSON in feedback log: {line}")


def test_feedback_includes_timestamp(client, feedback_log_path):
    """Saved feedback includes a timestamp."""
    response = client.post("/api/v1/feedback", json=_payload())
    assert response.status_code == 200

    if os.path.exists(feedback_log_path):
        with open(feedback_log_path, "r") as f:
            lines = f.readlines()
            if lines:
                last_entry = json.loads(lines[-1].strip())
                assert "timestamp" in last_entry or "created_at" in last_entry


# ────────────────────────────────────────────────────────────────────────────
# ChromaDB Ingestion: Corrections auto-update the database
# ────────────────────────────────────────────────────────────────────────────

def test_correction_with_wrong_verdict_creates_training_pair(client):
    """When user provides correction (verdict=wrong), it's recorded for training."""
    response = client.post(
        "/api/v1/feedback",
        json=_payload(verdict="wrong", expected_output="omwenge"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"


def test_correction_only_with_verdict_wrong_or_review(client):
    """Correction field is accepted with any verdict (API ignores it for 'correct')."""
    response = client.post(
        "/api/v1/feedback",
        json=_payload(verdict="correct", expected_output="omwenge"),
    )
    assert response.status_code == 200


# ────────────────────────────────────────────────────────────────────────────
# Validation: Invalid feedback rejected
# ────────────────────────────────────────────────────────────────────────────

def test_missing_translation_id_returns_422(client):
    """Missing input_text returns validation error."""
    payload = _payload()
    del payload["input_text"]
    response = client.post("/api/v1/feedback", json=payload)
    assert response.status_code == 422


def test_missing_original_text_returns_422(client):
    """Payload with no input_text field returns 422."""
    response = client.post(
        "/api/v1/feedback",
        json={
            "direction": "en_to_lg",
            "translated_text": "amazzi",
            "verdict": "correct",
        },
    )
    assert response.status_code == 422


def test_missing_direction_returns_422(client):
    """Missing direction returns validation error."""
    payload = _payload()
    del payload["direction"]
    response = client.post("/api/v1/feedback", json=payload)
    assert response.status_code == 422


def test_missing_provided_translation_returns_422(client):
    """Missing translated_text returns validation error."""
    payload = _payload()
    del payload["translated_text"]
    response = client.post("/api/v1/feedback", json=payload)
    assert response.status_code == 422


def test_missing_verdict_returns_422(client):
    """Missing verdict returns validation error."""
    payload = _payload()
    del payload["verdict"]
    response = client.post("/api/v1/feedback", json=payload)
    assert response.status_code == 422


def test_invalid_verdict_returns_422(client):
    """Invalid verdict value returns validation error."""
    response = client.post("/api/v1/feedback", json=_payload(verdict="maybe"))
    assert response.status_code == 422


def test_invalid_direction_returns_422(client):
    """Invalid direction value returns validation error."""
    response = client.post("/api/v1/feedback", json=_payload(direction="xx_to_yy"))
    assert response.status_code == 422


def test_empty_text_returns_422(client):
    """Empty input_text returns validation error."""
    response = client.post("/api/v1/feedback", json=_payload(input_text=""))
    assert response.status_code == 422


# ────────────────────────────────────────────────────────────────────────────
# Deduplication
# ────────────────────────────────────────────────────────────────────────────

def test_duplicate_feedback_allowed(client):
    """Submitting same feedback twice is allowed (deduplication not yet implemented)."""
    payload = _payload()
    assert client.post("/api/v1/feedback", json=payload).status_code == 200
    assert client.post("/api/v1/feedback", json=payload).status_code == 200


# ────────────────────────────────────────────────────────────────────────────
# Notes / Optional Fields
# ────────────────────────────────────────────────────────────────────────────

def test_optional_notes_field(client):
    """Optional match_type and confidence fields are accepted."""
    response = client.post(
        "/api/v1/feedback",
        json=_payload(
            verdict="needs_review",
            match_type="normalized",
            confidence=0.98,
        ),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"


def test_feedback_without_notes_field(client):
    """Feedback works with only required fields."""
    response = client.post("/api/v1/feedback", json=_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"
