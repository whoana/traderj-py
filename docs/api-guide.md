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

---

## 22. AI Tuner — 튜닝 이력

**용도:** AI 튜너가 수행한 파라미터 튜닝 이력 조회

```bash
# 전체 이력
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/tuning/history"

# 전략별 필터
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/tuning/history?strategy_id=STR-001&limit=10"

# 상태별 필터
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/tuning/history?status=monitoring"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_id | query | null | 전략 ID 필터 |
| status | query | null | `monitoring`, `confirmed`, `rolled_back`, `rejected` |
| limit | query | 50 | 개수 (1~200) |

```json
[
  {
    "tuning_id": "tune-001",
    "created_at": "2026-03-24T00:00:00+00:00",
    "strategy_id": "STR-001",
    "status": "monitoring",
    "reason": "tuning_applied",
    "changes": [
      {
        "parameter_name": "buy_threshold",
        "tier": "tier_1",
        "old_value": 0.10,
        "new_value": 0.12,
        "change_pct": 0.20
      }
    ],
    "eval_metrics": {
      "win_rate": 0.40,
      "profit_factor": 1.2,
      "max_drawdown": 0.03,
      "eval_window": "2026-03-17~2026-03-24"
    },
    "validation_pf": 1.5,
    "validation_mdd": 0.02,
    "llm_provider": "claude",
    "llm_model": "claude-sonnet-4-20250514",
    "llm_confidence": "high"
  }
]
```

---

## 23. AI Tuner — 튜닝 상세

**용도:** 특정 튜닝 세션의 상세 정보 조회

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/tuning/history/tune-001"
```

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| tuning_id | path | **필수** 튜닝 세션 ID |

응답: 22번과 동일한 단일 객체. 없으면 404.

---

## 24. AI Tuner — 수동 롤백

**용도:** 특정 튜닝 세션의 파라미터 변경을 즉시 롤백

```bash
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/tuning/rollback/tune-001"
```

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| tuning_id | path | **필수** 롤백할 튜닝 세션 ID |

```json
{"status": "rolled_back", "tuning_id": "tune-001"}
```

---

## 25. AI Tuner — 튜너 상태

**용도:** AI Tuner 전체 상태 (파이프라인 상태, 모니터링 중 세션, 등록된 전략)

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/tuning/status"
```

파라미터 없음.

```json
{
  "state": "idle",
  "active_monitoring": [
    {"tuning_id": "tune-001", "strategy_id": "STR-001"}
  ],
  "consecutive_rollbacks": 0,
  "registered_strategies": ["STR-001"],
  "latest_tuning": {
    "STR-001": { "tuning_id": "tune-001", "status": "monitoring", "..." : "..." }
  }
}
```

| 필드 | 설명 |
|------|------|
| state | `idle`, `evaluating`, `optimizing`, `applying`, `monitoring`, `suspended` |
| active_monitoring | 현재 48시간 모니터링 중인 세션 목록 |
| consecutive_rollbacks | 연속 롤백 횟수 (3회 이상이면 SUSPENDED) |
| registered_strategies | 튜너에 등록된 전략 ID 목록 |
| latest_tuning | 전략별 최근 튜닝 결과 |

---

## 26. AI Tuner — LLM 프로바이더 상태

**용도:** Claude/OpenAI 프로바이더 건강 상태 및 비용 예산 확인

```bash
curl -H "X-API-Key: $TRADERJ_API_KEY" \
  "https://traderj-engine.fly.dev/api/v1/tuning/provider-status"
```

파라미터 없음.

```json
{
  "claude": {"state": "closed", "failures": 0},
  "budget": {"used_usd": 0.05, "limit_usd": 5.0}
}
```

| 필드 | 설명 |
|------|------|
| claude/openai | Circuit Breaker 상태 (`closed`=정상, `open`=차단, `half_open`=복구 시도) |
| budget | 월간 LLM 비용 사용량/한도 (USD) |

---

## 27. AI Tuner — 수동 튜닝 트리거

**용도:** 특정 전략에 대해 즉시 튜닝 세션 실행 (디버깅/테스트용)

```bash
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tier": "tier_1"}' \
  "https://traderj-engine.fly.dev/api/v1/tuning/trigger/STR-001"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| strategy_id | path | **필수** | 전략 ID |
| tier | body | tier_1 | `tier_1` (시그널), `tier_2` (리스크), `tier_3` (레짐) |

```json
{
  "tuning_id": "tune-002",
  "strategy_id": "STR-001",
  "tier": "tier_1",
  "status": "monitoring",
  "reason": "tuning_applied",
  "changes_count": 3
}
```

| status 값 | 의미 |
|-----------|------|
| monitoring | 튜닝 적용 완료, 48시간 모니터링 시작 |
| rejected | 최소 거래 수 미달 또는 가드레일 위반 |
| pending_approval | Tier 3 변경 — 수동 승인 대기 |

---

## 28. AI Tuner — Tier 3 승인/거부

**용도:** Tier 3 (레짐 파라미터) 변경에 대한 수동 승인 또는 거부

```bash
# 승인
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"approved": true}' \
  "https://traderj-engine.fly.dev/api/v1/tuning/approve/tune-003"

# 거부
curl -X POST -H "X-API-Key: $TRADERJ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"approved": false}' \
  "https://traderj-engine.fly.dev/api/v1/tuning/approve/tune-003"
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| tuning_id | path | **필수** | 승인 대기 중인 튜닝 세션 ID |
| approved | body | true | `true`=승인, `false`=거부 |

```json
{"tuning_id": "tune-003", "action": "approved"}
```
