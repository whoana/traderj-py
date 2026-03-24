"""HybridOptimizer — Optuna Bayesian optimization + LLM candidate selection.

Combines statistical search (Optuna TPE) with LLM-guided candidate
selection and approval for parameter optimization.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable

import optuna
import pandas as pd

from engine.strategy.backtest.engine import BacktestConfig, BacktestEngine
from engine.strategy.backtest.walk_forward import (
    WalkForwardConfig,
    WalkForwardEngine,
)
from engine.strategy.risk import RiskConfig
from engine.strategy.signal import SignalGenerator
from engine.tuner.config import ALL_BOUNDS, GuardrailSettings, get_bounds_for_tier
from engine.tuner.degraded import DegradedFallback
from engine.tuner.enums import LLMConfidence, LLMProviderName, TierLevel
from engine.tuner.models import (
    EvaluationResult,
    OptimizerCandidate,
    OptimizationResult,
    ParameterBounds,
    TuningDecision,
)
from engine.tuner.prompts import (
    APPROVAL_TEMPLATE,
    CANDIDATE_SELECTION_TEMPLATE,
    SYSTEM_PROMPT,
    parse_llm_json,
)
from engine.tuner.provider_router import ProviderRouter

logger = logging.getLogger(__name__)

# Silence Optuna's verbose logging
optuna.logging.set_verbosity(optuna.logging.WARNING)


class HybridOptimizer:
    """Optuna Bayesian optimization + LLM candidate selection."""

    def __init__(
        self,
        provider_router: ProviderRouter,
        degraded: DegradedFallback,
        config: GuardrailSettings,
    ) -> None:
        self._router = provider_router
        self._degraded = degraded
        self._config = config

    async def optimize(
        self,
        strategy_id: str,
        evaluation: EvaluationResult,
        tier: TierLevel,
        current_params: dict[str, float],
        ohlcv_by_tf: dict[str, pd.DataFrame],
        signal_generator: SignalGenerator,
        risk_config: RiskConfig | None = None,
    ) -> OptimizationResult:
        """Run Optuna optimization + LLM selection + safety validation.

        Steps:
        1. Determine search bounds from tier + current params
        2. Run Optuna study (n_trials)
        3. Select top-k candidates
        4. LLM selects best candidate (fallback: degraded)
        5. Safety validation via backtest
        6. LLM approval (fallback: degraded)
        7. Return OptimizationResult
        """
        bounds = get_bounds_for_tier(tier)
        n_trials = self._config.optuna_n_trials
        top_k = self._config.optuna_top_k

        # 1. Create and run Optuna study
        objective = self._create_optuna_objective(
            strategy_id=strategy_id,
            tier=tier,
            current_params=current_params,
            ohlcv_by_tf=ohlcv_by_tf,
            signal_generator=signal_generator,
            risk_config=risk_config,
        )

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        # 2. Extract top-k candidates
        sorted_trials = sorted(
            [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE],
            key=lambda t: t.value if t.value is not None else float("-inf"),
            reverse=True,
        )
        top_trials = sorted_trials[:top_k]

        candidates = [
            OptimizerCandidate(
                candidate_id=f"C-{i+1:03d}",
                params=dict(t.params),
                validation_pf=t.value if t.value is not None else 0.0,
                validation_mdd=t.user_attrs.get("mdd", 0.0),
                validation_win_rate=t.user_attrs.get("win_rate", 0.0),
                validation_trades=t.user_attrs.get("trades", 0),
                optuna_trial_number=t.number,
            )
            for i, t in enumerate(top_trials)
        ]

        if not candidates:
            return OptimizationResult(
                candidates=[],
                selected=None,
                decision=TuningDecision(
                    approved=False,
                    selected_candidate=None,
                    reason="No valid Optuna trials completed",
                    provider=LLMProviderName.DEGRADED,
                    model=None,
                ),
                optuna_study_stats=self._study_stats(study),
            )

        # 3. Select best candidate via LLM (fallback: degraded)
        selected = await self._select_candidate(
            strategy_id, candidates, evaluation,
        )

        # 4. Safety validation: backtest selected candidate
        baseline_pf = evaluation.metrics.profit_factor
        baseline_mdd = evaluation.metrics.max_drawdown
        baseline_wr = evaluation.metrics.win_rate
        baseline_trades = evaluation.metrics.total_trades

        sim_result = self._safety_backtest(
            selected, current_params, tier,
            ohlcv_by_tf, signal_generator, risk_config,
        )

        # 5. LLM approval (fallback: degraded)
        decision = await self._approve_candidate(
            strategy_id=strategy_id,
            candidate=selected,
            sim_result=sim_result,
            baseline_pf=baseline_pf,
            baseline_mdd=baseline_mdd,
            baseline_wr=baseline_wr,
            baseline_trades=baseline_trades,
        )

        return OptimizationResult(
            candidates=candidates,
            selected=selected if decision.approved else None,
            decision=decision,
            optuna_study_stats=self._study_stats(study),
        )

    def _create_optuna_objective(
        self,
        strategy_id: str,
        tier: TierLevel,
        current_params: dict[str, float],
        ohlcv_by_tf: dict[str, pd.DataFrame],
        signal_generator: SignalGenerator,
        risk_config: RiskConfig | None = None,
    ) -> Callable[[optuna.Trial], float]:
        """Create Optuna objective function.

        Each trial samples parameters and runs WalkForward backtest.
        Returns validation_pf as the objective (maximize).
        """
        bounds = get_bounds_for_tier(tier)
        max_change_pct = self._config.max_change_pct
        wf_train = self._config.wf_train_bars
        wf_test = self._config.wf_test_bars

        def objective(trial: optuna.Trial) -> float:
            # Sample parameters within narrowed bounds
            trial_params: dict[str, float] = {}
            for b in bounds:
                current_val = current_params.get(b.name, (b.min_value + b.max_value) / 2)
                low, high = self._narrow_bounds(current_val, b, max_change_pct)
                trial_params[b.name] = trial.suggest_float(b.name, low, high)

            # Normalize weight groups
            tf_keys = [k for k in trial_params if k.startswith("tf_weight_")]
            if tf_keys:
                total = sum(trial_params[k] for k in tf_keys)
                if total > 0:
                    for k in tf_keys:
                        trial_params[k] = trial_params[k] / total

            sw_keys = [k for k in trial_params if k.startswith("score_w")]
            if sw_keys:
                total = sum(trial_params[k] for k in sw_keys)
                if total > 0:
                    for k in sw_keys:
                        trial_params[k] = trial_params[k] / total

            # Build modified signal generator
            sig_gen = self._build_signal_generator(signal_generator, trial_params)
            rc = self._build_risk_config(risk_config, trial_params)

            # Run walk-forward
            wf_config = WalkForwardConfig(
                is_bars=wf_train,
                oos_bars=wf_test,
                step_size=wf_test,
            )
            wf_engine = WalkForwardEngine(
                signal_generator=sig_gen,
                risk_config=rc,
                wf_config=wf_config,
            )

            try:
                result = wf_engine.run(ohlcv_by_tf)
            except Exception:
                logger.debug("WF run failed for trial %d", trial.number)
                return 0.0

            metrics = result.aggregate_metrics
            pf = metrics.get("profit_factor", 0.0)
            mdd = metrics.get("max_drawdown_pct", 0.0)
            wr = metrics.get("win_rate", 0.0)
            trades = result.total_oos_trades

            trial.set_user_attr("mdd", mdd)
            trial.set_user_attr("win_rate", wr)
            trial.set_user_attr("trades", trades)

            # Penalize extreme MDD
            if mdd > 0.10:
                return 0.0

            return pf if pf > 0 else 0.0

        return objective

    def _narrow_bounds(
        self,
        current_value: float,
        bounds: ParameterBounds,
        max_change_pct: float,
    ) -> tuple[float, float]:
        """Narrow bounds to ±max_change_pct around current value, intersected with absolute bounds."""
        delta = abs(current_value) * max_change_pct
        if delta == 0:
            delta = (bounds.max_value - bounds.min_value) * max_change_pct

        low = max(bounds.min_value, current_value - delta)
        high = min(bounds.max_value, current_value + delta)

        # Ensure low < high
        if low >= high:
            low = bounds.min_value
            high = bounds.max_value

        return round(low, 6), round(high, 6)

    async def _select_candidate(
        self,
        strategy_id: str,
        candidates: list[OptimizerCandidate],
        evaluation: EvaluationResult,
    ) -> OptimizerCandidate:
        """Select best candidate via LLM or degraded fallback."""
        try:
            candidates_text = "\n".join(
                f"- {c.candidate_id}: PF={c.validation_pf:.2f}, MDD={c.validation_mdd:.2%}, "
                f"WR={c.validation_win_rate:.1%}, trades={c.validation_trades}, "
                f"params={json.dumps({k: round(v, 4) for k, v in c.params.items()})}"
                for c in candidates
            )

            prompt = CANDIDATE_SELECTION_TEMPLATE.format(
                strategy_id=strategy_id,
                n_candidates=len(candidates),
                candidates_text=candidates_text,
                regime=evaluation.metrics.regime or "unknown",
                regime_duration="N/A",
                btc_range="N/A",
                volume_ratio=1.0,
                adx=25.0,
                bb_width=0.04,
            )

            response = await self._router.complete(SYSTEM_PROMPT, prompt)
            if response:
                data = parse_llm_json(response.text)
                selected_id = data.get("selected_candidate_id")
                for c in candidates:
                    if c.candidate_id == selected_id:
                        return c
        except Exception:
            logger.exception("LLM candidate selection failed, using degraded")

        return self._degraded.select_candidate(candidates)

    def _safety_backtest(
        self,
        candidate: OptimizerCandidate,
        current_params: dict[str, float],
        tier: TierLevel,
        ohlcv_by_tf: dict[str, pd.DataFrame],
        signal_generator: SignalGenerator,
        risk_config: RiskConfig | None = None,
    ) -> dict[str, Any]:
        """Run backtest with candidate params for safety validation."""
        sig_gen = self._build_signal_generator(signal_generator, candidate.params)
        rc = self._build_risk_config(risk_config, candidate.params)

        bt_engine = BacktestEngine(
            signal_generator=sig_gen,
            risk_config=rc,
        )

        try:
            result = bt_engine.run(ohlcv_by_tf)
            return {
                "pf": result.metrics.get("profit_factor", 0.0),
                "mdd": result.metrics.get("max_drawdown_pct", 0.0),
                "trades": result.metrics.get("total_trades", 0),
                "win_rate": result.metrics.get("win_rate", 0.0),
            }
        except Exception:
            logger.exception("Safety backtest failed")
            return {"pf": 0.0, "mdd": 1.0, "trades": 0, "win_rate": 0.0}

    async def _approve_candidate(
        self,
        strategy_id: str,
        candidate: OptimizerCandidate,
        sim_result: dict[str, Any],
        baseline_pf: float,
        baseline_mdd: float,
        baseline_wr: float,
        baseline_trades: int,
    ) -> TuningDecision:
        """Approve candidate via LLM or degraded fallback."""
        sim_pf = sim_result.get("pf", 0.0)
        sim_mdd = sim_result.get("mdd", 0.0)
        sim_trades = sim_result.get("trades", 0)
        sim_wr = sim_result.get("win_rate", 0.0)

        try:
            changes_text = "\n".join(
                f"  {k}: {v:.4f}" for k, v in candidate.params.items()
            )
            prompt = APPROVAL_TEMPLATE.format(
                strategy_id=strategy_id,
                changes_text=changes_text,
                sim_pf=sim_pf,
                base_pf=baseline_pf,
                sim_mdd=sim_mdd,
                base_mdd=baseline_mdd,
                sim_trades=sim_trades,
                base_trades=baseline_trades,
                sim_win_rate=sim_wr,
                base_win_rate=baseline_wr,
            )

            response = await self._router.complete(SYSTEM_PROMPT, prompt)
            if response:
                data = parse_llm_json(response.text)
                return TuningDecision(
                    approved=data.get("approved", False),
                    selected_candidate=candidate,
                    reason=data.get("reason", ""),
                    provider=LLMProviderName(response.provider),
                    model=response.model,
                )
        except Exception:
            logger.exception("LLM approval failed, using degraded")

        # Degraded fallback
        approved = self._degraded.approve(
            candidate,
            baseline_pf=baseline_pf,
            baseline_mdd=baseline_mdd,
        )
        return TuningDecision(
            approved=approved,
            selected_candidate=candidate,
            reason="degraded_rule_based_approval",
            provider=LLMProviderName.DEGRADED,
            model=None,
        )

    @staticmethod
    def _build_signal_generator(
        base: SignalGenerator,
        params: dict[str, float],
    ) -> SignalGenerator:
        """Create a new SignalGenerator with modified Tier 1 params."""
        from engine.strategy.scoring import ScoreWeights

        sig = SignalGenerator(
            strategy_id=base.strategy_id,
            scoring_mode=base.scoring_mode,
            entry_mode=base.entry_mode,
            score_weights=base.score_weights,
            tf_weights=dict(base.tf_weights),
            buy_threshold=base.buy_threshold,
            sell_threshold=base.sell_threshold,
            macro_weight=base.macro_weight,
        )

        # Apply Tier 1 params
        if "buy_threshold" in params:
            sig.buy_threshold = params["buy_threshold"]
        if "sell_threshold" in params:
            sig.sell_threshold = params["sell_threshold"]
        if "macro_weight" in params:
            sig.macro_weight = params["macro_weight"]

        # TF weights
        tf_map = {"tf_weight_1h": "1h", "tf_weight_4h": "4h", "tf_weight_1d": "1d"}
        new_tf: dict[str, float] = {}
        for param_name, tf_key in tf_map.items():
            if param_name in params:
                new_tf[tf_key] = params[param_name]
        if new_tf:
            merged = dict(sig.tf_weights)
            merged.update(new_tf)
            sig.tf_weights = merged

        # Score weights (normalize to sum=1.0)
        if any(k.startswith("score_w") for k in params):
            w1 = params.get("score_w1", sig.score_weights.w1)
            w2 = params.get("score_w2", sig.score_weights.w2)
            w3 = params.get("score_w3", sig.score_weights.w3)
            total = w1 + w2 + w3
            if total > 0:
                w1, w2, w3 = w1 / total, w2 / total, w3 / total
            sig.score_weights = ScoreWeights(w1=w1, w2=w2, w3=w3)

        return sig

    @staticmethod
    def _build_risk_config(
        base: RiskConfig | None,
        params: dict[str, float],
    ) -> RiskConfig:
        """Create a new RiskConfig with modified Tier 2 params."""
        from dataclasses import replace

        rc = base or RiskConfig()
        tier2_keys = {
            "atr_stop_multiplier", "reward_risk_ratio",
            "trailing_stop_activation_pct", "trailing_stop_distance_pct",
            "max_position_pct", "volatility_cap_pct", "daily_max_loss_pct",
        }
        overrides = {k: v for k, v in params.items() if k in tier2_keys}
        if overrides:
            rc = replace(rc, **overrides)
        return rc

    @staticmethod
    def _study_stats(study: optuna.Study) -> dict[str, Any]:
        """Extract summary stats from Optuna study."""
        completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
        values = [t.value for t in completed if t.value is not None]
        return {
            "n_trials": len(study.trials),
            "n_completed": len(completed),
            "best_value": study.best_value if completed else None,
            "best_params": dict(study.best_params) if completed else {},
            "value_mean": sum(values) / len(values) if values else 0.0,
            "value_std": (
                (sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)) ** 0.5
                if len(values) > 1
                else 0.0
            ),
        }
