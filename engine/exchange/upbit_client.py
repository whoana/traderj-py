"""Upbit Exchange Client — ccxt wrapper implementing ExchangeClient Protocol.

Provides rate-limited access to Upbit REST API for:
- Market data (ticker, OHLCV)
- Order management (create, cancel)
- Balance queries
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import ccxt.async_support as ccxt

from engine.exchange.rate_limiter import SlidingWindowRateLimiter
from shared.models import Candle

logger = logging.getLogger(__name__)


class UpbitExchangeClient:
    """Async Upbit exchange client with rate limiting."""

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self._access_key = access_key or os.environ.get("UPBIT_ACCESS_KEY", "")
        self._secret_key = secret_key or os.environ.get("UPBIT_SECRET_KEY", "")

        self._exchange: ccxt.upbit | None = None
        self._public_limiter = SlidingWindowRateLimiter(max_requests=500, window_seconds=60.0)
        self._private_limiter = SlidingWindowRateLimiter(max_requests=100, window_seconds=60.0)

    async def connect(self) -> None:
        self._exchange = ccxt.upbit(
            {
                "apiKey": self._access_key,
                "secret": self._secret_key,
                "enableRateLimit": False,  # We handle rate limiting ourselves
            }
        )
        await self._exchange.load_markets()
        logger.info("Upbit exchange client connected, %d markets loaded", len(self._exchange.markets))

    async def disconnect(self) -> None:
        if self._exchange:
            await self._exchange.close()
            self._exchange = None

    @property
    def exchange(self) -> ccxt.upbit:
        assert self._exchange is not None, "Exchange not connected"
        return self._exchange

    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Fetch current ticker for a symbol.

        Returns dict with keys: last, bid, ask, high, low, volume, etc.
        """
        await self._public_limiter.acquire()
        ticker = await self.exchange.fetch_ticker(symbol)
        return {
            "last": str(ticker.get("last") or 0),
            "bid": str(ticker.get("bid") or 0),
            "ask": str(ticker.get("ask") or 0),
            "high": str(ticker.get("high") or 0),
            "low": str(ticker.get("low") or 0),
            "volume": str(ticker.get("baseVolume") or 0),
            "timestamp": ticker.get("timestamp"),
        }

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> list[Candle]:
        """Fetch OHLCV candles.

        Timeframes: '1m', '3m', '5m', '15m', '1h', '4h', '1d'
        """
        await self._public_limiter.acquire()
        raw = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return [
            Candle(
                time=datetime.fromtimestamp(row[0] / 1000, tz=UTC),
                symbol=symbol,
                timeframe=timeframe,
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=Decimal(str(row[5])),
            )
            for row in raw
        ]

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: Decimal,
        price: Decimal | None = None,
    ) -> dict[str, Any]:
        """Create an order on Upbit.

        Returns dict with keys: id, status, price, amount, filled, etc.
        """
        await self._private_limiter.acquire()
        params: dict[str, Any] = {}
        order = await self.exchange.create_order(
            symbol=symbol,
            type=str(order_type),
            side=str(side),
            amount=float(amount),
            price=float(price) if price else None,
            params=params,
        )
        logger.info(
            "Order created: %s %s %s amount=%s price=%s -> id=%s",
            symbol,
            side,
            order_type,
            amount,
            price,
            order.get("id"),
        )
        return {
            "id": order.get("id"),
            "status": order.get("status"),
            "price": str(order.get("price", 0)),
            "amount": str(order.get("amount", 0)),
            "filled": str(order.get("filled", 0)),
            "remaining": str(order.get("remaining", 0)),
            "timestamp": order.get("timestamp"),
        }

    async def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Cancel an open order."""
        await self._private_limiter.acquire()
        result = await self.exchange.cancel_order(order_id, symbol)
        logger.info("Order cancelled: %s on %s", order_id, symbol)
        return {
            "id": result.get("id"),
            "status": result.get("status"),
        }

    async def fetch_balance(self) -> dict[str, Decimal]:
        """Fetch account balance.

        Returns dict like {"KRW": Decimal("10000000"), "BTC": Decimal("0.5")}
        """
        await self._private_limiter.acquire()
        raw = await self.exchange.fetch_balance()
        result: dict[str, Decimal] = {}
        for currency, info in raw.get("total", {}).items():
            if info and float(info) > 0:
                result[currency] = Decimal(str(info))
        return result
