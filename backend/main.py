# backend/main.py

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from backend.api.routes import health, knowledge, translate, teach, feedback, chat, tts

app = FastAPI(
    title="Luganda AI Studio",
    description="AI-powered Luganda translation, learning, and chat assistant",
    version="0.3.0"
)

# ─── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── API Routes ───────────────────────────────────────────────
app.include_router(health.router,     prefix="/api/v1/health",     tags=["Health"])
app.include_router(knowledge.router,  prefix="/api/v1/knowledge",  tags=["Knowledge"])
app.include_router(translate.router,  prefix="/api/v1/translate",  tags=["Translate"])
app.include_router(teach.router,      prefix="/api/v1/teach",      tags=["Teach"])
app.include_router(feedback.router,   prefix="/api/v1/feedback",   tags=["Feedback"])
app.include_router(chat.router,       prefix="/api/v1/chat",       tags=["Chat"])
app.include_router(tts.router,        prefix="/api/v1/tts",        tags=["TTS"])

# ─── Frontend Static Files ────────────────────────────────────
frontend_path = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/app", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

# ─── Root Redirect ────────────────────────────────────────────
@app.get("/")
async def root():
    return {"message": "Luganda AI Studio API is running. Visit /app/index.html for the UI."}