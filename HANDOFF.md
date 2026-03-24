# HANDOFF: traderj

## Goal

BTC/KRW 자동매매 봇 엔진(TraderJ). SQLite 기본 DB, 시그널 기반 전략 9종(default + STR-001~008), Paper/Backtest/Real 모드 운영. 레짐 감지(6-type) → 전략 자동 전환(Signal + DCA/Grid), Telegram 알림, 모니터링 대시보드 연동.

**현재 목표**: 핵심 기능 완성됨. 대시보드 UX 개선 + 운영 모니터링 단계.

---

## Current Progress

### COMPLETED — 대시보드 UX 개선 (2026-03-24)

**전략 설명 팝업 (커밋 완료, 배포 완료):**
- Control 탭 전략 버튼 클릭 시 확인 다이얼로그에 전략 이름, 설명, 매핑 레짐 표시
- `PRESET_INFO` 상수에 8개 전략 설명 + 레짐 매핑 정의
- `ConfirmDialog`에 `whitespace-pre-line` 추가로 줄바꿈 지원
- 커밋: `c811c2c` — feat(dashboard): show strategy description and regime on switch confirm

**캐시 방지 (배포 완료, 미커밋):**
- API 프록시 응답에 `Cache-Control: no-store, no-cache, must-revalidate` + `Pragma: no-cache` 헤더 추가
- `export const dynamic = "force-dynamic"` 설정
- `dashboard/vercel.json` 신규 생성 — Vercel 인프라 레벨 API 캐시 방지
- 수정 파일: `dashboard/src/app/api/engine/[...path]/route.ts`, `dashboard/vercel.json`

**차트 자동 스크롤 (배포 완료, 미커밋):**
- `CandlestickChart.tsx`에서 폴링 업데이트 시 `scrollToRealTime()` 호출 추가
- 문제: 기존에는 `fitContent()`가 최초 로드 시에만 호출되어, 이후 폴링으로 새 캔들 추가되어도 뷰포트가 과거에 고정
- 수정 파일: `dashboard/src/components/chart/CandlestickChart.tsx`

**⚠️ 미커밋 파일 (다음 세션에서 커밋 필요):**
- `dashboard/src/app/api/engine/[...path]/route.ts` — Cache-Control 헤더
- `dashboard/src/components/chart/CandlestickChart.tsx` — scrollToRealTime
- `dashboard/vercel.json` — Vercel 캐시 설정 (신규)

**차트 3/21 표시 문제 조사:**
- 엔진: 정상 실행 (Tick 1274, 60초 간격)
- DB 데이터: 3/23까지 정상 존재 (1d, 4h, 1h 모두)
- 원인 추정: Vercel CDN 캐시 + 차트 뷰포트 고정 → 위 수정으로 해결 시도
- **사용자 확인 대기**: 배포 후 브라우저 새로고침으로 최신 데이터 표시 여부 확인 필요

### COMPLETED — 레짐 6-type 확장 + Bear 프리셋 (2026-03-23)

RegimeType 4→6 확장 + Bear 프리셋(STR-007/008) 추가. 엔진 + 대시보드 배포 완료.

**레짐 6-type:**
- 기존 4종: `bull_trend_high_vol`, `bull_trend_low_vol`, `ranging_high_vol`, `ranging_low_vol`
- 신규 2종: `bear_trend_high_vol`, `bear_trend_low_vol`

**커밋:**
- `c191ade` — feat(strategy): expand regime detection to 6 types with bear market presets
- `2154ca4` — fix(strategy): tune STR-007 -- remove daily_gate that blocked all bear buys
- `229dad9` — feat(dashboard): add STR-007/008 presets and regime color coding

### COMPLETED — Phase 4: Next.js 모니터링 대시보드 (2026-03-22~23)

Vercel 배포 + 인증(비밀번호 + Passkey/Face ID) + 실시간 모니터링.

- 대시보드: `https://dashboard-six-mu-40.vercel.app`
- 엔진 API: `https://traderj-engine.fly.dev/api/v1/*`
- API 프록시 패턴: 브라우저 → Next.js `/api/engine/*` → Fly.io `/api/v1/*`

### COMPLETED — Earlier Phases

