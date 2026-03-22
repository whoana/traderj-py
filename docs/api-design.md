# TraderJ API 설계서

**버전:** 0.2.0
**최종 수정:** 2026-03-22
**API 버전:** v1 (URL prefix: `/api/v1`)
**인증:** `X-API-Key` 헤더 (환경변수 `TRADERJ_API_KEY`)

---

## 1. 아키텍처

### 임베디드 모드 (Fly.io 운영)
```
[Fly.io Machine - nrt (Tokyo)]
  └─ scripts/run_paper.py
       ├─ Engine (TradingLoop + DataStore)
       └─ FastAPI (uvicorn, port 8000)
            ├─ 같은 asyncio loop에서 실행
            ├─ DataStore 인스턴스 공유 (IPC 불필요)
            └─ TradingLoops dict 직접 참조

[Vercel]
  └─ Next.js Dashboard
       └─ API Routes (서버사이드)
            └─ → https://traderj-engine.fly.dev/api/v1/* (X-API-Key)
```

### 설계 원칙

1. **임베디드 모드**: API 서버가 엔진과 같은 프로세스에서 실행 (IPC 불필요)
2. **컴포넌트 공유**: DataStore, TradingLoops, EventBus를 직접 참조
3. **URL 버전닝**: 모든 API 경로에 `/api/v1` prefix
4. **인증**: `X-API-Key` 헤더, Fly.io 자동 TLS

### 컴포넌트 의존성
```
run_paper.py
  ├─ bootstrap() → AppOrchestrator
  │    ├─ store (DataStore)
  │    ├─ trading_loops (dict[str, TradingLoop])
  │    └─ event_bus (EventBus)
  │
  └─ create_embedded_app(store, loops, event_bus, exchange, settings)
       └─ FastAPI app
            ├─ deps.data_store = store        (공유)
            ├─ deps.trading_loops = loops      (공유)
            └─ 모든 라우트에서 직접 참조
```

---

## 2. URL 체계

- 모든 엔드포인트: `/api/v1/...`
- Health check: `/health` (버전 없음, 로드밸런서/모니터링용)
- WebSocket: `/ws/v1/stream` (기존)
- 향후 breaking change 시 `/api/v2` 추가, v1 유지

---

## 3. 엔드포인트 전체 목록

### 3.1 헬스체크 (인증 불필요)

| Method | Path | 설명 | 구현 파일 |
|--------|------|------|-----------|
| GET | `/health` | 서비스 헬스체크 | `api/routes/health.py` |

### 3.2 데이터 조회 (읽기 전용)

| Method | Path | 설명 | 파라미터 | 구현 파일 |
|--------|------|------|----------|-----------|
| GET | `/api/v1/balance` | 잔고 현황 | `?strategy_id=STR-001` | `balance.py` |
| GET | `/api/v1/positions` | 포지션 목록 | `?strategy_id=&status=open&page=1&size=20` | `positions.py` |
| GET | `/api/v1/orders` | 주문 이력 | `?strategy_id=&status=filled&page=1&size=20` | `orders.py` |
| GET | `/api/v1/signals` | 시그널 이력 | `?strategy_id=&page=1&size=20` | `signals.py` |
| GET | `/api/v1/pnl/daily` | 일별 손익 | `?strategy_id=STR-001&days=30` | `pnl.py` |
| GET | `/api/v1/pnl/summary` | 손익 요약 | `?strategy_id=` | `pnl.py` |
| GET | `/api/v1/risk/{strategy_id}` | 리스크 상태 | path: `strategy_id` | `risk.py` |
| GET | `/api/v1/macro/latest` | 매크로 스냅샷 | - | `macro.py` |
| GET | `/api/v1/candles/{symbol}/{tf}` | 캔들 데이터 | path: `symbol`, `tf`, `?limit=200` | `candles.py` |
| GET | `/api/v1/analytics/pnl` | 누적 PnL 곡선 | `?strategy_id=STR-001&days=30` | `analytics.py` |
| GET | `/api/v1/analytics/compare` | 전략 비교 | `?strategy_ids=STR-001,STR-002&days=30` | `analytics.py` |

### 3.3 엔진 제어

