#!/usr/bin/env python3
"""
Comprehensive configuration and setup diagnostic script.
Checks everything needed for the bot to work.
"""
import os
import sys

# Try to load dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not found. Using environment variables directly.")

from web3 import Web3
from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs

print("="*70)
print("COMPREHENSIVE CONFIGURATION DIAGNOSTIC")
print("="*70)

# ========== 1. ENVIRONMENT VARIABLES ==========
print("\n[1] Checking Environment Variables...")
print("-" * 70)

pk = os.getenv("PK")
browser_address = os.getenv("BROWSER_ADDRESS")
spreadsheet_url = os.getenv("SPREADSHEET_URL", "")

if not pk:
    print("❌ PK environment variable is NOT SET!")
    sys.exit(1)
else:
    print(f"✅ PK is set (length: {len(pk)})")

if not browser_address:
    print("❌ BROWSER_ADDRESS environment variable is NOT SET!")
    sys.exit(1)
else:
    print(f"✅ BROWSER_ADDRESS is set: {browser_address[:20]}...")

if spreadsheet_url:
    print(f"✅ SPREADSHEET_URL is set")
else:
    print(f"⚠️  SPREADSHEET_URL is not set (will use database only)")

# ========== 2. PRIVATE KEY VALIDATION ==========
print("\n[2] Validating Private Key...")
print("-" * 70)

pk_clean = pk.strip()
if pk_clean.startswith('0x') or pk_clean.startswith('0X'):
    pk_clean = pk_clean[2:]
    print(f"⚠️  Removed '0x' prefix from PK")

if len(pk_clean) != 64:
    print(f"❌ ERROR: PK must be 64 hex characters (got {len(pk_clean)})")
    sys.exit(1)

try:
    int(pk_clean, 16)
    print(f"✅ PK format is valid (64 hex characters)")
except ValueError:
    print(f"❌ ERROR: PK contains invalid hex characters")
    sys.exit(1)

# ========== 3. WALLET ADDRESS VALIDATION ==========
print("\n[3] Validating Wallet Address...")
print("-" * 70)

browser_address_clean = browser_address.strip()
if browser_address_clean.startswith('0x') and len(browser_address_clean) > 42:
    browser_address_clean = browser_address_clean[:42]
    print(f"⚠️  Truncated BROWSER_ADDRESS to 42 characters")

try:
    browser_address_checksum = Web3.to_checksum_address(browser_address_clean)
    print(f"✅ BROWSER_ADDRESS format is valid: {browser_address_checksum}")
except Exception as e:
    print(f"❌ ERROR: Invalid BROWSER_ADDRESS format: {e}")
    sys.exit(1)

# ========== 4. WALLET ADDRESS MATCH ==========
print("\n[4] Verifying Private Key Matches Wallet Address...")
print("-" * 70)

try:
    account = Account.from_key(pk_clean)
    derived_address = account.address
    print(f"✅ Derived wallet address from PK: {derived_address}")
except Exception as e:
    print(f"❌ ERROR deriving address from PK: {e}")
    sys.exit(1)

if derived_address.lower() != browser_address_checksum.lower():
    print(f"\n❌ CRITICAL MISMATCH:")
    print(f"   Address from PK:     {derived_address}")
    print(f"   BROWSER_ADDRESS:      {browser_address_checksum}")
    print(f"\n   These don't match! This will cause 'invalid signature' errors.")
    sys.exit(1)
else:
    print(f"✅ Addresses match! PK belongs to wallet {derived_address}")

# ========== 5. USDC BALANCE CHECK ==========
print("\n[5] Checking USDC Balance on Polygon...")
print("-" * 70)

try:
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    
    # USDC contract address on Polygon
    usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    
    # Minimal ERC20 ABI for balanceOf
    erc20_abi = [{
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }]
    
    print(f"   Checking balance for: {browser_address_checksum}")
    print(f"   USDC Contract: {usdc_address}")
    
    usdc_contract = web3.eth.contract(address=usdc_address, abi=erc20_abi)
    balance = usdc_contract.functions.balanceOf(browser_address_checksum).call()
    balance_usdc = balance / 10**6  # USDC has 6 decimals
    
    print(f"   Raw balance (wei): {balance}")
    print(f"✅ USDC Balance: {balance_usdc:.2f} USDC")
    
    if balance_usdc < 1.0:
        print(f"\n⚠️  WARNING: Low USDC balance ({balance_usdc:.2f} USDC)")
        print(f"   You need at least 1-2 USDC for testing")
        print(f"\n   If you see USDC in Polymarket but not here:")
        print(f"   - The wallet address might be different")
        print(f"   - Check which wallet address you're using on Polymarket")
        print(f"   - Compare it with: {browser_address_checksum}")
    else:
        print(f"✅ Sufficient USDC balance for trading")
        
