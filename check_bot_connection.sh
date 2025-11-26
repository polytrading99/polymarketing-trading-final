#!/bin/bash

echo "=== BOT CONNECTION DIAGNOSTIC ==="
echo ""

echo "1. Checking environment variables in worker container:"
docker compose exec -T worker printenv | grep -E "PK|BROWSER_ADDRESS" | sed 's/PK=.*/PK=***HIDDEN***/' | sed 's/\(BROWSER_ADDRESS=0x\)[^ ]*/\1***HIDDEN***/'
echo ""

echo "2. Checking if Polymarket client initialized:"
docker compose logs worker | grep -i "initializing polymarket client" | tail -3
echo ""

echo "3. Checking for authentication errors:"
docker compose logs worker | grep -iE "error.*client|failed.*auth|credential|api.*key" | tail -5
echo ""

echo "4. Checking WebSocket connections:"
docker compose logs worker | grep -i "subscription message" | tail -3
echo ""

echo "5. Checking for order creation attempts:"
docker compose logs worker --tail=200 | grep -iE "sending buy order|creating new order|send_buy_order" | tail -10
echo ""

echo "6. Checking recent errors:"
docker compose logs worker --tail=100 | grep -iE "error|exception|failed" | tail -10
echo ""

echo "7. Checking if bot sees your wallet:"
docker compose logs worker | grep -i "browser_wallet\|wallet" | tail -5
echo ""

echo "8. Recent activity (last 20 lines):"
docker compose logs worker --tail=20

