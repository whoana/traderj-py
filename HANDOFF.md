# HANDOFF: traderj

## Goal

BTC/KRW 자동매매 봇 엔진(TraderJ). SQLite를 기본 DB로 사용하고, 시그널 기반 전략 7종(default + STR-001~006)을 Paper/Backtest/Real 모드로 운영한다. 레짐 감지 -> 전략 자동 전환(Signal + DCA/Grid), Telegram 알림, Dashboard 연동까지 포함.

**현재 목표**: Fly.io(도쿄)에 엔진 배포 + Next.js 모니터링 대시보드를 Vercel에 재개발

---

## Current Progress

### ACTIVE — Fly.io + Vercel 배포 (2026-03-21, B안 확정)

Oracle Cloud Free Tier 가입 오류로 B안(Fly.io + Vercel) 확정. 계획 수립 완료, 실행 대기.

**아키텍처:**
```
[Fly.io nrt(도쿄)]           [Vercel]
  TraderJ Engine               Next.js 모니터링 (신규 개발)
  Python 3.13 + SQLite         대시보드 SSR
  Telegram 알림                API Routes → 엔진 프록시
  경량 API (8000)
```

**Phase 1~3 (엔진 배포)**: 계획 완료, 약 1시간 20분 소요 예상
**Phase 4 (Next.js 모니터링)**: 별도 프로젝트로 진행

**사전 확인:**
- flyctl 설치됨 (/opt/homebrew/bin/flyctl), 로그인 완료 (whoana@gmail.com)
- Docker v29.2.1, Dockerfile 존재 (engine/Dockerfile, production target)
- 가용 리전: nrt(도쿄) ~30ms

### COMPLETED — SL/포지션 버그 수정 (2026-03-21)

1. **trading_loop.py:419** — SL fallback 추가: risk decision 없으면 진입가 ×0.97 (3%) 자동 SL
2. **position_manager.py:53** — 중복 포지션 감지 시 CRITICAL 로그 경고 추가
3. **DB** — 2개 오픈 포지션(pos2+pos3)을 가중평균 합산 병합 → 단일 포지션으로 정리

### COMPLETED — 실환경 전환 검토 (2026-03-21)

**판정: ❌ 실환경 전환 불가** — 추가 검증 필요
- 11일/1건 거래 → 통계적 무의미
- BTC HODL 대비 -2.17% 열위 (Alpha 부재)
- 백테스트 9개 전략 중 7개 마이너스
- 최소 2개월 추가 페이퍼 검증 권고

### COMPLETED — 180일 Robustness 검증 (2026-03-08)

180일 장기 백테스트 + 파라미터 민감도(+-20%) 분석 수행.
- 파라미터 안정성 7/7 Stable
- MDD 전체 1.3% 미만
- `scripts/run_backtest_robustness.py`

### COMPLETED — DCA/Grid TradingLoop 연동 / 레짐 매핑 / 전략 튜닝 / SQLite 전환 / Telegram 알림

---

## What Worked

- **SL fallback 로직**: decision이 None이어도 3% 고정 SL 자동 적용 — 재발 방지 효과
- **포지션 합산 병합**: 중복 포지션 문제를 가중평균 합산으로 해결
- **Grid Search Walk-Forward**: 60d train / 30d OOS 분할로 과적합 방지
- **HYBRID + 장기 TF**: 횡보장에서 HYBRID + 4h/1d 조합이 안정적
- **Protocol 기반 추상화**: DataStore Protocol 덕분에 DB 교체 용이
- **RegimeSwitchManager**: debounce(3회) + cooldown(60분)으로 안정적 레짐 전환
- **DCA 상태 보존**: 레짐 전환 시 매수 이력 유지
- **파라미터 안정성 7/7**: threshold +-20% 변동에도 수익률 변동 1pp 이내
- **caffeinate + nohup**: 맥북 슬립 방지 + 터미널 종료 후에도 유지

## What Didn't Work

- **Oracle Cloud Free Tier 가입**: 내부 오류로 계정 생성 실패 → Fly.io로 전환
- **SL 없이 11일 운영**: position_manager가 strategy당 1포지션만 관리, 두 번째 포지션의 SL 누락
- **TP 미설정 운영**: 미실현 +222,394원 → +31,285원으로 이익 녹음 (수익 확정 메커니즘 부재)
- **15m 타임프레임**: 노이즈 + 속도 저하. 제거 후 개선
- **높은 macro_weight(0.2~0.3)**: 백테스트에서 tech_score 감쇄
- **180일 양수 수익률 달성 실패**: 장기 횡보/하락장에서 0/7 전략이 양수

