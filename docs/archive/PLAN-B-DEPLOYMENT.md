# TraderJ 배포 계획 B: Fly.io + Vercel

**확정일:** 2026-03-21
**배경:** Oracle Cloud Free Tier 가입 내부 오류로 불가 → Fly.io + Vercel로 전환

---

## 아키텍처

```
[Fly.io nrt(도쿄)]           [Vercel]
  TraderJ Engine               Next.js 모니터링 (신규 개발)
  Python 3.13 + SQLite         대시보드 SSR
  Telegram 알림                API Routes → 엔진 프록시
  경량 API (8000)
```

---

## Phase 1: Fly.io 앱 생성 + 배포

**작업 내용:**

1. **fly.toml 생성** (프로젝트 루트)
   - app = `traderj-engine`
   - region = `nrt` (도쿄, ~30ms)
   - VM: shared-cpu-1x, 512MB RAM
   - mount: `traderj_data` → `/data` (SQLite 영속)
   - process: `python -u -m scripts.run_paper`

2. **Dockerfile 수정** (`engine/Dockerfile`)
   - CMD를 `run_paper`로 변경
   - `/data` 디렉토리 생성
   - DB_SQLITE_PATH → `/data/traderj.db`

3. **시크릿 등록**
   ```bash
   fly secrets set TELEGRAM_BOT_TOKEN=<token> TELEGRAM_CHAT_ID=<id> API_KEY=<key>
   ```

4. **볼륨 생성 + 배포**
   ```bash
   fly volumes create traderj_data --region nrt --size 1
   fly deploy
   ```

---

## Phase 2: 엔진 경량 API 추가

**엔드포인트:**
| Method | Path | 설명 |
|--------|------|------|
| GET | `/health` | 헬스체크 |
| GET | `/api/positions` | 현재 포지션 |
| GET | `/api/orders` | 주문 내역 |
| GET | `/api/pnl` | 손익 현황 |
| GET | `/api/signals` | 시그널 내역 |
| GET | `/api/balance` | 잔고 |

**인증:** `X-API-Key` 헤더
**접근:** `https://traderj-engine.fly.dev`

**구현:**
- FastAPI 경량 서버 (trading loop과 병행 실행)
- SQLite 읽기 전용 연결
- 포트 8000

---

## Phase 3: DB 이전 + 배포 워크플로우

1. **기존 DB 업로드**
   ```bash
   fly ssh sftp shell
   put traderj.db /data/traderj.db
   ```

2. **원클릭 배포**
   ```bash
   fly deploy
   ```

3. **DB 백업**
   ```bash
   fly ssh sftp get /data/traderj.db ./backup_traderj.db
   ```

---

## Phase 4: Next.js 모니터링 대시보드 (별도 프로젝트)

- 프로젝트: `traderj-monitor/` (Vercel 배포)
- 환경변수: `ENGINE_URL=https://traderj-engine.fly.dev`
- SSR 대시보드 + API 프록시
- 기존 `dashboard/` 디렉토리는 제거 예정 (Next.js로 재개발)

---

## 비용 예상

| 서비스 | 플랜 | 월 비용 |
|--------|------|---------|
| Fly.io | Hobby (shared-cpu-1x, 512MB, 1GB Volume) | $3~5 |
| Vercel | Hobby (무료) | $0 |
| **합계** | | **$3~5/월** |

---

## 사전 확인 사항

- [x] flyctl 설치됨 (`/opt/homebrew/bin/flyctl`)
- [x] Fly.io 로그인 완료 (`whoana@gmail.com`)
- [x] Docker 설치됨 (v29.2.1)
- [x] Dockerfile 존재 (`engine/Dockerfile`, production target)
- [x] 가용 리전 확인 (`nrt` 도쿄)
- [x] 신용카드 등록 완료

---

## 현재 상태

- Phase 1~4 계획 수립 완료
- 실행 대기 중
