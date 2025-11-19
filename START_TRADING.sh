#!/bin/bash
# Script to start trading with small amounts for testing

echo "=== Configuring Small Trade Sizes ==="
docker compose exec -T postgres psql -U poly -d poly << 'SQL'
-- Update market configs to use small amounts for testing
UPDATE market_config 
SET 
  trade_size = 1.0,    -- $1 per order (very small)
  min_size = 0.5,      -- Minimum $0.50
  max_size = 5.0,      -- Maximum $5
  max_spread = 0.05,   -- 5% max spread
  is_active = true     -- Activate the config
WHERE id IN (
  SELECT mc.id 
  FROM market_config mc
  JOIN market m ON mc.market_id = m.id
  WHERE mc.is_active = false OR mc.is_active IS NULL
  LIMIT 1  -- Start with just 1 market for testing
);
SQL

echo ""
echo "=== Activating Market ==="
docker compose exec -T postgres psql -U poly -d poly << 'SQL'
-- Activate the market that has an active config
UPDATE market 
SET status = 'active' 
WHERE id IN (
  SELECT market_id 
  FROM market_config 
  WHERE is_active = true 
  LIMIT 1
);
SQL

echo ""
echo "=== Starting Bot ==="
docker compose exec -T postgres psql -U poly -d poly << 'SQL'
-- Start bot for active market (with explicit UUID generation)
INSERT INTO bot_run (id, market_id, status, started_at)
SELECT gen_random_uuid(), id, 'running', NOW()
FROM market 
WHERE status = 'active'
AND id NOT IN (SELECT market_id FROM bot_run WHERE status = 'running')
LIMIT 1;
SQL

echo ""
echo "✅ Trading started!"
echo ""
echo "Monitor with:"
echo "  docker compose logs -f worker"
echo ""
echo "Dashboard: http://localhost:3000"
echo ""

