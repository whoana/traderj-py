# Round 1: UX 감사 보고서 - Bit Trader 대시보드

**작성일**: 2026-03-02
**감사 대상**: `dashboard/streamlit_app.py` (Streamlit 기반 모니터링 대시보드)
**감사자**: Dashboard Designer (Senior Trading Dashboard Specialist)

---

## 1. Executive Summary

현재 bit-trader 대시보드는 Streamlit 기반의 **읽기 전용 모니터링 도구**로, 봇 상태/잔고/시그널/주문/차트를 한 페이지에 표시한다. 프로토타이핑 단계에서는 빠르게 구축할 수 있는 합리적 선택이었으나, **트레이딩 대시보드로서의 핵심 요구사항** 대부분을 충족하지 못하고 있다.

### 핵심 문제 요약

| 영역 | 심각도 | 현재 상태 |
|------|--------|-----------|
| 실시간성 | **Critical** | 30초 auto-refresh 주석 처리됨, 실제로는 수동 새로고침 |
| 봇 관리 | **Critical** | 시작/중지/설정 UI 전무 - CLI/터미널에서만 가능 |
| 차트 품질 | **High** | 종가 line chart만 표시, 캔들스틱/지표 오버레이 없음 |
| 반응형 디자인 | **High** | 모바일/태블릿 미지원 |
| 전략 비교 | **High** | 단일 전략만 조회 가능, 멀티봇 비교 뷰 없음 |
| 알림 설정 | **Medium** | 텔레그램 알림만 존재, 대시보드 내 알림/설정 UI 없음 |
| 접근성 | **Medium** | Streamlit 기본 테마 의존, 커스텀 접근성 미적용 |

**종합 UX 성숙도**: 2/10 (프로토타입 수준)

---

## 2. 현재 대시보드 구조 분석

### 2.1 페이지 레이아웃

현재 대시보드는 **단일 페이지, 수직 스크롤** 구조로 다음 섹션이 순서대로 배치된다:

```
┌──────────────────────────────────────────────┐
│  Sidebar: Strategy 선택 (selectbox)          │
├──────────────────────────────────────────────┤
│  Header: Bit Trader Dashboard                │
├──────────────────────────────────────────────┤
│  Paper Balance (KRW | BTC | Total | PnL)     │  ← 4-column metrics
├──────────────────────────────────────────────┤
│  Bot Status | Open Position | Macro Score    │  ← 3-column metrics
├──────────────────────────────────────────────┤
│  Daily PnL (line chart + 3 metrics)          │  ← st.line_chart
├──────────────────────────────────────────────┤
│  Recent Signals (dataframe, 20 rows)         │  ← st.dataframe
├──────────────────────────────────────────────┤
│  Recent Orders (dataframe, 20 rows)          │  ← st.dataframe
├──────────────────────────────────────────────┤
│  Price Chart 1H (line chart + 2 metrics)     │  ← st.line_chart (close only)
├──────────────────────────────────────────────┤
│  Position History (dataframe, 20 rows)       │  ← st.dataframe
└──────────────────────────────────────────────┘
```

### 2.2 사용된 Streamlit 컴포넌트

| 컴포넌트 | 용도 | 한계 |
|----------|------|------|
| `st.metric()` | KPI 표시 | delta 표시 미활용, 실시간 업데이트 불가 |
| `st.line_chart()` | PnL/가격 차트 | 캔들스틱 미지원, 인터랙션 제한적 |
| `st.dataframe()` | 테이블 데이터 | 정렬/필터링 제한적, 행 클릭 이벤트 없음 |
| `st.sidebar.selectbox()` | 전략 필터 | 멀티셀렉트/비교 뷰 미지원 |
| `st.columns()` | 레이아웃 | 고정 비율, 반응형 breakpoint 없음 |

### 2.3 데이터 접근 방식

- **직접 SQLite 연결** (`sqlite3.connect`, `PRAGMA query_only=ON`)
- pandas `read_sql()`로 각 섹션마다 개별 쿼리 실행
- **캐싱 없음**: 페이지 로드마다 모든 쿼리 재실행
- **에러 핸들링**: 모든 섹션이 try/except로 감싸져 실패 시 "N/A" 표시 (사일런트 실패)

