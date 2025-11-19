## Docker & Deployment Guide

### Prerequisites

- Docker Engine 24+ and Docker Compose v2
- `uv` not required locally (handled inside containers)
- Copy a `.env` file with production secrets (private key, etc.) into the project root before running containers. Example:

```bash
cp .env.example .env
```

Populate values for:
- `PK`, `BROWSER_ADDRESS`
- Any API tokens, alert webhooks, etc.

### Build & Run Locally

1. **Sync dependencies and migrations (first run)**
   ```bash
   docker compose build
   docker compose run --rm backend uv run alembic upgrade head
   docker compose run --rm backend uv run python -m app.scripts.sync_config
   ```

2. **Start the full stack**
   ```bash
   docker compose up
   ```

   Services exposed:
   - API: http://localhost:8000 (FastAPI + Prometheus metrics at `/metrics`)
   - Next.js dashboard: http://localhost:3000
   - Postgres: localhost:5432
   - Redis: localhost:6379
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3001 (credentials `admin` / `admin`)

3. **Watch logs**
   ```bash
   docker compose logs -f backend worker
   ```

4. **Shutdown**
   ```bash
   docker compose down
   ```

### Production Notes

- Create an `.env.production` file and point Compose to it:
  ```bash
  docker compose --env-file .env.production up -d
  ```
- For HTTPS termination use a reverse proxy (Traefik, Nginx, Caddy) in front of the `web` and `backend` services.
- Set persistent storage volumes for Postgres and Grafana (already defined in `docker-compose.yml`).
- Configure Grafana alerting based on Prometheus metrics (`poly_orders_open`, `poly_positions_size`, `poly_trades_total`).
- For multi-machine deployments consider separating the trading worker from the API/UI (deploy only the required services).

### Updating

- Pull latest code:
  ```bash
  git pull
  docker compose build --no-cache
  docker compose up -d
  ```
- Run database migrations and config sync:
  ```bash
  docker compose run --rm backend uv run alembic upgrade head
  docker compose run --rm backend uv run python -m app.scripts.sync_config
  ```

