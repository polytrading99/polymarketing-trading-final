"""
Diagnostic script to check:
1. Funder address (BROWSER_ADDRESS) correctness
2. NegRisk flag detection and usage

According to Polymarket docs, "invalid signature" can be caused by:
- Incorrect Funder and or Private Key
- Incorrect NegRisk flag in your order arguments
"""

import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions, OrderType
from py_clob_client.constants import POLYGON
from web3 import Web3


def main():
    print("=" * 70)
    print("DIAGNOSE FUNDER & NEGRISK ISSUES")
    print("=" * 70)
    
    # 1. Check environment variables
    print("\n1. CHECKING ENVIRONMENT VARIABLES")
    print("-" * 70)
    
    pk = os.getenv("PK")
    browser_address = os.getenv("BROWSER_ADDRESS")
    
    if not pk:
        print("❌ PK (Private Key) not found in environment")
        return
    else:
        print(f"✅ PK found: {pk[:10]}...{pk[-10:]}")
    
    if not browser_address:
        print("❌ BROWSER_ADDRESS not found in environment")
        return
    else:
        print(f"✅ BROWSER_ADDRESS found: {browser_address}")
    
    # Clean and checksum the address
    browser_address = browser_address.strip()
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    
    try:
        browser_address = Web3.to_checksum_address(browser_address)
        print(f"✅ Checksummed address: {browser_address}")
    except Exception as e:
        print(f"❌ Invalid address format: {e}")
        return
    
    # 2. Initialize client and check funder
    print(f"\n2. INITIALIZING CLOB CLIENT")
    print("-" * 70)
    
    try:
        # Clean PK (remove 0x if present)
        key = pk
        if key.startswith('0x') or key.startswith('0X'):
            key = key[2:]
        
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=key,
            chain_id=POLYGON,
            funder=browser_address,  # This is the POLYMARKET_PROXY_ADDRESS
            signature_type=2  # 2 for Browser Wallet
        )
        
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)
        
        print(f"✅ Client initialized")
        print(f"   Funder (POLYMARKET_PROXY_ADDRESS): {browser_address}")
        print(f"   Signature Type: 2 (Browser Wallet)")
        print(f"\n   ⚠️  IMPORTANT: The funder address MUST be the address")
        print(f"      shown BELOW your profile picture on Polymarket.com")
        print(f"      If this doesn't match, orders will fail with 'invalid signature'")
        
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 3. Fetch a market and check negrisk detection
    print(f"\n3. CHECKING NEGRISK DETECTION")
    print("-" * 70)
    
    try:
        markets = client.get_sampling_markets()
        
        if not markets or 'data' not in markets or len(markets['data']) == 0:
            print("❌ No markets found")
            return
        
        # Check first 5 markets
        print(f"Checking first 5 markets for negrisk detection:\n")
        
        for i, market in enumerate(markets['data'][:5]):
            question = market.get('question', 'Unknown')
            tokens = market.get('tokens', [])
            rewards = market.get('rewards', {})
            
            # Method 1: Check rewards field (current method)
            has_min_size = bool(rewards.get('min_size'))
            has_max_spread = bool(rewards.get('max_spread'))
            is_negrisk_method1 = has_min_size or has_max_spread
            
            # Method 2: Check if rewards object exists and has any keys
            is_negrisk_method2 = bool(rewards and len(rewards) > 0)
            
            print(f"Market {i+1}: {question[:60]}...")
            print(f"   Rewards object: {rewards}")
            print(f"   Method 1 (min_size or max_spread): {is_negrisk_method1}")
            print(f"   Method 2 (rewards exists): {is_negrisk_method2}")
            
            if tokens:
                token_yes = tokens[0].get('token_id')
                print(f"   Token YES: {token_yes}")
                print(f"   → Should use neg_risk={is_negrisk_method1} when placing orders")
            print()
        
    except Exception as e:
        print(f"❌ Failed to check markets: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. Test order creation with correct vs incorrect negrisk flag
    print(f"\n4. TESTING ORDER CREATION")
    print("-" * 70)
    
    try:
        # Get first market
        market = markets['data'][0]
        tokens = market.get('tokens', [])
        if not tokens:
            print("❌ No tokens in market")
            return
        
        token_yes = tokens[0].get('token_id')
        rewards = market.get('rewards', {})
        is_negrisk = bool(rewards.get('min_size') or rewards.get('max_spread'))
        
        print(f"Market: {market.get('question', 'Unknown')[:60]}...")
        print(f"Token: {token_yes}")
        print(f"Detected as negrisk: {is_negrisk}")
        print(f"\nCreating test order with neg_risk={is_negrisk}...")
        
        order_args = OrderArgs(
            token_id=str(token_yes),
            price=0.5,
            size=1.0,
            side="BUY"
        )
        
        if is_negrisk:
            signed_order = client.create_order(
                order_args,
                options=PartialCreateOrderOptions(neg_risk=True)
            )
            print(f"✅ Order created with neg_risk=True")
        else:
            signed_order = client.create_order(order_args)
            print(f"✅ Order created with neg_risk=False (default)")
        
        # Try to post
        print(f"\nAttempting to post order...")
        try:
            resp = client.post_order(signed_order, OrderType.GTC)
            print(f"✅✅✅ SUCCESS! Order posted!")
            print(f"Response: {resp}")
        except Exception as e:
            error_str = str(e)
            print(f"❌ Failed to post order: {error_str}")
            
            if "invalid signature" in error_str.lower():
                print(f"\n{'='*70}")
                print("INVALID SIGNATURE - POSSIBLE CAUSES:")
                print("="*70)
                print(f"1. FUNDER ADDRESS MISMATCH:")
                print(f"   Current funder: {browser_address}")
                print(f"   → Go to https://polymarket.com")
                print(f"   → Check the address BELOW your profile picture")
                print(f"   → It MUST match: {browser_address}")
                print(f"   → If different, update BROWSER_ADDRESS in .env")
                print()
                print(f"2. NEGRISK FLAG INCORRECT:")
                print(f"   Market detected as negrisk: {is_negrisk}")
                print(f"   → If market IS negrisk but we used neg_risk=False, that's wrong")
                print(f"   → If market is NOT negrisk but we used neg_risk=True, that's wrong")
                print()
                print(f"3. PRIVATE KEY MISMATCH:")
                print(f"   → PK must be the private key for the funder address")
                print(f"   → Export from your wallet or https://reveal.magic.link/polymarket")
                print()
                print(f"4. MISSING CONTRACT APPROVALS:")
                print(f"   → Run: python -m app.scripts.check_contract_approvals")
                print(f"   → Or make a manual trade on Polymarket.com")
        
    except Exception as e:
        print(f"❌ Failed to create test order: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'='*70}")
    print("SUMMARY")
    print("="*70)
    print(f"✅ Funder address: {browser_address}")
    print(f"   → Verify this matches the address below your profile on Polymarket.com")
    print(f"✅ Client initialized with signature_type=2 (Browser Wallet)")
    print(f"✅ Checked negrisk detection logic")
    print(f"\nIf orders still fail with 'invalid signature':")
    print(f"1. Verify funder address matches Polymarket profile")
    print(f"2. Verify PK is correct for that address")
    print(f"3. Check negrisk flag is correct for each market")
    print(f"4. Ensure contract approvals are set (make manual trade)")


if __name__ == "__main__":
    main()

