"""Dashboard passkey credential storage.

Simple CRUD for WebAuthn passkey credentials stored in the engine's SQLite DB.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.middleware.auth import verify_api_key

router = APIRouter(
    prefix="/passkeys",
    tags=["passkeys"],
    dependencies=[Depends(verify_api_key)],
)

_DB_PATH = os.environ.get("DB_SQLITE_PATH", "data/traderj.db")
_table_ready = False


async def _ensure_table() -> None:
    global _table_ready
    if _table_ready:
        return
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_passkeys (
                credential_id TEXT PRIMARY KEY,
                public_key    TEXT NOT NULL,
                counter       INTEGER NOT NULL DEFAULT 0,
                transports    TEXT NOT NULL DEFAULT '[]',
                created_at    TEXT NOT NULL
            )
        """)
        await db.commit()
    _table_ready = True


class PasskeyCreate(BaseModel):
    credential_id: str
    public_key: str
    counter: int = 0
    transports: list[str] = []


class PasskeyResponse(BaseModel):
    credential_id: str
    public_key: str
    counter: int
    transports: list[str]
    created_at: str


class CounterUpdate(BaseModel):
    counter: int


@router.get("")
async def list_passkeys() -> list[PasskeyResponse]:
    await _ensure_table()
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM dashboard_passkeys ORDER BY created_at"
        ) as cursor:
            rows = await cursor.fetchall()
    return [
        PasskeyResponse(
            credential_id=row["credential_id"],
            public_key=row["public_key"],
            counter=row["counter"],
            transports=json.loads(row["transports"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.post("", status_code=201)
async def create_passkey(body: PasskeyCreate) -> PasskeyResponse:
    await _ensure_table()
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(_DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO dashboard_passkeys
                   (credential_id, public_key, counter, transports, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    body.credential_id,
                    body.public_key,
                    body.counter,
                    json.dumps(body.transports),
                    now,
                ),
            )
            await db.commit()
        except aiosqlite.IntegrityError as e:
            raise HTTPException(status_code=409, detail="Passkey already exists") from e
    return PasskeyResponse(
        credential_id=body.credential_id,
        public_key=body.public_key,
        counter=body.counter,
        transports=body.transports,
        created_at=now,
    )


@router.put("/{credential_id}/counter")
async def update_counter(credential_id: str, body: CounterUpdate) -> dict:
    await _ensure_table()
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE dashboard_passkeys SET counter = ? WHERE credential_id = ?",
            (body.counter, credential_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Passkey not found")
    return {"ok": True}


@router.delete("/{credential_id}")
async def delete_passkey(credential_id: str) -> dict:
    await _ensure_table()
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM dashboard_passkeys WHERE credential_id = ?",
            (credential_id,),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Passkey not found")
    return {"ok": True}
