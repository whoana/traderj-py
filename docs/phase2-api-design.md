# Phase 2: FastAPI 임베디드 API 서버 설계서

**작성일:** 2026-03-22
**목적:** 엔진 프로세스 내 FastAPI 서버 병행 실행, Next.js 대시보드 연동
**API 버전:** v1 (URL prefix: `/api/v1`)
**인증:** `X-API-Key` 헤더 (환경변수 `TRADERJ_API_KEY`)

---

## 1. 아키텍처 개요

### 현재 (Phase 1)
```
[Fly.io Machine]
  └─ scripts/run_paper.py
       └─ Engine (TradingLoop + DataStore)
       └─ ❌ API 없음 — SSH로만 접근 가능
```

### 목표 (Phase 2)
```
[Fly.io Machine]
  └─ scripts/run_paper.py
       ├─ Engine (TradingLoop + DataStore)  ← 기존
       └─ FastAPI (uvicorn, port 8000)      ← 추가
            ├─ 같은 asyncio loop에서 실행
            ├─ DataStore 인스턴스 공유 (IPC 불필요)
            └─ TradingLoops dict 직접 참조

[Vercel]
  └─ Next.js Dashboard
       └─ API Routes (서버사이드)
            └─ → https://traderj-engine.fly.dev/api/v1/* (X-API-Key)
```

### 핵심 설계 원칙

1. **임베디드 모드**: API 서버가 엔진과 같은 프로세스에서 실행 (IPC 불필요)
2. **컴포넌트 공유**: DataStore, TradingLoops, EventBus를 직접 참조
3. **기존 코드 재사용**: `api/` 패키지의 라우트, 스키마, 미들웨어 최대 활용
4. **URL 버전닝**: 모든 API 경로에 `/api/v1` prefix

---

## 2. URL 체계

### 버전 규칙
- 모든 엔드포인트: `/api/v1/...`
- Health check: `/health` (버전 없음, 로드밸런서/모니터링용)
- WebSocket: `/ws/v1/stream` (기존 유지)
- 향후 breaking change 시 `/api/v2` 추가, v1 유지

---

## 3. 엔드포인트 상세

### 3.1 헬스체크 (인증 불필요)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/health` | 서비스 헬스체크 |

```json
// GET /health
{
  "status": "ok",
  "uptime": 3600.5,
  "db": "connected",
  "engine": "running",
  "version": "0.2.0"
}
```

---

### 3.2 데이터 조회 (읽기 전용)

| Method | Path | 설명 | 상태 |
|--------|------|------|------|
| GET | `/api/v1/positions` | 포지션 목록 | ✅ 기존 |
| GET | `/api/v1/orders` | 주문 이력 | ✅ 기존 |
| GET | `/api/v1/signals` | 시그널 이력 | ✅ 기존 |
| GET | `/api/v1/pnl/daily` | 일별 손익 | ✅ 기존 |
| GET | `/api/v1/pnl/summary` | 손익 요약 | ✅ 기존 |
| GET | `/api/v1/candles/{symbol}/{tf}` | 캔들 데이터 | ✅ 기존 |
| GET | `/api/v1/risk/{strategy_id}` | 리스크 상태 | ✅ 기존 |
| GET | `/api/v1/macro/latest` | 매크로 스냅샷 | ✅ 기존 |
| GET | `/api/v1/analytics/pnl` | 누적 PnL 곡선 | ✅ 기존 |
| GET | `/api/v1/analytics/compare` | 전략 비교 | ✅ 기존 |
| GET | `/api/v1/balance` | 잔고 현황 | 🔧 신규 |

