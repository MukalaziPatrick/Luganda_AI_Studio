# backend/core/config.py

import os
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=False)  # CHANGED: wire up .env loading

# ─── Base Paths ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATASETS_DIR = BASE_DIR / "datasets"
RAW_DOWNLOADS_DIR = DATASETS_DIR / "raw_downloads"

# ─── ChromaDB ─────────────────────────────────────────────────
CHROMA_PATH = DATA_DIR / "chromadb"

# ─── Progress Tracking ────────────────────────────────────────
PROGRESS_FILE = DATA_DIR / "progress" / "progress.json"

# ─── Phase 1: Imported datasets ──────────────────────────────
IMPORTED_DATASETS_DIR = DATA_DIR / "datasets"

# ─── Phase 3: Feedback + Training ────────────────────────────
FEEDBACK_DIR = DATA_DIR / "feedback"
TRAINING_DIR = DATA_DIR / "training"

# ─── Ollama ───────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")  # CHANGED: env-configurable
OLLAMA_DEFAULT_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "qwen3:1.7b")   # CHANGED: fits in 4GB VRAM (only ~1.1GB)
OLLAMA_TIMEOUT = 120

# ─── OpenRouter ───────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")  # CHANGED: new for OpenRouter integration
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-2-9b-it:free")  # CHANGED: new for OpenRouter
OPENROUTER_TIMEOUT_SECONDS = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "8"))  # CHANGED: new for OpenRouter
OPENROUTER_DAILY_LIMIT_USD = float(os.getenv("OPENROUTER_DAILY_LIMIT_USD", "0.10"))  # CHANGED: new for OpenRouter

# ─── Chat Settings ────────────────────────────────────────────
CHAT_MAX_HISTORY = 10
CHAT_CONTEXT_RESULTS = 5

# ─── App Settings (used by routes that import `settings`) ─────
# CHANGED: added all attributes used across the codebase
settings = SimpleNamespace(
    app_name="Luganda AI Studio",
    app_version="1.0.0",
    chroma_dir=CHROMA_PATH,                # used by chroma_client.py
    datasets_dir=DATASETS_DIR,             # used by services/ingestion/loader.py
    imported_datasets_dir=IMPORTED_DATASETS_DIR,  # Phase 1: downloaded datasets
    feedback_dir=FEEDBACK_DIR,             # Phase 3: user feedback
    training_dir=TRAINING_DIR,             # Phase 3: training data accumulation
    # CHANGED: OpenRouter configuration
    openrouter_api_key=OPENROUTER_API_KEY,
    openrouter_model=OPENROUTER_MODEL,
    openrouter_timeout_seconds=OPENROUTER_TIMEOUT_SECONDS,
    openrouter_daily_limit_usd=OPENROUTER_DAILY_LIMIT_USD,
)