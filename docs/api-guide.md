# TraderJ API 사용 설명서

**Base URL:** `https://traderj-engine.fly.dev`
**인증:** `X-API-Key` 헤더 (환경변수 `TRADERJ_API_KEY`)
**버전:** v1

---

## 인증

모든 API 호출(health 제외)에 `X-API-Key` 헤더 필요:
```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" https://traderj-engine.fly.dev/api/v1/...
```

---

## 1. 헬스체크

**용도:** 서비스 상태 확인 (인증 불필요)

```bash
curl https://traderj-engine.fly.dev/health
```
```json
{"status": "ok", "uptime": 3600.5, "db": "connected", "engine": "running"}
```

---

## 2. 잔고 조회

**용도:** 전략별 KRW/BTC 잔고, 총 자산 평가, 수익률 확인

```bash
# 기본 (STR-001)
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/balance"

# 특정 전략
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/balance?strategy_id=STR-005"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_id | query | STR-001 | 전략 ID |

```json
{
  "strategy_id": "STR-001",
  "krw": "10085107",
  "btc": "0",
  "initial_krw": "10000000",
  "total_value_krw": "10085107",
  "pnl_krw": "85107",
  "pnl_pct": 0.85
}
```

---

## 3. 포지션 조회

**용도:** 현재/과거 포지션 목록, 미실현 PnL 확인

```bash
# 전체 포지션
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/positions"

# 열린 포지션만
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/positions?status=open"

# 특정 전략 + 페이지네이션
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/positions?strategy_id=STR-001&page=1&size=10"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_id | query | null | 전략 ID 필터 |
| status | query | null | `open` 또는 `closed` |
| page | query | 1 | 페이지 번호 (1부터) |
| size | query | 20 | 페이지 크기 (최대 100) |

---

## 4. 주문 이력

**용도:** 주문 내역 확인 (매수/매도/취소)

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/orders?strategy_id=STR-001&status=filled&size=50"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_id | query | null | 전략 ID 필터 |
| status | query | null | `pending`, `filled`, `cancelled`, `failed` |
| page | query | 1 | 페이지 번호 |
| size | query | 20 | 페이지 크기 (최대 100) |

---

## 5. 시그널 이력

**용도:** 매매 시그널 발생 이력 (방향, 스코어, 컴포넌트별 점수)

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/signals?strategy_id=STR-001&size=10"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_id | query | null | 전략 ID 필터 |
| page | query | 1 | 페이지 번호 |
| size | query | 20 | 페이지 크기 (최대 100) |

---

## 6. 일별 손익

**용도:** 일자별 실현/미실현 손익, 거래 횟수

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/pnl/daily?strategy_id=STR-001&days=7"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_id | query | **필수** | 전략 ID |
| days | query | 30 | 조회 기간 (1~365) |

---

## 7. 손익 요약

**용도:** 전략별 누적 실현 손익, 총 거래 수

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/pnl/summary?strategy_id=STR-001"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_id | query | null | 전략 ID (미지정 시 전체) |

---

## 8. 리스크 상태

**용도:** 연속 손실 횟수, 일일 손익, 쿨다운 상태 확인

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/risk/STR-001"
```

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| strategy_id | path | **필수** 전략 ID |

---

## 9. 매크로 스냅샷

**용도:** Fear&Greed, 펀딩 레이트, BTC 도미넌스, 김프 등 매크로 지표

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/macro/latest"
```

파라미터 없음.

```json
{
  "timestamp": "2026-03-22T04:00:00Z",
  "fear_greed": 65.0,
  "funding_rate": 0.01,
  "btc_dominance": 54.2,
  "btc_dom_7d_change": -0.5,
  "dxy": 103.5,
  "kimchi_premium": 2.1,
  "market_score": 0.62
}
```

---

## 10. 캔들 데이터

**용도:** OHLCV 캔들 조회

```bash
# BTC/KRW 4시간봉 최근 100개
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/candles/BTC-KRW/4h?limit=100"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| symbol | path | **필수** | 심볼 (`BTC-KRW`, 대시 구분) |
| timeframe | path | **필수** | 타임프레임 (`1h`, `4h`, `1d`) |
| limit | query | 200 | 개수 (최대 1000) |

---

## 11. PnL 분석 (누적 곡선)

**용도:** 누적 PnL, MDD, 피크 PnL, 에쿼티 커브

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/analytics/pnl?strategy_id=STR-001&days=30"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_id | query | **필수** | 전략 ID |
| days | query | 30 | 기간 (1~365) |

---

## 12. 전략 비교

**용도:** 복수 전략의 PnL, 샤프비율 비교

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/analytics/compare?strategy_ids=STR-001,STR-005&days=30"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_ids | query | **필수** | 쉼표 구분 전략 ID 목록 |
| days | query | 30 | 기간 (1~365) |

---

## 13. 엔진 상태

**용도:** 엔진 running/stopped, 전략별 상태, 레짐, tick 카운트

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/engine/status"
```

