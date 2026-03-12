"""Telegram Notifier — send trading alerts via Telegram Bot API.

Implements the shared Notifier Protocol.
Uses httpx for async HTTP requests to Telegram Bot API.
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal

import httpx

from shared.models import DailyPnL

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Sends trade alerts, risk alerts, daily summaries, and errors to Telegram."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self._enabled = enabled and bool(self._token) and bool(self._chat_id)
        self._client: httpx.AsyncClient | None = None

        if not self._enabled:
            logger.warning("TelegramNotifier disabled: missing bot_token or chat_id")

    async def start(self) -> None:
        if self._enabled:
            self._client = httpx.AsyncClient(timeout=10.0)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send_trade_alert(
        self,
        strategy_id: str,
        side: str,
        amount: Decimal,
        price: Decimal,
    ) -> None:
        emoji = "\U0001f7e2" if str(side).lower() == "buy" else "\U0001f534"
        total_krw = amount * price
        text = (
            f"{emoji} <b>Trade Alert</b>\n"
            f"Strategy: <code>{strategy_id}</code>\n"
            f"Side: <b>{str(side).upper()}</b>\n"
            f"Amount: {amount} BTC\n"
            f"Price: {price:,.0f} KRW\n"
            f"Total: {total_krw:,.0f} KRW"
        )
        await self._send(text)

    async def send_risk_alert(
        self,
        strategy_id: str,
        alert_type: str,
        message: str,
    ) -> None:
        text = (
            f"\u26a0\ufe0f <b>Risk Alert</b>\n"
            f"Strategy: <code>{strategy_id}</code>\n"
            f"Type: <code>{alert_type}</code>\n"
            f"Detail: {message}"
        )
        await self._send(text)

    async def send_daily_summary(
        self,
        strategy_id: str,
        pnl: DailyPnL,
    ) -> None:
        total = pnl.realized + pnl.unrealized
        emoji = "\U0001f4c8" if total >= 0 else "\U0001f4c9"
        text = (
            f"{emoji} <b>Daily Summary</b> ({pnl.date})\n"
            f"Strategy: <code>{strategy_id}</code>\n"
            f"Realized: {pnl.realized:+,.0f} KRW\n"
            f"Unrealized: {pnl.unrealized:+,.0f} KRW\n"
            f"Trades: {pnl.trade_count}"
        )
        await self._send(text)

    async def send_error(self, message: str) -> None:
        text = f"\u274c <b>Error</b>\n{message}"
        await self._send(text)

    async def _send(self, text: str) -> None:
        if not self._enabled:
            logger.debug("Telegram disabled, skipping: %s", text[:80])
            return

        if not self._client:
            await self.start()

        url = _TELEGRAM_API_BASE.format(token=self._token)
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            resp = await self._client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error("Telegram send failed: %d %s", resp.status_code, resp.text[:200])
        except httpx.HTTPError as exc:
            logger.error("Telegram HTTP error: %s", exc)
