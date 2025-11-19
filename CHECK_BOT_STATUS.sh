#!/bin/bash
# Script to check if bot is running and using your wallet

echo "=== Bot Status Check ==="
echo ""

echo "1. Checking Database for Running Bots:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT br.id, m.question, br.status, br.started_at FROM bot_run br JOIN market m ON br.market_id = m.id WHERE br.status = 'running' ORDER BY br.started_at DESC LIMIT 5;"

echo ""
echo "2. Checking Worker Logs (last 10 lines):"
docker compose logs worker --tail=10 2>&1 | grep -v "^worker-1"

echo ""
echo "3. Checking Wallet Configuration:"
if grep -q "^PK=" .env && grep -q "^BROWSER_ADDRESS=" .env; then
    echo "   ✅ Wallet credentials found in .env"
    echo "   Wallet Address: $(grep '^BROWSER_ADDRESS=' .env | cut -d'=' -f2 | head -c 10)..."
else
    echo "   ❌ Wallet credentials NOT found in .env"
    echo "   Please set PK and BROWSER_ADDRESS in .env file"
fi

echo ""
echo "4. Checking Active Markets:"
docker compose exec -T postgres psql -U poly -d poly -c "SELECT COUNT(*) as active_markets FROM market WHERE status = 'active';"

echo ""
echo "5. To verify bot is using your wallet:"
echo "   - Go to https://polymarket.com"
echo "   - Connect your MetaMask wallet"
echo "   - Check 'My Orders' - you should see orders placed by the bot"
echo "   - Check your positions - they should match the dashboard"

echo ""
echo "=== Check Complete ==="

