# HANDOFF: traderj

## Goal

BTC/KRW 자동매매 봇 엔진(TraderJ). SQLite 기본 DB, 시그널 기반 전략 11종(default + STR-001~010), Paper/Backtest/Real 모드 운영. 레짐 감지(6-type) → 전략 자동 전환, Telegram 알림, 모니터링 대시보드 연동. AI Tuner로 파라미터 자동 최적화.

**현재 목표**: 백테스트 기반 AI Tuner 활성화 완료. AI Tuner 상세설계서 작성 진행 중.

---

## Current Progress

### COMPLETED — AI Tuner ActionPanel 활성화 (2026-03-25)

백테스트 대시보드의 "준비중" 버튼 2개를 활성화:

**Action B — 레짐 매핑 적용:**
- `POST /backtest/apply-regime-map` 엔드포인트 추가
- 백테스트 AI레짐 분석 결과의 레짐-전략 제안을 `REGIME_PRESET_MAP`에 즉시 반영
- 수정: `api/routes/backtest.py` (ApplyRegimeMapRequest + endpoint)

**Action C — 파라미터 최적화:**
- `BacktestMode.OPTIMIZE` 모드 추가 (스키마, job_manager, 러너)
- `run_optimize()`: Optuna TPE sampler로 Tier 1 파라미터 최적화 (threshold, TF weights, score weights)
- 현재 preset 기준 ±30% 탐색, 자동 정규화, Top 3 후보 반환
- 10 trials ~5초, 30 trials ~15초 소요
- 수정: `engine/backtest/schemas.py`, `engine/backtest/runners.py`, `engine/backtest/job_manager.py`

**대시보드:**
- ActionPanel.tsx 완전 재작성: 두 버튼 활성화, 최적화 결과 카드(baseline vs 최적화), 후보 테이블, 파라미터 상세
- Props 확장: `startDate`, `endDate` 추가 (최적화 job에 날짜 전달용)
- 수정: `dashboard/src/components/backtest/ActionPanel.tsx`, `dashboard/src/app/backtest/page.tsx`

**테스트 결과:**
- apply-regime-map: API 직접 테스트 성공
- optimize: STR-010, 2024-11 기간, 10 trials → baseline +2.51% → 최적 +2.55%
- 엔진 Fly.io + 대시보드 Vercel 배포 완료

### COMPLETED — STR-009/010 신규 프리셋 + 백테스트 성능 수정 (2026-03-25)

**STR-009 "Bull Trend Rider (4h)":**
- 강세장용: buy_threshold=0.04, sell_threshold=-0.15
- 넓은 trailing stop (5%/4%), SL 6%, 포지션 35%
- `risk_config` 필드 추가 (per-preset risk overrides)

**STR-010 "Swing Trend (4h/1d)":**
- 중간 추세용: buy_threshold=0.06, sell_threshold=-0.12
- trailing 3%/3%, SL 5%, 포지션 25%

**백테스트 성능 수정 3건:**
1. `asyncio.to_thread()` — CPU-bound 백테스트가 이벤트 루프 차단 방지
2. 인디케이터 사전 계산 — O(n²) → O(n) (compute_indicators 1회만 실행)
3. `start_date`/`end_date` 파라미터 — 정확한 기간 필터링

**백테스트 "load failed" 버그 수정:**
- 180초 → 600초 타임아웃 (`JOB_TIMEOUT_SEC`)
- 3개 수정으로 ~70x 속도 개선 (180s → 20s)

### COMPLETED — Auth 500 에러 수정 (2026-03-25)

- `DASHBOARD_PASSWORD` 환경변수의 `!` 문자가 bash에서 깨짐
- `printf 'traderj2026!' | npx vercel env add` 로 해결
- route.ts에 try-catch + `export const runtime = "nodejs"` 추가

### COMPLETED — 대시보드 UX 개선 (2026-03-24)

전략 설명 팝업, Cache-Control 헤더, 차트 자동 스크롤 등.

### COMPLETED — Earlier Phases

