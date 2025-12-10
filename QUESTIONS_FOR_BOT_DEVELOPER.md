# Questions for Original Bot Developer

If the "invalid signature" error persists after all fixes, please ask the original bot developer these questions:

## 1. Signature Type and Funder Address

**Question:** When using `signature_type=2` (browser wallet) with a proxy/funder address, what are the exact requirements for:
- The `PROXY_ADDRESS` / `funder` parameter - should it be checksummed?
- The `signature_type` - must it be an integer (not string)?
- The relationship between the private key and the funder address?

**Context:** We're getting `PolyApiException[status_code=400, error_message={'error': 'invalid signature'}]` when the bot tries to place orders, even though:
- The account service can successfully read balance and positions (so the credentials work for read operations)
- The config has `signature_type=2` and a valid `PROXY_ADDRESS`
- Environment variables are set correctly

## 2. API Credentials Generation

**Question:** Does `create_or_derive_api_creds()` need to be called before placing orders? Are there any special requirements or initialization steps needed?

**Context:** The bot calls:
```python
creds = self.client.create_or_derive_api_creds()
self.client.set_api_creds(creds)
```
But we're still getting signature errors.

## 3. Order Signing Process

**Question:** When placing orders via `place_limit()`, what exactly is being signed? Is it:
- The order parameters (price, size, token_id)?
- A hash of the order?
- Something else?

**Context:** The bot successfully creates the order object but fails when posting it to the API.

## 4. Known Issues with py-clob-client

**Question:** Are there any known issues with `py-clob-client==0.28.0` related to:
- Signature validation for browser wallet users?
- Proxy address handling?
- Order signing for certain market types?

**Context:** We've seen GitHub issue #79 mentioned in some contexts about neg-risk markets, but this is happening on regular markets too.

## 5. Manual Trade Requirement

**Question:** Some documentation suggests a "fresh manual trade" is needed. Is this:
- Required for the first time using the API?
- Required after changing signature_type?
- Required periodically?
- Not actually required?

**Context:** The user has done manual trades multiple times, but the error persists.

## 6. Alternative Approaches

**Question:** If signature_type=2 with funder doesn't work, what are the alternatives?
- Use signature_type=1 (email/magic link)?
- Use signature_type=None (direct EOA)?
- Use a different authentication method?

## 7. Debugging Signature Issues

**Question:** What's the best way to debug "invalid signature" errors?
- Are there specific logs or debug flags?
- Can we inspect the signed order before posting?
- Is there a way to verify the signature is correct?

## 8. Config File vs Environment Variables

**Question:** Should the bot read credentials from:
- `config.json` file (current approach)?
- Environment variables directly?
- Both (env vars override config)?

**Context:** We're updating config.json from environment variables, but maybe the bot should read env vars directly.

## 9. Working Example

**Question:** Can you provide a minimal working example of placing an order with:
- signature_type=2
- A funder/proxy address
- The exact code and config needed

This would help us verify our setup matches the expected pattern.

## 10. Version Compatibility

**Question:** What versions of:
- `py-clob-client`
- `web3`
- `eth-account`

Are known to work together correctly? Are there any version-specific issues?

---

## Current Setup

- **py-clob-client**: 0.28.0
- **Python**: 3.9.18
- **Chain**: Polygon (137)
- **Signature Type**: 2 (browser wallet)
- **Funder**: Proxy address (checksummed)
- **Private Key**: Set correctly
- **Error**: `PolyApiException[status_code=400, error_message={'error': 'invalid signature'}]`

## What Works

- ✅ Reading account balance (via Web3)
- ✅ Reading positions (via data-api)
- ✅ Bot processes start and run
- ✅ Market data is received
- ✅ Bot logic executes correctly

## What Doesn't Work

- ❌ Placing orders (invalid signature error)
- ❌ All order placement attempts fail with the same error

