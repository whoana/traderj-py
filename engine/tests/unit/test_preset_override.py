"""Unit tests for preset_override.py — JSON override persistence."""

from __future__ import annotations

import json

import pytest

from engine.strategy.preset_override import (
    clear_all,
    clear_override,
    get_preset_overrides,
    get_regime_map_overrides,
    load_overrides,
    save_override,
    save_regime_map,
)


class TestLoadOverrides:
    def test_returns_empty_on_missing_file(self, tmp_path):
        data = load_overrides(str(tmp_path))
        assert data == {"version": 1, "presets": {}, "regime_map": {}}

    def test_loads_valid_file(self, tmp_path):
        f = tmp_path / "preset_overrides.json"
        f.write_text(json.dumps({"version": 1, "presets": {"STR-001": {"buy_threshold": 0.2}}, "regime_map": {}}))
        data = load_overrides(str(tmp_path))
        assert data["presets"]["STR-001"]["buy_threshold"] == 0.2

    def test_returns_empty_on_corrupt_json(self, tmp_path):
        f = tmp_path / "preset_overrides.json"
        f.write_text("not json at all {{{")
        data = load_overrides(str(tmp_path))
        assert data == {"version": 1, "presets": {}, "regime_map": {}}

    def test_returns_empty_on_invalid_structure(self, tmp_path):
        f = tmp_path / "preset_overrides.json"
        f.write_text(json.dumps({"no_presets_key": True}))
        data = load_overrides(str(tmp_path))
        assert data == {"version": 1, "presets": {}, "regime_map": {}}


class TestSaveOverride:
    def test_save_creates_file(self, tmp_path):
        path = save_override("STR-001", {"buy_threshold": 0.2}, str(tmp_path))
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["presets"]["STR-001"]["buy_threshold"] == 0.2

    def test_save_merges_existing(self, tmp_path):
        save_override("STR-001", {"buy_threshold": 0.2}, str(tmp_path))
        save_override("STR-001", {"sell_threshold": -0.15}, str(tmp_path))
        data = load_overrides(str(tmp_path))
        assert data["presets"]["STR-001"]["buy_threshold"] == 0.2
        assert data["presets"]["STR-001"]["sell_threshold"] == -0.15

    def test_save_multiple_strategies(self, tmp_path):
        save_override("STR-001", {"buy_threshold": 0.2}, str(tmp_path))
        save_override("STR-003", {"macro_weight": 0.5}, str(tmp_path))
        data = load_overrides(str(tmp_path))
        assert "STR-001" in data["presets"]
        assert "STR-003" in data["presets"]

    def test_save_sets_updated_at(self, tmp_path):
        save_override("STR-001", {"buy_threshold": 0.2}, str(tmp_path))
        data = load_overrides(str(tmp_path))
        assert "updated_at" in data


class TestSaveRegimeMap:
    def test_save_regime_map(self, tmp_path):
        save_regime_map({"TRENDING": "STR-009", "MEAN_REVERTING": "STR-003"}, str(tmp_path))
        data = load_overrides(str(tmp_path))
        assert data["regime_map"]["TRENDING"] == "STR-009"

    def test_regime_map_merges(self, tmp_path):
        save_regime_map({"TRENDING": "STR-009"}, str(tmp_path))
        save_regime_map({"MEAN_REVERTING": "STR-003"}, str(tmp_path))
        data = load_overrides(str(tmp_path))
        assert data["regime_map"]["TRENDING"] == "STR-009"
        assert data["regime_map"]["MEAN_REVERTING"] == "STR-003"


class TestGetOverrides:
    def test_get_existing(self, tmp_path):
        save_override("STR-001", {"buy_threshold": 0.2}, str(tmp_path))
        result = get_preset_overrides("STR-001", str(tmp_path))
        assert result == {"buy_threshold": 0.2}

    def test_get_nonexistent(self, tmp_path):
        result = get_preset_overrides("STR-999", str(tmp_path))
        assert result == {}

    def test_get_regime_map(self, tmp_path):
        save_regime_map({"TRENDING": "STR-009"}, str(tmp_path))
        result = get_regime_map_overrides(str(tmp_path))
        assert result == {"TRENDING": "STR-009"}


class TestClear:
    def test_clear_specific_strategy(self, tmp_path):
        save_override("STR-001", {"buy_threshold": 0.2}, str(tmp_path))
        save_override("STR-003", {"macro_weight": 0.5}, str(tmp_path))
        assert clear_override("STR-001", str(tmp_path)) is True
        data = load_overrides(str(tmp_path))
        assert "STR-001" not in data["presets"]
        assert "STR-003" in data["presets"]

    def test_clear_nonexistent_returns_false(self, tmp_path):
        assert clear_override("STR-999", str(tmp_path)) is False

    def test_clear_all(self, tmp_path):
        save_override("STR-001", {"buy_threshold": 0.2}, str(tmp_path))
        assert clear_all(str(tmp_path)) is True
        data = load_overrides(str(tmp_path))
        assert data == {"version": 1, "presets": {}, "regime_map": {}}

    def test_clear_all_no_file(self, tmp_path):
        assert clear_all(str(tmp_path)) is False
