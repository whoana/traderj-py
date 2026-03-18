# Design: TraderJ P0 Engine Safety Improvements
> Feature: `traderj-improvement` (P0 scope only)
> Created: 2026-03-17
> Phase: Design

---

## 1. 범위 (P0만)

| # | 항목 | 우선순위 |
|---|------|---------|
| P0-1 | Stop Loss / Take Profit DB 저장 누락 수정 | Critical |
| P0-2 | SL/TP 트리거 → 실제 청산 주문 실행 | Critical |
| P0-3 | Macro API placeholder → 실 데이터 연결 | High |

---

## 2. P0-1: Stop Loss / Take Profit DB 저장 누락

### 현재 버그

`position_manager.py`의 `set_stop_loss()`, `set_take_profit()`이 **sync 함수**로 인메모리만 업데이트하고 DB에 저장하지 않음.

```
BUY 체결 → _open_position() → DB save (stop_loss=NULL)
         → set_stop_loss()   → 인메모리만 업데이트 ← 버그!
엔진 재시작 → load_open_positions() → DB에서 읽으면 stop_loss=NULL 복원
```

### 수정: `engine/execution/position_manager.py`

**`set_stop_loss()` → async 전환 + DB 저장**
```python
# Before (sync, no DB)
def set_stop_loss(self, strategy_id: str, stop_loss: Decimal) -> bool:
    ...
    self._positions[strategy_id] = updated
    return True

# After (async, with DB save)
async def set_stop_loss(self, strategy_id: str, stop_loss: Decimal) -> bool:
    ...
    self._positions[strategy_id] = updated
    await self._store.save_position(updated)  # ← 추가
    return True
```

**`set_take_profit()` → async 전환 + DB 저장** (동일 패턴)

### 수정: `engine/loop/trading_loop.py`

`_execute_buy()` 내 호출부를 `await`으로 변경:
```python
# Before
self._position_mgr.set_stop_loss(...)
self._position_mgr.set_take_profit(...)

# After
await self._position_mgr.set_stop_loss(...)
await self._position_mgr.set_take_profit(...)
```

---

## 3. P0-2: SL/TP 트리거 → 실제 청산 주문 실행

### 현재 버그

`position_manager.on_market_tick()` → 가격이 SL 이하 → `_trigger_stop_loss()` → `StopLossTriggeredEvent` 발행만 함.
**아무도 이 이벤트를 처리하지 않아 실제 청산 주문이 발행되지 않음.**

```
MarketTickEvent → on_market_tick() → 가격 < stop_loss
                                   → _trigger_stop_loss()
                                   → StopLossTriggeredEvent 발행
                                   → ... (구독자 없음, 포지션 그대로 열려있음) ← 버그!
```

### 수정: `engine/loop/trading_loop.py`

이벤트 구독 핸들러 2개 추가:

```python
async def _on_stop_loss_triggered(self, event: StopLossTriggeredEvent) -> None:
    """Stop loss 트리거 시 즉시 시장가 청산."""
    if event.strategy_id != self._strategy_id:
        return
    pos = self._position_mgr.get_position(self._strategy_id)
    if pos is None:
        return
    request = OrderRequestEvent(
        strategy_id=self._strategy_id,
        symbol=self._symbol,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        amount=pos.amount,
        idempotency_key=f"{self._strategy_id}-sl-{uuid.uuid4().hex[:8]}",
    )
    result = await self._order_mgr.handle_order_request(request)
    if result.success:
        logger.warning("Stop loss executed: %s BTC @ market", pos.amount)
    else:
        logger.error("Stop loss sell FAILED: %s", result.reason)

async def _on_take_profit_triggered(self, event: TakeProfitTriggeredEvent) -> None:
    """Take profit 트리거 시 즉시 시장가 청산."""
    if event.strategy_id != self._strategy_id:
        return
    pos = self._position_mgr.get_position(self._strategy_id)
    if pos is None:
        return
    request = OrderRequestEvent(
        strategy_id=self._strategy_id,
        symbol=self._symbol,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        amount=pos.amount,
        idempotency_key=f"{self._strategy_id}-tp-{uuid.uuid4().hex[:8]}",
    )
    result = await self._order_mgr.handle_order_request(request)
    if result.success:
        logger.info("Take profit executed: %s BTC @ market", pos.amount)
    else:
        logger.error("Take profit sell FAILED: %s", result.reason)
```

