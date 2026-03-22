Call the TraderJ API on Fly.io. Read docs/api-guide.md for full endpoint details.

Arguments: $ARGUMENTS

## Instructions

Parse `$ARGUMENTS` to determine what API call to make. The base URL is `https://traderj-engine.fly.dev`.
API key: read from `TRADERJ_API_KEY` env var (check `.env` file if env var not set — run `grep TRADERJ_API_KEY .env`).

### If argument is `help`

Print the following reference table and stop (do NOT make any API call):

```
/traderj-api-call <command> [params...]

── 조회 (GET) ──────────────────────────────────────
  health                     서비스 상태 (인증 불필요)
  balance [STRATEGY]         잔고/수익률 (기본: STR-001)
  positions [STRATEGY] [STATUS]  포지션 목록 (status: open|closed)
  orders [STRATEGY] [STATUS]     주문 이력 (status: filled|cancelled)
  signals [STRATEGY]         시그널 이력
  pnl-daily STRATEGY [DAYS]  일별 손익 (기본: 30일)
  pnl-summary [STRATEGY]     손익 요약
  risk STRATEGY              리스크 상태
  macro                      매크로 스냅샷
  candles SYMBOL TF [LIMIT]  캔들 (예: BTC-KRW 4h 100)
  analytics-pnl STRATEGY [DAYS]      누적 PnL 곡선
  analytics-compare IDS [DAYS]       전략 비교 (예: STR-001,STR-005)
  config                     현재 전략 설정
  regime                     레짐 상태
  version                    버전 정보
  engine-status              엔진 상태

── 제어 (POST) ─────────────────────────────────────
  engine-stop                엔진 정지
  engine-start               엔진 시작
  engine-restart             엔진 재시작
  position-close [STRATEGY]  포지션 청산 (기본: STR-001)
  sl STRATEGY PRICE          SL 변경 (예: STR-001 100000000)
  tp STRATEGY PRICE          TP 변경 (예: STR-001 115000000)
  strategy-switch PRESET     전략 변경 (예: STR-005)
```

### If argument is NOT `help`

1. Get the API key:
   - First try `echo $TRADERJ_API_KEY`
   - If empty, run `grep TRADERJ_API_KEY .env` and extract the value

2. Map the command to a curl call using the table below:

| Command | Method | URL Path | Query/Body |
|---------|--------|----------|------------|
| `health` | GET | `/health` | (no auth) |
| `balance [SID]` | GET | `/api/v1/balance` | `?strategy_id=SID` (default: STR-001) |
| `positions [SID] [STATUS]` | GET | `/api/v1/positions` | `?strategy_id=SID&status=STATUS` |
| `orders [SID] [STATUS]` | GET | `/api/v1/orders` | `?strategy_id=SID&status=STATUS` |
| `signals [SID]` | GET | `/api/v1/signals` | `?strategy_id=SID` |
| `pnl-daily SID [DAYS]` | GET | `/api/v1/pnl/daily` | `?strategy_id=SID&days=DAYS` |
| `pnl-summary [SID]` | GET | `/api/v1/pnl/summary` | `?strategy_id=SID` |
| `risk SID` | GET | `/api/v1/risk/SID` | - |
| `macro` | GET | `/api/v1/macro/latest` | - |
| `candles SYM TF [LIMIT]` | GET | `/api/v1/candles/SYM/TF` | `?limit=LIMIT` |
| `analytics-pnl SID [DAYS]` | GET | `/api/v1/analytics/pnl` | `?strategy_id=SID&days=DAYS` |
| `analytics-compare IDS [DAYS]` | GET | `/api/v1/analytics/compare` | `?strategy_ids=IDS&days=DAYS` |
| `config` | GET | `/api/v1/config` | - |
| `regime` | GET | `/api/v1/regime` | - |
| `version` | GET | `/api/v1/version` | - |
| `engine-status` | GET | `/api/v1/engine/status` | - |
| `engine-stop` | POST | `/api/v1/engine/stop` | - |
| `engine-start` | POST | `/api/v1/engine/start` | - |
| `engine-restart` | POST | `/api/v1/engine/restart` | - |
| `position-close [SID]` | POST | `/api/v1/position/close` | `{"strategy_id":"SID"}` |
| `sl SID PRICE` | POST | `/api/v1/position/sl` | `{"strategy_id":"SID","stop_loss":PRICE}` |
| `tp SID PRICE` | POST | `/api/v1/position/tp` | `{"strategy_id":"SID","take_profit":PRICE}` |
| `strategy-switch PRESET` | POST | `/api/v1/strategy/switch` | `{"strategy_id":"PRESET"}` |

3. Execute the curl command:
   - First try direct: `curl -s -H "X-API-Key: $API_KEY" "$BASE_URL$PATH?$QUERY"`
   - If DNS fails (exit code 6), retry with `--resolve traderj-engine.fly.dev:443:66.241.124.95`
   - If that also fails, fall back to Fly SSH: `fly ssh console -a traderj-engine -C "python3 -c \"import urllib.request,json; r=urllib.request.urlopen('http://localhost:8000$PATH'); print(r.read().decode())\""`
   - POST requests: `curl -s -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" -d '$BODY' "$BASE_URL$PATH"`
   - health endpoint: no X-API-Key header needed
   - Pipe through `python3 -m json.tool` for formatting

4. Show the formatted JSON result to the user with a brief Korean summary of the key values.

5. If the command is not recognized, show the help table.
