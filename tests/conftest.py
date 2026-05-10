import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_openrouter_state():
    """Reset openrouter_service module state between tests."""
    from backend.services.translation import openrouter_service
    yield
    openrouter_service._last_call_at = None
