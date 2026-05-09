# backend/api/routes/feedback.py

"""
Feedback endpoints.

POST /api/v1/feedback
  Receives a translation verdict from the frontend and appends it to a
  JSONL file on disk: data/feedback/feedback_log.jsonl

GET /api/v1/feedback
  Reads feedback_log.jsonl and returns all records as JSON, with a
  summary breakdown by verdict. Supports optional ?verdict= filter.

Each line in the JSONL file is one complete JSON record.
This format is append-only and safe for frequent writes.

Records accumulate here until a future ingestion step reads them
back into ChromaDB as correction pairs (Phase 4).
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Storage path ──────────────────────────────────────────────────────────────
# Resolves to: Luganda_AI_Studio/data/feedback/feedback_log.jsonl
# Path is relative to this file's location, walking up to the project root.

FEEDBACK_DIR = Path(__file__).resolve().parents[3] / "data" / "feedback"  # CHANGED: was [4], which resolved above the project root
FEEDBACK_FILE = FEEDBACK_DIR / "feedback_log.jsonl"

# Valid values for the verdict field
VALID_VERDICTS = {"correct", "wrong", "needs_review"}

# Valid values for the direction field
VALID_DIRECTIONS = {"en_to_lg", "lg_to_en"}


# ── Request model ─────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    """
    Fields sent by the browser when a user clicks a verdict button.

    Required fields must always be present.
    Optional fields come from the translation result and may be missing
    if the translation returned not_found.
    """

    # Required
    input_text: str
    direction: str
    translated_text: str
    verdict: str

    # Optional — from translation result metadata
    expected_output: Optional[str] = None
    match_type: Optional[str] = None
    confidence: Optional[float] = None
    matched_collection: Optional[str] = None

    # CHANGED: Validators keep bad data out of the feedback file
    @field_validator("verdict")
    @classmethod
    def verdict_must_be_valid(cls, v: str) -> str:
        if v not in VALID_VERDICTS:
            raise ValueError(
                f"verdict must be one of: {sorted(VALID_VERDICTS)}. Got: '{v}'"
            )
        return v

    @field_validator("direction")
    @classmethod
    def direction_must_be_valid(cls, v: str) -> str:
        if v not in VALID_DIRECTIONS:
            raise ValueError(
                f"direction must be one of: {sorted(VALID_DIRECTIONS)}. Got: '{v}'"
            )
        return v

    @field_validator("input_text", "translated_text")
    @classmethod
    def text_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text fields must not be empty or whitespace only")
        return v.strip()


# ── Response model ────────────────────────────────────────────────────────────

class FeedbackResponse(BaseModel):
    """
    What the backend returns after saving a feedback record.
    """
    status: str       # always "saved" on success
    id: str           # UUID of the saved record
    timestamp: str    # ISO 8601 timestamp of when it was saved
    message: str      # human-readable confirmation


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/",          # CHANGED: was "/feedback" → doubled to /api/v1/feedback/feedback
    response_model=FeedbackResponse,
    summary="Submit translation feedback",
    description=(
        "Receives a verdict on a translation result and appends it to "
        "the feedback log on disk. Verdicts are: correct, wrong, needs_review."
    ),
)
def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """
    Save a single feedback record to data/feedback/feedback_log.jsonl.

    Each record is one line of JSON (JSONL format).
    This makes the file safe to append to without reading the whole file first.
    """

    logger.info(
        f"POST /feedback | verdict='{request.verdict}' | "
        f"input='{request.input_text}' | direction='{request.direction}'"
    )

    # ── Build the full record ─────────────────────────────────────────────────
    # CHANGED: We generate id and timestamp here — never trust the browser for these.

    record_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    record = {
        "id": record_id,
        "timestamp": timestamp,
        "input_text": request.input_text,
        "direction": request.direction,
        "translated_text": request.translated_text,
        "verdict": request.verdict,
        "expected_output": request.expected_output,
        "match_type": request.match_type,
        "confidence": request.confidence,
        "matched_collection": request.matched_collection,
    }

    # ── Write to disk ─────────────────────────────────────────────────────────

    try:
        # Create the directory if it does not exist yet
        # This runs safely even if the folder already exists
        FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

        # Append one JSON line to the file
        # 'a' mode = append — never overwrites existing data
        # ensure_ascii=False = keeps Luganda characters intact (important!)
        with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info(f"Feedback saved: id={record_id} | file={FEEDBACK_FILE}")

    except OSError as e:
        # Disk error — log it and return 500 so the browser knows it failed
        logger.error(f"Failed to write feedback to disk: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=(
                "Could not save feedback to disk. "
                "Check that the data/feedback/ directory is writable."
            ),
        )

    # ── Return confirmation ───────────────────────────────────────────────────

    return FeedbackResponse(
        status="saved",
        id=record_id,
        timestamp=timestamp,
        message=f"Feedback recorded as '{request.verdict}'.",
    )


# ── GET /api/v1/feedback ──────────────────────────────────────────────────────
# CHANGED: New endpoint — reads the feedback log and returns it as JSON.
# Used by the Reviews page (frontend/reviews.html) to display all corrections.

class FeedbackSummary(BaseModel):
    total: int
    correct: int
    wrong: int
    needs_review: int
    has_correction: int   # entries where expected_output is non-empty


class FeedbackListResponse(BaseModel):
    summary: FeedbackSummary
    entries: List[dict]


@router.get(
    "/",
    response_model=FeedbackListResponse,
    summary="Get all feedback records",
    description=(
        "Reads data/feedback/feedback_log.jsonl and returns all records as JSON. "
        "Optional ?verdict= filter accepts: correct, wrong, needs_review. "
        "Returns newest entries first."
    ),
)
def get_feedback(
    verdict: Optional[str] = Query(
        default=None,
        description="Filter by verdict: correct | wrong | needs_review"
    )
) -> FeedbackListResponse:
    """
    Return all feedback records from disk, newest first.
    Optionally filter by verdict using ?verdict=correct etc.
    """

    logger.info(f"GET /feedback | verdict_filter='{verdict}'")

    # ── Validate the optional filter ─────────────────────────────────────────
    if verdict and verdict not in VALID_VERDICTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verdict filter '{verdict}'. Must be one of: {sorted(VALID_VERDICTS)}",
        )

    # ── Read the file — handle missing gracefully ─────────────────────────────
    records: List[dict] = []

    if FEEDBACK_FILE.exists():
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Skipping malformed line {line_num} in feedback log: {e}")
        except OSError as e:
            logger.error(f"Failed to read feedback log: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Could not read feedback log from disk.",
            )
    else:
        logger.info("Feedback log does not exist yet — returning empty list.")

    # ── Build summary across ALL records (before filter) ─────────────────────
    summary = FeedbackSummary(
        total=len(records),
        correct=sum(1 for r in records if r.get("verdict") == "correct"),
        wrong=sum(1 for r in records if r.get("verdict") == "wrong"),
        needs_review=sum(1 for r in records if r.get("verdict") == "needs_review"),
        has_correction=sum(1 for r in records if r.get("expected_output")),
    )

    # ── Apply optional filter ─────────────────────────────────────────────────
    if verdict:
        records = [r for r in records if r.get("verdict") == verdict]

    # ── Return newest first ───────────────────────────────────────────────────
    records.reverse()

    return FeedbackListResponse(summary=summary, entries=records)