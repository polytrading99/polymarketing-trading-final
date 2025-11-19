# MetaMask Wallet Setup - Step by Step

## ⚠️ CRITICAL REQUIREMENT

**Your wallet MUST have done at least ONE manual trade on Polymarket before the bot can work!**

This is a Polymarket requirement - the bot needs the permissions that are set when you do your first manual trade.

## Step 1: Get Your Private Key from MetaMask

1. **Open MetaMask extension** in your browser
2. **Click your account name** at the top (shows your account name/address)
3. **Click "Account details"** (or the three dots menu → Account details)
4. **Click "Show private key"**
5. **Enter your MetaMask password**
6. **Copy the private key** - it's a long string (64 characters, no spaces)

**Security Note**: Never share your private key! It gives full access to your wallet.

## Step 2: Get Your Wallet Address

1. In MetaMask, your **wallet address** is shown at the top
2. It starts with `0x` followed by 40 characters
3. **Copy this address**

## Step 3: Update Your .env File

```bash
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker
nano .env
```

Update these two lines:

```bash
# If your private key starts with 0x, REMOVE the 0x
PK=your_private_key_without_0x

# Your wallet address (keep the 0x)
BROWSER_ADDRESS=0xYourWalletAddressHere
```

**Example**:
- Private key from MetaMask: `0x1234567890abcdef...` → Use: `1234567890abcdef...` (remove 0x)
- Wallet address: `0xABCDEF123456...` → Use: `0xABCDEF123456...` (keep 0x)

Save and exit (Ctrl+X, then Y, then Enter)

## Step 4: Do One Manual Trade on Polymarket

**This is REQUIRED!** The bot won't work without this.

1. Go to **https://polymarket.com**
2. **Connect your MetaMask wallet** (click "Connect Wallet")
3. **Select any market** (any prediction market)
4. **Make ONE small trade**:
   - Buy or sell any amount (even $0.10 is fine)
   - Complete the transaction
   - Wait for it to confirm
5. **Done!** Now your wallet has the required permissions

## Step 5: Ensure You Have USDC on Polygon

1. **Check your MetaMask** - Make sure you're on Polygon network
2. **Add Polygon network** if needed:
   - Network Name: Polygon
   - RPC URL: https://polygon-rpc.com
   - Chain ID: 137
   - Currency Symbol: MATIC
3. **Get USDC on Polygon**:
   - You need at least $10-20 for testing
   - Bridge USDC from Ethereum to Polygon, or
   - Buy USDC directly on Polygon

## Step 6: Verify Your Setup

```bash
# Check .env file has the values
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker
grep -E "^PK=|^BROWSER_ADDRESS=" .env

# Should show:
# PK=something (without 0x)
# BROWSER_ADDRESS=0xsomething (with 0x)
```

## Step 7: Restart Worker (to load new credentials)

```bash
docker compose restart worker
```

## Step 8: Check Worker Logs

```bash
docker compose logs -f worker
```

You should see:
- "Initializing Polymarket client..."
- No authentication errors
- WebSocket connections established

If you see errors about authentication or permissions, go back to Step 4 and do the manual trade.

## Common Issues

### "Permission denied" or "Unauthorized"
→ You haven't done the manual trade yet (Step 4)

### "Invalid private key"
→ Check you removed the `0x` from private key in .env

### "Invalid address"
→ Check wallet address has `0x` prefix in .env

### "Insufficient balance"
→ Add more USDC to your wallet on Polygon

## Next Steps

Once your wallet is configured:
1. Sync markets: `docker compose exec backend uv run python app/scripts/sync_config.py`
2. Start trading: See QUICK_START.md
3. Monitor: Open http://localhost:3000

---

**Your wallet is now connected!** The bot will use your MetaMask wallet to trade on Polymarket.