- 레짐 6-type 확장 + Bear 프리셋 (2026-03-23)
- Next.js 모니터링 대시보드 Phase 4 (2026-03-22~23)
- FastAPI API 27개 엔드포인트
- Fly.io 엔진 배포

---

## What Worked

- **Optuna degraded mode**: LLM 없이 Optuna만으로 파라미터 최적화 — 빠르고 안정적
- **asyncio.to_thread()**: CPU-bound 백테스트를 이벤트 루프 밖에서 실행
- **인디케이터 사전 계산**: `compute_indicators()` 1회 실행 후 per-bar window slice로 재사용
- **per-preset risk_config**: `StrategyPreset`에 optional `RiskConfig` 필드 추가, 전략별 리스크 파라미터 분리
- **BacktestEngine date range**: `start_date`/`end_date` 파라미터로 정확한 기간 타겟팅
- **기존 job infrastructure 재사용**: OPTIMIZE 모드를 BacktestJobManager에 통합 — 별도 인프라 불필요
- **Cache-Control 헤더**: API 프록시 + vercel.json 양쪽에서 캐시 방지
- **API 프록시 패턴**: Next.js `/api/engine/*` → Fly.io `/api/v1/*`
- **StrEnum 자동 직렬화**: 새 모드/레짐 추가 시 API 변경 최소화

## What Didn't Work

- **STR-009 buy_threshold=0.04**: 너무 낮아서 초기 하락 시 조기 진입 → 3연속 SL 히트 → 쿨다운 → 상승 놓침. 강세장용이라도 최소 0.06 이상 필요
- **asyncio.to_thread(eng.run, data, ptf)**: positional arg 문제 — `primary_tf`는 3번째 인자. lambda로 감싸야 함: `asyncio.to_thread(lambda: eng.run(data, primary_tf=ptf))`
- **Vercel CLI 배포 경로**: `dashboard/` 내에서 실행 시 `dashboard/dashboard` 경로 찾음. 프로젝트 루트에서 `.vercel` 교체 후 배포 필요
- **daily_gate=True in bear preset**: Bear 시장에서 EMA gate가 모든 매수 차단 → False로 변경
- **Vercel env var bash `!`**: `vercel env add` 시 bash history expansion으로 `!` 깨짐 → `printf` stdin으로 해결

---

## Next Steps (순서대로)

### 1. 🔴 미커밋 변경사항 커밋

이번 세션과 이전 세션의 모든 변경사항이 미커밋 상태:
```bash
# 이전 세션 (3/24)
dashboard/src/app/api/engine/[...path]/route.ts  # Cache-Control
dashboard/src/components/chart/CandlestickChart.tsx  # scrollToRealTime
dashboard/vercel.json  # Vercel 캐시 설정

# 이번 세션 (3/25)
engine/backtest/schemas.py  # OPTIMIZE 모드
engine/backtest/runners.py  # run_optimize + per-preset risk
engine/backtest/job_manager.py  # OPTIMIZE summary
api/routes/backtest.py  # apply-regime-map + optimize
engine/strategy/presets.py  # STR-009/010 + risk_config
engine/strategy/backtest/engine.py  # 사전 계산 + date range
engine/strategy/signal.py  # 사전 계산 skip
dashboard/src/components/backtest/ActionPanel.tsx  # 버튼 활성화
dashboard/src/app/backtest/page.tsx  # ActionPanel props
```

### 2. 🟡 AI Tuner 상세설계서 작성

`docs/02-design/features/ai-tuner.design.md` — 계획 파일 존재:
`/Users/whoana/.claude/plans/sharded-hugging-kettle.md`

14개 섹션 구조의 상세설계서. 기획서 `docs/전략개선.md` 기반.
`engine/tuner/` 15개 모듈이 이미 구현됨 (93% match rate).
설계서는 "어떻게"를 코드 수준으로 문서화하는 역할.

### 3. 🟡 최적화 결과 "적용" 기능

