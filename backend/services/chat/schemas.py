# backend/services/chat/schemas.py

from pydantic import BaseModel
from typing import List, Optional


class ChatMessage(BaseModel):
    """A single message in the conversation."""
    role: str        # "user" or "assistant"
    content: str     # the message text


class ChatRequest(BaseModel):
    """What the frontend sends to the chat endpoint."""
    message: str
    history: Optional[List[ChatMessage]] = []
    language_mode: Optional[str] = "auto"
    # language_mode options:
    #   "auto"    — detect language automatically
    #   "luganda" — user is practising Luganda
    #   "english" — user wants English explanations


class ChatResponse(BaseModel):
    """Used for non-streaming responses (health checks, errors)."""
    reply: str
    context_used: Optional[List[str]] = []
    model: str
    error: Optional[str] = None