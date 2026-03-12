"""OHLCV Collector — fetches candle data from exchange and stores/publishes.

Scheduler calls collect() periodically per timeframe.
Publishes OHLCVUpdateEvent on new data.
"""

from __future__ import annotations

import logging

from shared.events import OHLCVUpdateEvent

logger = logging.getLogger(__name__)


class OHLCVCollector:
    """Fetches OHLCV data from exchange, stores in DB, publishes events."""

    def __init__(
        self,
        exchange_client: object,
        data_store: object,
        event_bus: object,
        symbol: str = "BTC/KRW",
    ) -> None:
        self._exchange = exchange_client
        self._store = data_store
        self._bus = event_bus
        self._symbol = symbol

    async def collect(self, timeframe: str, limit: int = 200) -> int:
        """Fetch OHLCV from exchange, upsert to DB, publish event.

        Returns number of candles upserted.
        """
        try:
            candles = await self._exchange.fetch_ohlcv(
                symbol=self._symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except Exception:
            logger.exception(
                "Failed to fetch OHLCV for %s/%s", self._symbol, timeframe
            )
            return 0

        if not candles:
            return 0

        count = await self._store.upsert_candles(candles)

        await self._bus.publish(
            OHLCVUpdateEvent(
                symbol=self._symbol,
                timeframe=timeframe,
                candles=candles,
            )
        )

        logger.debug(
            "Collected %d candles for %s/%s",
            count,
            self._symbol,
            timeframe,
        )
        return count

    async def collect_all_timeframes(
        self,
        timeframes: list[str] | None = None,
    ) -> dict[str, int]:
        """Collect OHLCV for multiple timeframes."""
        tfs = timeframes or ["15m", "1h", "4h", "1d"]
        results: dict[str, int] = {}
        for tf in tfs:
            results[tf] = await self.collect(tf)
        return results
