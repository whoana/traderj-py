# Plan: TraderJ Engine & Strategy Improvement
> Feature: `traderj-improvement`
> Created: 2026-03-17
> Phase: Plan

---

## 1. 배경 및 목적

### 1.1 트리거
- 2026-03-10 ~ 03-16 페이퍼 트레이딩 7일 운영 결과 검토
- 2026-03-16 전체 Gap Analysis (전체 매치율 88%, 목표 90%+)

### 1.2 목적
1. 페이퍼 트레이딩에서 발견된 **엔진 실전 취약점** 수정
2. Gap Analysis P1 미구현 항목 완성으로 **전체 매치율 90%+** 달성
3. Daily PnL 기록 외 **핵심 누락 기능** 추가

---

## 2. 현황 요약

### 2.1 페이퍼 트레이딩 성과 (7일)
| 지표 | 값 |
|------|-----|
| 총 평가자산 | 10,127,211 KRW (+1.27%) |
| 보유 포지션 | 2개 open (stop_loss = NULL) |
| 매수 주문 | 2건 (매도 0건) |
| KRW 미투자 | 6,400,000 KRW (64%) |
| Daily PnL 기록 | 수정 완료 (2026-03-17) |

### 2.2 Gap Analysis 현황 (2026-03-16)
| 도메인 | 점수 | 상태 |
|--------|------|------|
| Strategy Engine | 95% | PASS |
| Engine Architecture | 92% | PASS |
| API Server | 90% | PASS |
| Dashboard UI | 82% | WARN |
| Infrastructure | 78% | WARN |
| **전체 가중 평균** | **88%** | **WARN** |

---

## 3. 개선 항목 (우선순위별)

### P0 — 엔진 안전성 (실전 필수)

#### P0-1. Stop Loss / Take Profit 자동 설정
**문제**: 현재 2개 포지션 모두 `stop_loss = NULL`, `trailing_stop = NULL`
- 가격이 급락해도 자동 청산 없음 → 무제한 손실 노출
- `PositionManager`에 Stop Loss 설정 로직 누락

**수정 범위**:
- `engine/execution/position_manager.py`: 포지션 생성 시 entry_price 기준 stop_loss 자동 계산
- `engine/strategy/risk.py`의 ATR 기반 stop_loss 계산값을 포지션에 반영
- `engine/loop/trading_loop.py`: 매 tick마다 현재가가 stop_loss 이하 시 청산 이벤트 발행

**청산 조건**:
```
기본 Stop Loss = entry_price × (1 - stop_loss_pct)  # 기본 2~3%
ATR Stop Loss  = entry_price - (ATR × atr_multiplier)  # 더 정밀
Trailing Stop  = 고점 × (1 - trailing_pct)  # 수익 보호
```

#### P0-2. Take Profit (익절) 로직
**문제**: Buy 후 매도 시그널이 와도 포지션 청산 로직 없음
- 현재 `OrderManager`는 신규 매수만 실행, 기존 포지션 매도 미구현

**수정 범위**:
- `engine/loop/trading_loop.py`: SELL 시그널 → 보유 포지션 청산 주문 생성
- `engine/execution/order_manager.py`: close position 주문 타입 지원
- Tiered Exit (`engine/strategy/tiered_exit.py`) 연동: 1/3 → 2/3 → 전량 익절

#### P0-3. Macro API 실 데이터 연결
**문제**: `engine/data/macro.py`의 BTC Dominance, DXY, Funding Rate가 placeholder URL
- MacroScore가 가짜 데이터로 계산되어 시그널 품질 저하

**수정 범위**:
- BTC Dominance: CoinGecko API (`/api/v3/global`)
- Funding Rate: Binance API (`/fapi/v1/fundingRate`)
- DXY: Yahoo Finance 또는 Alpha Vantage (무료 키)

---

### P1 — Dashboard Analytics (Gap 해소)

#### P1-1. DailyPnLBars 컴포넌트
- 날짜별 실현/미실현 PnL 막대 차트 (Recharts)
- `/api/v1/pnl/daily` 데이터 사용
- 파일: `dashboard/src/components/analytics/DailyPnLBars.tsx`