| Method | Path | 설명 | 구현 파일 |
|--------|------|------|-----------|
| GET | `/api/v1/engine/status` | 엔진 상태 조회 | `engine.py` |
| POST | `/api/v1/engine/stop` | 트레이딩 루프 전체 정지 | `engine.py` |
| POST | `/api/v1/engine/start` | 트레이딩 루프 시작/재개 | `engine.py` |
| POST | `/api/v1/engine/restart` | 루프 정지 → 시작 | `engine.py` |

**설계 포인트:**
- stop은 TradingLoop.stop()만 호출, FastAPI 서버는 계속 실행
- 대시보드에서 "긴급 중지" 버튼으로 사용

### 3.4 포지션/전략 관리

| Method | Path | 설명 | Body | 구현 파일 |
|--------|------|------|------|-----------|
| POST | `/api/v1/position/close` | 긴급 포지션 청산 | `{"strategy_id": "STR-001"}` | `control.py` |
| POST | `/api/v1/position/sl` | SL 수동 변경 | `{"strategy_id": "STR-001", "stop_loss": 100000000}` | `control.py` |
| POST | `/api/v1/position/tp` | TP 수동 변경 | `{"strategy_id": "STR-001", "take_profit": 115000000}` | `control.py` |
| POST | `/api/v1/strategy/switch` | 전략 프리셋 변경 | `{"strategy_id": "STR-005"}` | `control.py` |

**설계 포인트:**
- position/close는 `loop._execute_regime_close(pos)` 사용 (시장가 매도)
- SL/TP 변경은 `position_manager.set_stop_loss/set_take_profit` 호출 (Decimal)
- strategy/switch는 `signal_gen.apply_preset(preset)` 호출

### 3.5 설정/레짐 조회

| Method | Path | 설명 | 구현 파일 |
|--------|------|------|-----------|
| GET | `/api/v1/config` | 현재 전략 설정 | `config.py` |
| GET | `/api/v1/regime` | 현재 레짐 상태 | `config.py` |

### 3.6 시스템

| Method | Path | 설명 | 구현 파일 |
|--------|------|------|-----------|
| GET | `/api/v1/version` | 버전/빌드 정보 | `version.py` |

### 3.7 봇 관리 (IPC/Standalone 모드)

| Method | Path | 설명 | 구현 파일 |
|--------|------|------|-----------|
| GET | `/api/v1/bots` | 봇 목록 | `bots.py` |
| GET | `/api/v1/bots/{strategy_id}` | 봇 상태 | `bots.py` |
| POST | `/api/v1/bots/{strategy_id}/start` | 봇 시작 | `bots.py` |
| POST | `/api/v1/bots/{strategy_id}/stop` | 봇 정지 | `bots.py` |

### 3.8 WebSocket (실시간)

| Path | 설명 |
|------|------|
| `/ws/v1/stream?api_key=...` | 실시간 이벤트 스트림 |

채널: `ticker`, `bot_status`, `orders`, `positions`, `signals`, `alerts`

---

## 4. 보안

| 항목 | 구현 |
|------|------|
| 인증 | `X-API-Key` 헤더 — 환경변수 `TRADERJ_API_KEY` |
| HTTPS | Fly.io 자동 TLS (force_https=true) |
| CORS | `CORS_ORIGINS` 환경변수로 허용 도메인 관리 |
| 보안 헤더 | `SecurityHeadersMiddleware` |
| 민감 데이터 | `SensitiveDataFilter` (로그에서 API_KEY 마스킹) |
| Swagger UI | production에서 비활성화 (`docs_url=None`) |

---

## 5. 엔드포인트 요약

| 구분 | 개수 |
|------|:----:|
| 헬스체크 | 1 |
| 데이터 조회 | 11 |
| 엔진 제어 | 4 |
| 포지션/전략 관리 | 4 |
| 설정/레짐 조회 | 2 |
| 시스템 | 1 |
| 봇 관리 | 4 |
| **합계** | **27** |

---

## 6. 배포 구성

```toml
# fly.toml
[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "off"     # 트레이딩 봇 — 항상 실행
  auto_start_machines = true
  min_machines_running = 1

  [http_service.concurrency]
    type = "connections"
    hard_limit = 25
    soft_limit = 20
```

시크릿: `flyctl secrets set TRADERJ_API_KEY="<key>"`