```json
// GET /api/v1/balance?strategy_id=STR-001
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

### 3.3 엔진 제어

| Method | Path | 설명 | 상태 |
|--------|------|------|------|
| GET | `/api/v1/engine/status` | 엔진 상태 조회 | 🔧 신규 |
| POST | `/api/v1/engine/stop` | 전체 트레이딩 루프 정지 | 🔧 신규 |
| POST | `/api/v1/engine/start` | 트레이딩 루프 시작/재개 | 🔧 신규 |
| POST | `/api/v1/engine/restart` | 루프 정지 → 시작 | 🔧 신규 |

```json
// GET /api/v1/engine/status
{
  "status": "running",
  "uptime_seconds": 3600,
  "trading_mode": "paper",
  "strategies": [
    {
      "strategy_id": "STR-001",
      "preset": "STR-003",
      "state": "scanning",
      "last_tick_at": "2026-03-22T03:50:00Z",
      "tick_count": 215,
      "has_open_position": false
    }
  ],
  "regime": {
    "current": "ranging_high_vol",
    "confidence": 0.15,
    "last_switch_at": "2026-03-21T14:02:33Z"
  }
}
```

```json
// POST /api/v1/engine/stop
// Body: {} (없음)
// Response:
{
  "success": true,
  "message": "All trading loops stopped",
  "stopped_strategies": ["STR-001"]
}
```

```json
// POST /api/v1/engine/start
// Body (optional):
{ "strategy_ids": ["STR-001"] }
// Response:
{
  "success": true,
  "message": "Trading loops started",
  "started_strategies": ["STR-001"]
}
```

---

### 3.4 포지션/전략 관리

| Method | Path | 설명 | 상태 |
|--------|------|------|------|
| POST | `/api/v1/position/close` | 긴급 포지션 청산 | 🔧 신규 |
| POST | `/api/v1/position/sl` | SL 수동 변경 | 🔧 신규 |
| POST | `/api/v1/position/tp` | TP 수동 변경 | 🔧 신규 |
| POST | `/api/v1/strategy/switch` | 전략 프리셋 변경 | 🔧 신규 |

```json
// POST /api/v1/position/close
{
  "strategy_id": "STR-001"
}
// Response:
{
  "success": true,
  "message": "Position closed at market price",
  "sold_amount": "0.01887986",
  "sold_price": "105999000",
  "realized_pnl": "1246.07"
}
```

```json
// POST /api/v1/position/sl
{
  "strategy_id": "STR-001",
  "stop_loss": 100000000
}
// Response:
{
  "success": true,
  "strategy_id": "STR-001",
  "old_sl": "103500000",
  "new_sl": "100000000"
}
```

```json
// POST /api/v1/position/tp
{
  "strategy_id": "STR-001",
  "take_profit": 115000000
}
// Response:
{
  "success": true,
  "strategy_id": "STR-001",
  "old_tp": null,
  "new_tp": "115000000"
}
```

```json
// POST /api/v1/strategy/switch
{
  "strategy_id": "STR-005"
}
// Response:
{
  "success": true,
  "old_preset": "STR-003",
  "new_preset": "STR-005",
  "message": "Strategy switched, position handling applied"
}
```

---

### 3.5 설정 조회

| Method | Path | 설명 | 상태 |
|--------|------|------|------|
| GET | `/api/v1/config` | 현재 전략 설정 | 🔧 신규 |
| GET | `/api/v1/regime` | 현재 레짐 상태 | 🔧 신규 |

```json
// GET /api/v1/config
{
  "trading_mode": "paper",
  "symbol": "BTC/KRW",
  "active_strategies": ["STR-001"],
  "current_preset": {
    "id": "STR-003",
    "name": "Hybrid Reversal",
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

```json
// GET /api/v1/regime
{
  "current_regime": "ranging_high_vol",
  "confidence": 0.15,
  "mapped_preset": "STR-003",
  "last_switch_at": "2026-03-21T14:02:33Z",
  "switch_count": 1,
  "switch_locked": false,
  "pending_count": 0,
  "dca_config": {
    "buy_amount_krw": 70000,
    "interval_hours": 48
  },
  "grid_config": {
    "grid_count": 8,
    "lower_price": 99639060,
    "upper_price": 112358940
  }
}
```

---

### 3.6 시스템

| Method | Path | 설명 | 상태 |
|--------|------|------|------|
| GET | `/api/v1/version` | 버전 정보 | 🔧 신규 |

```json
// GET /api/v1/version
{
  "version": "0.2.0",
  "python": "3.13.2",
  "commit": "5baf730",
  "started_at": "2026-03-22T03:00:00Z"
}
```

---

### 3.7 WebSocket (실시간)

| Path | 설명 | 상태 |
|------|------|------|
| `/ws/v1/stream?api_key=...` | 실시간 이벤트 스트림 | ✅ 기존 |

채널: `ticker`, `bot_status`, `orders`, `positions`, `signals`, `alerts`

---

## 4. 구현 계획

### Step 1: 임베디드 모드 인프라

**수정 파일:**

| 파일 | 변경 내용 |
|------|-----------|
| `api/deps.py` | `set_trading_loops()`, `get_loops()` 추가 — TradingLoop dict 직접 참조 |
| `api/main.py` | `create_embedded_app(store, loops, event_bus)` 팩토리 추가 — lifespan에서 자체 DataStore 생성 스킵 |
| `scripts/run_paper.py` | `uvicorn.Server` asyncio task 추가 — 엔진과 동시 실행 |
| `fly.toml` | `[[services]]` 또는 `[http_service]` 섹션 추가 — 포트 8000 외부 노출 |
| `engine/Dockerfile` | `fastapi`, `uvicorn` 의존성 확보 확인 |

**의존성 흐름:**
```
run_paper.py
  ├─ bootstrap() → app (AppOrchestrator)
  │    ├─ store (DataStore)
  │    ├─ trading_loops (dict[str, TradingLoop])
  │    └─ event_bus (EventBus)
  │
  └─ create_embedded_app(store, loops, event_bus)
       └─ FastAPI app
            ├─ deps.data_store = store        (공유)
            ├─ deps.trading_loops = loops      (공유)
            └─ 모든 라우트에서 직접 참조
```

### Step 2: 신규 라우트 구현

| 신규 라우트 파일 | 엔드포인트 |
|-----------------|-----------|
| `api/routes/balance.py` | `GET /balance` |
| `api/routes/engine.py` | `GET /engine/status`, `POST /engine/stop`, `POST /engine/start`, `POST /engine/restart` |
| `api/routes/control.py` | `POST /position/close`, `POST /position/sl`, `POST /position/tp`, `POST /strategy/switch` |
| `api/routes/config.py` | `GET /config`, `GET /regime` |
| `api/routes/version.py` | `GET /version` |

**의존성:**
- `balance.py` → DataStore (`get_paper_balance`)
- `engine.py` → TradingLoops dict (직접 `loop.start()` / `loop.stop()`)
- `control.py` → TradingLoops dict + PositionManager + OrderManager
- `config.py` → TradingLoops dict (preset, regime_switch_manager 접근)
- `version.py` → 정적 정보

### Step 3: 스키마 추가

`api/schemas/responses.py`에 추가:

```python
class BalanceResponse(BaseModel):
    strategy_id: str
    krw: str
    btc: str
    initial_krw: str
    total_value_krw: str
    pnl_krw: str
    pnl_pct: float

class EngineStatusResponse(BaseModel):
    status: str          # running / stopped
    uptime_seconds: float
    trading_mode: str
    strategies: list[StrategyStatusResponse]
    regime: RegimeStatusResponse | None

class StrategyStatusResponse(BaseModel):
    strategy_id: str
    preset: str
    state: str
    last_tick_at: datetime | None
    tick_count: int
    has_open_position: bool

class RegimeStatusResponse(BaseModel):
    current: str | None
    confidence: float
    last_switch_at: datetime | None

class EngineControlResponse(BaseModel):
    success: bool
    message: str
    strategies: list[str] = []

class PositionCloseResponse(BaseModel):
    success: bool
    message: str
    sold_amount: str | None = None
    sold_price: str | None = None
    realized_pnl: str | None = None

class SLTPUpdateResponse(BaseModel):
    success: bool
    strategy_id: str
    old_value: str | None
    new_value: str

class StrategySwitchResponse(BaseModel):
    success: bool
    old_preset: str
    new_preset: str
    message: str

class ConfigResponse(BaseModel):
    trading_mode: str
    symbol: str
    active_strategies: list[str]
    current_preset: dict
    risk: dict
    regime_switch: dict

class RegimeResponse(BaseModel):
    current_regime: str | None
    confidence: float
    mapped_preset: str
    last_switch_at: datetime | None
    switch_count: int
    switch_locked: bool

class VersionResponse(BaseModel):
    version: str
    python: str
    commit: str
    started_at: datetime
```

### Step 4: Fly.io 배포

```
① flyctl secrets set TRADERJ_API_KEY="<secure-random-key>"
② fly.toml에 HTTP 서비스 추가
③ fly deploy
④ curl https://traderj-engine.fly.dev/health 로 확인
⑤ curl -H "X-API-Key: ..." https://traderj-engine.fly.dev/api/v1/engine/status
```

---

## 5. fly.toml 변경사항

```toml
# 기존 [mounts], [build], [env], [[vm]] 유지

# 추가: HTTP 서비스 노출
[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "off"     # 트레이딩 봇이므로 항상 실행
  auto_start_machines = true
  min_machines_running = 1

  [http_service.concurrency]
    type = "connections"
    hard_limit = 25
    soft_limit = 20
```

---

## 6. 보안 고려사항

| 항목 | 구현 |
|------|------|
| 인증 | `X-API-Key` 헤더 — 환경변수 `TRADERJ_API_KEY` |
| HTTPS | Fly.io 자동 TLS 인증서 (force_https=true) |
| CORS | `CORS_ORIGINS` 환경변수로 Vercel 도메인만 허용 |
| Rate Limit | Fly.io 프록시 기본 보호 + 향후 미들웨어 추가 가능 |
| 보안 헤더 | 기존 `SecurityHeadersMiddleware` 재사용 |
| 민감 데이터 필터 | 기존 `SensitiveDataFilter` 재사용 (로그에서 API_KEY 마스킹) |
| Swagger UI | production 환경에서 비활성화 (`docs_url=None`) |

---

## 7. 엔드포인트 요약 (총 27개)

| 구분 | 기존 재사용 | 신규 구현 | 합계 |
|------|:---------:|:--------:|:----:|
| 헬스체크 | 1 | 0 | 1 |
| 데이터 조회 | 10 | 1 | 11 |
| 엔진 제어 | 0 | 4 | 4 |
| 포지션/전략 관리 | 0 | 4 | 4 |
| 설정 조회 | 0 | 2 | 2 |
| 시스템 | 0 | 1 | 1 |
| 봇 관리 (기존) | 4 | 0 | 4 |
| **합계** | **15** | **12** | **27** |

---

## 8. 구현 순서

```
Phase 2-1: 임베디드 인프라 (Step 1)
  api/deps.py 수정 → api/main.py 수정 → run_paper.py 수정
  → 로컬에서 엔진+API 동시 실행 확인

Phase 2-2: 필수 신규 라우트 (Step 2 일부)
  balance.py → engine.py → control.py
  → /health, /engine/status, /balance, /position/close 테스트

Phase 2-3: 설정/분석 라우트 (Step 2 나머지)
  config.py → version.py
  → 전체 엔드포인트 로컬 테스트

Phase 2-4: 배포 (Step 4)
  fly.toml 수정 → secrets 등록 → fly deploy → 외부 테스트
```
