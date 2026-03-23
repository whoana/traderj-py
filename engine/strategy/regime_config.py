"""Regime-adaptive configuration for DCA and Grid strategies.

Maps 6 market regimes to optimized DCA/Grid parameters:
  - BULL_TREND: DCA increases buy frequency + amount, Grid pauses
  - BEAR_TREND: DCA drastically reduces amount + strict RSI filter, Grid pauses
  - RANGING: Grid activates with tighter grids, DCA reduces frequency
  - HIGH_VOL: Wider grids, smaller DCA amounts, stricter volatility caps
  - LOW_VOL: Tighter grids, normal DCA amounts
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.strategy.dca import DCAConfig
from engine.strategy.grid import GridConfig, GridType
from shared.enums import RegimeType


@dataclass(frozen=True)
class DCARegimePreset:
    """DCA parameters optimized for a specific regime."""

    name: str
    regime: RegimeType
    config: DCAConfig


@dataclass(frozen=True)
class GridRegimePreset:
    """Grid parameters optimized for a specific regime."""

    name: str
    regime: RegimeType
    enabled: bool  # Grid should only run in ranging markets
    grid_count: int
    grid_type: GridType
    investment_per_grid: float
    range_pct: float  # grid range as % of current price (e.g., 0.10 = +-5%)


# ── DCA Regime Presets ──────────────────────────────────────────

DCA_BULL_TREND_HIGH_VOL = DCARegimePreset(
    name="DCA Bull Trend High Vol",
    regime=RegimeType.BULL_TREND_HIGH_VOL,
    config=DCAConfig(
        base_buy_krw=150_000,       # 상승추세: 금액 증가 (1.5x)
        interval_hours=12,          # 더 자주 매수 (12h)
        use_rsi_scaling=True,
        rsi_oversold=30.0,
        rsi_overbought=75.0,        # 과매수 기준 약간 완화 (추세 추종)
        rsi_skip=85.0,              # skip 기준 완화
        rsi_scale_up=2.0,           # 과매도 시 더 공격적
        rsi_scale_down=0.5,
        max_position_pct=0.60,      # 포지션 한도 상향
        volatility_cap_pct=0.10,    # 변동성 캡 완화 (고변동 허용)
    ),
)

DCA_BULL_TREND_LOW_VOL = DCARegimePreset(
    name="DCA Bull Trend Low Vol",
    regime=RegimeType.BULL_TREND_LOW_VOL,
    config=DCAConfig(
        base_buy_krw=120_000,       # 약간 증가 (1.2x)
        interval_hours=18,          # 보수적으로 자주
        use_rsi_scaling=True,
        rsi_oversold=30.0,
        rsi_overbought=70.0,
        rsi_skip=80.0,
        rsi_scale_up=1.5,
        rsi_scale_down=0.5,
        max_position_pct=0.55,
        volatility_cap_pct=0.08,
    ),
)

DCA_BEAR_TREND_HIGH_VOL = DCARegimePreset(
    name="DCA Bear Trend High Vol",
    regime=RegimeType.BEAR_TREND_HIGH_VOL,
    config=DCAConfig(
        base_buy_krw=30_000,        # 하락장+고변동: 금액 대폭 축소 (0.3x)
        interval_hours=72,          # 빈도 대폭 줄임 (3일)
        use_rsi_scaling=True,
        rsi_oversold=22.0,          # 극단적 과매도에서만 매수
        rsi_overbought=60.0,        # 과매수 기준 강화
        rsi_skip=70.0,
        rsi_scale_up=1.0,           # 스케일링 최소화
        rsi_scale_down=0.2,
        max_position_pct=0.15,      # 포지션 한도 대폭 축소
        volatility_cap_pct=0.12,    # 고변동 허용하되 캡 존재
    ),
)

DCA_BEAR_TREND_LOW_VOL = DCARegimePreset(
    name="DCA Bear Trend Low Vol",
    regime=RegimeType.BEAR_TREND_LOW_VOL,
    config=DCAConfig(
        base_buy_krw=50_000,        # 하락장+저변동: 금액 축소 (0.5x)
        interval_hours=48,          # 빈도 줄임 (2일)
        use_rsi_scaling=True,
        rsi_oversold=25.0,          # 과매도에서만 매수
        rsi_overbought=65.0,
        rsi_skip=75.0,
        rsi_scale_up=1.2,
        rsi_scale_down=0.3,
        max_position_pct=0.25,      # 포지션 한도 축소
        volatility_cap_pct=0.06,
    ),
)

DCA_RANGING_HIGH_VOL = DCARegimePreset(
    name="DCA Ranging High Vol",
    regime=RegimeType.RANGING_HIGH_VOL,
    config=DCAConfig(
        base_buy_krw=70_000,        # 횡보+고변동: 금액 축소 (0.7x)
        interval_hours=48,          # 빈도 줄임 (Grid에 위임)
        use_rsi_scaling=True,
        rsi_oversold=25.0,          # RSI 과매도 기준 강화
        rsi_overbought=65.0,        # 과매수 기준 강화
        rsi_skip=75.0,
        rsi_scale_up=1.5,
        rsi_scale_down=0.3,
        max_position_pct=0.40,      # 포지션 한도 축소
        volatility_cap_pct=0.10,    # 고변동 허용
    ),
)

DCA_RANGING_LOW_VOL = DCARegimePreset(
    name="DCA Ranging Low Vol",
    regime=RegimeType.RANGING_LOW_VOL,
    config=DCAConfig(
        base_buy_krw=80_000,        # 횡보+저변동: 약간 축소
        interval_hours=36,          # 빈도 줄임
        use_rsi_scaling=True,
        rsi_oversold=28.0,
        rsi_overbought=68.0,
        rsi_skip=78.0,
        rsi_scale_up=1.5,
        rsi_scale_down=0.4,
        max_position_pct=0.45,
        volatility_cap_pct=0.06,    # 저변동 구간이므로 캡 타이트
    ),
)

DCA_REGIME_MAP: dict[RegimeType, DCARegimePreset] = {
    RegimeType.BULL_TREND_HIGH_VOL: DCA_BULL_TREND_HIGH_VOL,
    RegimeType.BULL_TREND_LOW_VOL: DCA_BULL_TREND_LOW_VOL,
    RegimeType.BEAR_TREND_HIGH_VOL: DCA_BEAR_TREND_HIGH_VOL,
    RegimeType.BEAR_TREND_LOW_VOL: DCA_BEAR_TREND_LOW_VOL,
    RegimeType.RANGING_HIGH_VOL: DCA_RANGING_HIGH_VOL,
    RegimeType.RANGING_LOW_VOL: DCA_RANGING_LOW_VOL,
}


# ── Grid Regime Presets ──────────────────────────────────────────

GRID_BULL_TREND_HIGH_VOL = GridRegimePreset(
    name="Grid Bull Trend High Vol",
    regime=RegimeType.BULL_TREND_HIGH_VOL,
    enabled=False,                  # 상승추세에서 Grid 비활성화
    grid_count=0,
    grid_type=GridType.ARITHMETIC,
    investment_per_grid=0,
    range_pct=0,
)

GRID_BULL_TREND_LOW_VOL = GridRegimePreset(
    name="Grid Bull Trend Low Vol",
    regime=RegimeType.BULL_TREND_LOW_VOL,
    enabled=False,                  # 상승추세에서 Grid 비활성화
    grid_count=0,
    grid_type=GridType.ARITHMETIC,
    investment_per_grid=0,
    range_pct=0,
)

GRID_BEAR_TREND_HIGH_VOL = GridRegimePreset(
    name="Grid Bear Trend High Vol",
    regime=RegimeType.BEAR_TREND_HIGH_VOL,
    enabled=False,                  # 하락추세에서 Grid 비활성화
    grid_count=0,
    grid_type=GridType.ARITHMETIC,
    investment_per_grid=0,
    range_pct=0,
)

GRID_BEAR_TREND_LOW_VOL = GridRegimePreset(
    name="Grid Bear Trend Low Vol",
    regime=RegimeType.BEAR_TREND_LOW_VOL,
    enabled=False,                  # 하락추세에서 Grid 비활성화
    grid_count=0,
    grid_type=GridType.ARITHMETIC,
    investment_per_grid=0,
    range_pct=0,
)

GRID_RANGING_HIGH_VOL = GridRegimePreset(
    name="Grid Ranging High Vol",
    regime=RegimeType.RANGING_HIGH_VOL,
    enabled=True,                   # 횡보 고변동: Grid 활성화
    grid_count=8,                   # 넓은 그리드 (변동성 대응)
    grid_type=GridType.GEOMETRIC,   # % 기반 간격 (고변동에 적합)
    investment_per_grid=120_000,
    range_pct=0.12,                 # +-6% 범위
)

GRID_RANGING_LOW_VOL = GridRegimePreset(
    name="Grid Ranging Low Vol",
    regime=RegimeType.RANGING_LOW_VOL,
    enabled=True,                   # 횡보 저변동: Grid 활성화
    grid_count=12,                  # 촘촘한 그리드 (좁은 범위)
    grid_type=GridType.ARITHMETIC,  # 균등 간격 (저변동에 적합)
    investment_per_grid=80_000,
    range_pct=0.06,                 # +-3% 범위
)

GRID_REGIME_MAP: dict[RegimeType, GridRegimePreset] = {
    RegimeType.BULL_TREND_HIGH_VOL: GRID_BULL_TREND_HIGH_VOL,
    RegimeType.BULL_TREND_LOW_VOL: GRID_BULL_TREND_LOW_VOL,
    RegimeType.BEAR_TREND_HIGH_VOL: GRID_BEAR_TREND_HIGH_VOL,
    RegimeType.BEAR_TREND_LOW_VOL: GRID_BEAR_TREND_LOW_VOL,
    RegimeType.RANGING_HIGH_VOL: GRID_RANGING_HIGH_VOL,
    RegimeType.RANGING_LOW_VOL: GRID_RANGING_LOW_VOL,
}


def build_grid_config(
    preset: GridRegimePreset,
    current_price: float,
) -> GridConfig | None:
    """Build a GridConfig from a regime preset and current price.

    Returns None if grid is disabled for this regime.
    """
    if not preset.enabled or current_price <= 0:
        return None

    half_range = current_price * preset.range_pct / 2
    lower = current_price - half_range
    upper = current_price + half_range

    return GridConfig(
        upper_price=round(upper, 0),
        lower_price=round(lower, 0),
        num_grids=preset.grid_count,
        grid_type=preset.grid_type,
        investment_per_grid=preset.investment_per_grid,
        max_total_investment=preset.investment_per_grid * preset.grid_count,
    )
