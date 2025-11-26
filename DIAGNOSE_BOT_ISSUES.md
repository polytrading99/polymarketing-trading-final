# How to Diagnose Why Bot Isn't Trading

## Quick Diagnosis Steps

### Step 1: Check if Market is Active in Database

```bash
cd ~/poly-maker/polymarketing-trading-final
./check_active_markets.sh
```

**Expected output:**
- Should show at least 1 market with status "active"
- Should show at least 1 bot_run with status "running"

**If empty:**
- Market is not actually active → Click Play button on dashboard again
- Bot_run not created → Check backend logs for errors

### Step 2: Check Worker Logs for Active Markets

```bash
docker compose logs worker | grep -i "active markets\|active condition_ids\|Subscribing to"
```

**Expected output:**
```
Updated active markets: 1 markets with running bots
Active condition_ids: ['0x...']
Subscribing to 2 tokens from 1 active markets
```

**If shows "0 markets":**
- Worker can't see active markets → Database connection issue
- Check database connection errors in logs

### Step 3: Check if Worker is Processing Markets

```bash
docker compose logs worker --tail=100 | grep -E "perform_trade|For Yes|For No|buy_amount"
```

**Expected output:**
```
{timestamp}: {Market Question}
For Yes: buy_amount: 1.0, Position: 0.0
For No: buy_amount: 1.0, Position: 0.0
```

**If no output:**
- Worker not receiving WebSocket data → Check WebSocket connection
- Market not in active list → Check Step 2

### Step 4: Check for Order Creation

```bash
docker compose logs worker | grep -E "Sending Buy Order|Creating new order|BUY"
```

**Expected output:**
```
Sending Buy Order for 0x... because no existing orders and buy_amount=1.0
Creating new order for 1.0 at 0.45
```

**If no output:**
- Bot calculating but not placing orders → Check why (see Step 5)

### Step 5: Check Why Orders Aren't Placed

```bash
docker compose logs worker | grep -E "DEBUG|Not placing|Not sending|outside acceptable"
```

**Common reasons:**
- "Not placing buy order because..." → Check the reason
- "outside acceptable price range" → Market price too extreme
- "Not enough position + size" → Already at max position

## Common Issues and Fixes

### Issue 1: "Updated active markets: 0 markets"

**Problem:** Worker can't see active markets from database

**Fix:**
1. Check database connection:
   ```bash
   docker compose logs worker | grep -i "database.*error\|connection.*failed"
   ```

2. Restart worker:
   ```bash
   docker compose restart worker
   ```

3. Verify market is active:
   ```bash
   docker compose exec postgres psql -U poly -d poly -c "SELECT m.question, br.status FROM market m JOIN bot_run br ON m.id = br.market_id WHERE CAST(br.status AS TEXT) = 'running';"
   ```

### Issue 2: "Subscribing to 0 tokens"

**Problem:** No active markets found

**Fix:**
1. Make sure market is active in database (Step 1)
2. Wait 30 seconds for worker to refresh
3. Check logs again

### Issue 3: No "perform_trade" messages

**Problem:** WebSocket not receiving data or market not active

**Fix:**
1. Check WebSocket connection:
   ```bash
   docker compose logs worker | grep -i "subscription message\|websocket"
   ```

2. Verify market condition_id matches:
   - Check dashboard for condition_id
   - Check logs for "Active condition_ids"

### Issue 4: "DEBUG: Not placing buy order"

**Problem:** Trading conditions not met

**Common reasons:**
- Price outside 0.1-0.9 range
- Position already at max_size
- Spread too wide
- No buy_amount calculated

**Fix:**
- Check market parameters (trade_size, max_size, max_spread)
- Verify market has liquidity
- Check if position is already at max

### Issue 5: Dashboard Not Refreshing

**Problem:** Frontend not updating

**Fix:**
1. Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)
2. Check backend is running:
   ```bash
   docker compose ps backend
   ```
3. Check API:
   ```bash
   curl http://localhost:8000/api/markets
   ```

## Complete Diagnostic Script

Run this to get full status:

```bash
#!/bin/bash
echo "=== Complete Bot Diagnosis ==="
echo ""

echo "1. Database - Active Markets:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT COUNT(*) FROM market WHERE status = 'active';"

echo ""
echo "2. Database - Running Bots:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT COUNT(*) FROM bot_run WHERE CAST(status AS TEXT) = 'running';"

echo ""
echo "3. Worker - Active Markets Detected:"
docker compose logs worker | grep -i "Updated active markets\|Subscribing to" | tail -3

echo ""
echo "4. Worker - Recent Trading Activity:"
docker compose logs worker --tail=50 | grep -E "perform_trade|buy_amount: 1.0" | tail -5

echo ""
echo "5. Worker - Order Creation:"
docker compose logs worker --tail=200 | grep -E "Sending Buy Order|Creating new order" | tail -5

echo ""
echo "6. Worker - Errors:"
docker compose logs worker --tail=100 | grep -iE "error|exception|failed" | tail -5

echo ""
echo "=== Diagnosis Complete ==="
```

## Expected Flow When Working

1. **Dashboard:** Click Play → Market shows "ACTIVE"
2. **Database:** `bot_run` created with status "running"
3. **Worker (30s later):** "Updated active markets: 1 markets"
4. **Worker:** "Subscribing to 2 tokens from 1 active markets"
5. **Worker:** WebSocket receives data → "perform_trade" called
6. **Worker:** "Sending Buy Order" → "Creating new order"
7. **Polymarket:** Orders appear in "My Orders"
8. **Dashboard:** PnL and positions update

If any step fails, check the corresponding diagnostic above.

