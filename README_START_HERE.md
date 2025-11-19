# 🚀 START HERE - Quick Testing Guide

## The Problem You Had
The error "the input device is not a TTY" happens when using `docker compose exec` with heredoc. **Fixed!** Use the scripts below.

## ✅ Quick Start (3 Steps)

### Step 1: Create Market Configs (One Time)
```bash
./SETUP_MARKET_CONFIG.sh
```

This creates trading configurations for 5 markets with small amounts.

### Step 2: Start Trading
```bash
./START_TRADING.sh
```

This will:
- Set small trade sizes ($1-5)
- Activate one market
- Start the bot

### Step 3: Monitor
```bash
# Watch logs
docker compose logs -f worker

# Open dashboard
# http://localhost:3000
```

## Stop Trading
```bash
./STOP_TRADING.sh
```

## What Each Script Does

### `SETUP_MARKET_CONFIG.sh`
- Creates a default strategy
- Creates market configs for 5 markets
- Sets up trading parameters

### `START_TRADING.sh`
- Configures small trade sizes ($1-5)
- Activates one market
- Starts the bot

### `STOP_TRADING.sh`
- Stops all running bots
- Deactivates all markets

## Verify It's Working

1. **Check worker logs** - Should see:
   - "Initializing Polymarket client..."
   - "Loaded X active markets from database"
   - WebSocket connections

2. **Check dashboard** - http://localhost:3000
   - Market should show "ACTIVE"
   - PnL should update

3. **Check Polymarket** - https://polymarket.com
   - Connect your MetaMask
   - Check "My Orders" - should see bot's orders

## Troubleshooting

### "No market configs found"
→ Run `./SETUP_MARKET_CONFIG.sh` first

### "Bot not starting"
→ Check `.env` has correct `PK` and `BROWSER_ADDRESS`
→ Verify you did one manual trade on Polymarket

### "No orders appearing"
→ Wait 2-3 minutes
→ Check worker logs for errors
→ Verify wallet has USDC on Polygon

## Current Status

✅ All services running  
✅ 2,607 markets in database  
✅ Scripts ready to use  
✅ Ready for testing  

---

**Next**: Run `./SETUP_MARKET_CONFIG.sh` then `./START_TRADING.sh`

