"""Guardrails — parameter change safety rules.

Validates and clamps proposed parameter changes to prevent
extreme modifications that could destabilize the strategy.
"""

from __future__ import annotations

import logging
from dataclasses import replace as dc_replace

from engine.tuner.config import ALL_BOUNDS, GuardrailSettings
from engine.tuner.enums import DiagnosisDirection, TierLevel
from engine.tuner.models import GuardrailResult, ParameterBounds, ParameterChange
from engine.tuner.store import TunerStore

logger = logging.getLogger(__name__)


class Guardrails:
    """Parameter change safety rules."""

    def __init__(self, config: GuardrailSettings, tuner_store: TunerStore) -> None:
        self._config = config
        self._store = tuner_store

    async def validate_changes(
        self,
        changes: list[ParameterChange],
        strategy_id: str,
    ) -> GuardrailResult:
        """Validate and clamp proposed parameter changes.

        Rules:
        1. Each |change_pct| <= max_change_pct (clamp if exceeded)
        2. Each value within ParameterBounds.min_value~max_value
        3. tf_weights sum = 1.0 (normalize)
        4. score_weights sum = 1.0 (normalize)
        5. Tier 2: consecutive same-direction blocked
        6. Tier 3 included: requires_approval = True
        """
        violations: list[str] = []
        clamped: list[ParameterChange] = []
        requires_approval = False

        for change in changes:
            bounds = ALL_BOUNDS.get(change.parameter_name)
            if not bounds:
                violations.append(f"Unknown parameter: {change.parameter_name}")
                continue

            # Clamp value to safe range
            new_value = self.clamp_change(
                change.parameter_name,
                change.old_value,
                change.new_value,
                bounds,
            )

            # Track if clamping occurred
            if new_value != change.new_value:
                violations.append(
                    f"{change.parameter_name}: clamped {change.new_value:.4f} -> {new_value:.4f}"
                )

            # Recalculate change_pct
            if change.old_value != 0:
                new_change_pct = (new_value - change.old_value) / abs(change.old_value)
            else:
                new_change_pct = 0.0

            clamped.append(ParameterChange(
                parameter_name=change.parameter_name,
                tier=change.tier,
                old_value=change.old_value,
                new_value=new_value,
                change_pct=new_change_pct,
            ))

            # Tier 2: check consecutive direction
            if change.tier == TierLevel.TIER_2:
                direction = (
                    DiagnosisDirection.INCREASE
                    if new_value > change.old_value
                    else DiagnosisDirection.DECREASE
                )
                allowed = await self.check_tier2_direction(
                    strategy_id, change.parameter_name, direction,
                )
                if not allowed:
                    violations.append(
                        f"{change.parameter_name}: consecutive same-direction change blocked"
                    )

            # Tier 3: requires human approval
            if change.tier == TierLevel.TIER_3:
                requires_approval = True

        # Normalize weight groups
        clamped = self.normalize_weights(clamped, "tf_weight_")
        clamped = self.normalize_weights(clamped, "score_w")

        passed = len([v for v in violations if "blocked" in v]) == 0

        return GuardrailResult(
            passed=passed,
            violations=violations,
            clamped_changes=clamped,
            requires_approval=requires_approval,
        )

    def clamp_change(
        self,
        param_name: str,
        old_value: float,
        proposed_value: float,
        bounds: ParameterBounds,
    ) -> float:
        """Clamp proposed value to safe range.

        1. max_change = |old_value| * bounds.max_change_pct
        2. clamp to [old - max_change, old + max_change]
        3. clamp to [bounds.min_value, bounds.max_value]
        """
        max_change = abs(old_value) * bounds.max_change_pct
        if max_change == 0:
            # For zero old_value, use absolute bounds range * max_change_pct
            max_change = (bounds.max_value - bounds.min_value) * bounds.max_change_pct

        # Step 1: clamp to max change range
        clamped = max(old_value - max_change, min(proposed_value, old_value + max_change))

        # Step 2: clamp to absolute bounds
        clamped = max(bounds.min_value, min(clamped, bounds.max_value))

        return round(clamped, 6)

    async def check_tier2_direction(
        self,
        strategy_id: str,
        param_name: str,
        direction: DiagnosisDirection,
    ) -> bool:
        """Check if a Tier 2 parameter's last change was in the same direction.

        Same direction → False (blocked).
        Different direction or no history → True (allowed).
        """
        last_direction = await self._store.get_last_change_direction(
            strategy_id, param_name,
        )
        if last_direction is None:
            return True
        return last_direction != direction

    @staticmethod
    def normalize_weights(
        changes: list[ParameterChange],
        prefix: str,
    ) -> list[ParameterChange]:
        """Normalize a group of weight parameters so they sum to 1.0."""
        group_indices: list[int] = []
        group_values: list[float] = []

        for i, c in enumerate(changes):
            if c.parameter_name.startswith(prefix):
                group_indices.append(i)
                group_values.append(c.new_value)

        if not group_indices:
            return changes

        total = sum(group_values)
        if total == 0 or abs(total - 1.0) < 1e-9:
            return changes

        # Normalize
        result = list(changes)
        for idx, val in zip(group_indices, group_values):
            normalized = val / total
            old_change = result[idx]
            if old_change.old_value != 0:
                new_pct = (normalized - old_change.old_value) / abs(old_change.old_value)
            else:
                new_pct = 0.0
            result[idx] = ParameterChange(
                parameter_name=old_change.parameter_name,
                tier=old_change.tier,
                old_value=old_change.old_value,
                new_value=round(normalized, 6),
                change_pct=new_pct,
            )

        return result
