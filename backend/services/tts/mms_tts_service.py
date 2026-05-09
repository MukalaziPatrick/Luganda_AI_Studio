# backend/services/tts/mms_tts_service.py

"""
Meta MMS TTS service for Luganda.

Model: facebook/mms-tts-lug
- Luganda-specific voice (real language, not a generic Latin voice)
- CPU-capable, no VRAM required
- ~few hundred MB download
- Lazy-loaded on first request (same pattern as nllb_service.py)

First call: 5–15 s (model loading)
Subsequent: 1–2 s on CPU
"""

import io
import logging
from typing import Optional

import numpy as np
import torch

logger = logging.getLogger(__name__)

MODEL_NAME = "facebook/mms-tts-lug"


class MMSTTSService:
    """Lazy-loaded wrapper around facebook/mms-tts-lug."""

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None

    def _load(self) -> None:
        if self._model is not None:
            return
        logger.info(f"[MMS-TTS] Loading model {MODEL_NAME} — this takes ~10s on first run")
        from transformers import VitsModel, VitsTokenizer
        self._tokenizer = VitsTokenizer.from_pretrained(MODEL_NAME)
        self._model = VitsModel.from_pretrained(MODEL_NAME)
        self._model.eval()
        logger.info("[MMS-TTS] Model loaded")

    def synthesize(self, text: str) -> Optional[bytes]:
        """
        Synthesize Luganda text into WAV bytes.
        Returns None if synthesis fails.
        """
        try:
            self._load()

            with torch.no_grad():
                inputs = self._tokenizer(text, return_tensors="pt")
                output = self._model(**inputs).waveform

            # output[0] selects first batch item; squeeze removes any remaining singleton dims
            waveform = output[0].squeeze().cpu().numpy().astype(np.float32)
            sample_rate = self._model.config.sampling_rate

            return _to_wav_bytes(waveform, sample_rate)

        except Exception as e:
            logger.error(f"[MMS-TTS] Synthesis failed: {e}", exc_info=True)
            return None


def _to_wav_bytes(waveform: np.ndarray, sample_rate: int) -> bytes:
    """Convert a float32 numpy waveform array to WAV bytes."""
    import scipy.io.wavfile as wavfile

    # Clip to [-1, 1] before scaling — VITS output can exceed this range
    pcm = np.clip(waveform, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    buf = io.BytesIO()
    wavfile.write(buf, sample_rate, pcm)
    return buf.getvalue()


mms_tts_service = MMSTTSService()
