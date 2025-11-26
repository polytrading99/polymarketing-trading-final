#!/bin/bash

echo "=== Diagnosing Why No Active Markets ==="
echo ""

echo "1. Checking for active markets in database:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT COUNT(*) as active_markets FROM market WHERE status = 'active';"

echo ""
echo "2. Checking for running bots in database:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT COUNT(*) as running_bots FROM bot_run WHERE CAST(status AS TEXT) = 'running';"

echo ""
echo "3. Checking markets with running bots:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT m.condition_id, m.question, br.status FROM market m JOIN bot_run br ON m.id = br.market_id WHERE CAST(br.status AS TEXT) = 'running' LIMIT 5;"

echo ""
echo "4. Checking worker logs for database errors:"
docker compose logs worker --tail=50 | grep -iE "Failed to update active|database.*error|exception" | tail -5

echo ""
echo "=== Diagnosis Complete ==="
echo ""
echo "If you see 0 active markets or 0 running bots:"
echo "  1. Go to dashboard: http://51.38.126.98:3000"
echo "  2. Click Play (▶) button on a market"
echo "  3. Wait 30 seconds"
echo "  4. Run this script again"

