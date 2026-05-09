# backend/api/routes/health.py

"""
Health check endpoint.

GET /api/v1/health

Returns basic information to confirm the server is running correctly.
Used to verify the app is alive before testing other endpoints.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    message: str


@router.get(
    "/",          # CHANGED: was "/health" which doubled to /api/v1/health/health
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns server status and basic app information.",
)
def health_check() -> HealthResponse:
    """
    Simple health check.
    If this returns 200, the server is running correctly.
    """
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,        # ← lowercase, matches config.py
        version=settings.app_version,      # ← lowercase, matches config.py
        message="Luganda AI Studio backend is running.",
    )