---

## 3. 상세 감사 항목

### 3.1 실시간성 (Severity: Critical)

**현재 상태**:
- `st.caption("Auto-refreshes every 30 seconds")` 라벨만 존재
- 실제 auto-refresh 로직은 구현되어 있지 않음 (`time.sleep(0)` 후 아무 동작 없음)
- 사용자가 **수동으로 브라우저 새로고침**해야 최신 데이터 확인 가능
- `streamlit-autorefresh` 패키지 미사용

**영향 분석**:
- 봇이 EXECUTING 상태에서 주문 실행 중이더라도 사용자는 인지 불가
- 가격 급변 시 현재 포지션의 unrealized PnL이 실시간 반영되지 않음
- Stop Loss 트리거 시 대시보드에서 즉시 확인 불가 (텔레그램에서만 알림)
- 3개 봇 동시 운영 시 각 봇의 상태 변화를 놓칠 가능성 높음

**경쟁 플랫폼 기준**:
- TradingView: WebSocket 기반 실시간 틱 업데이트 (~1ms 지연)
- Binance: WebSocket 기반 실시간 오더북/체결 스트림
- 현재 bit-trader: UpbitWebSocket 클래스가 이미 존재하지만 대시보드에서 미활용

**개선 기회**:
- WebSocket 기반 실시간 데이터 스트림 (UpbitWebSocket 활용)
- Server-Sent Events 또는 WebSocket을 통한 푸시 업데이트
- 최소 5초 이내의 데이터 지연 목표

---

### 3.2 봇 관리 기능 (Severity: Critical)

**현재 상태**:
- 대시보드는 **순수 읽기 전용** - 봇 제어 기능 전무
- 봇 시작/중지: CLI 명령 또는 PID 파일 기반 프로세스 관리
- 전략 파라미터 변경: `params.py` 직접 수정 후 재시작 필요
- 상태 확인: bot_state 테이블 조회만 가능 (IDLE/SCANNING/EXECUTING 등)

**트레이더 워크플로우 갭**:

| 작업 | 현재 방법 | 이상적 방법 |
|------|-----------|-------------|
| 봇 시작 | 터미널 CLI 명령 | 대시보드 Start 버튼 |
| 봇 중지 | PID kill / CLI | 대시보드 Stop 버튼 + 확인 다이얼로그 |
| 봇 일시정지 | 미구현 | Pause/Resume 토글 |
| 전략 변경 | params.py 수정 → 재시작 | 드롭다운 + 파라미터 슬라이더 |
| 임계값 조정 | 코드 수정 → 재시작 | 실시간 파라미터 튜닝 UI |
| 긴급 청산 | 미구현 | Emergency Exit 버튼 |
| 로그 확인 | 터미널 tail -f | 대시보드 내 로그 뷰어 |

**누락된 핵심 기능**:
1. **Bot Control Panel**: Start/Stop/Pause per strategy
2. **Parameter Tuning UI**: 임계값, 포지션 크기, 손절 비율 조정
3. **Emergency Actions**: 즉시 전체 포지션 청산, 봇 긴급 중지
4. **Multi-bot Overview**: 3개 봇의 상태를 한 눈에 비교

---

### 3.3 정보 아키텍처 (Severity: High)

**표시되는 데이터 vs 누락된 데이터**:

| 데이터 | 표시 여부 | 표시 품질 | 비고 |
|--------|-----------|-----------|------|
| Paper Balance (KRW/BTC) | O | Good | 4-column metric 적절 |
| Bot State | O | Fair | 이모지 색상 코드, 상태 변화 이력 없음 |
| Open Position | O | Fair | 단일 포지션만 표시, 진입가 대비 현재가 시각화 없음 |
| Macro Score | O | Fair | 숫자만 표시, 트렌드/변화 방향 없음 |
| Daily PnL | O | Poor | 기본 line chart, 누적 수익 곡선 없음 |
| Recent Signals | O | Poor | 원시 데이터 테이블, score 시각화 없음 |
| Recent Orders | O | Poor | 원시 데이터 테이블, 체결 상태 시각화 없음 |
| Price Chart | O | **Very Poor** | close 값만 line chart, OHLCV 캔들스틱 아님 |
| Position History | O | Poor | 원시 데이터 테이블, PnL 색상 코딩 없음 |
| **Drawdown Chart** | **X** | - | MDD 시각화 전무 |
| **Equity Curve** | **X** | - | 누적 자산 추이 없음 |
| **Risk Metrics** | **X** | - | Sharpe, MDD, 일일 한도 잔여량 |
| **Order Book** | **X** | - | WebSocket에 orderbook 콜백 있으나 미활용 |
| **Trade Volume Profile** | **X** | - | 거래량 프로파일 없음 |
| **Strategy Comparison** | **X** | - | 멀티 전략 성과 비교 뷰 없음 |
| **Alert History** | **X** | - | 텔레그램 발송 내역 대시보드 미표시 |
| **Technical Indicators** | **X** | - | EMA/RSI/MACD 등 차트 오버레이 없음 |
| **Signal Score Heatmap** | **X** | - | 시간대별 시그널 강도 시각화 없음 |
| **Backtest Results** | **X** | - | 백테스트 성과 대시보드 통합 없음 |

**정보 우선순위 문제**:
- 가장 중요한 정보(현재 포지션 상태, unrealized PnL)가 페이지 중간에 매몰
- 스크롤 없이 볼 수 있는 Above-the-fold 영역에 핵심 KPI가 분산됨
- Signals/Orders 테이블이 원시 데이터 형태로 과도한 화면 공간 점유

---

### 3.4 차트 및 시각화 품질 (Severity: High)

**가격 차트 분석**:

| 항목 | 현재 | 기대치 (트레이딩 대시보드) |
|------|------|---------------------------|
| 차트 타입 | `st.line_chart(close)` | 캔들스틱 (OHLCV) + 볼린저 밴드 |
| 기술 지표 | 없음 | EMA, RSI, MACD, 볼린저밴드 오버레이 |
| 타임프레임 | 1H 고정 | 15m/1H/4H/1D 전환 가능 |
| 인터랙션 | 없음 | 줌, 패닝, 크로스헤어, 가격 알림 |
| 거래 마커 | 없음 | 매수/매도 포인트 차트 위에 표시 |
| 데이터 범위 | 168시간 (7일) | 사용자 선택 가능 (1D~1Y) |

**PnL 차트 분석**:
- realized/unrealized만 line chart로 표시
- 누적 수익 곡선(Equity Curve) 없음
- Drawdown 시각화 없음 (리스크 관리에 필수)
- 일별 PnL 막대 차트 (양수=녹색, 음수=적색) 없음
- Win/Loss 분포 히스토그램 없음

**시그널 시각화**:
- 원시 숫자 테이블만 제공
- score 값을 색상 그라데이션으로 표현하지 않음
- 시간대별 시그널 히트맵 없음
- 각 서브스코어(trend/momentum/volume/macro) 레이더 차트 없음

---

### 3.5 반응형 디자인 (Severity: High)

**현재 상태**:
- `layout="wide"` 설정으로 데스크톱 와이드 모드 사용
- Streamlit의 기본 반응형은 컬럼 스태킹만 제공
- `st.columns(4)`, `st.columns(3)` 등 고정 그리드 사용
- 모바일에서 4-column metric이 수직으로 풀리면 과도한 스크롤 발생

**디바이스별 문제점**:

| 디바이스 | 문제 |
|----------|------|
| **데스크톱 (1920px+)** | 와이드 모드에서 테이블이 과도하게 넓어짐 |
| **노트북 (1366px)** | 차트가 너무 작아 가독성 저하 |
| **태블릿 (768px)** | 4-column metric이 2+2로 분할되어 어색한 레이아웃 |
| **모바일 (375px)** | 모든 컬럼이 수직 스태킹, 핵심 정보까지 5-6스크롤 필요 |

**트레이더 사용 시나리오**:
- 외출 중 모바일로 봇 상태 확인 -> 현재 불가능 (UX 매우 열악)
- 태블릿으로 차트 분석 -> 차트 인터랙션 제한
- 멀티 모니터 대시보드 -> 여러 전략을 동시 모니터링하는 레이아웃 미지원

