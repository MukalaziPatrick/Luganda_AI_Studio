# backend/services/ingestion/pdf_loader.py

"""
PDF Loader
===========

Reads PDF files from datasets/raw_downloads/ and converts them into
text chunks ready for embedding and storage in ChromaDB.

HANDLES TWO TYPES OF PDFs:
  1. Digital PDFs  — text can be selected/copied in a PDF viewer
                   → extract text directly using PyMuPDF (fast, accurate)

  2. Scanned PDFs  — pages are photos/images, no selectable text
                   → use Tesseract OCR to read the image (slower, ~80% accurate)

HOW IT DETECTS WHICH TYPE:
  It tries to extract text from the first 3 pages using PyMuPDF.
  If it gets fewer than 50 characters per page on average, it assumes
  the PDF is scanned and switches to OCR mode.

CHUNKING:
  Each page is split into chunks of ~CHUNK_WORDS words (default 200).
  Smaller chunks = more precise search results.
  Each chunk stores: text, source filename, page number, chunk index.

TESSERACT PATH:
  Hardcoded to: C:\\Program Files\\Tesseract-OCR\\tesseract.exe
  This is the confirmed installation path on this machine.

OUTPUT RECORD SHAPE:
  {
    "collection": "documents",
    "doc_id":     str,    # stable hash ID
    "text":       str,    # the chunk text (for embedding)
    "metadata": {
      "source_file":   str,   # e.g. "luganda_grammar.pdf"
      "page":          int,   # 1-indexed page number
      "chunk_index":   int,   # chunk number within the whole document
      "pdf_type":      str,   # "digital" or "scanned"
      "luganda":       str,   # empty — not auto-extracted from PDFs
      "english":       str,   # empty — not auto-extracted from PDFs
      "data_type":     "document",
      "needs_review":  bool,  # True for scanned (OCR may have errors)
    }
  }
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Confirmed Tesseract installation path on this machine
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Words per chunk (approximate)
# 200 words ≈ 2-3 paragraphs — good for search precision
CHUNK_WORDS = 200

# If average chars per page is below this, treat as scanned
SCANNED_THRESHOLD_CHARS = 50

# Minimum chunk length to be worth storing (filters out page headers, etc.)
MIN_CHUNK_CHARS = 40


# ── Setup pytesseract path ────────────────────────────────────────────────────

def _configure_tesseract() -> bool:
    """
    Point pytesseract at the confirmed Tesseract installation.
    Returns True if configured successfully, False if not available.
    """
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        return True
    except ImportError:
        logger.warning("pytesseract not installed. Scanned PDFs cannot be OCR'd.")
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_chunk_id(filename: str, page: int, chunk_index: int) -> str:
    """
    Generate a stable unique ID for a PDF chunk.
    Based on: filename + page number + chunk index within document.
    """
    key = f"documents|{filename}|p{page}|c{chunk_index}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def _clean_text(text: str) -> str:
    """
    Clean extracted text:
      - Collapse multiple spaces and tabs into one space
      - Collapse 3+ newlines into 2 (preserve paragraph breaks)
      - Strip leading/trailing whitespace
    """
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_into_chunks(text: str, chunk_words: int = CHUNK_WORDS) -> list[str]:
    """
    Split a block of text into chunks of approximately chunk_words words.

    Tries to split at sentence boundaries (". ") where possible to avoid
    cutting a sentence in half. Falls back to word-count splitting if no
    sentence boundary is found nearby.

    Returns a list of non-empty text chunks.
    """
    words = text.split()
    if not words:
        return []

    chunks = []
    current_words = []

    for word in words:
        current_words.append(word)

        if len(current_words) >= chunk_words:
            chunk = " ".join(current_words)

            # Try to find a sentence end near the boundary
            # Look back up to 30 words for a period
            sentence_end = -1
            for i in range(len(current_words) - 1, max(len(current_words) - 30, -1), -1):
                if current_words[i].endswith("."):
                    sentence_end = i
                    break

            if sentence_end > 0:
                # Split at the sentence boundary
                good_chunk = " ".join(current_words[:sentence_end + 1])
                remainder  = current_words[sentence_end + 1:]
                chunks.append(good_chunk)
                current_words = remainder
            else:
                # No sentence boundary found — just split at word count
                chunks.append(chunk)
                current_words = []

    # Add any remaining words as the last chunk
    if current_words:
        chunks.append(" ".join(current_words))

    # Filter out very short chunks (page numbers, headers, etc.)
    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]


# ── Digital PDF Extraction ────────────────────────────────────────────────────

def _extract_digital_text(pdf_path: Path) -> dict[int, str]:
    """
    Extract text from a digital PDF using PyMuPDF.

    Returns a dict mapping page_number (1-indexed) → page text.
    Empty pages are included as empty strings so we know the page exists.
    """
    import pymupdf as fitz  # PyMuPDF 1.24+

    page_texts = {}
    try:
        doc = fitz.open(str(pdf_path))
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            page_texts[page_num + 1] = _clean_text(text)
        doc.close()
    except Exception as e:
        logger.error(f"PyMuPDF failed on {pdf_path.name}: {e}")

    return page_texts


# ── Scanned PDF OCR ───────────────────────────────────────────────────────────

def _extract_scanned_text(pdf_path: Path) -> dict[int, str]:
    """
    Extract text from a scanned PDF using Tesseract OCR.

    Process per page:
      1. Render page as a high-resolution image (300 DPI)
      2. Pass image to Tesseract
      3. Return the OCR'd text

    This is slower than digital extraction — expect ~5-15 seconds per page
    depending on page complexity.

    Returns a dict mapping page_number (1-indexed) → OCR'd text.
    """
    import pymupdf as fitz  # PyMuPDF 1.24+
    import pytesseract
    from PIL import Image
    import io

    _configure_tesseract()

    page_texts = {}

    try:
        doc = fitz.open(str(pdf_path))

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Render page at 300 DPI for better OCR accuracy
            # matrix scale: 300/72 = 4.167
            mat  = fitz.Matrix(300 / 72, 300 / 72)
            pix  = page.get_pixmap(matrix=mat)

            # Convert to PIL Image for pytesseract
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))

            # Run OCR
            # lang="eng" — English language model
            # If Luganda language data is installed, use lang="eng+lug"
            try:
                ocr_text = pytesseract.image_to_string(img, lang="eng")
            except Exception as ocr_err:
                logger.warning(
                    f"{pdf_path.name} page {page_num + 1}: "
                    f"OCR failed — {ocr_err}. Storing empty page."
                )
                ocr_text = ""

            page_texts[page_num + 1] = _clean_text(ocr_text)
            logger.debug(
                f"{pdf_path.name} page {page_num + 1}: "
                f"OCR extracted {len(ocr_text)} chars"
            )

        doc.close()

    except Exception as e:
        logger.error(f"Scanned extraction failed on {pdf_path.name}: {e}")

    return page_texts


# ── PDF Type Detection ────────────────────────────────────────────────────────

def _detect_pdf_type(pdf_path: Path) -> str:
    """
    Detect whether a PDF is digital (selectable text) or scanned (image).

    Method:
      Extract text from the first 3 pages using PyMuPDF.
      Calculate average characters per page.
      If average < SCANNED_THRESHOLD_CHARS, treat as scanned.

    Returns: "digital" or "scanned"
    """
    import pymupdf as fitz  # PyMuPDF 1.24+

    try:
        doc   = fitz.open(str(pdf_path))
        pages = min(3, len(doc))
        total_chars = 0

        for i in range(pages):
            text = doc[i].get_text("text")
            total_chars += len(text.strip())

        doc.close()

        avg_chars = total_chars / pages if pages > 0 else 0
        pdf_type  = "digital" if avg_chars >= SCANNED_THRESHOLD_CHARS else "scanned"

        logger.info(
            f"{pdf_path.name}: avg {avg_chars:.0f} chars/page → detected as {pdf_type}"
        )
        return pdf_type

    except Exception as e:
        logger.warning(f"Could not detect PDF type for {pdf_path.name}: {e}. Assuming digital.")
        return "digital"


# ── Main PDF Loader ───────────────────────────────────────────────────────────

def load_pdf_file(pdf_path: Path) -> list[dict]:
    """
    Load a single PDF file and return a list of chunk records.

    Steps:
      1. Detect if digital or scanned
      2. Extract text page by page (direct or OCR)
      3. Split each page into chunks of ~CHUNK_WORDS words
      4. Return a record dict for each chunk

    Parameters
    ----------
    pdf_path : Path
        Full path to the PDF file.

    Returns
    -------
    list of record dicts, each with:
        collection, doc_id, text, metadata
    """
    if not pdf_path.exists():
        logger.error(f"PDF not found: {pdf_path}")
        return []

    filename = pdf_path.name
    logger.info(f"Processing PDF: {filename}")

    # Step 1: Detect type
    pdf_type = _detect_pdf_type(pdf_path)

    # Step 2: Extract text
    if pdf_type == "digital":
        logger.info(f"{filename}: extracting text directly (digital PDF)")
        page_texts = _extract_digital_text(pdf_path)
    else:
        logger.info(f"{filename}: running OCR (scanned PDF) — this may take a while...")
        page_texts = _extract_scanned_text(pdf_path)

    if not page_texts:
        logger.warning(f"{filename}: no text extracted. Skipping.")
        return []

    # Step 3: Chunk each page and build records
    records     = []
    chunk_index = 0  # Global chunk counter across the whole document

    for page_num in sorted(page_texts.keys()):
        page_text = page_texts[page_num]

        if not page_text or len(page_text) < MIN_CHUNK_CHARS:
            logger.debug(f"{filename} page {page_num}: empty or too short, skipping")
            continue

        chunks = _split_into_chunks(page_text, CHUNK_WORDS)

        for chunk_text in chunks:
            doc_id = _make_chunk_id(filename, page_num, chunk_index)

            records.append({
                "collection": "documents",
                "doc_id":     doc_id,
                "text":       chunk_text,
                "metadata": {
                    # These are empty for PDFs — set manually if needed later
                    "luganda": "",
                    "english": "",
                    # Document provenance
                    "source_file":  filename,
                    "page":         page_num,
                    "chunk_index":  chunk_index,
                    "pdf_type":     pdf_type,
                    "data_type":    "document",
                    # Flag scanned pages for human review
                    # because OCR may have errors
                    "needs_review": pdf_type == "scanned",
                },
            })
            chunk_index += 1

    logger.info(
        f"{filename}: {len(page_texts)} pages → "
        f"{len(records)} chunks ({pdf_type})"
    )
    return records


def load_all_pdfs(raw_downloads_dir: Optional[Path] = None) -> list[dict]:
    """
    Load all PDF files from the raw_downloads directory.

    Parameters
    ----------
    raw_downloads_dir : Path, optional
        Directory to scan for PDFs.
        Defaults to datasets/raw_downloads/ relative to project root.

    Returns
    -------
    list of all chunk records from all PDFs combined.
    """
    if raw_downloads_dir is None:
        # Project root is 4 levels up from this file:
        # backend/services/ingestion/pdf_loader.py → root
        project_root      = Path(__file__).resolve().parents[3]
        raw_downloads_dir = project_root / "datasets" / "raw_downloads"

    if not raw_downloads_dir.exists():
        logger.error(f"raw_downloads directory not found: {raw_downloads_dir}")
        return []

    pdf_files = sorted(raw_downloads_dir.glob("*.pdf"))

    if not pdf_files:
        logger.warning(f"No PDF files found in: {raw_downloads_dir}")
        return []

    logger.info(f"Found {len(pdf_files)} PDF files in {raw_downloads_dir}")

    all_records = []
    for pdf_path in pdf_files:
        records = load_pdf_file(pdf_path)
        all_records.extend(records)
        logger.info(f"  {pdf_path.name}: {len(records)} chunks")

    logger.info(f"Total PDF chunks loaded: {len(all_records)}")
    return all_records
