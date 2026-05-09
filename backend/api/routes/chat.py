# backend/api/routes/chat.py

"""
FastAPI route for the chat assistant.
Exposes two endpoints:
  POST /api/v1/chat/message  — streaming chat (main endpoint)
  GET  /api/v1/chat/status   — check if Ollama is reachable
"""

import httpx
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.core.config import OLLAMA_BASE_URL, OLLAMA_DEFAULT_MODEL
from backend.services.chat.schemas import ChatRequest
from backend.services.chat.service import stream_chat_response

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/message")
async def chat_message(request: ChatRequest):
    """
    Main chat endpoint.
    Accepts a message + history, returns a streaming response.
    Each chunk is a Server-Sent Event (SSE).
    """
    return StreamingResponse(
        stream_chat_response(
            user_message=request.message,
            history=request.history or [],
            model=OLLAMA_DEFAULT_MODEL
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # prevents nginx from buffering the stream
        }
    )


@router.get("/status")
async def chat_status():
    """
    Check whether Ollama is running and the model is available.
    Called by the frontend on page load to show a status indicator.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                default_available = any(
                    OLLAMA_DEFAULT_MODEL in m for m in models
                )
                return {
                    "ollama_running": True,
                    "models_available": models,
                    "default_model": OLLAMA_DEFAULT_MODEL,
                    "default_model_available": default_available
                }
    except Exception as e:
        logger.warning(f"Ollama status check failed: {e}")

    return {
        "ollama_running": False,
        "models_available": [],
        "default_model": OLLAMA_DEFAULT_MODEL,
        "default_model_available": False
    }