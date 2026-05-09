# backend/api/routes/tts.py

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io

from backend.services.tts.mms_tts_service import mms_tts_service

logger = logging.getLogger(__name__)
router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    lang: str = "lug"  # reserved for future multi-language support; only "lug" supported now


@router.post("")
def text_to_speech(request: TTSRequest):
    """
    Synthesize Luganda text into a WAV audio stream.

    Returns: audio/wav stream
    Errors: 400 if text is empty or lang unsupported, 503 if model fails
    """
    if request.lang != "lug":
        raise HTTPException(status_code=400, detail=f"lang '{request.lang}' is not supported. Only 'lug' is available.")
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty")
    if len(text) > 500:
        raise HTTPException(status_code=400, detail="text must be 500 characters or fewer")

    wav_bytes = mms_tts_service.synthesize(text)

    if wav_bytes is None:
        raise HTTPException(status_code=503, detail="TTS synthesis failed. Try again.")

    return StreamingResponse(
        io.BytesIO(wav_bytes),
        media_type="audio/wav",
        headers={"Content-Disposition": "inline; filename=tts.wav"},
    )
