#!/bin/bash

echo "=== Checking Active Markets and Bot Status ==="
echo ""

echo "1. Active markets in database:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT id, question, status FROM market WHERE status = 'active' LIMIT 5;"

echo ""
echo "2. Running bots:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT br.id, m.question, br.status FROM bot_run br JOIN market m ON br.market_id = m.id WHERE CAST(br.status AS TEXT) = 'running' LIMIT 5;"

echo ""
echo "3. Markets with active configs:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT m.id, m.question, mc.is_active FROM market m JOIN market_config mc ON m.id = mc.market_id WHERE mc.is_active = true LIMIT 5;"

