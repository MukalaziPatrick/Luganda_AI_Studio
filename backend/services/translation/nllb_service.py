# backend/services/translation/nllb_service.py

"""
NLLB-200 neural translation service.

Used as fallback when the search pipeline (exact → normalized → partial → semantic)
returns no result. Translates any text, not just stored entries.

Model: facebook/nllb-200-distilled-600M
- Supports Luganda natively (language code: lug_Latn)
- ~2.3 GB download, ~1.5 GB VRAM in float16
- Fits on RTX 3050 (4 GB VRAM) alongside ChromaDB + MiniLM
- Lazy-loaded on first neural request so ChromaDB-only lookups stay fast

Performance on RTX 3050:
  First call: 5-10 s  (model loading)
  Subsequent: 1-3 s   (GPU)  /  5-10 s (CPU fallback)
"""

import logging
import torch
from typing import Optional
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

logger = logging.getLogger(__name__)

MODEL_NAME = "facebook/nllb-200-distilled-600M"

# NLLB-200 BCP-47 codes for supported directions
_LANG_CODES: dict[str, tuple[str, str]] = {
    "en_to_lg": ("eng_Latn", "lug_Latn"),
    "lg_to_en": ("lug_Latn", "eng_Latn"),
}


class NLLBTranslator:
    """Lazy-loaded wrapper around NLLB-200-distilled-600M."""

    def __init__(self) -> None:
        self._tokenizer: Optional[AutoTokenizer] = None
        self._model: Optional[AutoModelForSeq2SeqLM] = None
        self._device: Optional[str] = None
        self._loaded = False

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        if self._loaded:
            return

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"[NLLB] Loading {MODEL_NAME} on {self._device} ...")

        self._tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

        dtype = torch.float16 if self._device == "cuda" else torch.float32
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=dtype,
        ).to(self._device)

        self._model.eval()
        self._loaded = True
        logger.info(f"[NLLB] Model ready on {self._device}.")

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def translate(self, text: str, direction: str) -> Optional[str]:
        """
        Translate text using NLLB-200.

        Args:
            text:      The text to translate.
            direction: "en_to_lg" or "lg_to_en"

        Returns:
            Translated string, or None if the model fails.
        """
        if direction not in _LANG_CODES:
            logger.error(f"[NLLB] Unknown direction: {direction}")
            return None

        try:
            self._load()
        except Exception as e:
            logger.error(f"[NLLB] Model load failed: {e}", exc_info=True)
            return None

        src_lang, tgt_lang = _LANG_CODES[direction]

        try:
            self._tokenizer.src_lang = src_lang
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=256,
            ).to(self._device)

            forced_bos = self._tokenizer.convert_tokens_to_ids(tgt_lang)

            with torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    forced_bos_token_id=forced_bos,
                    max_new_tokens=256,
                    num_beams=4,
                    early_stopping=True,
                )

            result = self._tokenizer.decode(output_ids[0], skip_special_tokens=True)
            logger.debug(f"[NLLB] '{text}' ({direction}) → '{result}'")
            return result.strip() or None

        except torch.cuda.OutOfMemoryError:
            # VRAM exhausted — retry on CPU
            logger.warning("[NLLB] CUDA OOM. Retrying on CPU.")
            return self._translate_on_cpu(text, direction)

        except Exception as e:
            logger.error(f"[NLLB] Translation failed: {e}", exc_info=True)
            return None

    def _translate_on_cpu(self, text: str, direction: str) -> Optional[str]:
        """CPU fallback used when CUDA runs out of VRAM."""
        if direction not in _LANG_CODES:
            return None
        src_lang, tgt_lang = _LANG_CODES[direction]
        try:
            self._tokenizer.src_lang = src_lang
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=256,
            )  # no .to() — stays on CPU

            forced_bos = self._tokenizer.convert_tokens_to_ids(tgt_lang)

            with torch.no_grad():
                output_ids = self._model.to("cpu").generate(
                    **inputs,
                    forced_bos_token_id=forced_bos,
                    max_new_tokens=256,
                )

            result = self._tokenizer.decode(output_ids[0], skip_special_tokens=True)
            return result.strip() or None

        except Exception as e:
            logger.error(f"[NLLB] CPU fallback also failed: {e}", exc_info=True)
            return None


# Singleton — imported by service.py
nllb_translator = NLLBTranslator()
