# HANDOFF: traderj

## Goal

BTC/KRW 자동매매 봇 엔진(TraderJ). SQLite 기본 DB, 시그널 기반 전략 7종(default + STR-001~006), Paper/Backtest/Real 모드 운영. 레짐 감지 → 전략 자동 전환(Signal + DCA/Grid), Telegram 알림, 모니터링 대시보드 연동.

**현재 목표**: Phase 4 Next.js 대시보드 완성 (Vercel) — 기본 기능 구현 완료, 추가 페이지(Analytics, Control) 개발 필요

---

## Current Progress

### COMPLETED — Phase 4: Next.js 모니터링 대시보드 (2026-03-22~23)

Vercel 배포 + 인증 + 실시간 모니터링 대시보드 구현 완료.

**배포:**
- 대시보드: `https://dashboard-six-mu-40.vercel.app`
- 엔진 API: `https://traderj-engine.fly.dev/api/v1/*`
- Vercel 환경변수: ENGINE_URL, ENGINE_API_KEY, DASHBOARD_PASSWORD, SESSION_SECRET

**인증 시스템:**
- 비밀번호 로그인: HttpOnly 세션 쿠키 (`traderj-session`, 7일 만료)
- Passkey/Face ID: WebAuthn 표준 (`@simplewebauthn/server` v13 + `@simplewebauthn/browser` v13)
- Passkey 자격증명: 엔진 SQLite DB의 `dashboard_passkeys` 테이블에 저장
- 미들웨어: 인증되지 않은 요청 → `/login` 리다이렉트

**대시보드 메인 (page.tsx):**
- Status Bar: Running 뱃지, Strategy ID, Uptime, Emergency Stop 버튼
- KPI 카드 4개: Total Balance, Return(%), BTC Price(실시간), Regime
- BTC/KRW 캔들스틱 차트 (lightweight-charts, 1h/4h/1d)
- Open Positions 패널 (SL/TP 표시)
- Macro Indicators 패널 (Fear & Greed, Kimchi Premium, Funding Rate, BTC Dominance, Market Score)
- 30초 자동 갱신

**API 프록시 패턴:**
- 브라우저 → Next.js API Routes (`/api/engine/*`) → Fly.io 엔진 (`/api/v1/*`)
- API 키는 서버사이드에만 존재 (브라우저 노출 없음)
- GET/POST/PUT/DELETE 모두 지원하는 catch-all 프록시

**모바일 최적화 (iPhone 13 Pro, 390x844):**
- TopNav 44px, 반응형 아이콘/폰트
- KPI 카드 반응형 패딩/폰트 (모바일: label 10px, value 16px)
- 차트 높이: 모바일 250px / 데스크탑 400px
- Y축 라벨 축약 포맷 (116000000 → 116.0M)
- Emergency Stop 모바일에서 "STOP"으로 축약

**매크로 데이터 수집 (엔진 수정):**
- `MacroCollector` httpx 기반 실제 API 호출 구현
- Fear & Greed (api.alternative.me), Funding Rate (Binance Futures), BTC Dominance (CoinGecko)
- Kimchi Premium: Upbit vs Binance + USD/KRW 환율 계산 (신규 구현)
- `bootstrap.py` + `run_paper.py`에 5분 주기 스케줄러 등록
- 엔진 Fly.io 재배포 완료

**구현 파일 (dashboard/):**
- `src/app/page.tsx` — 메인 대시보드 (KPI, 차트, 포지션, 매크로)
- `src/app/login/page.tsx` — 로그인 (비밀번호 + Passkey)
- `src/app/settings/page.tsx` — 설정 (Passkey 관리, Regime, Risk, Macro, Config)
- `src/app/api/engine/[...path]/route.ts` — 엔진 프록시 (GET/POST/PUT/DELETE)
- `src/app/api/auth/route.ts` — 비밀번호 인증
- `src/app/api/auth/passkey/` — WebAuthn 4개 라우트 (register-options/verify, auth-options/verify)
- `src/components/layout/TopNav.tsx` — 상단 내비게이션
- `src/components/chart/CandlestickChart.tsx` — lightweight-charts 캔들스틱
- `src/components/settings/PasskeyManager.tsx` — Passkey CRUD UI
- `src/lib/api.ts` — 클라이언트 API 래퍼
- `src/lib/engine.ts` — 서버사이드 엔진 fetch
- `src/lib/passkey.ts` — 서버사이드 Passkey 헬퍼
- `src/middleware.ts` — 인증 미들웨어

