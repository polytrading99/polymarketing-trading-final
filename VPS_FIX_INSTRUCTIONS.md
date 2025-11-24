# VPS Fix Instructions - CORS and Bot Start Errors

## Problem

Two errors when clicking "Start Market":
1. **CORS Error**: Frontend can't access backend due to CORS policy
2. **500 Internal Server Error**: Backend error when starting bot

## Fixes Applied

### 1. CORS Configuration Fixed

The backend now supports configurable CORS origins via `CORS_ORIGINS` environment variable.

**On your VPS**, do the following:

#### Option A: Set in .env file (Recommended)
```bash
# Edit your .env file
nano .env

# Add this line:
CORS_ORIGINS=http://51.38.126.98:3000

# Save and exit (Ctrl+X, Y, Enter)
```

#### Option B: Set in docker-compose.yml directly
Edit `docker-compose.yml` and change:
```yaml
environment:
  CORS_ORIGINS: http://51.38.126.98:3000
```

### 2. Bot Run UUID Generation Fixed

Fixed the bot start endpoint to explicitly generate UUIDs.

### 3. Restart Services

After making changes, restart the backend:

```bash
# Stop services
docker compose down

# Rebuild (to apply code changes)
docker compose build backend

# Start services
docker compose up -d

# Verify backend is running
docker compose logs backend | tail -20
```

## Verification

1. **Test CORS is fixed:**
   ```bash
   # Test from VPS
   curl -H "Origin: http://51.38.126.98:3000" \
        -H "Access-Control-Request-Method: POST" \
        -H "Access-Control-Request-Headers: Content-Type" \
        -X OPTIONS \
        http://localhost:8000/bot/test/start
   ```
   
   Should see `Access-Control-Allow-Origin` header in response.

2. **Test bot start:**
   - Go to dashboard: `http://51.38.126.98:3000`
   - Click "Start" on a market
   - Check browser console (F12) - should no longer see CORS errors
   - Check backend logs: `docker compose logs backend | tail -50`

## If Still Getting Errors

### Check Backend Logs
```bash
docker compose logs backend | grep -i "error\|exception\|traceback" | tail -30
```

### Test API Directly
```bash
# Test health endpoint
curl http://localhost:8000/health/

# Test markets endpoint
curl http://localhost:8000/markets | head -100

# Test bot start (replace MARKET_ID with actual ID)
curl -X POST http://localhost:8000/bot/MARKET_ID/start \
     -H "Content-Type: application/json" \
     -d '{}'
```

### Common Issues

1. **CORS still blocked**: 
   - Verify `CORS_ORIGINS` is set correctly in .env
   - Check backend logs for CORS errors
   - Restart backend: `docker compose restart backend`

2. **500 Internal Server Error**:
   - Check backend logs for detailed error
   - Verify database is accessible
   - Check if market has strategy_configs

3. **Market not found**:
   - Verify markets are synced: `docker compose exec backend uv run python -m app.scripts.sync_config`
   - Check database: `docker compose exec postgres psql -U poly -d poly -c "SELECT COUNT(*) FROM market;"`

## Quick Fix Summary

```bash
# 1. Set CORS_ORIGINS in .env
echo 'CORS_ORIGINS=http://51.38.126.98:3000' >> .env

# 2. Restart backend
docker compose restart backend

# 3. Check logs
docker compose logs backend -f
```

Then try clicking "Start Market" again in the dashboard.

