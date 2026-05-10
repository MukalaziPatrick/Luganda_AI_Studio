# backend/services/translation/schemas.py

"""
Request and response schemas for the translation API.

These are Pydantic models. They:
- validate incoming data automatically
- produce clean structured JSON responses
- make the API self-documenting in /docs
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------- #
# Request
# ---------------------------------------------------------------------- #

class TranslationRequest(BaseModel):
    """
    What the caller sends to /api/v1/translate
    """

    text: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="The text to translate.",
        examples=["hello", "ndaba", "How are you?"],
    )

    @field_validator("text")
    @classmethod
    def text_must_not_be_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be whitespace only")
        return v

    direction: Literal["en_to_lg", "lg_to_en"] = Field(
        ...,
        description=(
            "Translation direction. "
            "'en_to_lg' = English to Luganda. "
            "'lg_to_en' = Luganda to English."
        ),
        examples=["en_to_lg", "lg_to_en"],
    )


# ---------------------------------------------------------------------- #
# Response
# ---------------------------------------------------------------------- #

class TranslationResponse(BaseModel):
    """
    What the API returns after a translation attempt.
    """

    # --- Input echo ---
    input_text: str = Field(description="The original text that was submitted.")
    direction: str = Field(description="The direction that was requested.")

    # --- Result ---
    translated_text: Optional[str] = Field(
        default=None,
        description="The translated text, if found.",
    )

    # --- Match quality ---
    match_type: Optional[str] = Field(
        default=None,
        description=(
            "How the match was found. "
            "One of: 'exact', 'normalized', 'semantic', 'not_found'."
        ),
    )

    confidence: Optional[float] = Field(
        default=None,
        description=(
            "Similarity score for semantic matches. "
            "Between 0.0 and 1.0. Only present for semantic matches."
        ),
    )

    # --- Source info ---
    matched_collection: Optional[str] = Field(
        default=None,
        description="Which ChromaDB collection the match came from.",
    )

    matched_source_file: Optional[str] = Field(
        default=None,
        description="Which dataset source file the match came from, if recorded.",
    )

    # --- Status ---
    status: str = Field(
        description=(
            "Overall result. "
            "One of: 'success', 'not_found'."
        ),
    )

    message: str = Field(
        description="A human-readable summary of the result.",
    )