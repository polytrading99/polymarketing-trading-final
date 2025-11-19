# Complete Setup Guide - MetaMask Wallet Connection

## Step 1: Get Your Wallet Information from MetaMask

### Get Your Wallet Address
1. Open MetaMask extension
2. Click on your account name at the top
3. Click "Account details"
4. Click "Show private key" (you'll need to enter your password)
5. **Copy your wallet address** (starts with 0x...)

### Get Your Private Key
⚠️ **SECURITY WARNING**: Your private key gives full access to your wallet. Keep it secure!

1. In MetaMask, go to Account details
2. Click "Show private key"
3. Enter your MetaMask password
4. **Copy the private key** (long string of characters, no spaces)

## Step 2: Set Up Environment Variables

### Create .env File
```bash
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker
cp .env.example .env
```

### Edit .env File
Open `.env` and add your credentials:

```bash
# Your MetaMask private key (the one you copied)
PK=your_private_key_here_without_0x_prefix

# Your MetaMask wallet address
BROWSER_ADDRESS=0xYourWalletAddressHere

# Your Google Sheets URL (if you have one, otherwise leave as is)
SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit

# Database (already configured)
DATABASE_URL=postgresql+asyncpg://poly:poly@postgres:5432/poly

# Redis (already configured)
REDIS_URL=redis://redis:6379/0

# Environment
ENVIRONMENT=development
LOG_LEVEL=INFO
```

**Important Notes**:
- If your private key starts with `0x`, remove the `0x` prefix
- Your wallet address should start with `0x` and keep it
- Make sure your wallet has USDC on Polygon network

## Step 3: Prepare Your Wallet

### ⚠️ CRITICAL: Do One Manual Trade First
Polymarket requires your wallet to have done at least one manual trade through their UI before the bot can trade. This sets up the necessary permissions.

1. Go to https://polymarket.com
2. Connect your MetaMask wallet
3. Make at least ONE small trade manually (buy or sell any market)
4. Wait for the trade to complete

**This is required** - the bot won't work without this!

### Ensure You Have USDC on Polygon
1. Make sure your wallet has USDC on Polygon network
2. You'll need at least $10-20 for initial testing
3. Add Polygon network to MetaMask if not already added:
   - Network Name: Polygon
   - RPC URL: https://polygon-rpc.com
   - Chain ID: 137
   - Currency Symbol: MATIC

## Step 4: Start the System

### Start All Services
```bash
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker
docker compose up -d
```

Wait 15-20 seconds for all services to start, then verify:
```bash
docker compose ps
```

All services should show "Up" status.

### Verify Services Are Running
```bash
# Check API
curl http://localhost:8000/health/

# Check frontend (open in browser)
# http://localhost:3000
```

## Step 5: Sync Markets to Database

### Load Markets from Google Sheets
```bash
docker compose exec backend uv run python app/scripts/sync_config.py
```

You should see output like:
```
Fetched X markets and Y strategies
```

If you don't have Google Sheets set up, you can add markets manually to the database (see below).

## Step 6: Configure a Market for Testing

### Option A: Use Google Sheets (Recommended)
1. Create a Google Sheet with market data
2. Update `SPREADSHEET_URL` in `.env`
3. Run sync script again

### Option B: Add Market Manually to Database
```bash
# Connect to database
docker compose exec postgres psql -U poly -d poly

# Insert a test market (replace with actual market data)
INSERT INTO market (condition_id, question, neg_risk, token_yes, token_no, status)
VALUES (
  '0xYourConditionID',
  'Test Market Question',
  false,
  'YourTokenYesID',
  'YourTokenNoID',
  'inactive'
);

# Exit database
\q
```

## Step 7: Configure Trading Parameters

### Set Small Trade Sizes for Testing
```bash
# Connect to database
docker compose exec postgres psql -U poly -d poly

# Update market config with small trade sizes
UPDATE market_config 
SET 
  trade_size = 1.0,  -- $1 per order
  min_size = 0.5,    -- Minimum $0.50
  max_size = 5.0,    -- Maximum $5
  max_spread = 0.05  -- 5% max spread
WHERE market_id = (SELECT id FROM market WHERE condition_id = 'YOUR_CONDITION_ID');

\q
```

## Step 8: Start Trading

### Method 1: Via Database (Recommended for Testing)
```bash
# Connect to database
docker compose exec postgres psql -U poly -d poly

# Activate market and create bot run
UPDATE market 
SET status = 'active' 
WHERE condition_id = 'YOUR_CONDITION_ID';

INSERT INTO bot_run (market_id, status, started_at)
SELECT id, 'running', NOW()
FROM market 
WHERE condition_id = 'YOUR_CONDITION_ID'
AND status = 'active';

\q
```

### Method 2: Via API (If UI button works)
1. Open dashboard: http://localhost:3000
2. Find your market
3. Click the Play button (▶)
4. Status should change to "ACTIVE"

## Step 9: Monitor Trading

### Watch Worker Logs
```bash
docker compose logs -f worker
```

You should see:
- "Initializing Polymarket client..."
- "Loaded X active markets from database"
- WebSocket connections established
- Order book updates
- Order placements

### Check Dashboard
1. Open: http://localhost:3000
2. You should see:
   - Market status: ACTIVE
   - Real-time PnL updates
   - Position counts
   - Fees paid

### Check Metrics
```bash
# View metrics
curl http://localhost:8000/metrics/ | grep poly_

# Or open Grafana
# http://localhost:3001 (admin/admin)
```

## Step 10: Verify Trading is Working

### Check Orders on Polymarket
1. Go to https://polymarket.com
2. Connect your MetaMask wallet
3. Check "My Orders" - you should see orders placed by the bot

### Check Positions
1. In dashboard, check position counts
2. In Polymarket, check your positions
3. They should match

### Monitor First Few Trades
- Watch logs for order placements
- Verify orders appear on Polymarket
- Check that trades execute
- Monitor PnL updates

## Step 11: Stop Trading (When Done Testing)

### Via Database
```bash
docker compose exec postgres psql -U poly -d poly

UPDATE bot_run 
SET status = 'stopped', stopped_at = NOW()
WHERE market_id = (SELECT id FROM market WHERE condition_id = 'YOUR_CONDITION_ID')
AND status = 'running';

UPDATE market 
SET status = 'inactive' 
WHERE condition_id = 'YOUR_CONDITION_ID';

\q
```

### Via Dashboard (If UI works)
- Click Stop button on the market card

## Troubleshooting

### Bot Not Connecting?
```bash
# Check worker logs
docker compose logs worker --tail=50

# Common issues:
# - Missing PK or BROWSER_ADDRESS in .env
# - Wallet hasn't done manual trade (REQUIRED!)
# - Wrong network (must be Polygon)
# - No USDC balance
```

### No Markets Showing?
```bash
# Sync markets again
docker compose exec backend uv run python app/scripts/sync_config.py

# Check database
docker compose exec postgres psql -U poly -d poly -c "SELECT COUNT(*) FROM market;"
```

### Orders Not Placing?
1. Verify wallet has USDC
2. Check you did manual trade first
3. Verify market is active in database
4. Check worker logs for errors

## Safety Tips for Testing

1. **Start Small**: Use $1-5 trade sizes initially
2. **Monitor Closely**: Watch first few trades
3. **Test Stop**: Verify you can stop the bot
4. **Check Balances**: Monitor wallet balance
5. **Review Logs**: Check for any errors

## Quick Reference

```bash
# Start system
docker compose up -d

# Sync markets
docker compose exec backend uv run python app/scripts/sync_config.py

# Watch logs
docker compose logs -f worker

# Stop system
docker compose down

# Restart services
docker compose restart backend worker
```

## Access Points

- **Dashboard**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Grafana**: http://localhost:3001 (admin/admin)
- **Health Check**: http://localhost:8000/health/

---

**Ready to test!** Follow these steps and you'll be trading with small amounts in about 10 minutes.

