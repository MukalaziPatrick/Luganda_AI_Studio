"""
Test suite for OpenRouter last_call_at timestamp tracking.

Verifies that the openrouter_service module correctly tracks
when the last successful OpenRouter translation call was made.
"""

from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from backend.services.translation import openrouter_service as svc


def test_last_call_at_starts_as_none():
    """_last_call_at should be None until a successful translation occurs."""
    # Reset state for isolation
    svc._last_call_at = None
    assert svc.get_last_call_at() is None


def test_get_last_call_at_returns_string_after_set():
    """get_last_call_at() should return the ISO 8601 timestamp when set."""
    svc._last_call_at = "2026-05-10T12:00:00+00:00"
    assert svc.get_last_call_at() == "2026-05-10T12:00:00+00:00"
    svc._last_call_at = None  # clean up


def test_translate_updates_last_call_at_on_success():
    """
    translate() should set _last_call_at to an ISO 8601 timestamp
    when the OpenRouter API call succeeds.

    This test mocks httpx.Client to simulate a successful response,
    verifying that the global _last_call_at is actually updated
    during a real translate() call (not just set directly).
    """
    # Reset state
    svc._last_call_at = None

    # Mock the httpx.Client.post() method to return a successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "usage": {"cost": 0.0001},
        "choices": [
            {
                "message": {
                    "content": "Oli otya"
                }
            }
        ]
    }

    with patch("backend.services.translation.openrouter_service.httpx.Client") as mock_client_class:
        # Mock the context manager (__enter__ and __exit__)
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        # Mock settings to enable OpenRouter
        with patch("backend.services.translation.openrouter_service.settings") as mock_settings:
            mock_settings.openrouter_api_key = "test-key"
            mock_settings.openrouter_daily_limit_usd = 10.0
            mock_settings.openrouter_model = "gemma-2-9b-it:free"
            mock_settings.openrouter_timeout_seconds = 30

            # Call translate() — should update _last_call_at
            result = svc.openrouter_translator.translate("hello", "en_to_lg")

            # Verify the translation was returned
            assert result == "Oli otya", f"Expected 'Oli otya', got '{result}'"

            # Verify _last_call_at was updated to an ISO 8601 timestamp
            timestamp = svc.get_last_call_at()
            assert timestamp is not None, "_last_call_at should be set after successful translation"
            assert isinstance(timestamp, str), "_last_call_at should be a string"

            # Verify it's a valid ISO 8601 format (contains T and +)
            assert "T" in timestamp, f"Expected ISO 8601 format, got {timestamp}"

            # Clean up
            svc._last_call_at = None


def test_translate_does_not_update_last_call_at_on_failure():
    """
    translate() should NOT update _last_call_at if the API call fails.
    """
    # Reset state
    svc._last_call_at = None

    # Mock the httpx.Client.post() method to return a 500 error
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("backend.services.translation.openrouter_service.httpx.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client_instance

        with patch("backend.services.translation.openrouter_service.settings") as mock_settings:
            mock_settings.openrouter_api_key = "test-key"
            mock_settings.openrouter_daily_limit_usd = 10.0
            mock_settings.openrouter_model = "gemma-2-9b-it:free"
            mock_settings.openrouter_timeout_seconds = 30

            # Call translate() — should return None and not update _last_call_at
            result = svc.openrouter_translator.translate("hello", "en_to_lg")

            # Verify None was returned
            assert result is None, "Expected None on API error"

            # Verify _last_call_at was NOT updated
            assert svc.get_last_call_at() is None, "_last_call_at should remain None on failure"
