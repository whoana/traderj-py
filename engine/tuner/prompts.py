"""LLM prompt templates for AI Tuner."""

from __future__ import annotations

import json
import re
from typing import Any

SYSTEM_PROMPT = (
    "You are a BTC/KRW automated trading strategy analyst. "
    "You analyze strategy performance metrics and recommend parameter adjustments. "
    "Always respond in valid JSON format. Do not include markdown code fences."
)

DIAGNOSIS_TEMPLATE = """\
Below are the performance metrics for strategy {strategy_id} ({strategy_name}) \
over the past {eval_days} days:

- Regime: {regime}
- Total trades: {total_trades}
- Win rate: {win_rate:.1%}
- Profit Factor: {profit_factor:.2f}
- Max Drawdown: {max_drawdown:.2%}
- Avg R-multiple: {avg_r_multiple:.2f}
- Avg holding time: {avg_holding_hours:.1f}h
- Signal accuracy: {signal_accuracy:.1%}
- Total return: {total_return_pct:.2%}
- Current parameters: {current_params_json}

Analyze:
1. Root cause of underperformance (1-2 causes, be specific)
2. Which Tier {tier} parameters to adjust (from: {adjustable_params})
3. Direction (increase/decrease) and reasoning

Respond in JSON:
{{
  "root_causes": ["cause1", "cause2"],
  "recommended_params": [
    {{"name": "param_name", "direction": "increase|decrease", "reason": "..."}}
  ],
  "confidence": "high|medium|low"
}}"""

CANDIDATE_SELECTION_TEMPLATE = """\
Optuna generated {n_candidates} parameter candidates for {strategy_id}:

{candidates_text}

Current market context:
- Regime: {regime} (lasted {regime_duration}h)
- 7d BTC/KRW price range: {btc_range}
- Recent volume vs 20d average: {volume_ratio:.0%}
- Current ADX: {adx:.1f}, BB Width: {bb_width:.4f}

Select the best candidate considering:
1. Risk-adjusted performance (PF vs MDD tradeoff)
2. Trade frequency (too few = unreliable, too many = overtrading)
3. Current market conditions

Respond in JSON:
{{
  "selected_candidate_id": "candidate_id",
  "reasoning": "explanation",
  "risk_assessment": "assessment of downside risk",
  "confidence": "high|medium|low"
}}"""

APPROVAL_TEMPLATE = """\
Safety validation results for {strategy_id} parameter change:

Proposed changes:
{changes_text}

30-day simulation results:
- PF: {sim_pf:.2f} (baseline: {base_pf:.2f})
- MDD: {sim_mdd:.2%} (baseline: {base_mdd:.2%})
- Trades: {sim_trades} (baseline: {base_trades})
- Win rate: {sim_win_rate:.1%} (baseline: {base_win_rate:.1%})

Should this change be approved? Consider:
1. Is the improvement statistically significant given {sim_trades} trades?
2. Is the MDD acceptable relative to the improvement?
3. Are there signs of overfitting (e.g., profit from few outlier trades)?

Respond in JSON:
{{
  "approved": true,
  "reason": "detailed justification",
  "confidence": "high|medium|low"
}}"""

SUMMARY_TEMPLATE = """\
Summarize this tuning session in 2-3 Korean sentences for the operator:
Strategy: {strategy_id}
Changes: {changes_text}
Before: PF={old_pf:.2f}, Win={old_win:.1%}, MDD={old_mdd:.2%}
After (simulated): PF={new_pf:.2f}, Win={new_win:.1%}, MDD={new_mdd:.2%}
LLM diagnosis: {diagnosis_summary}"""


def parse_llm_json(text: str) -> dict[str, Any]:
    """Extract and parse JSON from LLM response text.

    Tries in order:
    1. Direct json.loads()
    2. Extract from ```json ... ``` code block
    3. Extract first { ... } block (brace-matched)
    """
    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Code block extraction
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Brace-matched extraction
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    msg = f"Failed to parse JSON from LLM response: {text[:200]}"
    raise ValueError(msg)