---

### 3.6 접근성 (Severity: Medium)

**색상 대비**:
- Streamlit 기본 다크/라이트 테마 의존
- 봇 상태 이모지(원형 색상)가 유일한 시각적 구분 -> 색각 이상자 배려 없음
- PnL 양수/음수 색상 구분 미적용 (숫자에 +/- 부호만)
- 데이터 테이블에 조건부 서식(Conditional Formatting) 없음

**키보드 네비게이션**:
- Streamlit 기본 Tab 네비게이션 의존
- 차트 키보드 인터랙션 없음
- 전략 선택기 외에 키보드 단축키 없음

**스크린 리더 지원**:
- Streamlit이 생성하는 HTML에 의존 (ARIA 라벨 커스텀 불가)
- metric 위젯의 숫자 값에 대한 맥락 정보 부족
- 차트의 대체 텍스트 없음

---

### 3.7 사용자 워크플로우 분석 (Severity: High)

**트레이더의 일상적 대시보드 사용 시나리오**:

#### 시나리오 1: 아침 점검 (Morning Check)
```
이상적 워크플로우:
1. 대시보드 접속 → 전체 봇 상태 한눈에 확인 (5초)
2. 야간 거래 내역 확인 (10초)
3. 각 전략별 PnL 비교 (10초)
4. 오늘 시장 상황(매크로 스코어) 확인 (5초)
Total: ~30초

현재 워크플로우:
1. 대시보드 접속 → 새로고침 (수동) (10초)
2. 사이드바에서 전략 선택 → 새로고침 대기 (5초)
3. 스크롤하며 각 섹션 확인 (30초)
4. 다른 전략 선택 → 같은 과정 반복 × 3 (45초)
5. 터미널에서 봇 프로세스 확인 (15초)
Total: ~105초 (3.5배 비효율)
```

#### 시나리오 2: 긴급 상황 대응 (Emergency Response)
```
이상적 워크플로우:
1. 알림 수신 → 대시보드에서 상황 파악 (5초)
2. 긴급 청산 버튼 클릭 (3초)
3. 봇 일시 정지 (2초)
Total: ~10초

현재 워크플로우:
1. 텔레그램 알림 수신 (즉시)
2. 대시보드 접속 → 새로고침 (10초)
3. 터미널 접근 → PID 확인 → kill 명령 (30초+)
4. 수동 청산 명령 실행 (미구현 - 불가능)
Total: 40초+ (치명적 지연, 긴급 시 손실 확대 가능)
```

#### 시나리오 3: 전략 성과 분석 (Performance Review)
```
이상적 워크플로우:
1. 전략 비교 뷰에서 3개 봇 성과 병렬 확인 (10초)
2. 기간별 PnL/MDD/Sharpe 확인 (10초)
3. 특정 거래 클릭 → 상세 분석 (10초)
Total: ~30초

현재 워크플로우:
1. 전략 A 선택 → 데이터 확인 → 메모 (60초)
2. 전략 B 선택 → 반복 (60초)
3. 전략 C 선택 → 반복 (60초)
4. 수동으로 비교 (MDD/Sharpe 데이터 없음)
Total: 180초+ (비교 불가, 의사결정 지연)
```

---

### 3.8 데이터 모델 활용도 분석

현재 백엔드에서 사용 가능하지만 **대시보드에서 미활용되는 데이터**:

| 데이터 소스 | Store 메서드 | 대시보드 활용 | 비고 |
|------------|-------------|-------------|------|
| `candles.open/high/low` | `get_candles()` | **미사용** | close만 차트에 표시 |
| `signals.details` (JSON) | `insert_signal()` | **미사용** | 서브스코어 상세 분석 가능 |
| `positions.current_price` | `get_open_position()` | **미사용** | 실시간 포지션 가치 계산 가능 |
| `positions.unrealized_pnl` | `get_open_position()` | **미사용** | 미실현 손익 추적 가능 |
| `bot_state.metadata` (JSON) | `set_bot_state()` | **미사용** | 상태 상세 정보 표시 가능 |
| WebSocket ticker | `on_ticker()` | **미사용** | 실시간 가격 업데이트 가능 |
| WebSocket orderbook | `on_orderbook()` | **미사용** | 오더북 depth 시각화 가능 |
| WebSocket trade | `on_trade()` | **미사용** | 실시간 체결 스트림 가능 |
| `daily_pnl.loss_count` | `upsert_daily_pnl()` | **미사용** | 승/패 분석 가능 |
| Macro 상세 (dxy, nasdaq, btc_dom) | `get_latest_macro()` | **부분** | market_score만 표시 |