#### P1-2. DrawdownChart 컴포넌트
- 최대 낙폭(MDD) 시각화 (Recharts AreaChart, 음수 영역)
- 파일: `dashboard/src/components/analytics/DrawdownChart.tsx`

#### P1-3. MacroBar 컴포넌트
- 하단 고정 바: Fear&Greed | BTC Dom | Funding Rate | Kimchi Premium
- `/api/v1/macro/latest` 실시간 업데이트
- 파일: `dashboard/src/components/MacroBar.tsx`

#### P1-4. RSI Sub-chart 패널
- 캔들차트 하단 100px RSI 패널 (Lightweight Charts pane)
- 파일: `dashboard/src/components/chart/RSIPanel.tsx`

---

### P1 — API 완성 (Gap 해소)

#### P1-5. Backtest API 엔드포인트
- `GET /api/v1/backtest/results` — 결과 목록 조회
- `POST /api/v1/backtest/run` — 백테스트 실행 트리거
- 파일: `api/routes/backtest.py`

---

### P2 — Infrastructure 정비

#### P2-1. 코드 품질 설정 파일
- `ruff.toml` (Python linting)
- `mypy.ini` (type checking)

#### P2-2. Integration Test CI
- `.github/workflows/integration.yml`
- 주요 시나리오: paper trading 1-tick, API 헬스체크, DB 마이그레이션

#### P2-3. Prometheus/Grafana 설정
- `prometheus.yml` 스크래핑 설정
- 기본 Grafana 대시보드 JSON

---

## 4. 구현 순서

```
Week 1: P0 엔진 안전성
  1. P0-1: Stop Loss 자동 설정 + 모니터링 tick
  2. P0-2: Take Profit / 포지션 청산 주문
  3. P0-3: Macro API 실 데이터 연결
  4. 테스트: engine/tests/unit/test_position_manager.py 추가

Week 2: P1 Dashboard + API
  5. P1-5: Backtest API 엔드포인트 (API 먼저 — Dashboard 의존)
  6. P1-1: DailyPnLBars 컴포넌트
  7. P1-2: DrawdownChart 컴포넌트
  8. P1-3: MacroBar 컴포넌트
  9. P1-4: RSI Sub-chart 패널

Week 3: P2 Infrastructure + 검증
  10. P2-1: ruff.toml, mypy.ini
  11. P2-2: integration.yml
  12. Gap Analysis 재실행 → 90%+ 확인
```

---

## 5. 예상 효과

| 항목 | 현재 | 개선 후 |
|------|------|---------|
| 전체 Gap 매치율 | 88% | **90%+** |
| 포지션 최대 손실 | 무제한 | ATR 기반 제한 |
| 자본 활용도 | 36% | 50~70% (익절 후 재투자) |
| Macro 데이터 품질 | placeholder | 실 데이터 |
| Dashboard P1 완성도 | 55% | 85%+ |

---

## 6. 성공 기준

- [ ] P0: 포지션 생성 시 stop_loss 자동 할당 (NULL 없음)
- [ ] P0: SELL 시그널 → 포지션 청산 주문 정상 실행
- [ ] P0: Macro API 실 데이터 수신 확인
- [ ] P1: Dashboard analytics 페이지 DailyPnLBars + DrawdownChart 렌더링
- [ ] P1: MacroBar 하단 표시
- [ ] P1: Backtest API 200 응답
- [ ] Overall: Gap Analysis 90%+ 달성

---

## 7. 리스크 및 제약

| 리스크 | 대응 |
|--------|------|
| Stop Loss 로직 버그로 불필요한 청산 | 충분한 유닛 테스트 + 페이퍼 모드만 적용 |
| Macro API 외부 의존성 | 실패 시 기존 값 유지 (graceful degradation) |
| DXY 유료 API | 무료 대안 우선 적용 (Alpha Vantage free tier) |
| Dashboard 빌드 시간 | 컴포넌트 단위 점진적 추가 |

---

*Plan Version: 1.0 | Author: Claude | Date: 2026-03-17*
