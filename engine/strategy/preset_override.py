"""JSON-based preset override persistence.

Saves optimized parameters to /data/preset_overrides.json (Fly.io volume)
so they survive engine restarts. Only changed parameters are stored (sparse override).
Falls back to presets.py defaults on JSON corruption or missing file.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default path: /data on Fly.io volume, or local ./data for dev
_DEFAULT_DIR = os.environ.get("OVERRIDE_DATA_DIR", "/data")
_OVERRIDE_FILENAME = "preset_overrides.json"


def _override_path(data_dir: str | None = None) -> Path:
    d = data_dir or _DEFAULT_DIR
    return Path(d) / _OVERRIDE_FILENAME


def load_overrides(data_dir: str | None = None) -> dict[str, Any]:
    """Load the override file. Returns empty structure on any error."""
    path = _override_path(data_dir)
    if not path.exists():
        return {"version": 1, "presets": {}, "regime_map": {}}
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict) or "presets" not in data:
            logger.warning("preset_overrides.json has invalid structure, ignoring")
            return {"version": 1, "presets": {}, "regime_map": {}}
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load preset_overrides.json: %s", e)
        return {"version": 1, "presets": {}, "regime_map": {}}


def _normalize_weights(params: dict[str, float]) -> dict[str, float]:
    """Normalize score_w and tf_weight groups to sum to 1.0 before saving."""
    result = dict(params)

    # Normalize score weights
    sw_keys = [k for k in result if k.startswith("score_w")]
    if sw_keys:
        total = sum(result[k] for k in sw_keys)
        if total > 0:
            for k in sw_keys:
                result[k] = result[k] / total
            # Force exact sum via last key
            if len(sw_keys) >= 2:
                result[sw_keys[-1]] = 1.0 - sum(result[k] for k in sw_keys[:-1])

    # Normalize tf weights
    tf_keys = [k for k in result if k.startswith("tf_weight_")]
    if tf_keys:
        total = sum(result[k] for k in tf_keys)
        if total > 0:
            for k in tf_keys:
                result[k] = result[k] / total

    return result


def save_override(
    strategy_id: str,
    params: dict[str, float],
    data_dir: str | None = None,
) -> Path:
    """Save parameter overrides for a strategy (sparse — changed params only).

    Merges into existing overrides. Returns the path written.
    """
    params = _normalize_weights(params)
    data = load_overrides(data_dir)
    existing = data.get("presets", {}).get(strategy_id, {})
    existing.update(params)
    data.setdefault("presets", {})[strategy_id] = existing
    data["updated_at"] = datetime.now(UTC).isoformat()
    data["version"] = data.get("version", 1)

    path = _override_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: write to temp then rename
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    logger.info("Saved preset override for %s: %s", strategy_id, params)
    return path


def save_regime_map(
    regime_map: dict[str, str],
    data_dir: str | None = None,
) -> Path:
    """Save regime-strategy mapping overrides.

    Merges into existing regime_map. Returns the path written.
    """
    data = load_overrides(data_dir)
    existing_map = data.get("regime_map", {})
    existing_map.update(regime_map)
    data["regime_map"] = existing_map
    data["updated_at"] = datetime.now(UTC).isoformat()

    path = _override_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    logger.info("Saved regime map override: %s", regime_map)
    return path


def get_preset_overrides(strategy_id: str, data_dir: str | None = None) -> dict[str, float]:
    """Get override params for a specific strategy. Returns empty dict if none."""
    data = load_overrides(data_dir)
    return data.get("presets", {}).get(strategy_id, {})


def get_regime_map_overrides(data_dir: str | None = None) -> dict[str, str]:
    """Get regime map overrides. Returns empty dict if none."""
    data = load_overrides(data_dir)
    return data.get("regime_map", {})


def clear_override(strategy_id: str, data_dir: str | None = None) -> bool:
    """Remove all overrides for a strategy. Returns True if anything was removed."""
    data = load_overrides(data_dir)
    presets = data.get("presets", {})
    if strategy_id not in presets:
        return False
    del presets[strategy_id]
    data["updated_at"] = datetime.now(UTC).isoformat()

    path = _override_path(data_dir)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    logger.info("Cleared preset override for %s", strategy_id)
    return True


def clear_all(data_dir: str | None = None) -> bool:
    """Remove the entire override file."""
    path = _override_path(data_dir)
    if path.exists():
        path.unlink()
        logger.info("Cleared all preset overrides")
        return True
    return False
