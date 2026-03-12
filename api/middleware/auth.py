"""API Key authentication middleware."""

from __future__ import annotations

import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key() -> str:
    return os.environ.get("TRADERJ_API_KEY", "dev-api-key")


async def verify_api_key(
    api_key: str | None = Security(API_KEY_HEADER),
) -> str:
    """Dependency that validates the API key."""
    expected = get_api_key()
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