---

### 3.9 경쟁 플랫폼 대비 갭 분석

#### TradingView 대비

| 기능 | TradingView | Bit Trader | Gap |
|------|------------|------------|-----|
| 캔들스틱 차트 | 50+ 차트 타입 | line chart만 | Critical |
| 기술 지표 오버레이 | 100+ 인디케이터 | 없음 | Critical |
| 실시간 데이터 | ~1ms WebSocket | 수동 새로고침 | Critical |
| 드로잉 도구 | 트렌드라인, 피보나치 등 | 없음 | High |
| 멀티 타임프레임 | 자유 전환 | 1H 고정 | High |
| 알림 시스템 | 가격/지표 기반 알림 | 대시보드 내 없음 | High |
| 반응형 디자인 | 모바일 앱 + 웹 | 미지원 | High |
| 비교 차트 | 다중 자산/전략 비교 | 없음 | Medium |

#### Binance Dashboard 대비

| 기능 | Binance | Bit Trader | Gap |
|------|---------|------------|-----|
| 포지션 관리 UI | 실시간 포지션 + 원클릭 청산 | 읽기 전용 | Critical |
| 오더북 시각화 | 실시간 depth chart | 없음 | High |
| PnL 분석 | 일별/주별/월별 + 자산 곡선 | 기본 line chart | High |
| 봇 제어 | API 기반 전략 관리 | CLI에서만 가능 | Critical |
| 모바일 대응 | 네이티브 앱 | 미지원 | High |
| 거래 내역 상세 | 필터/검색/내보내기 | 최근 20건 테이블 | Medium |

---

## 4. 기술적 제약 분석

### 4.1 Streamlit 프레임워크의 구조적 한계

| 한계 | 영향 | 대안 |
|------|------|------|
| **Re-run 모델**: 모든 인터랙션이 전체 스크립트 재실행 | 느린 응답, 상태 손실 | React/Next.js SPA |
| **서버 사이드 렌더링**: 클라이언트 사이드 인터랙션 제한 | 차트 줌/패닝 불가 | 클라이언트 사이드 렌더링 |
| **WebSocket 미지원**: 네이티브 WebSocket 클라이언트 불가 | 실시간 업데이트 불가 | WebSocket API + SSE |
| **컴포넌트 레이아웃**: CSS 커스텀 제한적 | 정교한 대시보드 레이아웃 불가 | TailwindCSS + Grid |
| **차트 라이브러리**: Altair/Plotly 기반 (금융 특화 아님) | 캔들스틱/depth chart 한계 | Lightweight Charts / D3.js |
| **상태 관리**: session_state 기본, 복잡한 상태 처리 어려움 | 멀티 뷰/필터 상태 관리 곤란 | React 상태 관리 (Zustand 등) |

### 4.2 데이터 접근 계층 문제

현재 대시보드는 SQLite에 직접 연결하여 동기식 쿼리를 실행한다:

```python
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("PRAGMA query_only=ON")
```

**문제점**:
- 봇의 async aiosqlite와 대시보드의 sync sqlite3가 동시 접근 시 잠재적 잠금 이슈
- `PRAGMA query_only=ON`으로 안전성 확보했으나, WAL 모드에서도 장시간 읽기 시 write 차단 가능
- 쿼리 캐싱 없음 - 매 렌더링마다 8+ 쿼리 실행
- 커넥션 관리: `conn.close()`가 스크립트 끝에서 호출되나, Streamlit 재실행 시 매번 새 연결

---

## 5. UX 갭 우선순위 매트릭스

### Impact vs Effort 매트릭스

