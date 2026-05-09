# backend/services/translation/openrouter_service.py

"""
OpenRouter neural translation — Pass 4.5 in the translation pipeline.

Used between semantic search and NLLB-200.
Skipped entirely if OPENROUTER_API_KEY is not set.

On any failure (timeout, HTTP error, bad response, spend limit):
  returns None → pipeline falls through to NLLB-200.

Confidence returned: 0.75
Match type: "neural_api"
"""

import logging
from typing import Optional

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_LANG_NAMES = {
    "en_to_lg": ("English", "Luganda"),
    "lg_to_en": ("Luganda", "English"),
}

# In-memory daily spend counter. Resets on server restart.
# Sufficient for personal/small-team use.
_daily_spend_usd: float = 0.0


class OpenRouterTranslator:
    """Thin wrapper around the OpenRouter chat completions API."""

    def is_enabled(self) -> bool:
        return bool(settings.openrouter_api_key)

    def translate(self, text: str, direction: str) -> Optional[str]:
        """
        Translate `text` using OpenRouter.
        Returns the translated string, or None if unavailable/failed.
        """
        global _daily_spend_usd

        if not self.is_enabled():
            return None

        if _daily_spend_usd >= settings.openrouter_daily_limit_usd:
            logger.warning(
                f"[OpenRouter] Daily spend limit "
                f"${settings.openrouter_daily_limit_usd:.2f} reached. "
                f"Skipping — falling back to NLLB-200."
            )
            return None

        source_lang, target_lang = _LANG_NAMES.get(direction, ("English", "Luganda"))

        payload = {
            "model": settings.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Luganda-English translator. "
                        "Return only the translated text. "
                        "No explanation, no punctuation changes, no added context."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Translate the following from {source_lang} to {target_lang}: {text}"
                    ),
                },
            ],
        }

        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=settings.openrouter_timeout_seconds) as client:
                response = client.post(_OPENROUTER_URL, json=payload, headers=headers)

            if response.status_code != 200:
                logger.warning(
                    f"[OpenRouter] HTTP {response.status_code} — "
                    f"falling back to NLLB-200."
                )
                return None

            data = response.json()

            # Track spend if the API reports it
            usage = data.get("usage", {})
            cost = usage.get("cost", 0.0)
            if cost:
                _daily_spend_usd += cost

            translated = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )

            if not translated:
                logger.warning("[OpenRouter] Empty response — falling back to NLLB-200.")
                return None

            logger.info(f"[OpenRouter] '{text}' → '{translated}'")
            return translated

        except httpx.TimeoutException:
            logger.warning(
                f"[OpenRouter] Timeout after {settings.openrouter_timeout_seconds}s "
                f"— falling back to NLLB-200."
            )
            return None
        except Exception as e:
            logger.warning(f"[OpenRouter] Error: {e} — falling back to NLLB-200.")
            return None


openrouter_translator = OpenRouterTranslator()
