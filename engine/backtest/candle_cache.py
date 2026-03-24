"""OHLCV candle cache — stores fetched candles in SQLite to avoid re-fetching."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiosqlite
import pandas as pd

logger = logging.getLogger(__name__)

# Timeframe → milliseconds per bar
_TF_MS = {
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS backtest_candle_cache (
    symbol    TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open      REAL NOT NULL,
    high      REAL NOT NULL,
    low       REAL NOT NULL,
    close     REAL NOT NULL,
    volume    REAL NOT NULL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);
"""


class CandleCache:
    """OHLCV candle cache backed by SQLite."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def init_table(self) -> None:
        await self._db.executescript(CREATE_TABLE_SQL)

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start_ms: int,
        end_ms: int,
        fetcher=None,
    ) -> pd.DataFrame:
        """Load candles from cache, fetch missing gaps via `fetcher`."""
        cached = await self._load(symbol, timeframe, start_ms, end_ms)

        if fetcher is not None:
            gaps = self._find_gaps(cached, start_ms, end_ms, timeframe)
            for gap_start, gap_end in gaps:
                logger.info("Fetching gap %s %s %d→%d", symbol, timeframe, gap_start, gap_end)
                fresh = await fetcher(symbol, timeframe, gap_start, gap_end)
                if fresh:
                    await self._save(symbol, timeframe, fresh)
                    fresh_df = _raw_to_df(fresh)
                    cached = pd.concat([cached, fresh_df]) if not cached.empty else fresh_df

        if cached.empty:
            return cached
        return cached.sort_index().loc[~cached.index.duplicated(keep="first")]

    async def _load(self, symbol: str, tf: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        rows = await self._db.execute_fetchall(
            """SELECT timestamp, open, high, low, close, volume
               FROM backtest_candle_cache
               WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp""",
            (symbol, tf, start_ms, end_ms),
        )
        if not rows:
            return pd.DataFrame()
        data = {
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
        }
        index = pd.DatetimeIndex(
            [datetime.fromtimestamp(r[0] / 1000, tz=timezone.utc) for r in rows]
        )
        return pd.DataFrame(data, index=index)

    async def _save(self, symbol: str, tf: str, raw: list[list]) -> None:
        rows = [(symbol, tf, int(c[0]), c[1], c[2], c[3], c[4], c[5]) for c in raw]
        await self._db.executemany(
            """INSERT OR IGNORE INTO backtest_candle_cache
               (symbol, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await self._db.commit()

    def _find_gaps(
        self, cached: pd.DataFrame, start_ms: int, end_ms: int, tf: str,
    ) -> list[tuple[int, int]]:
        """Find time ranges not covered by cached data."""
        step = _TF_MS.get(tf, 3_600_000)

        if cached.empty:
            return [(start_ms, end_ms)]

        cached_ts = set(int(t.timestamp() * 1000) for t in cached.index)
        expected_ts = set(range(start_ms, end_ms + 1, step))
        missing = sorted(expected_ts - cached_ts)

        if not missing:
            return []

        # Merge consecutive missing into ranges
        gaps: list[tuple[int, int]] = []
        g_start = missing[0]
        g_end = missing[0]
        for ts in missing[1:]:
            if ts - g_end <= step:
                g_end = ts
            else:
                gaps.append((g_start, g_end))
                g_start = ts
                g_end = ts
        gaps.append((g_start, g_end))
        return gaps


def _raw_to_df(raw: list[list]) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    data = {
        "open": [c[1] for c in raw],
        "high": [c[2] for c in raw],
        "low": [c[3] for c in raw],
        "close": [c[4] for c in raw],
        "volume": [c[5] for c in raw],
    }
    index = pd.DatetimeIndex(
        [datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc) for c in raw]
    )
    return pd.DataFrame(data, index=index)
