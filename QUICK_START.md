# Quick Start - 5 Minute Setup

## Prerequisites
- MetaMask wallet with USDC on Polygon
- Wallet has done at least ONE manual trade on Polymarket (required!)

## Step 1: Get Wallet Info (2 minutes)

1. **Open MetaMask** → Account details → Show private key
2. **Copy two things**:
   - Private key (long string)
   - Wallet address (starts with 0x)

## Step 2: Configure (1 minute)

```bash
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker

# Create .env file
cat > .env << 'EOF'
PK=YOUR_PRIVATE_KEY_HERE
BROWSER_ADDRESS=0xYOUR_WALLET_ADDRESS
SPREADSHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit
DATABASE_URL=postgresql+asyncpg://poly:poly@postgres:5432/poly
REDIS_URL=redis://redis:6379/0
ENVIRONMENT=development
LOG_LEVEL=INFO
EOF

# Edit .env and replace YOUR_PRIVATE_KEY_HERE and YOUR_WALLET_ADDRESS
nano .env
```

**Important**: 
- Remove `0x` from private key if it has one
- Keep `0x` in wallet address

## Step 3: Start System (30 seconds)

```bash
docker compose up -d
sleep 15
docker compose ps  # Verify all services are "Up"
```

## Step 4: Sync Markets (30 seconds)

```bash
docker compose exec backend uv run python app/scripts/sync_config.py
```

## Step 5: Configure Small Trade Sizes (1 minute)

```bash
docker compose exec postgres psql -U poly -d poly << 'SQL'
-- Set small trade sizes for testing
UPDATE market_config 
SET 
  trade_size = 1.0,    -- $1 per order
  min_size = 0.5,      -- Minimum $0.50
  max_size = 5.0,      -- Maximum $5
  max_spread = 0.05    -- 5% max spread
WHERE id IN (SELECT id FROM market_config LIMIT 1);
SQL
```

## Step 6: Start Trading (30 seconds)

```bash
docker compose exec postgres psql -U poly -d poly << 'SQL'
-- Activate first market and start bot
UPDATE market SET status = 'active' WHERE id = (SELECT id FROM market LIMIT 1);

INSERT INTO bot_run (market_id, status, started_at)
SELECT id, 'running', NOW()
FROM market 
WHERE status = 'active'
LIMIT 1;
SQL
```

## Step 7: Monitor (Ongoing)

```bash
# Watch logs
docker compose logs -f worker

# Open dashboard
# http://localhost:3000
```

## Verify It's Working

1. **Check logs** - Should see "WebSocket connected"
2. **Check dashboard** - Market should show "ACTIVE"
3. **Check Polymarket** - Go to site, check "My Orders"
4. **Wait 1-2 minutes** - Orders should appear

## Stop Trading

```bash
docker compose exec postgres psql -U poly -d poly << 'SQL'
UPDATE bot_run SET status = 'stopped', stopped_at = NOW() WHERE status = 'running';
UPDATE market SET status = 'inactive' WHERE status = 'active';
SQL
```

## Troubleshooting

**Bot not starting?**
- Check `.env` has correct PK and BROWSER_ADDRESS
- Verify wallet did manual trade on Polymarket
- Check wallet has USDC on Polygon

**No markets?**
- Run sync script again
- Check Google Sheets URL is correct

**Orders not placing?**
- Check worker logs: `docker compose logs worker`
- Verify market is active: `docker compose exec postgres psql -U poly -d poly -c "SELECT status FROM market;"`

---

**That's it!** You should be trading in under 5 minutes.

