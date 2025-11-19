#!/bin/bash
# Script to create market configs for testing

echo "=== Creating Strategy (if needed) ==="
docker compose exec -T postgres psql -U poly -d poly << 'SQL'
-- Create a default strategy if it doesn't exist
INSERT INTO strategy (id, name, default_params, created_at)
VALUES (
  gen_random_uuid(),
  'default',
  '{}'::jsonb,
  NOW()
)
ON CONFLICT (name) DO NOTHING;
SQL

echo ""
echo "=== Creating Market Configs for First 5 Markets ==="
docker compose exec -T postgres psql -U poly -d poly << 'SQL'
-- Create market configs with small trade sizes
INSERT INTO market_config (
  id, market_id, strategy_id, is_active,
  trade_size, min_size, max_size, max_spread, tick_size,
  params, created_at, updated_at
)
SELECT 
  gen_random_uuid(),
  m.id,
  (SELECT id FROM strategy WHERE name = 'default' LIMIT 1),
  false,  -- Start inactive
  1.0,    -- $1 per order
  0.5,    -- Minimum $0.50
  5.0,    -- Maximum $5
  0.05,   -- 5% max spread
  0.01,   -- Tick size
  '{}'::jsonb,
  NOW(),
  NOW()
FROM market m
WHERE m.id NOT IN (SELECT market_id FROM market_config)
LIMIT 5;
SQL

echo ""
echo "✅ Market configs created!"
echo ""
echo "Now you can run: ./START_TRADING.sh"
echo ""

