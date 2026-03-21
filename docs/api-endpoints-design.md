# TraderJ Engine API 엔드포인트 설계

**작성일:** 2026-03-21
**목적:** FastAPI 경량 서버 구현 + Next.js 대시보드 연동용 API 설계
**인증:** X-API-Key 헤더

---

## 📊 데이터 조회 (기본)

| Method | Path | 설명 | 파라미터 |
|--------|------|------|----------|
| GET | `/health` | 헬스체크 (uptime, DB상태, 전략상태) | - |
| GET | `/api/positions` | 현재 포지션 (미실현 PnL 포함) | `?strategy_id=` |
| GET | `/api/orders` | 주문 이력 | `?strategy_id=&limit=50` |
| GET | `/api/pnl` | 일별 손익 | `?days=30` |
| GET | `/api/signals` | 최근 시그널 | `?limit=20&strategy_id=` |
| GET | `/api/balance` | 잔고 현황 | `?strategy_id=` |

---

## 🔧 엔진 제어

| Method | Path | 설명 | Body |
|--------|------|------|------|
| GET | `/api/engine/status` | 엔진 상태 (running/stopped/error, 현재 전략, 마지막 tick 시간, uptime) | - |
| POST | `/api/engine/stop` | 엔진 긴급 중지 (트레이딩 루프만 정지, API 서버는 유지) | - |
| POST | `/api/engine/start` | 엔진 시작 (중지된 상태에서 재개) | `{"strategy_ids": ["STR-001"]}` |
| POST | `/api/engine/restart` | 엔진 중지 → 시작 | `{"strategy_ids": ["STR-001"]}` |

**설계 포인트:**
- stop은 TradingLoop.stop()만 호출, FastAPI 서버는 계속 실행
- start/restart 시 strategy_ids 변경 가능
- 대시보드에서 "긴급 중지" 버튼으로 사용

---

## ⚙️ 설정/관리

| Method | Path | 설명 | Body |
|--------|------|------|------|
| GET | `/api/config` | 현재 전략 설정 조회 (프리셋 파라미터, 리스크 설정) | - |
| POST | `/api/strategy/switch` | 전략 변경 (루프 재시작) | `{"strategy_id": "STR-005"}` |
| POST | `/api/position/close` | 수동 포지션 청산 (긴급 탈출) | `{"strategy_id": "STR-001"}` |
| POST | `/api/sl` | SL 수동 변경 | `{"strategy_id": "STR-001", "stop_loss": 100000000}` |
| POST | `/api/tp` | TP 수동 변경 | `{"strategy_id": "STR-001", "take_profit": 110000000}` |

**설계 포인트:**
- position/close는 현재가로 시장가 매도 시뮬레이션
- strategy/switch는 기존 루프 중지 → 새 전략으로 루프 시작
- SL/TP 변경은 position_manager.set_stop_loss/set_take_profit 호출

---

## 📈 분석

| Method | Path | 설명 | 파라미터 |
|--------|------|------|----------|
| GET | `/api/performance` | 누적 수익률, 승률, MDD, 샤프비율 등 통계 | `?days=30` |
| GET | `/api/candles` | 최근 캔들 데이터 | `?timeframe=4h&limit=100` |
| GET | `/api/regime` | 현재 레짐 상태 (trending/ranging/volatile) | - |

---

## 🛡 시스템

| Method | Path | 설명 | 파라미터 |
|--------|------|------|----------|
| GET | `/api/logs` | 최근 로그 (tail) | `?lines=100&level=warning` |
| POST | `/api/db/backup` | DB 백업 트리거 (볼륨 내 복사) | - |
| GET | `/api/version` | 엔진 버전, 빌드 시간, Python 버전 | - |

---

## 우선순위

### 🔴 Phase 2 필수 (첫 배포)
1. `GET /health`
2. `GET /api/positions`
3. `GET /api/orders`
4. `GET /api/pnl`
5. `GET /api/signals`
6. `GET /api/balance`
7. `GET /api/engine/status`
8. `POST /api/engine/stop`
9. `POST /api/engine/start`
10. `POST /api/position/close` (긴급 청산)

### 🟡 Phase 2 권장 (같이 구현하면 좋음)
11. `POST /api/engine/restart`
12. `GET /api/config`
13. `POST /api/strategy/switch`
14. `POST /api/sl`
15. `POST /api/tp`
16. `GET /api/performance`

### 🟢 Phase 4와 함께 (대시보드 개발 시)
17. `GET /api/logs`
18. `GET /api/candles`
19. `GET /api/regime`
20. `POST /api/db/backup`
21. `GET /api/version`

---

## 기술 스택

- **프레임워크:** FastAPI (uvicorn)
- **인증:** X-API-Key 헤더 (환경변수 API_KEY)
- **포트:** 8000 (fly.toml에 서비스 추가 필요)
- **실행:** trading loop과 같은 프로세스에서 asyncio로 병행 실행
- **DB 접근:** 기존 data_store 인스턴스 공유 (읽기 위주, 쓰기는 제어 API만)

## 대시보드 연동

Next.js 대시보드(Vercel)에서 이 API를 호출:
```
[Vercel Next.js] → API Routes → https://traderj-engine.fly.dev/api/* (X-API-Key)
```

API Routes가 프록시 역할을 하여 API_KEY를 서버사이드에서 관리.