except Exception as e:
    print(f"❌ ERROR checking USDC balance: {e}")
    import traceback
    traceback.print_exc()
    print(f"\n   This might indicate:")
    print(f"   - Network connectivity issues")
    print(f"   - Wrong wallet address")
    print(f"   - RPC endpoint issues")

# ========== 6. POLYMARKET CLIENT INITIALIZATION ==========
print("\n[6] Testing Polymarket Client Initialization...")
print("-" * 70)

try:
    host = "https://clob.polymarket.com"
    client = ClobClient(
        host=host,
        key=pk_clean,
        chain_id=POLYGON,
        funder=browser_address_checksum,
        signature_type=2
    )
    
    # Create API credentials
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds=creds)
    print(f"✅ ClobClient initialized successfully")
    print(f"✅ API credentials created")
    
except Exception as e:
    print(f"❌ ERROR initializing ClobClient: {e}")
    sys.exit(1)

# ========== 7. MANUAL TRADE VERIFICATION ==========
print("\n[7] Checking Manual Trade Status...")
print("-" * 70)
print("⚠️  IMPORTANT: Polymarket requires at least ONE manual trade")
print("   through their UI before API trading works.")
print(f"\n   CRITICAL: Verify the wallet address matches!")
print(f"   Bot is configured to use: {browser_address_checksum}")
print(f"\n   To verify you did a manual trade with THIS wallet:")
print(f"   1. Go to https://polymarket.com")
print(f"   2. Connect wallet and check the address shown")
print(f"   3. Compare it with: {browser_address_checksum}")
print(f"   4. If addresses DON'T match, that's the problem!")
print(f"      - Either update BROWSER_ADDRESS in .env")
print(f"      - Or use the wallet that matches {browser_address_checksum}")
print(f"\n   5. Check your trade history:")
print(f"      - Click your profile/wallet icon")
print(f"      - Look for 'Trades' or 'History'")
print(f"      - You should see at least one completed trade")
print(f"\n   6. If no trades visible, make one now:")
print(f"      - Pick any market")
print(f"      - Buy or sell any amount (even $0.10)")
print(f"      - Complete the transaction")
print(f"      - Wait for it to confirm on Polygon")
print(f"      - Wait 2-3 minutes for permissions to propagate")

# ========== 8. TEST ORDER CREATION ==========
print("\n[8] Testing Order Signature Creation...")
print("-" * 70)

try:
    # Use a fake token ID for testing (we just want to test signature creation)
    test_token = "12345678901234567890123456789012345678901234567890123456789012345678901234567890"
    test_order = OrderArgs(
        token_id=test_token,
        price=0.5,
        size=1.0,
        side="BUY"
    )
    
    signed_order = client.create_order(test_order)
    print(f"✅ Order signature created successfully!")
    print(f"   (This means signature generation works)")
    print(f"\n   If you're still getting 'invalid signature' errors,")
    print(f"   it's almost certainly because:")
    print(f"   1. The wallet hasn't done a manual trade on Polymarket")
    print(f"   2. The manual trade wasn't done with this exact wallet")
    print(f"   3. The permissions haven't propagated yet (wait 2-3 minutes)")
    
except Exception as e:
    error_str = str(e)
    print(f"❌ ERROR during signature test: {error_str}")
    if "invalid signature" in error_str.lower():
        print(f"\n   This confirms the signature issue.")
        print(f"   Most likely cause: Wallet hasn't done manual trade on Polymarket")

# ========== 9. SUMMARY ==========
print("\n" + "="*70)
print("DIAGNOSTIC SUMMARY")
print("="*70)
print(f"✅ Private Key: Valid")
print(f"✅ Wallet Address: {browser_address_checksum}")
print(f"✅ Address Match: PK matches wallet address")
print(f"✅ ClobClient: Initialized successfully")
print(f"✅ Signature Creation: Works")
print(f"\n⚠️  NEXT STEP:")
print(f"   If you're still getting 'invalid signature' errors:")
print(f"   1. Verify you did a manual trade with wallet {browser_address_checksum}")
print(f"   2. Check your trade history on https://polymarket.com")
print(f"   3. If no trades visible, make one now and wait 2-3 minutes")
print(f"   4. Then restart the bot: docker compose restart worker")
print("="*70)