**구현 파일 (엔진):**
- `engine/data/macro.py` — MacroCollector (httpx, 5개 외부 API)
- `engine/bootstrap.py` — MacroCollector 등록
- `scripts/run_paper.py` — 매크로 5분 주기 수집 태스크
- `api/routes/passkeys.py` — Passkey CRUD API (aiosqlite)

### COMPLETED — Phase 2: FastAPI 임베디드 API (2026-03-22)

엔진 프로세스 내 FastAPI 서버 구현 + Fly.io 배포 완료. 27개 엔드포인트.

### COMPLETED — Phase 1: Fly.io 엔진 배포 (2026-03-21~22)

- `fly.toml`, `engine/Dockerfile` 생성
- SQLite DB 볼륨 마운트 (`/data/traderj.db`)
- Telegram 알림 동작 확인

### COMPLETED — 기타

- SL/포지션 버그 수정: SL fallback 3%, 중복 포지션 감지
- 180일 Robustness 검증: 파라미터 안정성 7/7 Stable
- DCA/Grid 연동, 레짐 매핑, SQLite 전환, Telegram 알림

---

## What Worked

- **API 프록시 패턴**: Next.js API Routes → 엔진 API 프록시로 API 키 서버사이드 유지
- **WebAuthn Passkey**: `@simplewebauthn`으로 Face ID/Touch ID 인증 구현
- **Cookie 기반 세션**: HttpOnly 쿠키 + 미들웨어 조합으로 간단한 인증
- **window.location.href**: Next.js App Router에서 `router.push()` 대신 full reload로 쿠키 인증 리다이렉트 해결
- **next/dynamic + ssr: false**: `@simplewebauthn/browser` SSR 크래시 해결
- **lightweight-charts custom priceFormat**: Y축 라벨 포맷 커스터마이징
- **httpx (transitive dep)**: `python-telegram-bot`이 이미 httpx 의존 → 추가 설치 불필요
- **임베디드 API 패턴**: `create_embedded_app()` → 엔진 컴포넌트 직접 공유
- **Protocol 기반 추상화**: DataStore Protocol 덕분에 DB/API 교체 용이
- **caffeinate + nohup**: 맥북 슬립 방지 + 터미널 종료 후 유지

## What Didn't Work

- **router.push("/")**: Next.js App Router에서 쿠키 기반 인증 후 리다이렉트 실패 → `window.location.href` 사용
- **@simplewebauthn/browser 정적 import**: SSR 시 window/navigator 참조로 크래시 → dynamic import 필수
- **Vercel Blob 스토어**: Passkey 저장용으로 시도했으나 interactive prompt 문제 → 엔진 API 저장으로 전환
- **vercel env add <<< "value"**: stdin 구문 안 됨 → `--value "value" --yes` 플래그 사용
- **MacroCollector http_client=None**: 기본값만 반환 → httpx 직접 사용으로 변경
- **bootstrap_and_run()만 수정**: run_paper.py는 별도 엔트리포인트라 매크로 스케줄링 누락 → 양쪽 모두 수정 필요

---

## Next Steps (순서대로)

### 1. ✅ 변경사항 커밋 + 푸시 — 완료

커밋 `6e0c9f6` (Phase 4 대시보드), `c53483a` (스토리보드 Gap 해결). 푸시 완료.

### 2. ✅ Analytics 페이지 — 구현 완료

PnL 차트 (Cumulative + Daily), 트레이드 이력 테이블, 기간 선택 (7/14/30/60/90일).

### 3. ✅ Control 페이지 — 구현 완료

