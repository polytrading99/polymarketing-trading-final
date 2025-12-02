"""
Diagnostic script to check why orders are failing with "invalid signature".

This script verifies:
1. PK matches the wallet address
2. Wallet has done trades on Polymarket
3. API credentials are valid
"""

import os
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
import requests

load_dotenv()


def main():
    print("=" * 60)
    print("SIGNATURE DIAGNOSTICS")
    print("=" * 60)
    
    # 1. Check PK and derive wallet address
    pk = os.getenv("PK", "").strip()
    if pk.startswith("0x") or pk.startswith("0X"):
        pk = pk[2:]
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    
    if not pk:
        print("❌ ERROR: PK not set in .env")
        return
    
    if not browser_address:
        print("❌ ERROR: BROWSER_ADDRESS not set in .env")
        return
    
    print(f"\n1. Checking PK format...")
    print(f"   PK length: {len(pk)} (should be 64)")
    print(f"   PK is hex: {all(c in '0123456789abcdefABCDEF' for c in pk)}")
    
    if len(pk) != 64:
        print(f"   ❌ PK length is wrong! Expected 64, got {len(pk)}")
        return
    
    # Derive wallet address from PK
    try:
        account = Account.from_key(pk)
        derived_address = account.address
        print(f"   ✅ PK is valid")
        print(f"   Derived wallet from PK: {derived_address}")
    except Exception as e:
        print(f"   ❌ Failed to derive wallet from PK: {e}")
        return
    
    # 2. Check if BROWSER_ADDRESS matches derived address
    browser_address_checksum = Web3.to_checksum_address(browser_address)
    print(f"\n2. Checking BROWSER_ADDRESS...")
    print(f"   BROWSER_ADDRESS from .env: {browser_address}")
    print(f"   BROWSER_ADDRESS (checksum): {browser_address_checksum}")
    print(f"   Derived from PK: {derived_address}")
    
    if browser_address_checksum.lower() != derived_address.lower():
        print(f"   ❌ MISMATCH! BROWSER_ADDRESS doesn't match PK!")
        print(f"   This is likely the problem!")
        print(f"   Fix: Set BROWSER_ADDRESS={derived_address} in .env")
        return
    else:
        print(f"   ✅ BROWSER_ADDRESS matches PK")
    
    # 3. Check if wallet has done trades on Polymarket
    print(f"\n3. Checking if wallet has trades on Polymarket...")
    wallet = browser_address_checksum
    
    try:
        # Check trades via Polymarket API
        trades_url = f"https://data-api.polymarket.com/trades?user={wallet}&limit=10"
        response = requests.get(trades_url, timeout=10)
        
        if response.status_code == 200:
            trades = response.json()
            if isinstance(trades, list) and len(trades) > 0:
                print(f"   ✅ Wallet has {len(trades)} recent trades on Polymarket")
                print(f"   Latest trade: {trades[0]}")
            else:
                print(f"   ⚠️  Wallet has NO trades on Polymarket")
                print(f"   This could be the issue - you need at least ONE manual trade")
        else:
            print(f"   ⚠️  Could not check trades (API returned {response.status_code})")
    except Exception as e:
        print(f"   ⚠️  Could not check trades: {e}")
    
    # 4. Check wallet balance
    print(f"\n4. Checking wallet balance...")
    try:
        web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        balance_wei = web3.eth.get_balance(wallet)
        balance_eth = balance_wei / 10**18
        print(f"   MATIC balance: {balance_eth:.4f} MATIC")
        
        # Check USDC balance
        usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        from poly_data.abis import erc20_abi
        usdc_contract = web3.eth.contract(address=usdc_address, abi=erc20_abi)
        usdc_balance = usdc_contract.functions.balanceOf(wallet).call() / 10**6
        print(f"   USDC balance: {usdc_balance:.2f} USDC")
    except Exception as e:
        print(f"   ⚠️  Could not check balance: {e}")
    
    # 5. Test API credentials
    print(f"\n5. Testing Polymarket API client initialization...")
    try:
        from poly_data.polymarket_client import PolymarketClient
        client = PolymarketClient()
        print(f"   ✅ PolymarketClient initialized successfully")
        print(f"   Wallet: {client.browser_wallet}")
        print(f"   API Key: {client.creds.api_key[:20]}...")
        
        # Try to get orders (this tests API auth)
        try:
            orders = client.get_all_orders()
            print(f"   ✅ API credentials work - can fetch orders")
            print(f"   Current open orders: {len(orders)}")
        except Exception as e:
            print(f"   ⚠️  Could not fetch orders: {e}")
    except Exception as e:
        print(f"   ❌ Failed to initialize PolymarketClient: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("DIAGNOSTICS COMPLETE")
    print("=" * 60)
    print("\nIf BROWSER_ADDRESS doesn't match PK, that's the problem!")
    print("If wallet has no trades, you need to do ONE manual trade first.")
    print("If everything looks correct but still fails, try:")
    print("  1. Regenerating API credentials (delete and recreate)")
    print("  2. Making another small manual trade")
    print("  3. Checking if the trade was on the correct wallet address")


if __name__ == "__main__":
    main()