파라미터 없음.

```json
{
  "status": "running",
  "uptime_seconds": 3600.0,
  "trading_mode": "paper",
  "strategies": [
    {
      "strategy_id": "STR-001",
      "preset": "STR-003",
      "state": "monitoring",
      "last_tick_at": null,
      "tick_count": 215,
      "has_open_position": false,
      "running": true
    }
  ],
  "regime": {
    "current": "ranging_high_vol",
    "confidence": 0.15,
    "mapped_preset": "STR-003",
    "last_switch_at": "2026-03-21T14:02:33Z",
    "switch_count": 1,
    "locked": false
  }
}
```

---

## 14. 엔진 제어

**용도:** 트레이딩 루프 정지/시작/재시작 (API 서버는 유지)

```bash
# 정지
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/engine/stop"

# 시작
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/engine/start"

# 재시작
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/engine/restart"
```

Body 없음. 응답:
```json
{"success": true, "message": "Stopped 1 trading loop(s)", "stopped_strategies": ["STR-001"]}
```

---

## 15. 포지션 청산 (긴급)

**용도:** 시장가로 즉시 포지션 청산

```bash
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"strategy_id": "STR-001"}' \
  "https://traderj-engine.fly.dev/api/v1/position/close"
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| strategy_id | body | STR-001 | 전략 ID |

---

## 16. SL 변경

**용도:** Stop Loss 가격 수동 변경

```bash
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"strategy_id": "STR-001", "stop_loss": 100000000}' \
  "https://traderj-engine.fly.dev/api/v1/position/sl"
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| strategy_id | body | STR-001 | 전략 ID |
| stop_loss | body | **필수** | SL 가격 (KRW) |

---

## 17. TP 변경

**용도:** Take Profit 가격 수동 변경

```bash
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"strategy_id": "STR-001", "take_profit": 115000000}' \
  "https://traderj-engine.fly.dev/api/v1/position/tp"
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| strategy_id | body | STR-001 | 전략 ID |
| take_profit | body | **필수** | TP 가격 (KRW) |

---

## 18. 전략 변경

**용도:** 실행 중인 전략 프리셋 변경 (STR-001~STR-006)

```bash
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"strategy_id": "STR-005"}' \
  "https://traderj-engine.fly.dev/api/v1/strategy/switch"
```

| 필드 | 타입 | 설명 |
|------|------|------|
| strategy_id | body | **필수** 변경할 프리셋 ID |

---

## 19. 설정 조회

**용도:** 현재 전략 파라미터, 리스크 설정, 레짐 스위치 설정

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/config"
```

파라미터 없음.

```json
{
  "trading_mode": "paper",
  "symbol": "BTC/KRW",
  "active_strategies": ["STR-001"],
  "current_preset": {
    "id": "STR-003",
    "scoring_mode": "hybrid",
    "entry_mode": "weighted",
    "buy_threshold": 0.06,
    "sell_threshold": -0.06,
    "tf_weights": {"4h": 0.4, "1d": 0.6},
    "use_daily_gate": false,
    "macro_weight": 0.15
  },
  "risk": {
    "max_position_pct": 0.3,
    "daily_loss_limit": 200000,
    "max_consecutive_losses": 3
  },
  "regime_switch": {
    "enabled": true,
    "debounce_count": 3,
    "cooldown_minutes": 60,
    "close_position_on_switch": true,
    "loss_threshold_pct": 0.015
  }
}
```

---

## 20. 레짐 상태

**용도:** 현재 시장 레짐, DCA/Grid 설정, 스위치 이력

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/regime"
```

파라미터 없음.

```json
{
  "current_regime": "ranging_high_vol",
  "confidence": 0.15,
  "mapped_preset": "STR-003",
  "last_switch_at": "2026-03-21T14:02:33Z",
  "switch_count": 1,
  "switch_locked": false,
  "pending_count": 0,
  "dca_config": {"buy_amount_krw": 70000, "interval_hours": 48},
  "grid_config": null
}
```

---

## 21. 버전 정보

**용도:** API 버전, Python 버전, git commit, 시작 시간

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/version"
```

```json
{
  "version": "0.2.0",
  "python": "3.13.12",
  "commit": "3591848",
  "started_at": "2026-03-22T03:00:00+00:00"
}
```
