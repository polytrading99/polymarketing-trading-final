# How to Run the Scripts

## Step-by-Step Instructions

### 1. Open Terminal
Open a terminal/command prompt on your computer.

### 2. Navigate to Project Directory
```bash
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker
```

### 3. Run the Scripts

#### Option A: Make Scripts Executable and Run (Recommended)
```bash
# Make scripts executable (one time only)
chmod +x *.sh

# Run setup (creates market configs - already done, but you can run again)
./SETUP_MARKET_CONFIG.sh

# Start trading
./START_TRADING.sh
```

#### Option B: Run with bash
```bash
# Run setup
bash SETUP_MARKET_CONFIG.sh

# Start trading
bash START_TRADING.sh
```

#### Option C: Run with sh
```bash
# Run setup
sh SETUP_MARKET_CONFIG.sh

# Start trading
sh START_TRADING.sh
```

## Complete Example

Here's the complete sequence:

```bash
# 1. Go to project directory
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker

# 2. Make scripts executable (one time)
chmod +x SETUP_MARKET_CONFIG.sh START_TRADING.sh STOP_TRADING.sh

# 3. Create market configs (if not already done)
./SETUP_MARKET_CONFIG.sh

# 4. Start trading
./START_TRADING.sh

# 5. Monitor (in another terminal or after)
docker compose logs -f worker

# 6. Stop trading when done
./STOP_TRADING.sh
```

## What You'll See

When you run `./START_TRADING.sh`, you should see:
```
=== Configuring Small Trade Sizes ===
UPDATE 1

=== Activating Market ===
UPDATE 1

=== Starting Bot ===
INSERT 0 1

✅ Trading started!

Monitor with:
  docker compose logs -f worker

Dashboard: http://localhost:3000
```

## Verify It's Working

### Check Worker Logs
```bash
docker compose logs -f worker
```

You should see:
- "Initializing Polymarket client..."
- "Loaded X active markets from database"
- WebSocket connections
- Order book updates

### Check Dashboard
Open in browser: **http://localhost:3000**

You should see:
- Market with "ACTIVE" status
- Real-time PnL updates
- Position counts

### Check Database
```bash
docker compose exec -T postgres psql -U poly -d poly -c "SELECT m.question, br.status FROM market m JOIN bot_run br ON m.id = br.market_id WHERE br.status = 'running';"
```

## Stop Trading

When you want to stop:
```bash
./STOP_TRADING.sh
```

Or manually:
```bash
bash STOP_TRADING.sh
```

## Troubleshooting

### "Permission denied"
```bash
chmod +x *.sh
```

### "No such file or directory"
Make sure you're in the right directory:
```bash
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker
ls *.sh  # Should show the scripts
```

### Scripts not working
Try running with bash explicitly:
```bash
bash START_TRADING.sh
```

---

**That's it!** Just run `./START_TRADING.sh` to start trading.

