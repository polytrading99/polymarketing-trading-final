# Testing Guide: Fix Allowance and Test Bot Trading

## Step 1: Stop the Bot (if running)

```bash
# On your VPS
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.stop_bot_immediately
```

Or via API:
```bash
curl -X POST http://localhost:8000/mm-bot/stop
```

## Step 2: Approve USDC for Trading

Run the approval script inside the Docker container:

```bash
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.approve_usdc_for_trading
```

**What this does:**
- Checks your current USDC allowance for the Polymarket Exchange contract
- If allowance is low (< $1000), it approves maximum allowance
- Signs and sends the transaction using your private key
- Waits for confirmation

**Expected output:**
```
======================================================================
  APPROVE USDC FOR POLYMARKET TRADING
======================================================================

Proxy Address: 0x...
Wallet Address (from PK): 0x...
Approving from: 0x...
Approving to: 0x4bfb41d5b3570dfe3a6c6c0c11b55b319906cb0a

Checking current allowance...
Current USDC Allowance: $0.00
⚠️  Allowance is low ($0.00)
  Approving maximum allowance...

Sending approval transaction...
✓ Transaction sent: 0x...
  View on PolygonScan: https://polygonscan.com/tx/0x...
Waiting for confirmation...
✓ Transaction confirmed!
  Block: ...
  Gas used: ...

✓ New Allowance: $115,792,089,237,316,195,423,570,985,008,687,907,853,269,984,665,640,564,039,457.00

✅ USDC is now approved for trading!
```

**If you see an error:**
- **"insufficient funds"**: Your wallet needs MATIC for gas fees (even though you're approving USDC)
- **"nonce"**: Transaction conflict, wait a moment and try again
- **"invalid signature"**: Check your PK environment variable

## Step 3: Verify Allowance

Check your balance and allowance:

```bash
docker exec -it polymarketing-trading-final-backend-1 curl http://localhost:8000/account/balance
```

You should see:
```json
{
  "usdc_balance": 5.0,
  "matic_balance": ...,
  "wallet_address": "0x...",
  "allowance": 115792089237316195423570985008687907853269984665640564039457.00
}
```

## Step 4: Restart the Bot

```bash
curl -X POST http://localhost:8000/mm-bot/restart
```

Or start it:
```bash
curl -X POST http://localhost:8000/mm-bot/start
```

## Step 5: Monitor Bot Activity

### Check bot status:
```bash
curl http://localhost:8000/mm-bot/status
```

### Watch logs for order attempts:
```bash
# Main bot logs
docker exec -it polymarketing-trading-final-backend-1 tail -f /app/polymarket_mm_deliver/logs/mm_main.log | grep -E "(entry|order|ERROR|WARN)"

# Or check recent activity
docker exec -it polymarketing-trading-final-backend-1 tail -50 /app/polymarket_mm_deliver/logs/mm_main.log
```

### Check for successful orders:
```bash
# Check open orders
curl http://localhost:8000/account/orders

# Check positions
curl http://localhost:8000/account/positions
```

## Step 6: Verify Orders Are Placed

### Via Dashboard:
1. Open `http://your-vps-ip:3000/mm-bot` in your browser
2. Check the "Open Orders" section
3. Check the "Recent Errors" section (should be empty or show different errors)

### Via API:
```bash
# Get detailed bot status
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.check_bot_status_detailed
```

## What to Look For

### ✅ Success Indicators:
- No more "not enough balance / allowance" errors in logs
- Orders appear in `/account/orders` endpoint
- Bot status shows `"is_running": true` and processes are alive
- Dashboard shows open orders

### ❌ If Still Failing:
1. **Check balance**: Ensure you have at least $5 USDC
2. **Check MATIC**: You need MATIC for gas (even though orders use USDC)
3. **Check logs**: Look for specific error messages
4. **Check config**: Ensure `MIN_TRADE_SIZE` is set to 5.0 or lower

## Quick Test Commands

```bash
# 1. Stop bot
curl -X POST http://localhost:8000/mm-bot/stop

# 2. Approve USDC
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.approve_usdc_for_trading

# 3. Check allowance
curl http://localhost:8000/account/balance

# 4. Restart bot
curl -X POST http://localhost:8000/mm-bot/restart

# 5. Monitor logs
docker exec -it polymarketing-trading-final-backend-1 tail -f /app/polymarket_mm_deliver/logs/mm_main.log | grep -E "(entry|order)"
```

## Troubleshooting

### Error: "insufficient funds for gas"
- Your wallet needs MATIC (Polygon's native token) for gas fees
- Get MATIC from a faucet or exchange
- Check balance: `curl http://localhost:8000/account/balance`

### Error: "order size lower than minimum: 5"
- Your `MIN_TRADE_SIZE` in config.json is too low
- Polymarket requires minimum $5 orders
- Current config should have `MIN_TRADE_SIZE: 5.0`

### Error: Still getting "not enough balance / allowance"
- Verify allowance was approved: Check the transaction on PolygonScan
- Ensure you're approving from the correct address (the one with your USDC)
- Restart the bot after approval

### Bot not placing orders
- Check if market conditions are met (see `BOT_TRADING_INFO.md`)
- Bot only trades BTC 15m Up/Down contracts
- Bot needs specific price conditions to enter
- Check logs for entry conditions: `grep "ENTRY" /app/polymarket_mm_deliver/logs/mm_main.log`

