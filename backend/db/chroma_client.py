# backend/db/chroma_client.py

import logging
import chromadb
from backend.core.config import settings

logger = logging.getLogger(__name__)


def get_chroma_client() -> chromadb.ClientAPI:
    """
    Creates and returns a persistent ChromaDB client.
    Data is stored on disk at the path defined in settings.chroma_dir.
    """
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Connecting to ChromaDB at: {settings.chroma_dir}")

    client = chromadb.PersistentClient(
        path=str(settings.chroma_dir),
    )
    return client


# This line is what gets imported by other files.
chroma_client = get_chroma_client()