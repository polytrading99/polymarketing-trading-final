# How to Verify Bot is Actually Running and Trading

## Quick Verification Commands

### 1. Check if Processes are Running
```bash
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.verify_bot_activity
```

This will show:
- ✓ If processes are actually running
- ✓ Recent log activity
- ✓ What the bot is doing

### 2. Check Logs Directly
```bash
# Main bot log (trading activity)
docker exec -it polymarketing-trading-final-backend-1 tail -50 /app/polymarket_mm_deliver/logs/mm_main.log

# Trade process log (market data)
docker exec -it polymarketing-trading-final-backend-1 tail -50 /app/polymarket_mm_deliver/logs/trade.log
```

### 3. Check Process Status via API
```bash
curl http://localhost:8000/mm-bot/status
```

## What to Look For in Logs

### ✅ Good Signs (Bot is Working):
- `[RESOLVE-OK] market_id=...` - Bot found a market
- `[ROUND] start=...` - Bot started a new trading round
- `[S1-ENTRY-YES] BUY ...` or `[S1-ENTRY-NO] BUY ...` - Bot placed an order
- `[FILL] first fill detected` - Order was filled
- `order_id=...` - Order IDs being created

### ⚠️ Waiting Signs (Bot is Running but Not Trading):
- `[ROUND] ...` but no `ENTRY` messages - Waiting for bid ≥ 0.6
- `[RESOLVE] ...` but no market found - No market for current bucket
- No activity for several minutes - Waiting for next 15-minute bucket

### ❌ Error Signs:
- `error`, `exception`, `traceback`, `failed` - Something is wrong
- Process exits immediately - Crash on startup

## What Changes Should Appear on Polymarket?

### When Bot is Trading, You Should See:

1. **Open Orders** (in your Polymarket portfolio):
   - BUY orders on BTC Up/Down markets
   - Orders typically $12-16 in size
   - Orders at bid price (≥ 0.6)

2. **Positions** (if orders fill):
   - Active positions in BTC Up/Down markets
   - Either "YES" (Up) or "NO" (Down) positions
   - Position value: $12-16

3. **Trade History**:
   - BUY orders being placed
   - SELL orders (take profit or stop loss exits)
   - Fills showing order execution

### How to Check on Polymarket:

1. **Go to Polymarket.com**
2. **Click your profile** (top right)
3. **Go to "Portfolio" or "Positions"**
4. **Look for:**
   - **Open Orders**: Pending BUY orders
   - **Active Positions**: BTC Up/Down positions
   - **Trade History**: Recent trades

5. **Search for BTC markets:**
   - Look for markets like "BTC will be up/down in the next 15 minutes"
   - Check if you have any orders or positions there

## Why You Might Not See Changes

### Bot is Running but Not Trading:

1. **Market Conditions Not Met:**
   - Bid price < 0.6 (bot only enters when bid ≥ 0.6)
   - This is a safety feature - bot waits for good entry prices

2. **Waiting for Next Bucket:**
   - Bot trades every 15 minutes
   - If you just started it, wait for the next 15-minute window

3. **No Market Available:**
   - BTC Up/Down market might not exist for current time bucket
   - Bot will wait for next bucket

4. **Position Limits:**
   - Bot has reached its position cap ($12-16)
   - Will wait until positions are closed

### Bot is Not Running:

1. **Check if processes are actually running:**
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 ps aux | grep -E "main_final|trade.py"
   ```

2. **Check for crashes:**
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.verify_bot_activity
   ```

## Expected Timeline

- **Immediately**: Processes should start
- **Within 1-2 minutes**: Logs should show activity
- **Within 15 minutes**: First order should be placed (if conditions met)
- **Ongoing**: New orders every 15 minutes when conditions are met

## Troubleshooting

### If Bot Shows "Running" but No Activity:

1. **Check logs for waiting messages:**
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 tail -100 /app/polymarket_mm_deliver/logs/mm_main.log | grep -E "ROUND|ENTRY|RESOLVE|waiting"
   ```

2. **Check current market conditions:**
   - Go to Polymarket and find a BTC 15m Up/Down market
   - Check the bid price - is it ≥ 0.6?

3. **Wait for next 15-minute bucket:**
   - Bot rotates markets every 15 minutes
   - Current time might be in the middle of a bucket

### If No Changes on Polymarket:

1. **Verify bot is actually placing orders:**
   - Check logs for `order_id=` entries
   - These mean orders were submitted

2. **Check if orders are filling:**
   - Look for `[FILL]` messages in logs
   - Unfilled orders stay as "Open Orders"

3. **Check your Polymarket account:**
   - Make sure you're logged into the correct account
   - Check that the BROWSER_ADDRESS matches your Polymarket proxy address

## Quick Status Check Script

Run this to get a complete status:
```bash
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.verify_bot_activity
```

This will tell you:
- ✓ Are processes running?
- ✓ Are logs being written?
- ✓ Is there recent trading activity?
- ⚠ What conditions need to be met?

