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
