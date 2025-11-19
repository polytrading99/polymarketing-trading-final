#!/bin/bash
# Script to stop all trading

echo "=== Stopping Bot ==="
docker compose exec -T postgres psql -U poly -d poly << 'SQL'
-- Stop all running bots
UPDATE bot_run 
SET status = 'stopped', stopped_at = NOW()
WHERE status = 'running';
SQL

echo ""
echo "=== Deactivating Markets ==="
docker compose exec -T postgres psql -U poly -d poly << 'SQL'
-- Deactivate all active markets
UPDATE market 
SET status = 'inactive' 
WHERE status = 'active';
SQL

echo ""
echo "✅ Trading stopped!"
echo ""