현재 optimize는 결과만 보여주고 적용 버튼이 없음.
필요: "적용" 클릭 시 최적 파라미터를 엔진의 현재 SignalGenerator에 hot-swap.
`POST /backtest/apply-optimized-params` 엔드포인트 + ActionPanel "적용" 버튼.

### 4. 🟢 TP(Take Profit) 로직 보완

현재 합산 포지션에 TP 미설정. `load_open_positions()` 시 TP 없는 포지션에 자동 TP 설정 필요.

### 5. 🟢 Vercel Git 자동 배포 연동

현재 CLI 수동 배포. GitHub 레포 연결 + Root Directory `dashboard` 설정 필요.

---

## 현재 엔진 상태 (2026-03-25)

| 항목 | 값 |
|------|-----|
| 모드 | Paper Trading (Fly.io nrt) |
| 전략 | 11종 (default + STR-001~010, 레짐 자동전환) |
| 레짐 감지 | 6-type (bull/bear/ranging × high/low vol) |
| 엔진 API | https://traderj-engine.fly.dev |
| 대시보드 | https://dashboard-six-mu-40.vercel.app |
| 매크로 수집 | 5분 주기 (Fear & Greed, Funding Rate, BTC Dom, Kimchi Premium) |
| Git | main, 다수 미커밋 변경사항 있음 |
| Telegram | chat_id: 8704649186 |

---

## Key Files Reference

| File | Role |
|------|------|
| `engine/config/settings.py` | 모든 설정 (DB, Exchange, Trading, Telegram) |
| `engine/bootstrap.py` | 앱 부트스트랩 (컴포넌트 와이어링) |
| `engine/loop/trading_loop.py` | 트레이딩 루프 (tick cycle, 레짐 감지) |
| `engine/strategy/presets.py` | 전략 프리셋 11개 (STR-009/010 추가) |
| `engine/strategy/regime.py` | 레짐 감지 + REGIME_PRESET_MAP |
| `engine/strategy/risk.py` | RiskConfig (SL/TP/Trailing Stop) |
| `engine/strategy/signal.py` | SignalGenerator (8단계 파이프라인) |
| `engine/strategy/backtest/engine.py` | BacktestEngine (사전 계산 + date range) |
| `engine/backtest/runners.py` | 백테스트 러너 4종 (single, compare, ai_regime, optimize) |
| `engine/backtest/analyzer.py` | 결과 분석 + 레짐 매핑 제안 |
| `engine/backtest/job_manager.py` | 비동기 job 관리 |
| `engine/tuner/optimizer.py` | HybridOptimizer (Optuna + LLM) |
| `engine/tuner/config.py` | Tier 1/2/3 파라미터 범위 |
| `api/routes/backtest.py` | 백테스트 API (6 endpoints) |
| `dashboard/src/app/backtest/page.tsx` | 백테스트 페이지 |
| `dashboard/src/components/backtest/ActionPanel.tsx` | 분석+액션 패널 (3 buttons) |
| `dashboard/src/app/api/engine/[...path]/route.ts` | 엔진 API 프록시 |
| `docs/전략개선.md` | AI Tuner 기획서 |

## Architecture Notes

- **기본 DB: SQLite** (`DB_TYPE=sqlite`), `/data/traderj.db` (Fly.io 볼륨)
- **시간대: UTC** — 엔진 UTC, 대시보드 `toLocaleString("ko-KR")` 한국 시간
- **API 인증**: `X-API-Key` 헤더, 환경변수 `TRADERJ_API_KEY`
- **대시보드 인증**: 비밀번호 + Passkey(Face ID), HttpOnly 세션 쿠키 (7일)
- **API 프록시**: 브라우저 → Next.js `/api/engine/*` → Fly.io `/api/v1/*`
- **전략 프리셋**: 11종, 레짐 자동 전환 (REGIME_PRESET_MAP)
- **venv**: `.venv/bin/python` (Python 3.13)
- **Telegram MCP**: chat_id: 8704649186
- **AI Tuner**: `engine/tuner/` 15개 모듈 구현 완료, 백테스트 UI 연동 완료
