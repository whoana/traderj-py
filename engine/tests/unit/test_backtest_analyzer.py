"""Unit tests for engine.backtest.analyzer."""

from engine.backtest.analyzer import analyze_regime_mapping, analyze_results


def _make_result(mode="compare", strategies=None, market=None, ai_regime=None):
    return {
        "mode": mode,
        "period": {"start": "2024-11-01", "end": "2024-11-30", "days": 30},
        "market": market or {"start_price": 98_000_000, "end_price": 130_000_000, "change_pct": 32.65},
        "strategies": strategies or [],
        "ai_regime": ai_regime,
    }


def _strat(sid, ret, trades=5, wr=50.0):
    return {
        "strategy_id": sid,
        "name": f"Test {sid}",
        "metrics": {
            "total_return_pct": ret,
            "total_trades": trades,
            "win_rate_pct": wr,
            "sharpe_ratio": 0.5,
            "profit_factor": 1.2,
            "max_drawdown_pct": 3.0,
        },
    }


class TestAnalyzeResults:
    def test_empty_strategies(self):
        result = analyze_results(_make_result(strategies=[]))
        assert result["best_strategy_id"] is None
        assert result["total_strategies"] == 0

    def test_best_worst_identification(self):
        strategies = [_strat("STR-001", 5.0), _strat("STR-002", -2.0), _strat("STR-003", 10.0)]
        result = analyze_results(_make_result(strategies=strategies))
        assert result["best_strategy_id"] == "STR-003"
        assert result["best_return_pct"] == 10.0
        assert result["worst_strategy_id"] == "STR-002"
        assert result["worst_return_pct"] == -2.0

    def test_beat_market_count(self):
        strategies = [_strat("STR-001", 35.0), _strat("STR-002", 30.0), _strat("STR-003", 40.0)]
        market = {"start_price": 100, "end_price": 132, "change_pct": 32.65}
        result = analyze_results(_make_result(strategies=strategies, market=market))
        # 35.0 and 40.0 beat 32.65
        assert result["beat_market_count"] == 2

    def test_insights_generated(self):
        strategies = [_strat("STR-001", 5.0)]
        result = analyze_results(_make_result(strategies=strategies))
        assert len(result["insights"]) > 0
        assert any("최고 성과" in i for i in result["insights"])

    def test_actions_compare_mode(self):
        strategies = [_strat("STR-001", 5.0)]
        result = analyze_results(_make_result(mode="compare", strategies=strategies))
        assert "switch" in result["actions"]
        assert "optimize" in result["actions"]

    def test_actions_ai_regime_mode(self):
        ai = {
            "weekly_decisions": [],
            "aggregate_metrics": {"total_return_pct": 3.0},
            "equity_curve": [],
            "trades": [],
        }
        strategies = [_strat("STR-001", 5.0)]
        result = analyze_results(_make_result(mode="ai_regime", strategies=strategies, ai_regime=ai))
        assert "switch" in result["actions"]
        assert "regime_map" in result["actions"]
        assert "optimize" in result["actions"]

    def test_ai_insight_when_underperforming(self):
        ai = {
            "weekly_decisions": [],
            "aggregate_metrics": {"total_return_pct": 2.0},
            "equity_curve": [],
            "trades": [],
        }
        strategies = [_strat("STR-001", 5.0)]
        result = analyze_results(_make_result(mode="ai_regime", strategies=strategies, ai_regime=ai))
        assert any("부진" in i for i in result["insights"])


class TestAnalyzeRegimeMapping:
    def test_empty_without_ai_regime(self):
        result = _make_result(mode="compare")
        suggestions = analyze_regime_mapping(result)
        assert suggestions == []

    def test_no_suggestions_when_mapping_is_optimal(self):
        ai = {
            "weekly_decisions": [
                {"week": 1, "start": "11/01", "end": "11/07", "regime": "bull_trend_low_vol",
                 "preset": "STR-001", "name": "Conservative", "return_pct": 5.0, "trades": 2},
            ],
            "aggregate_metrics": {"total_return_pct": 5.0},
            "equity_curve": [],
            "trades": [],
        }
        # STR-001 is the mapped preset for bull_trend_low_vol, and it's the best
        strategies = [_strat("STR-001", 5.0), _strat("STR-002", 3.0)]
        result = _make_result(mode="ai_regime", strategies=strategies, ai_regime=ai)
        suggestions = analyze_regime_mapping(result)
        # STR-001 already mapped and has best overall return
        assert len(suggestions) == 0

    def test_suggestion_when_better_strategy_exists(self):
        ai = {
            "weekly_decisions": [
                {"week": 1, "start": "11/01", "end": "11/07", "regime": "bull_trend_low_vol",
                 "preset": "STR-001", "name": "Conservative", "return_pct": -1.0, "trades": 2},
            ],
            "aggregate_metrics": {"total_return_pct": -1.0},
            "equity_curve": [],
            "trades": [],
        }
        # STR-003 has much better return
        strategies = [_strat("STR-001", -1.0), _strat("STR-003", 8.0)]
        result = _make_result(mode="ai_regime", strategies=strategies, ai_regime=ai)
        suggestions = analyze_regime_mapping(result)
        assert len(suggestions) > 0
        assert suggestions[0]["suggested_strategy"] == "STR-003"
        assert suggestions[0]["improvement_pct"] > 0
