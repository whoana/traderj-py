# TraderJ 코드베이스 vs 전략 문서 비교 분석 보고서

## Context
`trader4j/docs/crypto_bot_trading_strategies.md` 문서에 기술된 트레이딩 봇 전략/기능 요구사항과 `traderj` 프로젝트의 실제 구현 상태를 비교 분석한다.

---

## 1. 핵심 전략 구현 비교

| # | 문서 전략 | 구현 상태 | 상세 |
|---|----------|----------|------|
| 1-1 | **Grid Trading** | **미구현** | 일정 가격 간격 매수/매도 주문 배치 로직 없음 |
| 1-2 | **DCA (분할매수)** | **미구현** | 일정 간격 고정금액 매수, AI 강화 DCA 모두 없음 |
| 1-3 | **Momentum / Trend Following** | **구현됨** | `filters.py`의 `trend_score()`, `momentum_score()`, `quick_momentum_score()` |
| 1-4 | **Arbitrage (차익거래)** | **미구현** | 멀티 거래소 지원 자체가 없음 (Upbit만) |
| 1-5 | **Mean Reversion (평균회귀)** | **부분 구현** | `reversal_score()`로 과매수/과매도 감지는 하나, 전용 Mean Reversion 전략은 아님 |

### 추가 구현된 전략 (문서에 없음)
- **Breakout (돌파)**: `breakout_score()` - BB 돌파 + 거래량 확인
- **Volume Analysis**: `volume_score()` - OBV, CMF 기반
- **7개 프리셋**: DEFAULT, STR-001~006 (Conservative~Scalper)

### 평가: 5개 중 1.5개 구현 = **30%**

---

## 2. 기술 지표 비교

| 문서 요구 지표 | 구현 | 구현 위치 |
|---------------|------|----------|
| 이동평균 (50일, 200일 MA) | **EMA 20/50/200** | `indicators.py` |
| RSI (14기간) | **구현** (30/70 기준) | `indicators.py` |
| MACD (12, 26, 9) | **구현** | `indicators.py` |
| 볼린저 밴드 (20기간, 2SD) | **구현** (%B, Width 포함) | `indicators.py` |
| ATR | **구현** (14일, 절대값+%) | `indicators.py` |
| Stochastic RSI | **구현** (문서에 없으나 추가) | `indicators.py` |
| OBV, CMF | **구현** (문서에 없으나 추가) | `indicators.py` |

### 멀티 지표 확인 전략 (문서 섹션 1-3)
| 시그널 | 문서 조건 | 구현 상태 |
|--------|----------|----------|
| 매수 | BB 하단 + RSI<30 + MACD 양의 크로스 | `reversal_score()`에서 유사 로직 (개별 점수 합산 방식) |
| 매도 | BB 상단 + RSI>70 + MACD 음의 크로스 | 동일하게 부분 반영 |

### 평가: **100%** (문서 요구 지표 전부 + 추가 지표)

---

## 3. 리스크 관리 비교

| 문서 요구사항 | 구현 | 상세 |
|-------------|------|------|
| **고정 비율법 (1~2%)** | **구현** | `risk.py`: target_risk_pct=2%, 포지션 5~20% 범위 |
| **변동성 기반 포지션 사이징 (ATR)** | **구현** | `risk.py`: position_pct = target_risk / atr_pct |
| **상관관계 분석** | **미구현** | 상관 자산 과다 노출 방지 로직 없음 |
| **ATR 기반 손절** | **구현** | `risk.py`: SL = entry - (ATR x 2.0) |
| **계단식 손절 (Tiered)** | **미구현** | 단일 손절만 구현 |
| **트레일링 스톱** | **모델만** | `models.py`에 필드 존재, 실제 로직 미구현 |
| **최소 R:R 비율 1:2** | **미구현** | R:R 비율 검증 로직 없음 |
| **최대 드로다운 한도** | **부분 구현** | 일일 손실 한도(5%)는 있으나 누적 MDD 기반 중지는 없음 |
| **일일 손실 한도** | **구현** | `risk_manager.py`: daily_max_loss_pct=5% |
| **서킷 브레이커** | **구현** | `circuit_breaker.py`: 3연속 실패->차단, 5분 후 반개방 |

### 추가 구현 (문서에 없음)
- 연속 손실 쿨다운: 3연패 -> 24시간 거래 중단
- 변동성 상한: ATR > 8% 시 매수 차단
- 최소 주문금액: 5,000원 미만 거부

### 평가: 10개 중 5.5개 구현 = **55%**

---

## 4. AI 전략 전환 비교

| 문서 요구사항 | 구현 | 상세 |
|-------------|------|------|
| 변동성 급등 감지 -> 전략 전환 | **미구현** | 수동 프리셋 선택만 가능 |
| 횡보 감지 -> 전략 전환 | **미구현** | 시장 레짐 분류 로직 없음 |
| 시장 심리 분석(NLP) | **미구현** | NLP 기반 분석 없음 |
| 매크로 지표 통합 | **구현** | `macro.py`: 공포탐욕, 펀딩레이트, BTC 도미넌스, 김프, DXY |
| Daily Gate (일봉 필터) | **구현** | `mtf.py`: EMA20>EMA50 시 매수 허용 |

