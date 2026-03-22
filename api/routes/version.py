"""Version info endpoint."""

from __future__ import annotations

import platform
import subprocess
from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from api.middleware.auth import verify_api_key

router = APIRouter(tags=["system"], dependencies=[Depends(verify_api_key)])

_start_time = datetime.now(UTC)


def _get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


_commit = _get_git_commit()


@router.get("/version")
async def get_version():
    return {
        "version": "0.2.0",
        "python": platform.python_version(),
        "commit": _commit,
        "started_at": _start_time.isoformat(),
    }