- Phase 2: FastAPI 임베디드 API (27개 엔드포인트)
- Phase 1: Fly.io 엔진 배포 (SQLite 볼륨 마운트)
- 180일 Robustness 검증, DCA/Grid 레짐 연동, Telegram 알림

---

## What Worked

- **Cache-Control 헤더**: API 프록시 응답 + vercel.json 양쪽에서 캐시 방지
- **scrollToRealTime()**: lightweight-charts 폴링 업데이트 시 최신 캔들로 자동 스크롤
- **fly ssh console + python3**: 운영 DB 직접 쿼리로 데이터 존재 확인
- **PRESET_INFO 상수**: 백엔드 수정 없이 프론트엔드에서 전략 설명 표시
- **기존 ConfirmDialog 재활용**: 별도 팝업 컴포넌트 없이 description에 전략 정보 포함
- **API 프록시 패턴**: Next.js API Routes → 엔진 API 프록시로 API 키 서버사이드 유지
- **WebAuthn Passkey**: `@simplewebauthn`으로 Face ID/Touch ID 인증 구현
- **StrEnum 자동 직렬화**: RegimeType 확장 시 API 엔드포인트 변경 불필요

## What Didn't Work

- **Vercel CLI 배포 경로 문제**: `dashboard/` 디렉토리에 `.vercel` 프로젝트 설정이 있고 Vercel 웹 설정의 Root Directory가 `dashboard`로 되어 있어, dashboard 내에서 `vercel --prod` 실행 시 `dashboard/dashboard` 경로를 찾으려 함. **해결**: 프로젝트 루트에서 `.vercel`을 dashboard 프로젝트로 임시 교체 후 배포 (`mv .vercel .vercel-root-bak && cp -r dashboard/.vercel . && npx vercel --prod && rm -rf .vercel && mv .vercel-root-bak .vercel`)
- **시간대(TZ) 변경**: 엔진 시간대를 KST로 바꾸는 것은 불필요 — 엔진은 UTC 표준, 대시보드는 `toLocaleString("ko-KR")`로 이미 한국 시간 표시, lightweight-charts도 브라우저 로컬 TZ 자동 적용
- **GitHub Actions Artifact 한도**: 계정 전체 500MB 초과 → `innodev-platform` 조직의 다른 레포에 4,400+ artifact가 원인. 삭제 시도했으나 사용자가 중단
- **router.push("/")**: Next.js App Router에서 쿠키 기반 인증 후 리다이렉트 실패 → `window.location.href` 사용
- **daily_gate=True in bear preset**: Bear 시장에서 EMA gate가 모든 매수 차단 → False로 변경

---

## Next Steps (순서대로)

### 1. 🔴 미커밋 변경사항 커밋 + 확인

```bash
git add dashboard/src/app/api/engine/[...path]/route.ts dashboard/src/components/chart/CandlestickChart.tsx dashboard/vercel.json
git commit -m "fix(dashboard): add cache-control headers and chart auto-scroll to latest"
```

사용자에게 **브라우저 새로고침 후 차트가 최신 날짜까지 표시되는지** 확인 요청.
만약 여전히 3/21까지만 보이면, 브라우저 개발자 도구 Network 탭에서 `/api/engine/candles/BTC-KRW/4h?limit=200` 응답 데이터를 확인해야 함.

### 2. 🟡 GitHub Actions Artifact 정리

계정 전체 저장소 한도 초과 상태. 주요 레포:
- `innodev-platform/CICD`: 605 artifacts
- `innodev-platform/hr-portal4Python`: 575 artifacts
- `innodev-platform/mi-advanced-manager`: 562 artifacts
```bash
# 레포별 artifact 일괄 삭제
gh api "repos/{owner}/{repo}/actions/artifacts" --paginate -q '.artifacts[].id' | while read id; do
  gh api -X DELETE "repos/{owner}/{repo}/actions/artifacts/$id"
done
```

### 3. 🟢 TP(Take Profit) 로직 보완

현재 합산 포지션에 TP 미설정. `load_open_positions()` 시 TP 없는 포지션에 자동 TP 설정 필요.

### 4. 🟢 운영 모니터링

- Fly.io 페이퍼 트레이딩에서 6-type 레짐 전환 동작 관찰
- Bear 프리셋(STR-007/008) 실전 전환 확인
- DCA/Grid 레짐별 동작 검증