엔진 Start/Stop/Restart, 전략 프리셋 선택 (STR-001~006), 포지션 Close, SL/TP 조정.

### 4. ✅ Storyboard Gap 해결 — 완료

- Emergency Stop: `confirm()` → 커스텀 ConfirmDialog 모달
- StatusBadge: running 상태 pulse 애니메이션
- 모바일 하단 탭 바 내비게이션 (BottomNav, sm:hidden, safe-area 패딩)

### 5. 🟢 TP(Take Profit) 로직 보완

현재 합산 포지션에 TP 미설정. `load_open_positions()` 시 TP 없는 포지션에 자동 TP 설정 필요.

### 6. 🟢 전략 개선 (선택)

- DCA/Grid 백테스트 엔진 구현

---

## 현재 엔진 상태 (2026-03-23)

| 항목 | 값 |
|------|-----|
| 모드 | Paper Trading (Fly.io nrt) |
| 전략 | STR-001 (preset: STR-005, 레짐 자동전환) |
| 레짐 | ranging_low_vol |
| 포지션 | 없음 (BTC 0) |
| 잔고 | KRW ~10,085,107 |
| PnL | +0.85% |
| 엔진 API | https://traderj-engine.fly.dev |
| 대시보드 | https://dashboard-six-mu-40.vercel.app |
| 매크로 수집 | 5분 주기 실시간 (Fear & Greed, Funding Rate, BTC Dom, Kimchi Premium) |
| 테스트 | 467+ passed |
| Git | commit c53483a (main) |

---

## Key Files Reference

| File | Role |
|------|------|
| `engine/config/settings.py` | 모든 설정 (DB, Exchange, Trading, Telegram) |
| `engine/bootstrap.py` | 앱 부트스트랩 (컴포넌트 와이어링 + MacroCollector) |
| `engine/loop/trading_loop.py` | 트레이딩 루프 (tick cycle) |
| `engine/data/macro.py` | MacroCollector (httpx 기반 5개 외부 API) |
| `engine/strategy/signal.py` | SignalGenerator (8단계 파이프라인) |
| `engine/strategy/presets.py` | 전략 프리셋 7개 |
| `api/main.py` | FastAPI 앱 팩토리 (standalone + embedded) |
| `api/routes/passkeys.py` | Passkey CRUD API |
| `scripts/run_paper.py` | Paper Trading + API + Macro 수집 실행기 |
| `fly.toml` | Fly.io 배포 설정 |
| `dashboard/` | Next.js 15 App Router 대시보드 (Vercel) |
| `dashboard/src/app/page.tsx` | 메인 대시보드 (KPI, 차트, 포지션, 매크로) |
| `dashboard/src/middleware.ts` | 인증 미들웨어 |
| `dashboard/src/lib/engine.ts` | 서버사이드 엔진 API 래퍼 |
| `docs/dashboard-storyboard-visual.html` | 대시보드 스토리보드 (5 screens) |
| `docs/api-guide.md` | API 사용 설명서 |
| `shared/protocols.py` | DataStore Protocol 정의 |

## Architecture Notes

- **기본 DB: SQLite** (`DB_TYPE=sqlite`), `/data/traderj.db` (Fly.io 볼륨)
- **API 인증**: `X-API-Key` 헤더, 환경변수 `TRADERJ_API_KEY`
- **대시보드 인증**: 비밀번호 + Passkey(Face ID), HttpOnly 세션 쿠키
- **API 프록시**: 브라우저 → Next.js `/api/engine/*` → Fly.io `/api/v1/*`
- **전략 프리셋**: 2026-03-08 튜닝 완료, 파라미터 안정성 7/7
- **position_manager**: strategy_id당 1포지션
- **매크로 수집**: 5분 주기, httpx로 4개 외부 API 호출
- **venv**: `.venv/bin/python` (Python 3.13)
- **Telegram MCP**: Claude Code에서 Telegram 채널 리슨 가능 (chat_id: 8704649186)
- **Claude Code 스킬**: `/traderj-api-call help` 로 API 호출 목록 확인
