"""WebSocket endpoint handler."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.ws.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_ws_api_key(api_key: str | None) -> bool:
    expected = os.environ.get("TRADERJ_API_KEY", "dev-api-key")
    return api_key is not None and api_key == expected


@router.websocket("/ws/v1/stream")
async def websocket_endpoint(websocket: WebSocket, api_key: str | None = None):
    """Main WebSocket endpoint with query-param authentication."""
    if not _verify_ws_api_key(api_key):
        await websocket.close(code=4001, reason="Invalid API key")
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.handle_message(websocket, data)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        logger.exception("WS handler error")
        await manager.disconnect(websocket)
