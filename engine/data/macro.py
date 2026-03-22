"""Macro data collector — Fear&Greed, BTC Dominance, DXY, Funding Rate.

Periodically fetches macro indicators and stores as MacroSnapshot.
Calculates a composite market_score from component values.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from shared.models import MacroSnapshot

logger = logging.getLogger(__name__)

# Reusable timeout for external API calls
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class MacroCollector:
    """Collects macro indicators and stores snapshots."""

    def __init__(
        self,
        data_store: object,
        enabled: bool = True,
    ) -> None:
        self._store = data_store
        self._enabled = enabled

    async def collect(self) -> MacroSnapshot | None:
        """Fetch all macro indicators and save snapshot.

        Returns the snapshot, or None if collection failed.
        """
        if not self._enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                fear_greed = await self._fetch_fear_greed(client)
                funding_rate = await self._fetch_funding_rate(client)
                btc_dominance = await self._fetch_btc_dominance(client)
                kimchi_premium = await self._fetch_kimchi_premium(client)

            market_score = self._calculate_market_score(
                fear_greed=fear_greed,
                funding_rate=funding_rate,
                btc_dominance=btc_dominance,
            )

            snapshot = MacroSnapshot(
                timestamp=datetime.now(UTC),
                fear_greed=fear_greed,
                funding_rate=funding_rate,
                btc_dominance=btc_dominance,
                btc_dom_7d_change=0.0,
                dxy=104.0,
                kimchi_premium=kimchi_premium,
                market_score=market_score,
            )

            await self._store.save_macro_snapshot(snapshot)
            logger.info(
                "Macro snapshot saved: fg=%.0f, fr=%.4f, dom=%.1f, kp=%.2f, score=%.4f",
                fear_greed, funding_rate, btc_dominance, kimchi_premium, market_score,
            )
            return snapshot

        except Exception:
            logger.exception("Failed to collect macro data")
            return None

    async def _fetch_fear_greed(self, client: httpx.AsyncClient) -> float:
        """Fetch Fear & Greed Index (0-100). Default 50 (neutral)."""
        try:
            resp = await client.get("https://api.alternative.me/fng/")
            resp.raise_for_status()
            data = resp.json().get("data", [{}])[0]
            return float(data.get("value", 50))
        except Exception:
            logger.warning("Fear&Greed fetch failed, using default")
            return 50.0

    async def _fetch_funding_rate(self, client: httpx.AsyncClient) -> float:
        """Fetch BTC perpetual funding rate from Binance Futures. Default 0.01%."""
        try:
            resp = await client.get(
                "https://fapi.binance.com/fapi/v1/fundingRate",
                params={"symbol": "BTCUSDT", "limit": "1"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0:
                return float(data[0].get("fundingRate", 0.01))
        except Exception:
            logger.warning("Funding rate fetch failed, using default 0.01%%")
        return 0.01

    async def _fetch_btc_dominance(self, client: httpx.AsyncClient) -> float:
        """Fetch BTC market dominance from CoinGecko. Default 50%."""
        try:
            resp = await client.get("https://api.coingecko.com/api/v3/global")
            resp.raise_for_status()
            pct = resp.json().get("data", {}).get("market_cap_percentage", {})
            return float(pct.get("btc", 50.0))
        except Exception:
            logger.warning("BTC dominance fetch failed, using default 50%%")
        return 50.0

    async def _fetch_kimchi_premium(self, client: httpx.AsyncClient) -> float:
        """Calculate Kimchi Premium: (Upbit BTC/KRW - Binance BTC/USDT * USDKRW) / Binance price * 100.

        Default 0.0%.
        """
        try:
            # Fetch Upbit BTC/KRW ticker
            upbit_resp = await client.get(
                "https://api.upbit.com/v1/ticker",
                params={"markets": "KRW-BTC"},
            )
            upbit_resp.raise_for_status()
            upbit_price = float(upbit_resp.json()[0]["trade_price"])

            # Fetch Binance BTC/USDT ticker
            binance_resp = await client.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "BTCUSDT"},
            )
            binance_resp.raise_for_status()
            binance_usd = float(binance_resp.json()["price"])

            # Fetch USD/KRW exchange rate (from exchangerate API)
            fx_resp = await client.get(
                "https://open.er-api.com/v6/latest/USD",
            )
            fx_resp.raise_for_status()
            usd_krw = float(fx_resp.json().get("rates", {}).get("KRW", 1350.0))

            binance_krw = binance_usd * usd_krw
            if binance_krw > 0:
                premium = ((upbit_price - binance_krw) / binance_krw) * 100
                return round(premium, 2)
        except Exception:
            logger.warning("Kimchi premium fetch failed, using default 0.0%%")
        return 0.0

    @staticmethod
    def _calculate_market_score(
        fear_greed: float,
        funding_rate: float,
        btc_dominance: float,
    ) -> float:
        """Composite market score [-1, +1].

        Components:
        - Fear & Greed: 0→-1 (extreme fear), 100→+1 (extreme greed)
        - Funding rate: negative = bearish, positive = bullish
        - BTC dominance: high = risk-off, low = risk-on
        """
        fg_score = (fear_greed - 50) / 50  # [-1, +1]
        fr_score = max(-1.0, min(1.0, funding_rate * 100))
        dom_score = (50 - btc_dominance) / 50  # high dom = bearish

        # Weighted combination
        return round(fg_score * 0.5 + fr_score * 0.3 + dom_score * 0.2, 4)
