# Testing Bot Start Endpoint

## Endpoint
`POST http://51.38.126.98:8000/bot/{market_id}/start`

## Test Methods

### 1. Using curl (Command Line)

**Basic test:**
```bash
curl -X POST http://51.38.126.98:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start \
     -H "Content-Type: application/json" \
     -d '{}'
```

**With verbose output (see headers and status):**
```bash
curl -v -X POST http://51.38.126.98:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start \
     -H "Content-Type: application/json" \
     -d '{}'
```

**With strategy name (optional):**
```bash
curl -X POST http://51.38.126.98:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start \
     -H "Content-Type: application/json" \
     -d '{"strategy_name": "your_strategy_name", "operator": "test"}'
```

**From your VPS (localhost test):**
```bash
curl -X POST http://localhost:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start \
     -H "Content-Type: application/json" \
     -d '{}'
```

### 2. Using HTTPie (if installed)

```bash
http POST http://51.38.126.98:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start
```

### 3. Using Python

```python
import requests

url = "http://51.38.126.98:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start"
response = requests.post(url, json={})
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

### 4. Using JavaScript/Fetch (Browser Console)

Open browser console (F12) and run:
```javascript
fetch('http://51.38.126.98:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({})
})
.then(response => response.json())
.then(data => console.log('Success:', data))
.catch(error => console.error('Error:', error));
```

### 5. Using Postman or Insomnia

1. Create new POST request
2. URL: `http://51.38.126.98:8000/bot/36cd1df1-da11-40f2-916f-8f70eee800a9/start`
3. Headers: `Content-Type: application/json`
4. Body (raw JSON): `{}`

## Expected Responses

### Success (201 Created)
```json
{
  "id": "uuid-here",
  "market_id": "36cd1df1-da11-40f2-916f-8f70eee800a9",
  "condition_id": "0x...",
  "started_at": "2025-11-20T...",
  "stopped_at": null,
  "status": "running",
  "stop_reason": null,
  "operator": null
}
```

### Error Responses

**404 Not Found (Market doesn't exist):**
```json
{
  "detail": "Market not found"
}
```

**409 Conflict (Bot already running):**
```json
{
  "detail": "Bot is already running for this market"
}
```

**500 Internal Server Error:**
Check backend logs for details.

## Check Backend Logs

**On your VPS:**
```bash
# View real-time logs
docker compose logs -f backend

# View last 50 lines
docker compose logs backend | tail -50

# Filter for errors
docker compose logs backend | grep -i "error\|exception" | tail -20
```

## Verify Market Exists

Before testing, verify the market exists:
```bash
# Check market exists in database
docker compose exec postgres psql -U poly -d poly -c \
  "SELECT id, question, status FROM market WHERE id = '36cd1df1-da11-40f2-916f-8f70eee800a9';"
```

## Test API Health First

Test if API is accessible:
```bash
# Health check
curl http://51.38.126.98:8000/health/

# Should return: {"status":"ok","environment":"..."}
```

## Common Issues

### Connection Refused
- Backend not running: `docker compose ps backend`
- Firewall blocking: Check UFW or cloud provider firewall
- Wrong port: Verify port 8000 is open

### CORS Error
- Set `CORS_ORIGINS=http://51.38.126.98:3000` in `.env`
- Restart backend: `docker compose restart backend`

### 500 Internal Server Error
- Check backend logs: `docker compose logs backend | tail -50`
- Verify database is accessible
- Check if market has strategy_configs

### 404 Not Found
- Market ID doesn't exist in database
- Verify with: `docker compose exec postgres psql -U poly -d poly -c "SELECT id FROM market LIMIT 5;"`

## Quick Test Script

Save this as `test_bot_start.sh`:
```bash
#!/bin/bash

MARKET_ID="36cd1df1-da11-40f2-916f-8f70eee800a9"
API_URL="http://51.38.126.98:8000"

echo "Testing bot start endpoint..."
echo "Market ID: $MARKET_ID"
echo ""

# Test health first
echo "1. Testing API health..."
curl -s "$API_URL/health/" | jq .
echo ""

# Test bot start
echo "2. Testing bot start..."
curl -v -X POST "$API_URL/bot/$MARKET_ID/start" \
     -H "Content-Type: application/json" \
     -d '{}' | jq .
echo ""

echo "Done!"
```

Make executable and run:
```bash
chmod +x test_bot_start.sh
./test_bot_start.sh
```

