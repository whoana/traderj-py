"""Application settings loaded from environment variables.

Uses pydantic-settings for typed, validated configuration.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    model_config = {"env_prefix": "DB_", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    type: str = "sqlite"
    host: str = "localhost"
    port: int = 5432
    name: str = "traderj"
    user: str = "traderj"
    password: str = ""
    url: str = ""
    sqlite_path: str = "traderj.db"
    pool_min: int = 2
    pool_max: int = 10

    @model_validator(mode="after")
    def _build_url(self) -> DatabaseSettings:
        """Build url from individual fields if not explicitly set (postgres only)."""
        if self.type == "postgres" and not self.url:
            pw = quote_plus(self.password) if self.password else ""
            auth = f"{self.user}:{pw}" if pw else self.user
            self.url = f"postgresql://{auth}@{self.host}:{self.port}/{self.name}"
        return self


class ExchangeSettings(BaseSettings):
    model_config = {"env_prefix": "EXCHANGE_"}

    name: str = "upbit"
    api_key: str = ""
    api_secret: str = ""
    rate_limit_per_sec: int = 8


class TradingSettings(BaseSettings):
    model_config = {"env_prefix": "TRADING_"}

    mode: str = "paper"
    symbols: list[str] = ["BTC/KRW"]
    strategy_id: str = "STR-001"
    strategy_ids: list[str] = []
    initial_krw: int = 10_000_000
    max_position_pct: float = 0.3
    daily_loss_limit: int = 200_000
    max_consecutive_losses: int = 3

    def get_active_strategy_ids(self) -> list[str]:
        """Return active strategy IDs. Uses strategy_ids if set, else falls back to strategy_id."""
        if self.strategy_ids:
            return list(self.strategy_ids)
        return [self.strategy_id]


class APISettings(BaseSettings):
    model_config = {"env_prefix": "API_"}

    host: str = "0.0.0.0"
    port: int = 8000
    api_key: str = "dev-api-key"


class TelegramSettings(BaseSettings):
    model_config = {"env_prefix": "TELEGRAM_", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    bot_token: str = ""
    chat_id: str = ""
    enabled: bool = True

    @model_validator(mode="after")
    def _auto_disable(self) -> TelegramSettings:
        """Disable if bot_token or chat_id is missing."""
        if not self.bot_token or not self.chat_id:
            self.enabled = False
        return self


class AppSettings(BaseSettings):
    """Root settings aggregating all sub-settings."""

    model_config = {"env_prefix": "APP_", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    env: str = "development"
    log_level: str = "INFO"
    log_json: bool = False

    db: DatabaseSettings = DatabaseSettings()
    exchange: ExchangeSettings = ExchangeSettings()
    trading: TradingSettings = TradingSettings()
    api: APISettings = APISettings()
    telegram: TelegramSettings = TelegramSettings()
    tuner: Any = None

    @model_validator(mode="after")
    def _init_tuner(self) -> AppSettings:
        """Lazy-import TunerSettings to avoid circular deps."""
        if self.tuner is None:
            from engine.tuner.config import TunerSettings

            self.tuner = TunerSettings()
        return self
