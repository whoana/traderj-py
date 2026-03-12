"""Tests for DCA strategy engine."""

from datetime import UTC, datetime, timedelta

import pytest

from engine.strategy.dca import DCAConfig, DCADecision, DCAEngine


class TestDCABasicBuy:
    def test_first_buy_approved(self):
        engine = DCAEngine()
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=0,
        )
        assert decision.should_buy is True
        assert decision.buy_amount_krw == 100_000

    def test_buy_amount_matches_config(self):
        config = DCAConfig(base_buy_krw=200_000)
        engine = DCAEngine(config=config)
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=0,
        )
        assert decision.buy_amount_krw == 200_000

    def test_record_buy_updates_state(self):
        engine = DCAEngine()
        engine.record_buy(100_000)
        assert engine.buy_count == 1
        assert engine.total_invested == 100_000


class TestDCAInterval:
    def test_interval_not_reached_blocks(self):
        engine = DCAEngine()
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        engine.record_buy(100_000, now=now)

        # 12 hours later (interval = 24h)
        later = now + timedelta(hours=12)
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=100_000,
            now=later,
        )
        assert decision.should_buy is False
        assert "interval" in decision.reason

    def test_interval_reached_allows(self):
        engine = DCAEngine()
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        engine.record_buy(100_000, now=now)

        later = now + timedelta(hours=25)
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=100_000,
            now=later,
        )
        assert decision.should_buy is True

    def test_custom_interval(self):
        config = DCAConfig(interval_hours=4)
        engine = DCAEngine(config=config)
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        engine.record_buy(100_000, now=now)

        later = now + timedelta(hours=5)
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=100_000,
            now=later,
        )
        assert decision.should_buy is True


class TestDCARSIScaling:
    def test_oversold_scales_up(self):
        engine = DCAEngine()
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=0,
            current_rsi=20.0,
        )
        assert decision.should_buy is True
        assert decision.buy_amount_krw == 150_000  # 100K * 1.5
        assert decision.rsi_adjustment == "scale_up"

    def test_overbought_scales_down(self):
        engine = DCAEngine()
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=0,
            current_rsi=75.0,
        )
        assert decision.should_buy is True
        assert decision.buy_amount_krw == 50_000  # 100K * 0.5
        assert decision.rsi_adjustment == "scale_down"

    def test_very_high_rsi_skips(self):
        engine = DCAEngine()
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=0,
            current_rsi=85.0,
        )
        assert decision.should_buy is False
        assert decision.rsi_adjustment == "skip"

    def test_normal_rsi_no_adjustment(self):
        engine = DCAEngine()
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=0,
            current_rsi=50.0,
        )
        assert decision.should_buy is True
        assert decision.buy_amount_krw == 100_000
        assert decision.rsi_adjustment == "none"

    def test_rsi_scaling_disabled(self):
        config = DCAConfig(use_rsi_scaling=False)
        engine = DCAEngine(config=config)
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=0,
            current_rsi=20.0,  # oversold but scaling disabled
        )
        assert decision.buy_amount_krw == 100_000  # no adjustment


class TestDCASafetyLimits:
    def test_volatility_cap_blocks(self):
        engine = DCAEngine()
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=0,
            current_atr_pct=0.10,  # above 8% cap
        )
        assert decision.should_buy is False
        assert "volatility" in decision.reason

    def test_max_position_blocks(self):
        engine = DCAEngine()
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=6_000_000,  # 60% > 50% limit
        )
        assert decision.should_buy is False
        assert "max_position" in decision.reason

    def test_insufficient_balance(self):
        config = DCAConfig(base_buy_krw=100_000, min_buy_krw=5_000, max_position_pct=0.95)
        engine = DCAEngine(config=config)
        decision = engine.evaluate(
            total_balance_krw=10_000,
            existing_position_krw=8_000,  # only 2K available
        )
        assert decision.should_buy is False
        assert "below_min" in decision.reason

    def test_amount_capped_by_available(self):
        config = DCAConfig(base_buy_krw=200_000, max_position_pct=0.95)
        engine = DCAEngine(config=config)
        decision = engine.evaluate(
            total_balance_krw=1_000_000,
            existing_position_krw=900_000,  # only 100K available
        )
        assert decision.should_buy is True
        assert decision.buy_amount_krw == 100_000  # capped


class TestDCAReset:
    def test_reset_clears_state(self):
        engine = DCAEngine()
        engine.record_buy(100_000)
        engine.record_buy(100_000)
        assert engine.buy_count == 2

        engine.reset()
        assert engine.buy_count == 0
        assert engine.total_invested == 0.0

        # Can buy immediately after reset
        decision = engine.evaluate(
            total_balance_krw=10_000_000,
            existing_position_krw=0,
        )
        assert decision.should_buy is True