### 평가: **40%** (매크로 통합은 있으나 핵심인 자동 전략 전환 미구현)

---

## 5. 백테스팅 비교

| 문서 요구사항 | 구현 | 상세 |
|-------------|------|------|
| **Sharpe Ratio** | **구현** | `metrics.py`: 무위험율 3.5% 기준 |
| **Sortino Ratio** | **구현** | `metrics.py`: 하방 리스크만 반영 |
| **Profit Factor** | **구현** | `metrics.py`: 총수익/총손실 |
| **Max Drawdown** | **구현** | `metrics.py`: MDD% + Duration |
| **Win Rate** | **구현** | `metrics.py`: 승률 |
| 슬리피지/수수료 반영 | **구현** | 수수료 0.05%, 슬리피지 5BPS |
| Out-of-Sample 테스트 | **미구현** | Walk-forward 최적화 초안만 |
| 30~90일 페이퍼 트레이딩 | **지원** | PAPER 모드 구현됨 |

### 추가 구현 (문서에 없음)
- CAGR, Calmar Ratio
- 최대 연속 승/패, 평균 보유시간
- 7개 프리셋 일괄 백테스트 스크립트

### 평가: **95%**

---

## 6. 거래소 연동 비교

| 문서 언급 | 구현 | 상세 |
|----------|------|------|
| 유동성 높은 거래소 선택 | **Upbit만** | ccxt 기반, Public/Private API |
| BTC/USDT, ETH/USDT 추천 | **BTC/KRW** | KRW 마켓 기준 |
| 멀티 거래소 (Arbitrage용) | **미구현** | Binance 등 미지원 |

### 평가: **60%** (단일 거래소는 동작하나 확장성 부족)

---

## 종합 매칭률

| 영역 | 매칭률 | 핵심 갭 |
|------|--------|---------|
| 핵심 전략 | **30%** | Grid, DCA, Arbitrage 미구현 |
| 기술 지표 | **100%** | 완전 구현 |
| 리스크 관리 | **55%** | 트레일링 스톱, 계단식 손절, R:R 비율 미구현 |
| AI 전략 전환 | **40%** | 자동 전환 로직 미구현 (핵심 차별화 요소) |
| 백테스팅 | **95%** | Out-of-Sample 테스트만 미흡 |
| 거래소 연동 | **60%** | 단일 거래소 |
| **전체 가중 평균** | **~63%** | |

---

## 우선순위별 개선 권장사항

### P0 (즉시)
1. **트레일링 스톱 로직 구현** - 모델 필드는 있으나 로직 없음 (`position_manager.py`)
2. **자동 익절(Take-Profit) 목표가** - ATR 기반 TP 설정 (R:R 1:2)

### P1 (단기)
3. **DCA 전략 엔진** - 주기적 분할매수 + RSI 기반 동적 매수량 조절
4. **Grid Trading 엔진** - 횡보장 대응 전략
5. **시장 레짐 감지 모듈** - ADX + BB Width 기반 횡보/추세 분류

### P2 (중기)
6. **전략 자동 전환** - 레짐 감지 -> 전략 프리셋 자동 변경
7. **계단식 손절** - 50%/30%/20% 단계적 청산
8. **Walk-forward 백테스트** - Out-of-Sample 검증

### P3 (장기)
9. **멀티 거래소 지원** - Binance 추가 -> Arbitrage 가능
10. **NLP 시장 심리 분석** - 뉴스/소셜 감성 분석 통합

---

## 코드베이스 파일 매핑

| 파일 | 역할 | 관련 갭 |
|------|------|---------|
| `engine/strategy/risk.py` | ATR 기반 리스크 엔진 | P0: TP 추가 필요 |
| `engine/execution/position_manager.py` | 포지션 관리 | P0: 트레일링 스톱 로직 |
| `engine/execution/risk_manager.py` | 실행단 리스크 관리 | P0: R:R 검증 추가 |
| `engine/strategy/filters.py` | 6개 스코어링 함수 | - (완성) |
| `engine/strategy/signal.py` | 시그널 생성 파이프라인 | P2: 레짐 기반 전략 전환 |
| `engine/strategy/presets.py` | 7개 전략 프리셋 | P1: DCA/Grid 프리셋 추가 |
| `engine/strategy/indicators.py` | 기술 지표 계산 | - (완성) |
| `engine/strategy/mtf.py` | MTF 집계 + Daily Gate | - (완성) |
| `engine/data/macro.py` | 매크로 지표 | - (완성) |
| `engine/execution/circuit_breaker.py` | 서킷 브레이커 | - (완성) |
| `shared/models.py` | 데이터 모델 | P0: trailing_stop 필드 존재 |
| `shared/enums.py` | 열거형 | P1: RegimeType 존재 (활용 안됨) |
| `shared/events.py` | 이벤트 정의 | RegimeChangeEvent 존재 (활용 안됨) |

---

*분석일: 2026-03-07*
*분석 기준: traderj 코드베이스 현재 상태*
