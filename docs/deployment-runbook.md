# traderj Deployment Runbook

## Prerequisites

- Docker & Docker Compose v2+
- `.env` file (copy from `.env.example`)

## Quick Start (Development)

```bash
cp .env.example .env
# Edit .env — set DB_PASSWORD, TRADERJ_API_KEY

docker compose up -d
```

Services:
| Service | Port | URL |
|---------|------|-----|
| Dashboard | 3000 | http://localhost:3000 |
| API | 8000 | http://localhost:8000/api/v1/docs |
| Prometheus | 9090 | http://localhost:9090 |
| Grafana | 3001 | http://localhost:3001 |
| PostgreSQL | 5432 | — |
| Engine | 8001 | /metrics only |

## Production Deployment

### 1. Environment Variables

Required secrets (never commit to git):
```
DB_PASSWORD=<strong-password>
TRADERJ_API_KEY=<random-32-char-string>
UPBIT_ACCESS_KEY=<upbit-api-key>
UPBIT_SECRET_KEY=<upbit-secret-key>
GRAFANA_PASSWORD=<grafana-admin-password>
```

Trading config:
```
TRADING_MODE=live        # paper | live
TRADING_SYMBOL=BTC/KRW
CORS_ORIGINS=https://your-domain.com
TRADERJ_ENV=production   # disables Swagger docs
```

### 2. Build & Deploy

```bash
# Build production images
docker compose -f docker-compose.yml build

# Start with production target
docker compose up -d

# Verify health
curl -s http://localhost:8000/api/v1/health | jq
```

### 3. Database Migration

```bash
# Run Alembic migrations
docker compose exec engine alembic upgrade head
```

### 4. Monitoring Setup

Grafana setup:
1. Open http://localhost:3001 (admin / `GRAFANA_PASSWORD`)
2. Add Prometheus data source: http://prometheus:9090
3. Import dashboard JSON (if available)

Key alert rules (in `alert_rules.yml`):
- **EngineDown**: engine process unreachable for 1m
- **CircuitBreakerOpen**: trading halted (immediate)
- **HighOrderFailureRate**: >10% failure rate over 5m
- **DailyLossLimitApproaching**: daily PnL < -200K KRW
- **HighAPILatency**: p95 > 1s for 3m

### 5. Health Checks

```bash
# API health
curl http://localhost:8000/api/v1/health

# Engine metrics
curl http://localhost:8001/metrics

# Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].health'

# DB connectivity
docker compose exec postgres pg_isready -U traderj
```

## Operations

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f engine
docker compose logs -f api

# Last 100 lines
docker compose logs --tail=100 engine
```

### Restart Services

```bash
# Restart single service
docker compose restart engine

# Full restart
docker compose down && docker compose up -d
```

### Emergency Stop

```bash
# Stop trading immediately via API
curl -X POST http://localhost:8000/api/v1/bots/emergency-stop-all \
  -H "X-API-Key: $TRADERJ_API_KEY"

# Or stop engine container
docker compose stop engine
```

### Database Backup

```bash
# Backup
docker compose exec postgres pg_dump -U traderj traderj > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec -T postgres psql -U traderj traderj < backup_20260303.sql
```

## Security Checklist

- [ ] Change default `DB_PASSWORD` from `changeme`
- [ ] Change default `TRADERJ_API_KEY` from `changeme-api-key`
- [ ] Set `GRAFANA_PASSWORD` to non-default
- [ ] Set `TRADERJ_ENV=production` to disable Swagger docs
- [ ] Restrict `CORS_ORIGINS` to production domain only
- [ ] Never expose ports 5432 (Postgres) or 9090 (Prometheus) publicly
- [ ] Use reverse proxy (nginx/Caddy) with TLS for public access
- [ ] Telegram bot token secured and not in logs

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| Engine won't start | `docker compose logs engine` | Check DB connectivity, env vars |
| API 401 | X-API-Key header | Verify `TRADERJ_API_KEY` matches |
| WS disconnect | Browser console | Check `NEXT_PUBLIC_WS_URL` |
| No metrics | curl :8001/metrics | Check `PROMETHEUS_PORT` |
| DB pool exhausted | Prometheus `traderj_db_pool_used` | Increase `DB_POOL_MAX` |
