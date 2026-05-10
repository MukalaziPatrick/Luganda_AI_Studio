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
    for name in ("vocabulary", "sentences", "grammar", "proverbs", "total"):
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
    for key in ("nllb_loaded", "openrouter_last_call_at"):
        assert key in pl
