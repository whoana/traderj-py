# 레짐 감지 기반 전략 자동 전환 가이드

## 개요

시장 상태(레짐)를 실시간으로 감지하여, 최적의 전략 프리셋으로 자동 전환하는 기능입니다.

### 레짐 분류 (ADX + Bollinger Band Width)

| 레짐 | 조건 | 자동 전환 전략 |
|------|------|---------------|
| TRENDING_HIGH_VOL | ADX > 25, BB Width > 4% | STR-002 (Aggressive Trend) |
| TRENDING_LOW_VOL | ADX > 25, BB Width ≤ 4% | STR-001 (Conservative Trend) |
| RANGING_HIGH_VOL | ADX ≤ 25, BB Width > 4% | STR-003 (Hybrid Reversal) |
| RANGING_LOW_VOL | ADX ≤ 25, BB Width ≤ 4% | STR-005 (Low-Frequency Conservative) |

### 안전장치

| 장치 | 기본값 | 설명 |
|------|-------|------|
| 디바운스 | 3회 | 동일 레짐 3회 연속 감지 후 전환 |
| 쿨다운 | 60분 | 전환 후 60분간 재전환 차단 |
| 수동 잠금 | off | API로 자동 전환 비활성화 가능 |

---

## 1. 백테스트

과거 데이터로 레짐 전환 효과를 검증합니다. **Fixed(단일 전략)** vs **Regime-Adaptive(자동 전환)**를 동일 데이터에서 비교합니다.

### 기본 실행

```bash
# 가상환경 활성화
source .venv/bin/activate

# 기본: 최근 30일, 초기 프리셋 STR-001
python -m scripts.run_backtest_regime
```

### 옵션

```bash
# 60일 데이터로 테스트
python -m scripts.run_backtest_regime --days 60

# 초기 프리셋 변경 (STR-002부터 시작)
python -m scripts.run_backtest_regime --initial-preset STR-002

# 조합
python -m scripts.run_backtest_regime --days 90 --initial-preset STR-005
```

### 출력 예시

```
================================================================
  Regime-Adaptive Backtest — BTC/KRW 30일
  초기 자본: 10,000,000 KRW
  초기 프리셋: STR-001
================================================================

[1/2] Fixed 전략 백테스트: STR-001 (Conservative Trend (4h))
  완료: 12.3s, 1 trades

[2/2] Regime-Adaptive 백테스트 (초기: STR-001)
  완료: 12.5s, 4 trades, 2 regime switches

레짐 전환 이력
----------------------------------------------------------------
  trending_low_vol     → ranging_high_vol     | STR-001 → STR-003 | confidence=0.65
  ranging_high_vol     → trending_high_vol    | STR-003 → STR-002 | confidence=0.72

================================================================
  비교 결과
================================================================
지표                 |          Fixed |  Regime-Adaptive
----------------------------------------------------------
수익률 (%)           |          -0.29 |           +0.85
최종 자산 (KRW)      |     9,970,690 |      10,085,000
거래 수              |              1 |               4
승률 (%)             |            0.0 |            50.0
...
================================================================
```

### 결과 해석

- **수익률 비교**: Regime-Adaptive가 Fixed보다 높으면 레짐 전환이 유효
- **레짐 전환 이력**: 어떤 시점에 어떤 전략으로 전환됐는지 확인
- **거래 수 변화**: 전환으로 인해 거래 빈도가 달라질 수 있음
- 결과는 자동으로 SQLite DB에 저장됨 (`{preset}-fixed`, `{preset}-regime`)

### 기존 전체 전략 백테스트 (레짐 전환 없음)

```bash
# 7개 전략 개별 비교 (레짐 전환 없이 각 전략 단독 실행)
python -m scripts.run_backtest_all
```

---

## 2. 페이퍼 트레이딩 (실시간 시뮬레이션)

실제 Upbit 시세를 받아 가상 자산으로 매매합니다. **레짐 전환은 자동으로 활성화**되어 있습니다.

### 기본 실행

```bash
source .venv/bin/activate

# 3회 tick 실행 후 종료
python -m scripts.run_paper --ticks 3

# 특정 전략으로 시작 (레짐에 따라 자동 전환됨)
python -m scripts.run_paper --ticks 5 STR-001

# 연속 실행 (Ctrl+C로 종료)
python -m scripts.run_paper STR-001
```

### 멀티 전략

```bash
# 여러 전략 동시 실행 (각각 독립적으로 레짐 감지/전환)
python -m scripts.run_paper STR-001 STR-005
```

### 동작 방식

페이퍼 트레이딩에서 매 tick마다:

1. Upbit에서 실시간 OHLCV 데이터 fetch
2. **4h 데이터로 레짐 감지** (ADX + BB Width)
3. 레짐 변경 감지 시 → 디바운스(3회) → 쿨다운 확인 → **전략 프리셋 자동 교체**
4. 교체된 전략으로 시그널 생성 + 매매 실행

### 레짐 전환 로그 확인

```bash
# 로그 레벨을 DEBUG로 올리면 레짐 감지 상세 로그 출력
LOG_LEVEL=DEBUG python -m scripts.run_paper --ticks 5 STR-001
```

로그에서 확인할 수 있는 메시지:

```
INFO  - Regime auto-switch: regime_change_confirmed → STR-003 (regime=ranging_high_vol, confidence=0.65)
INFO  - SignalGenerator preset applied: STR-003 (mode=hybrid, tf={'1h': 0.4, '4h': 0.6})
```

---

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|-------|------|
| `DB_TYPE` | `sqlite` | 데이터 저장소 (`sqlite` / `postgres`) |
| `DB_SQLITE_PATH` | `traderj.db` | SQLite 파일 경로 |
| `LOG_LEVEL` | `INFO` | 로그 레벨 (`DEBUG`로 레짐 상세 확인) |
| `TRADING_MODE` | `paper` | 매매 모드 |

---

## 한계 및 향후 개선

### 현재 한계
- Signal 기반 전략(STR-001~006)만 자동 전환 대상
- DCA, Grid 엔진은 미포함 (별도 실행 루프 필요)
- 레짐 감지는 4h 데이터 기준 (데이터 부족 시 skip)

### 향후 개선 (P2)
- DCA/Grid 엔진을 레짐 매핑에 포함 (RANGING → Grid, 하락 추세 → DCA)
- 레짐별 리스크 파라미터 자동 조정 (HIGH_VOL → 넓은 SL, 작은 포지션)
- 대시보드에 레짐 상태 및 전환 이력 시각화
