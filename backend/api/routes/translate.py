# backend/api/routes/translate.py

"""
Translation route.

POST /api/v1/translate

This version adds proper exception logging so that if service.py
ever crashes again, the real error prints to the server console
before the 500 is returned to the client.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.services.translation.schemas import (
    TranslationRequest,
    TranslationResponse,
)
from backend.services.translation.service import translate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/",          # CHANGED: was "/translate" → doubled to /api/v1/translate/translate
    response_model=TranslationResponse,
    summary="Translate between English and Luganda",
    description=(
        "Submit a text and a direction (en_to_lg or lg_to_en). "
        "The system searches the Luganda dataset and returns the best match. "
        "If nothing is found, a clear not_found response is returned."
    ),
)
def translate_text(request: TranslationRequest) -> TranslationResponse:
    """
    Translate a word or sentence.

    - direction 'en_to_lg': English to Luganda
    - direction 'lg_to_en': Luganda to English
    """
    logger.info(
        f"POST /translate | text='{request.text}' | "
        f"direction='{request.direction}'"
    )

    try:
        result = translate(request)

        if result is None:
            logger.error(
                "translate() returned None. "
                "Check service.py for a missing return statement."
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "Translation service returned an empty result. "
                    "This is a bug — please report it."
                ),
            )

        return result

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            f"Unhandled error in translate_text: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "An internal error occurred during translation. "
                "Check the server console for the full traceback."
            ),
        )