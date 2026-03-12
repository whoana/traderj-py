# HANDOFF: traderj

## Goal

BTC/KRW 자동매매 봇 엔진(TraderJ). SQLite를 기본 DB로 사용하고, 시그널 기반 전략 7종(default + STR-001~006)을 Paper/Backtest/Real 모드로 운영한다. 레짐 감지 -> 전략 자동 전환(Signal + DCA/Grid), Telegram 알림, Dashboard 연동까지 포함.

---

## Current Progress

### COMPLETED -- 180일 Robustness 검증 (2026-03-08)

180일 장기 백테스트 + 파라미터 민감도(+-20%) 분석 수행.

- **180일 수익률**: 0/7 양수 (장기 횡보/하락장). default 가장 양호(-0.05%)
- **파라미터 안정성**: 7/7 Stable — threshold +-20% 변동해도 모두 1pp 이내
- MDD 전체 1.3% 미만, 리스크 관리 유효
- `scripts/run_backtest_robustness.py` 신규 생성

| Strategy | 180d Ret% | Sensitivity Range | Stable? |
|----------|--------:|------------------:|:-------:|
| default  | -0.05 | 0.00pp | YES |
| STR-001  | -0.38 | 0.12pp | YES |
| STR-002  | -0.57 | 0.09pp | YES |
| STR-003  | -0.70 | 0.33pp | YES |
| STR-004  | -0.39 | 0.70pp | YES |
| STR-005  | -0.67 | 0.15pp | YES |
| STR-006  | -0.57 | 0.26pp | YES |

### COMPLETED -- DCA/Grid TradingLoop 연동 (2026-03-08)

레짐 전환 시 TradingLoop 내 DCA/Grid 엔진이 자동으로 재구성됨.

- `engine/loop/trading_loop.py`:
  - `_dca_engine`, `_grid_engine` 필드 추가
  - `_reconfigure_dca_grid()`: 레짐별 DCA/Grid 엔진 생성/비활성화
  - `_get_last_close()`: OHLCV에서 최신 종가 추출
  - DCA 상태(매수 이력) 레짐 전환 시 보존
- 6개 테스트 추가 (test_trading_loop.py)

### COMPLETED -- DCA/Grid 레짐 매핑 (2026-03-08)

레짐별 DCA/Grid 파라미터를 정의하고 RegimeSwitchManager에 통합.

- `engine/strategy/regime_config.py` 신규: DCA/Grid 레짐별 프리셋 + `build_grid_config()`
- `engine/strategy/regime_switch.py`: `get_dca_config()`, `get_grid_config()` 메서드 추가
- 34개 테스트 (27 regime_config + 7 regime_switch 통합)

| 레짐 | DCA | Grid |
|------|-----|------|
| TRENDING_HIGH_VOL | 150K KRW, 12h | 비활성 |
| TRENDING_LOW_VOL | 120K KRW, 18h | 비활성 |
| RANGING_HIGH_VOL | 70K KRW, 48h | 8단계, GEOMETRIC, +-6% |
| RANGING_LOW_VOL | 80K KRW, 36h | 12단계, ARITHMETIC, +-3% |

### COMPLETED -- 전략 파라미터 튜닝 (2026-03-08)

4-Phase 튜닝: BacktestEngine SL/TP 구현 -> 그리드 서치(120조합) -> EMA 보정 -> presets 업데이트. 90일 Before/After에서 3/7 개선.

### COMPLETED -- SQLite 기본 DB 전환 / 레짐 감지 자동 전환 / Telegram 알림 / 용어 설명서

---

## What Worked

- **Grid Search Walk-Forward**: 60d train / 30d OOS 분할로 과적합 방지
- **HYBRID + 장기 TF**: 횡보장에서 HYBRID + 4h/1d 조합이 안정적
- **threshold 하향**: 0.05~0.12로 적정 거래 빈도 확보
- **SL/TP 구현**: BacktestEngine에서 실제 적용. 손실 제한 효과
- **Protocol 기반 추상화**: DataStore Protocol 덕분에 DB 교체 용이
- **RegimeSwitchManager**: debounce(3회) + cooldown(60분)으로 안정적 레짐 전환
- **DCA/Grid 레짐 매핑 분리**: `regime_config.py`로 독립 관리, 기존 코드 최소 변경
- **DCA 상태 보존**: 레짐 전환 시 매수 이력(buy_count, last_buy_time) 유지
- **파라미터 안정성 7/7**: threshold +-20% 변동에도 수익률 변동 1pp 이내

## What Didn't Work

