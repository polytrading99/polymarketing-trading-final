# Setting Up BROWSER_ADDRESS in .env

## ⚠️ IMPORTANT: Which Address to Use?

When you connect MetaMask to Polymarket, Polymarket creates a **proxy contract address** that acts as an intermediary. This proxy address is what you see **below your profile picture** on Polymarket.com.

### ✅ CORRECT: Use the Polymarket Proxy Address

**Set `BROWSER_ADDRESS` to the address shown below your profile picture on Polymarket.com**

Example:
```
BROWSER_ADDRESS=0x33649e7D995D1640D4b5F92A556f7a0fd022AC94
```

This is the **Polymarket Proxy Address** that:
- Holds your funds on Polymarket
- Is controlled by your MetaMask wallet
- Is what Polymarket's API expects for the `funder` parameter

### ❌ WRONG: Don't Use Your MetaMask Address

**Do NOT use your MetaMask wallet address** (the one you see in MetaMask itself)

The MetaMask address is different from the Polymarket proxy address.

## How to Find Your Polymarket Proxy Address

1. Go to https://polymarket.com
2. Log in with your MetaMask wallet
3. Click on your profile picture (top right)
4. Look at the address shown **below your profile picture**
5. Copy that address - this is your `BROWSER_ADDRESS`

## Private Key (PK)

The `PK` in your `.env` should still be the **private key of your MetaMask wallet** (the one that controls the proxy).

## Summary

- **BROWSER_ADDRESS**: Use the address below your profile picture on Polymarket.com (proxy address)
- **PK**: Use your MetaMask wallet's private key (which controls the proxy)

## Example .env Configuration

```bash
# Your MetaMask private key (no 0x prefix)
PK=244410728b282d6303bf68854df3d2bb461edcb0b2650c60f3135d08b368daaf

# The Polymarket proxy address (below your profile picture)
BROWSER_ADDRESS=0x33649e7D995D1640D4b5F92A556f7a0fd022AC94
```

## Why This Matters

If you use the wrong address (your MetaMask address instead of the proxy address), you'll get **"invalid signature"** errors when trying to place orders, because:

1. Polymarket's API expects the `funder` parameter to be the proxy address
2. The signature is generated using your MetaMask private key, but it's validated against the proxy address
3. If they don't match, the signature is invalid

