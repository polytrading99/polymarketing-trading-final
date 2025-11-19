# Quick Commands Reference

## The Problem
When using `docker compose exec` with heredoc (`<<`), you get "the input device is not a TTY" error.

## The Solution
Add `-T` flag to disable TTY allocation, OR use the provided scripts.

## Easy Way: Use Scripts

### Start Trading
```bash
./START_TRADING.sh
```

### Stop Trading
```bash
./STOP_TRADING.sh
```

## Manual Commands (with -T flag)

### Configure Small Trade Sizes
```bash
docker compose exec -T postgres psql -U poly -d poly -c "UPDATE market_config SET trade_size = 1.0, min_size = 0.5, max_size = 5.0, max_spread = 0.05 WHERE id IN (SELECT mc.id FROM market_config mc JOIN market m ON mc.market_id = m.id LIMIT 5);"
```

### Start Trading on One Market
```bash
# Activate market
docker compose exec -T postgres psql -U poly -d poly -c "UPDATE market SET status = 'active' WHERE id = (SELECT id FROM market WHERE status = 'inactive' LIMIT 1);"

# Start bot
docker compose exec -T postgres psql -U poly -d poly -c "INSERT INTO bot_run (market_id, status, started_at) SELECT id, 'running', NOW() FROM market WHERE status = 'active' AND id NOT IN (SELECT market_id FROM bot_run WHERE status = 'running') LIMIT 1;"
```

### Stop Trading
```bash
# Stop bot
docker compose exec -T postgres psql -U poly -d poly -c "UPDATE bot_run SET status = 'stopped', stopped_at = NOW() WHERE status = 'running';"

# Deactivate markets
docker compose exec -T postgres psql -U poly -d poly -c "UPDATE market SET status = 'inactive' WHERE status = 'active';"
```

## Alternative: Use psql file

### Create SQL file
```bash
cat > start_trading.sql << 'EOF'
UPDATE market_config SET trade_size = 1.0, min_size = 0.5, max_size = 5.0, max_spread = 0.05 WHERE id IN (SELECT mc.id FROM market_config mc JOIN market m ON mc.market_id = m.id LIMIT 5);
UPDATE market SET status = 'active' WHERE id = (SELECT id FROM market WHERE status = 'inactive' LIMIT 1);
INSERT INTO bot_run (market_id, status, started_at) SELECT id, 'running', NOW() FROM market WHERE status = 'active' AND id NOT IN (SELECT market_id FROM bot_run WHERE status = 'running') LIMIT 1;
EOF
```

### Execute SQL file
```bash
docker compose exec -T postgres psql -U poly -d poly < start_trading.sql
```

## Monitor Trading

```bash
# Watch worker logs
docker compose logs -f worker

# Check active markets
docker compose exec -T postgres psql -U poly -d poly -c "SELECT m.question, br.status FROM market m LEFT JOIN bot_run br ON m.id = br.market_id WHERE m.status = 'active';"

# Check dashboard
# Open: http://localhost:3000
```

## Quick Status Check

```bash
# Check if bot is running
docker compose exec -T postgres psql -U poly -d poly -c "SELECT COUNT(*) as running_bots FROM bot_run WHERE status = 'running';"

# Check active markets
docker compose exec -T postgres psql -U poly -d poly -c "SELECT COUNT(*) as active_markets FROM market WHERE status = 'active';"
```

---

**Remember**: Always use `-T` flag with `docker compose exec` when piping input or using heredoc!