### 5. 🟢 Vercel Git 자동 배포 연동

현재 Git push → Vercel 자동 배포가 연결되어 있지 않음. CLI로 수동 배포 중.
Vercel 웹 설정에서 GitHub 레포 연결 + Root Directory를 `dashboard`로 설정 필요.

---

## 현재 엔진 상태 (2026-03-24)

| 항목 | 값 |
|------|-----|
| 모드 | Paper Trading (Fly.io nrt) |
| 전략 | 9종 (default + STR-001~008, 레짐 자동전환) |
| 레짐 감지 | 6-type (bull/bear/ranging × high/low vol) |
| 포지션 | 없음 (BTC 0) |
| 잔고 | KRW ~10,091,401 |
| 엔진 API | https://traderj-engine.fly.dev |
| 대시보드 | https://dashboard-six-mu-40.vercel.app |
| 엔진 버전 | Fly.io v9 |
| 매크로 수집 | 5분 주기 (Fear & Greed, Funding Rate, BTC Dom, Kimchi Premium) |
| 테스트 | 507+ passed |
| Git | main, 최신 커밋 c811c2c (미푸시 변경사항 있음) |

---

## Key Files Reference

| File | Role |
|------|------|
| `engine/config/settings.py` | 모든 설정 (DB, Exchange, Trading, Telegram) |
| `engine/bootstrap.py` | 앱 부트스트랩 (컴포넌트 와이어링 + MacroCollector) |
| `engine/loop/trading_loop.py` | 트레이딩 루프 (tick cycle, 레짐 감지, OHLCV 수집) |
| `engine/data/macro.py` | MacroCollector (httpx 기반 4개 외부 API) |
| `engine/strategy/presets.py` | 전략 프리셋 9개 (STR-007/008 bear 포함) |
| `engine/strategy/regime.py` | 레짐 감지 + REGIME_PRESET_MAP |
| `engine/strategy/risk.py` | RiskConfig (SL/TP/Trailing Stop 설정) |
| `engine/data/ohlcv.py` | OHLCVCollector (캔들 수집 → DB 저장) |
| `api/routes/candles.py` | 캔들 API 엔드포인트 |
| `dashboard/src/app/page.tsx` | 메인 대시보드 |
| `dashboard/src/app/control/page.tsx` | Control (엔진/전략/포지션 제어) |
| `dashboard/src/components/chart/CandlestickChart.tsx` | 캔들스틱 차트 |
| `dashboard/src/app/api/engine/[...path]/route.ts` | 엔진 API 프록시 |
| `dashboard/src/lib/engine.ts` | 서버사이드 엔진 fetch (`cache: "no-store"`) |
| `dashboard/vercel.json` | Vercel 캐시 방지 헤더 설정 |
| `dashboard/src/middleware.ts` | 인증 미들웨어 |
| `docs/api-guide.md` | API 사용 설명서 |

## Architecture Notes

- **기본 DB: SQLite** (`DB_TYPE=sqlite`), `/data/traderj.db` (Fly.io 볼륨)
- **시간대: UTC** — 엔진 전체 UTC 표준, 대시보드에서 `toLocaleString("ko-KR")`로 한국 시간 표시
- **API 인증**: `X-API-Key` 헤더, 환경변수 `TRADERJ_API_KEY`
- **대시보드 인증**: 비밀번호 + Passkey(Face ID), HttpOnly 세션 쿠키 (7일 만료)
- **API 프록시**: 브라우저 → Next.js `/api/engine/*` → Fly.io `/api/v1/*`
- **Vercel 배포**: CLI 수동 (`npx vercel --prod`), Git 자동 배포 미연결
- **Vercel 배포 워크어라운드**: 루트 `.vercel`을 dashboard 프로젝트로 임시 교체 필요
- **전략 프리셋**: 9종, 레짐 자동 전환 (REGIME_PRESET_MAP)
- **venv**: `.venv/bin/python` (Python 3.13)
- **Telegram MCP**: Claude Code에서 Telegram 채널 리슨 가능 (chat_id: 8704649186)
- **Claude Code 스킬**: `/traderj-api-call help`로 API 호출 목록 확인
