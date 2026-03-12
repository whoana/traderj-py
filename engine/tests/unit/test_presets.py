"""Unit tests for strategy presets validation.

Verifies all 7 presets have valid, consistent configurations.
"""

from __future__ import annotations

import pytest

from engine.strategy.presets import (
    DEFAULT_PRESET,
    STRATEGY_PRESETS,
    STR_001,
    STR_002,
    STR_003,
    STR_004,
    STR_005,
    STR_006,
    StrategyPreset,
)
from shared.enums import EntryMode, ScoringMode


ALL_PRESETS = [DEFAULT_PRESET, STR_001, STR_002, STR_003, STR_004, STR_005, STR_006]


class TestPresetRegistry:
    def test_registry_has_7_presets(self):
        assert len(STRATEGY_PRESETS) == 7

    def test_unique_strategy_ids(self):
        ids = [p.strategy_id for p in ALL_PRESETS]
        assert len(ids) == len(set(ids))

    def test_all_presets_in_registry(self):
        for preset in ALL_PRESETS:
            assert preset.strategy_id in STRATEGY_PRESETS
            assert STRATEGY_PRESETS[preset.strategy_id] is preset


class TestPresetValues:
    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_buy_threshold_positive(self, preset: StrategyPreset):
        assert preset.buy_threshold > 0

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_sell_threshold_negative(self, preset: StrategyPreset):
        assert preset.sell_threshold < 0

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_tf_weights_sum_at_most_1(self, preset: StrategyPreset):
        total = sum(preset.tf_weights.values())
        assert total <= 1.0 + 1e-9, f"tf_weights sum {total} exceeds 1.0"

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_tf_weights_positive(self, preset: StrategyPreset):
        for tf, w in preset.tf_weights.items():
            assert w > 0, f"{tf} weight is not positive"

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_score_weights_valid(self, preset: StrategyPreset):
        sw = preset.score_weights
        assert sw.w1 >= 0 and sw.w1 <= 1
        assert sw.w2 >= 0 and sw.w2 <= 1
        assert sw.w3 >= 0 and sw.w3 <= 1
        total = sw.w1 + sw.w2 + sw.w3
        assert abs(total - 1.0) < 0.01, f"score_weights sum {total} != 1.0"

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_macro_weight_in_range(self, preset: StrategyPreset):
        assert 0 <= preset.macro_weight <= 1.0

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_valid_scoring_mode(self, preset: StrategyPreset):
        assert preset.scoring_mode in (ScoringMode.TREND_FOLLOW, ScoringMode.HYBRID)

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_valid_entry_mode(self, preset: StrategyPreset):
        assert preset.entry_mode in (EntryMode.WEIGHTED, EntryMode.MAJORITY)

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_majority_min_at_least_1(self, preset: StrategyPreset):
        assert preset.majority_min >= 1

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_has_name(self, preset: StrategyPreset):
        assert len(preset.name) > 0

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.strategy_id)
    def test_frozen(self, preset: StrategyPreset):
        with pytest.raises(AttributeError):
            preset.name = "changed"  # type: ignore[misc]


class TestSpecificPresets:
    def test_str001_conservative(self):
        assert STR_001.buy_threshold >= 0.05
        assert "4h" in STR_001.tf_weights
        assert "1d" in STR_001.tf_weights

    def test_str002_aggressive(self):
        assert STR_002.buy_threshold <= 0.15
        assert "1h" in STR_002.tf_weights

    def test_str003_hybrid(self):
        assert STR_003.scoring_mode == ScoringMode.HYBRID

    def test_str004_majority(self):
        assert STR_004.entry_mode == EntryMode.MAJORITY

    def test_str005_low_frequency(self):
        assert "1d" in STR_005.tf_weights

    def test_str006_scalper(self):
        assert STR_006.buy_threshold <= 0.12
