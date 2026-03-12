"""Macro data collector — Fear&Greed, BTC Dominance, DXY, Funding Rate.

Periodically fetches macro indicators and stores as MacroSnapshot.
Calculates a composite market_score from component values.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from shared.models import MacroSnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MacroSource:
    """External API endpoints for macro data (pluggable)."""

    fear_greed_url: str = "https://api.alternative.me/fng/"
    btc_dominance_url: str = ""  # placeholder
    dxy_url: str = ""  # placeholder
    funding_rate_url: str = ""  # placeholder


class MacroCollector:
    """Collects macro indicators and stores snapshots."""

    def __init__(
        self,
        data_store: object,
        http_client: object | None = None,
    ) -> None:
        self._store = data_store
        self._http = http_client

    async def collect(self) -> MacroSnapshot | None:
        """Fetch all macro indicators and save snapshot.

        Returns the snapshot, or None if collection failed.
        For Phase 2, uses defaults when external APIs are not configured.
        """
        try:
            fear_greed = await self._fetch_fear_greed()
            funding_rate = await self._fetch_funding_rate()
            btc_dominance = await self._fetch_btc_dominance()
            dxy = await self._fetch_dxy()

            market_score = self._calculate_market_score(
                fear_greed=fear_greed,
                funding_rate=funding_rate,
                btc_dominance=btc_dominance,
            )

            snapshot = MacroSnapshot(
                timestamp=datetime.now(timezone.utc),
                fear_greed=fear_greed,
                funding_rate=funding_rate,
                btc_dominance=btc_dominance,
                btc_dom_7d_change=0.0,  # TODO: calculate from history
                dxy=dxy,
                kimchi_premium=0.0,  # TODO: implement
                market_score=market_score,
            )

            await self._store.save_macro_snapshot(snapshot)
            logger.info("Macro snapshot saved: score=%.2f", market_score)
            return snapshot

        except Exception:
            logger.exception("Failed to collect macro data")
            return None

    async def _fetch_fear_greed(self) -> float:
        """Fetch Fear & Greed Index (0-100). Default 50 (neutral)."""
        if self._http is None:
            return 50.0
        try:
            resp = await self._http.get("https://api.alternative.me/fng/")
            data = resp.get("data", [{}])[0]
            return float(data.get("value", 50))
        except Exception:
            logger.warning("Fear&Greed fetch failed, using default")
            return 50.0

    async def _fetch_funding_rate(self) -> float:
        """Fetch BTC perpetual funding rate. Default 0.01%."""
        return 0.01  # TODO: implement exchange-specific API

    async def _fetch_btc_dominance(self) -> float:
        """Fetch BTC market dominance. Default 50%."""
        return 50.0  # TODO: implement CoinGecko/CoinMarketCap API

    async def _fetch_dxy(self) -> float:
        """Fetch US Dollar Index. Default 104.0."""
        return 104.0  # TODO: implement external data source

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