```
        Impact (High)
            │
     ┌──────┼───────────────────┐
     │ [A1] │ [A2]              │
     │실시간 │ 봇 관리 UI        │
     │업데이트│ 캔들스틱 차트      │
     │      │ 긴급 청산 기능     │
     ├──────┼───────────────────┤
     │ [B1] │ [B2]              │
     │PnL   │ 멀티 전략 비교     │
     │색상   │ 반응형 디자인      │
     │코딩  │ 오더북 시각화      │
     │      │ 백테스트 통합      │
     └──────┼───────────────────┘
            │
        Impact (Low)
   Effort(Low)        Effort(High)
```

### 개선 로드맵 권장

**Phase 1 (Quick Wins - 1~2주)**:
1. auto-refresh 구현 (streamlit-autorefresh)
2. PnL/포지션 조건부 색상 코딩
3. 가격 차트 Plotly 캔들스틱으로 교체
4. Macro 스코어 상세 표시 (FnG, DXY, Kimchi Premium 모두)

**Phase 2 (Core Features - 새 프레임워크 전환)**:
1. Next.js/SvelteKit 기반 대시보드 재구축
2. WebSocket 실시간 데이터 스트림 연동
3. 봇 Control Panel (Start/Stop/Pause)
4. 멀티 전략 비교 뷰

**Phase 3 (Advanced Features)**:
1. Lightweight Charts 기반 고성능 차트 (지표 오버레이)
2. 오더북 depth 시각화
3. Equity Curve + Drawdown 차트
4. 모바일 반응형 디자인
5. 알림 설정 UI

---

## 6. 핵심 권장사항

### 6.1 프레임워크 전환 필요성

Streamlit은 데이터 과학/분석 대시보드에 최적화되어 있으나, **트레이딩 대시보드의 핵심 요구사항**(실시간성, 인터랙티브 차트, 봇 제어, 반응형)을 충족하기 위해서는 **프론트엔드 프레임워크 전환이 불가피**하다.

**권장 기술 스택**:
- **프레임워크**: Next.js (App Router) 또는 SvelteKit
- **차트**: Lightweight Charts (TradingView 오픈소스) + D3.js
- **스타일링**: TailwindCSS
- **실시간**: WebSocket 클라이언트 (UpbitWebSocket과 직접 연동 또는 중간 API 서버)
- **상태 관리**: Zustand (React) 또는 SvelteKit stores

### 6.2 API 계층 필요성

현재 대시보드가 SQLite에 직접 연결하는 구조는 새 프레임워크에서 그대로 사용할 수 없다. 다음이 필요하다:

1. **REST API 서버**: 봇 상태 조회, 주문 내역, PnL 데이터 제공
2. **WebSocket 엔드포인트**: 실시간 가격, 봇 상태 변화 푸시
3. **봇 제어 API**: Start/Stop/Pause/Config 엔드포인트
4. 기존 Store 클래스의 메서드를 API로 노출

### 6.3 디자인 시스템 필요성

트레이딩 대시보드 특화 디자인 시스템 구축:
- 다크 테마 기본 (트레이더 선호)
- 양수(녹색)/음수(적색) 일관된 컬러 코드
- 숫자 포맷팅 (KRW 천단위 콤마, BTC 8자리 소수점)
- 금융 데이터 전용 타이포그래피 (모노스페이스 숫자)

---

## 7. 결론

현재 Streamlit 대시보드는 개발 초기 **프로토타이핑 목적으로는 충분**했으나, 3개 봇 동시 운영 + 실거래 전환을 앞둔 현재 시점에서는 **트레이더의 핵심 워크플로우를 지원하지 못하는 심각한 UX 갭**이 존재한다.

가장 시급한 문제는:
1. **실시간 데이터 부재** - 이미 WebSocket 인프라가 있으나 대시보드에서 미활용
2. **봇 제어 불가** - 긴급 상황 대응 시 치명적 지연 발생
3. **시각화 품질** - 트레이딩 의사결정을 지원할 수 없는 수준의 차트

프레임워크 전환과 함께 REST API + WebSocket 기반의 새로운 대시보드를 설계하는 것이 최적의 방향이다. 기존 bit-trader의 데이터 모델과 WebSocket 인프라를 최대한 활용하면서, 트레이더 중심의 UX를 구현해야 한다.