- **15m 타임프레임**: 노이즈 + 속도 저하. 제거 후 개선
- **높은 macro_weight(0.2~0.3)**: 백테스트에서 tech_score 감쇄
- **daily_gate**: 횡보장에서 거래 기회 감소
- **대규모 그리드(720개)**: 6시간+. 120개로 축소 후 45분
- **PYTHONUNBUFFERED 미설정**: 백그라운드 출력 버퍼링 -> PYTHONUNBUFFERED=1 필수
- **RiskEngine logging.WARNING**: 그리드 서치 중 로그 대량 출력 -> logging.ERROR 필요
- **180일 양수 수익률 달성 실패**: 장기 횡보/하락장에서 0/7 전략이 양수. 시장 구조적 한계

---

## Next Steps (순서대로)

### 1. Dashboard Sprint 4 이어서 진행

#### Task 2 완료: Settings Page 나머지
- `src/stores/useSettingsStore.ts`
- `src/components/settings/StrategyConfigForm.tsx`
- `src/app/settings/page.tsx`

#### Task 3: Backtest Viewer
- `src/stores/useBacktestStore.ts`
- `BacktestMetricsCard`, `BacktestEquityCurve`, `BacktestTradeList`, `BacktestResultList`
- `src/app/backtest/page.tsx`

#### Task 4~6: Indicator Overlays, Performance, Tests

### 2. 전략 개선 방향 (선택)
- 라이브용 macro_weight 별도 설정 (백테스트 0.0 vs 라이브 0.1~0.2)
- 상승장 데이터로 백테스트 (현재 180일은 횡보/하락장)
- DCA/Grid 백테스트 엔진 구현 (현재는 Signal 전략만 백테스트 가능)

### 3. Paper Trading 실전 검증 (선택)
- `scripts/run_paper.py`로 실시간 Paper Trading 수행
- 레짐 전환 + DCA/Grid 자동 구성이 실제로 작동하는지 확인

---

## Key Files Reference

| File | Role |
|------|------|
| `engine/config/settings.py` | 모든 설정 (DB, Exchange, Trading, Telegram) |
| `engine/data/__init__.py` | `create_data_store()` 팩토리 |
| `engine/data/sqlite_store.py` | SQLite DataStore (기본) |
| `engine/data/postgres_store.py` | PostgreSQL DataStore (옵션) |
| `engine/bootstrap.py` | 앱 부트스트랩 (컴포넌트 와이어링) |
| `engine/strategy/signal.py` | SignalGenerator (8단계 파이프라인) |
| `engine/strategy/presets.py` | 전략 프리셋 정의 (7개, 튜닝 완료) |
| `engine/strategy/filters.py` | 스코어링 함수 (trend/momentum/volume 등) |
| `engine/strategy/backtest/engine.py` | BacktestEngine (SL/TP/Trailing 포함) |
| `engine/strategy/risk.py` | RiskEngine + RiskConfig + RiskDecision |
| `engine/strategy/dca.py` | DCA 전략 엔진 |
| `engine/strategy/grid.py` | Grid 전략 엔진 |
| `engine/strategy/regime_config.py` | DCA/Grid 레짐별 프리셋 + build_grid_config() |
| `engine/strategy/regime_switch.py` | RegimeSwitchManager (Signal + DCA/Grid 통합) |
| `engine/loop/trading_loop.py` | 트레이딩 루프 (DCA/Grid 자동 재구성 포함) |
| `engine/notification/__init__.py` | NotificationBridge |
| `engine/notification/telegram.py` | TelegramNotifier |
| `scripts/run_backtest_all.py` | 전략별 백테스트 (90일) |
| `scripts/run_backtest_tuning.py` | 그리드 서치 파라미터 튜닝 |
| `scripts/run_backtest_compare.py` | Before/After 비교 |
| `scripts/run_backtest_robustness.py` | 180일 장기 + 파라미터 민감도 분석 |
| `scripts/run_paper.py` | Paper Trading 실행기 |
| `results/tuning_grid_*.csv` | 그리드 서치 결과 |
| `shared/protocols.py` | DataStore Protocol 정의 |
| `docs/signal-glossary.md` | 시그널 파이프라인 용어 설명서 |

## Architecture Notes

- **기본 DB: SQLite** (`DB_TYPE=sqlite`), PostgreSQL은 `DB_TYPE=postgres`로 전환 가능
- **백테스트**: 90일 기본(180일 robustness 별도), SL/TP/Trailing 실제 적용, macro_weight=0.0
- **전략 프리셋**: 2026-03-08 튜닝 완료, 파라미터 안정성 7/7 검증됨
- **레짐 전환**: Signal 전략 자동 전환 + DCA/Grid TradingLoop 자동 재구성 완료
- **테스트**: 467개 전체 통과 (`pytest engine/tests/ -v`)
- **venv**: `.venv/bin/python` (Python 3.13)
