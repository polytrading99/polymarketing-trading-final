"""
Test placing an order on a REGULAR (non-neg-risk) market to see if the issue
is specific to neg risk markets (there's a known GitHub issue #79 about this).
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs, OrderType

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()


def main():
    print("=" * 70)
    print("TEST REGULAR (NON-NEG-RISK) MARKET")
    print("=" * 70)
    print("\nThis tests if the 'invalid signature' issue is specific to neg-risk markets.")
    print("There's a known GitHub issue #79 about neg-risk markets causing this error.\n")
    
    pk = os.getenv("PK", "").strip()
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    
    if pk.startswith('0x') or pk.startswith('0X'):
        pk = pk[2:]
    
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    
    proxy_address = Web3.to_checksum_address(browser_address)
    
    try:
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=POLYGON,
            funder=proxy_address,
            signature_type=2
        )
        
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)
        
        print("Fetching markets...")
        markets = client.get_sampling_markets()
        
        # Find a REGULAR (non-neg-risk) market
        print("\nSearching for a REGULAR market (not neg-risk)...")
        regular_market = None
        
        for market in markets.get('data', [])[:50]:  # Check first 50 markets
            rewards = market.get('rewards', {})
            is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
            
            if not is_neg_risk:
                regular_market = market
                break
        
        if not regular_market:
            print("❌ No regular markets found in first 50 markets")
            print("   All markets appear to be neg-risk")
            return
        
        question = regular_market.get('question', 'Unknown')
        tokens = regular_market.get('tokens', [])
        
        if not tokens:
            print("❌ Market has no tokens")
            return
        
        token_yes = tokens[0].get('token_id')
        rewards = regular_market.get('rewards', {})
        is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
        
        print(f"✅ Found regular market:")
        print(f"   Question: {question[:60]}...")
        print(f"   Token: {token_yes}")
        print(f"   Neg Risk: {is_neg_risk}")
        print(f"   Min Size: {rewards.get('min_size', 'N/A')}")
        
        # Create order for REGULAR market (no neg_risk flag)
        print(f"\n{'='*70}")
        print("CREATING ORDER FOR REGULAR MARKET")
        print("="*70)
        
        order_args = OrderArgs(
            token_id=str(token_yes),
            price=0.5,
            size=5.0,  # Use 5 USDC (standard minimum)
            side="BUY"
        )
        
        # IMPORTANT: No neg_risk flag for regular market
        print("Creating order WITHOUT neg_risk flag...")
        signed_order = client.create_order(order_args)
        
        # Verify order values
        if hasattr(signed_order, 'order') and hasattr(signed_order.order, 'values'):
            values = signed_order.order.values
            print(f"\nOrder values:")
            print(f"   Maker: {values.get('maker')}")
            print(f"   Signer: {values.get('signer')}")
            print(f"   Signature Type: {values.get('signatureType')}")
        
        # Try to post
        print(f"\n{'='*70}")
        print("POSTING ORDER TO API")
        print("="*70)
        
        try:
            resp = client.post_order(signed_order, OrderType.GTC)
            print(f"✅✅✅ SUCCESS! Order posted on REGULAR market!")
            print(f"Response: {resp}")
            print(f"\n🎉 This confirms the issue is with NEG-RISK markets!")
            print(f"   There's a known bug in py-clob-client for neg-risk markets.")
            print(f"   See: https://github.com/Polymarket/py-clob-client/issues/79")
        except Exception as e:
            error_str = str(e)
            print(f"❌ Failed: {error_str}")
            
            if "invalid signature" in error_str.lower():
                print(f"\n{'='*70}")
                print("ANALYSIS")
                print("="*70)
                print(f"Even REGULAR markets fail with 'invalid signature'")
                print(f"This means the issue is NOT specific to neg-risk markets.")
                print(f"\nThe problem is more fundamental:")
                print(f"  1. Signature generation issue")
                print(f"  2. API validation issue")
                print(f"  3. Account activation issue")
            else:
                print(f"Different error - might be progress!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

