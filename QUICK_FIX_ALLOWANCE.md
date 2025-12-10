# QUICK FIX: "Not Enough Balance / Allowance" Error

## ⚠️ IMPORTANT: Stop Bot First

```bash
# Stop bot immediately
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.stop_bot_immediately
```

## The Problem

The error "not enough balance / allowance" means:
- ✅ You have USDC balance (bot can read it)
- ❌ Exchange contract doesn't have permission to spend your USDC
- This is required for ERC20 tokens before trading

## Solution: Approve USDC

### Option 1: Using MetaMask (RECOMMENDED for Browser Wallet Users)

If you're using a proxy address (browser wallet), you **MUST** approve from MetaMask:

1. **Go to Polymarket.com**
2. **Connect your MetaMask wallet**
3. **Make ONE small manual trade** (this automatically approves USDC)
   - Buy or sell any market for $1-2
   - This will approve USDC automatically
4. **Verify approval worked:**
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.approve_usdc_for_trading
   ```
   - Should show "Allowance is sufficient"

### Option 2: Manual Approval via MetaMask

1. Go to [Polygonscan USDC Contract](https://polygonscan.com/token/0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174#writeContract)
2. Connect MetaMask
3. Find "approve" function
4. Enter:
   - `_spender`: `0x4bfb41d5b3570dfe3a6c6c0c11b55b319906cb0a` (Exchange contract)
   - `_value`: `115792089237316195423570985008687907853269984665640564039457584007913129639935` (max approval)
5. Click "Write" and confirm in MetaMask

### Option 3: Script (Only works if proxy address = wallet address)

```bash
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.approve_usdc_for_trading
```

**Note:** This only works if your proxy address is the same as your wallet address. For browser wallet users, use Option 1 or 2.

## After Approval

1. **Verify approval:**
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.approve_usdc_for_trading
   ```
   Should show: "✓ Allowance is sufficient"

2. **Restart bot:**
   ```bash
   curl -X POST http://localhost:8000/mm-bot/restart
   ```

3. **Monitor logs:**
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 tail -f /app/polymarket_mm_deliver/logs/mm_main.log | grep -E "(ENTRY|success|error)"
   ```

## Why You Lost Money

If the bot placed orders that got filled, you may have:
- Bought positions at prices that moved against you
- Paid trading fees
- Had positions that need to be closed

**Check your positions:**
- Go to Polymarket.com → Portfolio
- See your current positions
- Close positions manually if needed

## Prevention

- ✅ Always approve USDC before starting bot
- ✅ Start with small position sizes
- ✅ Monitor bot activity closely
- ✅ Set stop-losses in config

