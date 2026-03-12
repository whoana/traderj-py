"""Health check endpoint — no auth required."""

from __future__ import annotations

import time

from fastapi import APIRouter

from api.schemas.responses import HealthResponse

router = APIRouter(tags=["health"])

_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        uptime=round(time.time() - _start_time, 1),
        db="connected",
        engine="running",
    )