---

## Next Steps (순서대로)

### 1. 🔴 Fly.io 엔진 배포 (Phase 1~3)

**Phase 1: 앱 생성 + 배포 (20분)**
```bash
# 1. fly.toml 생성 (프로젝트 루트에)
#    app=traderj-engine, region=nrt, shared-cpu-1x, 512MB
#    mount: traderj_data → /data (SQLite 영속)
#    process: python -u -m scripts.run_paper

# 2. Dockerfile 수정 — CMD를 run_paper로, /data 디렉토리 생성

# 3. 시크릿 등록
fly secrets set TELEGRAM_BOT_TOKEN=<token> TELEGRAM_CHAT_ID=<id> API_KEY=<key>

# 4. 볼륨 + 배포
fly volumes create traderj_data --region nrt --size 1
fly deploy
```

**Phase 2: 경량 API 추가 (30분)**
- GET /health, /api/positions, /api/orders, /api/pnl, /api/signals, /api/balance
- X-API-Key 인증
- Next.js 모니터링 연동용

**Phase 3: DB 이전 + 배포 워크플로우 (15분)**
- `fly ssh sftp` 로 기존 traderj.db 업로드
- `fly deploy` 원클릭 배포 확인

### 2. 🟡 Next.js 모니터링 대시보드 (Phase 4, 별도 프로젝트)

- traderj-monitor/ 신규 프로젝트 (Vercel 배포)
- ENGINE_URL=https://traderj-engine.fly.dev
- SSR 대시보드 + API 프록시
- 기존 dashboard/ 디렉토리는 제거 예정 (Next.js로 재개발)

### 3. 🟡 TP(Take Profit) 로직 보완

현재 합산 포지션에 TP 미설정. 신규 매수 시에만 TP 계산됨.
→ load_open_positions() 시 TP 없는 포지션에 자동 TP 설정 로직 추가 필요

### 4. 🟢 전략 개선 (선택)

- 매크로 데이터 통합 (macro_snapshots 현재 비어있음)
- STR-005, STR-001-regime 우선 검토 (백테스트 양수 전략)
- DCA/Grid 백테스트 엔진 구현

---

## 현재 엔진 상태 (2026-03-21)

| 항목 | 값 |
|------|-----|
| 모드 | Paper Trading (로컬 M2 MacBook) |
| 전략 | STR-001 (Conservative Trend, 4h primary) |
| 포지션 | 0.03148295 BTC @104,405,282원 |
| SL | 101,273,124원 (-3%) ✅ |
| TP | 미설정 ⚠️ |
| 누적수익률 | +0.64% (11일) |
| 테스트 | 467/467 passed |

---

## Key Files Reference

| File | Role |
|------|------|
| `engine/config/settings.py` | 모든 설정 (DB, Exchange, Trading, Telegram) |
| `engine/data/__init__.py` | `create_data_store()` 팩토리 |
| `engine/data/sqlite_store.py` | SQLite DataStore (기본) |
| `engine/bootstrap.py` | 앱 부트스트랩 (컴포넌트 와이어링) |
| `engine/strategy/signal.py` | SignalGenerator (8단계 파이프라인) |
| `engine/strategy/presets.py` | 전략 프리셋 정의 (7개, 튜닝 완료) |
| `engine/strategy/risk.py` | RiskEngine + RiskConfig + RiskDecision |
| `engine/loop/trading_loop.py` | 트레이딩 루프 (SL fallback 추가됨) |
| `engine/execution/position_manager.py` | 포지션 관리 (중복 감지 추가됨) |
| `engine/notification/telegram.py` | TelegramNotifier |
| `engine/Dockerfile` | Docker 빌드 (production target) |
| `scripts/run_paper.py` | Paper Trading 실행기 |
| `shared/protocols.py` | DataStore Protocol 정의 |

## Architecture Notes

- **기본 DB: SQLite** (`DB_TYPE=sqlite`), PostgreSQL은 `DB_TYPE=postgres`로 전환 가능
- **전략 프리셋**: 2026-03-08 튜닝 완료, 파라미터 안정성 7/7 검증됨
- **position_manager**: strategy_id당 1개 포지션만 메모리 관리 (구조적 한계, 중복 감지 경고 추가됨)
- **테스트**: 467개 전체 통과 (`pytest engine/tests/ -v`)
- **venv**: `.venv/bin/python` (Python 3.13)
- **Telegram MCP**: Claude Code에서 Telegram 채널 리슨 가능 (plugin:telegram:telegram)
