# backend/services/chat/service.py

"""
Handles all communication with Ollama.
Builds the system prompt, injects ChromaDB context,
manages conversation history, and streams the response.
"""

import httpx
import json
import logging
from typing import List, AsyncGenerator

from backend.core.config import (
    OLLAMA_BASE_URL,
    OLLAMA_DEFAULT_MODEL,
    OLLAMA_TIMEOUT,
    CHAT_MAX_HISTORY,
)
from backend.services.chat.schemas import ChatMessage
from backend.services.chat.context_builder import build_context

logger = logging.getLogger(__name__)


# ─── System Prompt ────────────────────────────────────────────

SYSTEM_PROMPT = """You are Luganda AI Studio, a helpful and encouraging Luganda language assistant.

Your job is to help users:
- Translate between Luganda and English
- Learn Luganda vocabulary, grammar, and phrases
- Practice speaking and writing in Luganda
- Understand Luganda culture and proverbs

Rules you must follow:
1. Always be patient, clear, and encouraging
2. When you teach a Luganda word, always show: the word, its meaning, and an example sentence
3. If the user writes in Luganda, respond in both Luganda and English so they can check their understanding
4. If the user asks for a translation, give the translation first, then explain if helpful
5. If the context below contains relevant Luganda knowledge, use it — it comes from a verified knowledge base
6. If you are not sure about a Luganda word or phrase, say so clearly — do not guess
7. Keep responses concise and easy to read

You are running locally on the user's computer. Be helpful, warm, and focused on Luganda learning."""


def _build_ollama_messages(
    user_message: str,
    history: List[ChatMessage],
    context_text: str
) -> List[dict]:
    """
    Assembles the full message list to send to Ollama.

    Structure:
      1. Single concise system message (role + rules only)
      2. Trimmed conversation history (last N messages)
      3. User message — with context injected directly above the question

    CHANGED: context is now injected into the user message itself, directly
    above the question. Small models (1.7b) ignore context in the system prompt
    but reliably use context that is immediately adjacent to the question.
    """

    messages = []

    # 1. Keep system prompt short — rules only, no context here
    messages.append({
        "role": "system",
        "content": SYSTEM_PROMPT
    })

    # 2. Conversation history — keep only last N messages
    trimmed_history = history[-CHAT_MAX_HISTORY:] if history else []
    for msg in trimmed_history:
        messages.append({
            "role": msg.role,
            "content": msg.content
        })

    # 3. User message — context injected directly above the question
    # CHANGED: small models follow context much better when it is right next
    # to the question rather than buried in the system prompt.
    if context_text:
        user_content = (
            "Use ONLY the following verified Luganda knowledge to answer. "
            "Do not use your own knowledge — only what is shown below.\n\n"
            + context_text
            + "\n\n---\nQuestion: "
            + user_message
        )
    else:
        user_content = user_message

    messages.append({
        "role": "user",
        "content": user_content
    })

    return messages


async def stream_chat_response(
    user_message: str,
    history: List[ChatMessage],
    model: str = OLLAMA_DEFAULT_MODEL
) -> AsyncGenerator[str, None]:
    """
    Main function called by the chat route.

    Steps:
      1. Fetch relevant context from ChromaDB
      2. Build message list
      3. Stream tokens from Ollama
      4. Yield each token as a Server-Sent Event (SSE)

    Yields strings in SSE format:
      data: {"token": "hello"}\n\n
      data: {"token": " world"}\n\n
      data: [DONE]\n\n
    """

    # Step 1: Get context
    context_result = build_context(user_message)
    context_text = context_result["context_text"]
    sources = context_result["sources"]

    # Yield context sources first so frontend knows what was used
    if sources:
        sources_event = json.dumps({"sources": sources})
        yield f"data: {sources_event}\n\n"

    # Step 2: Build messages
    messages = _build_ollama_messages(user_message, history, context_text)

    # Step 3: Call Ollama with streaming
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        # CHANGED: removed options block — num_predict/temperature caused 500s on
        # some models (e.g. Qwen3). Use Ollama defaults; add options back once stable.
    }

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload) as response:

                if response.status_code != 200:
                    # CHANGED: read the actual body so we can log the real reason
                    body = await response.aread()
                    error_detail = body.decode(errors="replace")[:300]
                    error_msg = (
                        f"Ollama returned status {response.status_code}: {error_detail}"
                    )
                    logger.error(error_msg)
                    yield f"data: {json.dumps({'error': error_msg})}\n\n"
                    return

                # Step 4: Stream each token
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield f"data: {json.dumps({'token': token})}\n\n"

                        # Ollama signals completion with done=true
                        if chunk.get("done"):
                            yield "data: [DONE]\n\n"
                            return

                    except json.JSONDecodeError:
                        continue

    except httpx.ConnectError:
        msg = "Cannot connect to Ollama. Make sure Ollama is running on port 11434."
        logger.error(msg)
        yield f"data: {json.dumps({'error': msg})}\n\n"

    except httpx.TimeoutException:
        msg = "Ollama took too long to respond. Try a shorter message or restart Ollama."
        logger.error(msg)
        yield f"data: {json.dumps({'error': msg})}\n\n"

    except Exception as e:
        logger.error(f"Unexpected chat error: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"