### 수정: `engine/bootstrap.py`

`_wire_event_subscriptions()` 에 trading_loop 파라미터 추가 + SL/TP 구독:

```python
def _wire_event_subscriptions(event_bus, pos_mgr, risk_mgr, trading_loop) -> None:
    # 기존 구독
    event_bus.subscribe(OrderFilledEvent, pos_mgr.on_order_filled)
    event_bus.subscribe(MarketTickEvent, pos_mgr.on_market_tick)
    event_bus.subscribe(OrderFilledEvent, risk_mgr.on_order_filled)
    event_bus.subscribe(PositionClosedEvent, risk_mgr.on_position_closed)
    # 신규: SL/TP 청산 핸들러
    event_bus.subscribe(StopLossTriggeredEvent, trading_loop._on_stop_loss_triggered)
    event_bus.subscribe(TakeProfitTriggeredEvent, trading_loop._on_take_profit_triggered)
```

호출부 업데이트:
```python
_wire_event_subscriptions(
    app.event_bus,
    components["position_manager"],
    components["risk_manager"],
    components["trading_loop"],   # ← 추가
)
```

---

## 4. P0-3: Macro API 실 데이터 연결

### 현재 버그

```python
async def _fetch_funding_rate(self) -> float:
    return 0.01   # TODO: hardcoded

async def _fetch_btc_dominance(self) -> float:
    return 50.0   # TODO: hardcoded

async def _fetch_dxy(self) -> float:
    return 104.0  # TODO: hardcoded (DXY는 market_score에 미사용 → 그대로 유지)
```

### 수정: `engine/data/macro.py`

**BTC Dominance → CoinGecko 무료 API**
```python
async def _fetch_btc_dominance(self) -> float:
    if self._http is None:
        return 50.0
    try:
        resp = await self._http.get("https://api.coingecko.com/api/v3/global")
        pct = resp.get("data", {}).get("market_cap_percentage", {})
        return float(pct.get("btc", 50.0))
    except Exception:
        logger.warning("BTC dominance fetch failed, using default")
        return 50.0
```

**Funding Rate → Binance Futures 무료 API**
```python
async def _fetch_funding_rate(self) -> float:
    if self._http is None:
        return 0.01
    try:
        resp = await self._http.get(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            params={"symbol": "BTCUSDT", "limit": 1},
        )
        if resp and isinstance(resp, list) and len(resp) > 0:
            return float(resp[0].get("fundingRate", 0.01))
    except Exception:
        logger.warning("Funding rate fetch failed, using default")
    return 0.01
```

**DXY → 변경 없음** (market_score 계산에 사용 안 됨, 리스크 낮음)

### HTTP 클라이언트 연결 확인

`MacroCollector`가 `http_client=None`으로 생성되면 실 API 호출 안 됨.
`bootstrap.py`에서 MacroCollector 인스턴스 생성 시 HTTP 클라이언트 주입 필요.

현재 bootstrap에 MacroCollector 없음 → 스케줄러 잡으로 주기적 호출 필요.
**구현 범위**: macro.py의 메서드만 수정 (HTTP 클라이언트 주입은 현행 유지).

---

## 5. 영향 범위 (변경 파일)

| 파일 | 변경 내용 |
|------|---------|
| `engine/execution/position_manager.py` | `set_stop_loss()`, `set_take_profit()` → async + DB 저장 |
| `engine/loop/trading_loop.py` | `_on_stop_loss_triggered()`, `_on_take_profit_triggered()` 추가; `await` 추가 |
| `engine/bootstrap.py` | `_wire_event_subscriptions()` 파라미터 + SL/TP 구독 추가 |
| `engine/data/macro.py` | `_fetch_btc_dominance()`, `_fetch_funding_rate()` 실 API 연결 |

---

## 6. 테스트 전략

| 케이스 | 방법 |
|--------|------|
| SL 설정 후 DB 확인 | `test_position_manager.py` — set_stop_loss() 후 store.positions 검증 |
| SL 트리거 → 주문 실행 | `test_position_manager.py` + `test_trading_loop.py` 통합 |
| TP 설정 + 트리거 | 동일 패턴 |
| Macro API graceful 실패 | `test_macro_collector.py` — http_client=None 기본값 검증 |
| 기존 테스트 통과 | 467개 기존 테스트 전부 통과 유지 |

---

*Design Version: 1.0 | Date: 2026-03-17*
