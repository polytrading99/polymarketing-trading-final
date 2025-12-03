"""
Comprehensive diagnostic to find why "invalid signature" errors occur.
Checks PK, funder address, wallet match, and trade history.
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()


def main():
    print("=" * 70)
    print("COMPREHENSIVE SIGNATURE DIAGNOSTIC")
    print("=" * 70)
    
    # 1. Check environment variables
    print("\n1. CHECKING ENVIRONMENT VARIABLES")
    print("-" * 70)
    
    pk = os.getenv("PK")
    browser_address = os.getenv("BROWSER_ADDRESS")
    
    if not pk:
        print("❌ PK not found")
        return
    
    if not browser_address:
        print("❌ BROWSER_ADDRESS not found")
        return
    
    # Clean PK
    key = pk.strip()
    if key.startswith('0x') or key.startswith('0X'):
        key = key[2:]
    
    # Clean browser address
    browser_address = browser_address.strip()
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    
    print(f"✅ PK found: {key[:10]}...{key[-10:]}")
    print(f"✅ BROWSER_ADDRESS found: {browser_address}")
    
    # 2. Verify PK matches funder address
    print(f"\n2. VERIFYING PK MATCHES FUNDER ADDRESS")
    print("-" * 70)
    
    try:
        web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        wallet = web3.eth.account.from_key(key)
        metamask_address = wallet.address
        proxy_address = Web3.to_checksum_address(browser_address)
        
        print(f"MetaMask Address (from PK): {metamask_address}")
        print(f"Proxy Address (BROWSER_ADDRESS): {proxy_address}")
        
        if metamask_address.lower() == proxy_address.lower():
            print("⚠️  WARNING: PK address matches proxy address!")
            print("   This is unusual - proxy should be different from MetaMask address")
            print("   Make sure BROWSER_ADDRESS is the address BELOW your profile on Polymarket")
        else:
            print("✅ Addresses are different (this is normal for proxy setup)")
            print("   MetaMask wallet controls the proxy")
        
    except Exception as e:
        print(f"❌ Error verifying addresses: {e}")
        return
    
    # 3. Check client initialization
    print(f"\n3. CHECKING CLOB CLIENT INITIALIZATION")
    print("-" * 70)
    
    try:
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=key,
            chain_id=POLYGON,
            funder=proxy_address,  # Use proxy address as funder
            signature_type=2  # Browser wallet
        )
        
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)
        
        print(f"✅ Client initialized successfully")
        print(f"   Funder: {proxy_address}")
        print(f"   Signature Type: 2 (Browser Wallet)")
        
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. Check if we can fetch markets (tests API connection)
    print(f"\n4. TESTING API CONNECTION")
    print("-" * 70)
    
    try:
        markets = client.get_sampling_markets()
        if markets and 'data' in markets:
            print(f"✅ API connection works - found {len(markets['data'])} markets")
        else:
            print("⚠️  API connection works but no markets returned")
    except Exception as e:
        print(f"❌ API connection failed: {e}")
        return
    
    # 5. Check portfolio/positions (indicates if wallet has traded)
    print(f"\n5. CHECKING WALLET TRADE HISTORY")
    print("-" * 70)
    
    try:
        import requests
        # Check portfolio value
        value_resp = requests.get(f'https://data-api.polymarket.com/value?user={proxy_address}')
        value_data = value_resp.json()
        
        portfolio_value = 0
        if isinstance(value_data, dict):
            portfolio_value = float(value_data.get('value', 0))
        elif isinstance(value_data, list) and len(value_data) > 0:
            portfolio_value = float(value_data[0].get('value', 0))
        
        print(f"Portfolio Value: ${portfolio_value:.2f}")
        
        if portfolio_value > 0:
            print("✅ Wallet has portfolio value - indicates previous trading activity")
        else:
            print("⚠️  No portfolio value - wallet may not have traded yet")
        
        # Check positions
        pos_resp = requests.get(f'https://data-api.polymarket.com/positions?user={proxy_address}')
        pos_data = pos_resp.json()
        
        position_count = 0
        if isinstance(pos_data, list):
            position_count = len(pos_data)
        elif isinstance(pos_data, dict) and 'data' in pos_data:
            position_count = len(pos_data['data'])
        
        print(f"Active Positions: {position_count}")
        
        if position_count > 0:
            print("✅ Wallet has active positions - definitely has traded before")
        else:
            print("⚠️  No active positions found")
            
    except Exception as e:
        print(f"⚠️  Could not check trade history: {e}")
    
    # 6. Try to create a signed order (without posting)
    print(f"\n6. TESTING ORDER SIGNATURE GENERATION")
    print("-" * 70)
    
    try:
        from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions
        
        # Get a test market
        market = markets['data'][0]
        tokens = market.get('tokens', [])
        if not tokens:
            print("❌ No tokens in market")
            return
        
        token_yes = tokens[0].get('token_id')
        rewards = market.get('rewards', {})
        is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
        
        print(f"Test Market: {market.get('question', 'Unknown')[:50]}...")
        print(f"Token: {token_yes}")
        print(f"Neg Risk: {is_neg_risk}")
        
        # Create order args
        order_args = OrderArgs(
            token_id=str(token_yes),
            price=0.5,
            size=5.0,
            side="BUY"
        )
        
        # Try to sign the order
        if is_neg_risk:
            signed_order = client.create_order(
                order_args,
                options=PartialCreateOrderOptions(neg_risk=True)
            )
        else:
            signed_order = client.create_order(order_args)
        
        print("✅ Order signed successfully")
        print(f"   Order type: {type(signed_order)}")
        
        # Inspect the signed order
        if hasattr(signed_order, 'order'):
            order = signed_order.order
            if hasattr(order, 'maker'):
                print(f"   Maker (funder): {order.maker}")
                if order.maker.lower() != proxy_address.lower():
                    print(f"   ⚠️  WARNING: Order maker ({order.maker}) doesn't match funder ({proxy_address})!")
                    print(f"      This could cause 'invalid signature' errors")
                else:
                    print(f"   ✅ Order maker matches funder address")
        
    except Exception as e:
        print(f"❌ Failed to create signed order: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 7. Summary and recommendations
    print(f"\n{'='*70}")
    print("DIAGNOSTIC SUMMARY")
    print("="*70)
    
    print(f"\n✅ Configuration:")
    print(f"   MetaMask: {metamask_address}")
    print(f"   Proxy (Funder): {proxy_address}")
    print(f"   Signature Type: 2 (Browser Wallet)")
    
    if portfolio_value == 0 and position_count == 0:
        print(f"\n🔴 CRITICAL ISSUE:")
        print(f"   This proxy address ({proxy_address}) has NO trading history!")
        print(f"   Polymarket requires at least ONE manual trade before API orders work.")
        print(f"\n   SOLUTION:")
        print(f"   1. Go to https://polymarket.com")
        print(f"   2. Connect MetaMask wallet: {metamask_address}")
        print(f"   3. Verify the address below your profile is: {proxy_address}")
        print(f"   4. Make ONE small manual trade (buy or sell any market)")
        print(f"   5. Wait for transaction to confirm")
        print(f"   6. Wait 2-3 minutes")
        print(f"   7. Try again")
    else:
        print(f"\n⚠️  Wallet has trading history but still getting 'invalid signature'")
        print(f"   Possible causes:")
        print(f"   1. Manual trade was done with a DIFFERENT wallet/proxy")
        print(f"   2. Signature generation issue (funder mismatch)")
        print(f"   3. PK doesn't match the wallet that controls this proxy")
        print(f"\n   Try:")
        print(f"   1. Make a NEW manual trade with THIS specific proxy")
        print(f"   2. Verify PK is for the MetaMask wallet that controls this proxy")
        print(f"   3. Check that BROWSER_ADDRESS matches address below profile on Polymarket")


if __name__ == "__main__":
    main()

