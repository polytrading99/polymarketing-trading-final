"""
Detailed signature debugging - inspect the actual signed order structure.
"""

import os
from dotenv import load_dotenv
from poly_data.polymarket_client import PolymarketClient
from data_updater.trading_utils import get_clob_client
from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions
import json

load_dotenv()


def inspect_signed_order(signed_order):
    """Inspect a signed order object to see its structure."""
    print(f"\n   Signed Order Details:")
    print(f"   Type: {type(signed_order)}")
    
    # Try to get all attributes
    if hasattr(signed_order, '__dict__'):
        print(f"   Attributes: {list(signed_order.__dict__.keys())}")
        for key, value in signed_order.__dict__.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                if isinstance(value, str) and len(value) > 50:
                    print(f"      {key}: {value[:50]}...")
                else:
                    print(f"      {key}: {value}")
    
    # Try common attributes
    for attr in ['hash', 'signature', 'maker', 'tokenId', 'price', 'size', 'side']:
        if hasattr(signed_order, attr):
            value = getattr(signed_order, attr)
            if isinstance(value, str) and len(value) > 50:
                print(f"   {attr}: {value[:50]}...")
            else:
                print(f"   {attr}: {value}")


def main():
    print("=" * 60)
    print("DETAILED SIGNATURE DEBUGGING")
    print("=" * 60)
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    print(f"\nWallet: {browser_address}\n")
    
    # Initialize client
    try:
        client = PolymarketClient()
        print(f"✅ PolymarketClient initialized")
        print(f"   Wallet: {client.browser_wallet}")
        print(f"   ClobClient funder: {client.client.funder if hasattr(client.client, 'funder') else 'N/A'}")
        print(f"   ClobClient signature_type: {client.client.signature_type if hasattr(client.client, 'signature_type') else 'N/A'}")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return
    
    # Get a test market
    clob_client = get_clob_client()
    if not clob_client:
        print(f"❌ Could not get CLOB client")
        return
    
    try:
        markets = clob_client.get_sampling_markets()
        if not markets or 'data' not in markets or len(markets['data']) == 0:
            print(f"❌ No markets found")
            return
        
        market = markets['data'][0]
        tokens = market.get('tokens', [])
        if not tokens:
            print(f"❌ Market has no tokens")
            return
        
        token_yes = tokens[0].get('token_id')
        rewards = market.get('rewards', {})
        is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
        
        print(f"\nTest Market:")
        print(f"   Question: {market.get('question', 'Unknown')}")
        print(f"   Token: {token_yes}")
        print(f"   Neg Risk: {is_neg_risk}")
        
        # Test 1: Create order via PolymarketClient
        print(f"\n{'='*60}")
        print("TEST 1: Create order via PolymarketClient.create_order()")
        print("=" * 60)
        
        order_args = OrderArgs(
            token_id=str(token_yes),
            price=0.5,
            size=1.0,
            side="BUY"
        )
        
        if is_neg_risk:
            signed_order = client.client.create_order(
                order_args,
                options=PartialCreateOrderOptions(neg_risk=True)
            )
        else:
            signed_order = client.client.create_order(order_args)
        
        inspect_signed_order(signed_order)
        
        print(f"\n   Attempting to post order...")
        try:
            resp = client.client.post_order(signed_order)
            print(f"   ✅✅✅ SUCCESS! Order posted!")
            print(f"   Response: {resp}")
            return
        except Exception as e:
            error_str = str(e)
            print(f"   ❌ Failed: {error_str}")
            
            # Try to get more details from the error
            if hasattr(e, 'response') or hasattr(e, 'status_code'):
                print(f"   Error details: {e}")
        
        # Test 2: Try with different price/size
        print(f"\n{'='*60}")
        print("TEST 2: Try with market price from order book")
        print("=" * 60)
        
        try:
            bids_df, asks_df = client.get_order_book(token_yes)
            if len(bids_df) > 0 and len(asks_df) > 0:
                best_bid = float(bids_df.iloc[-1]['price'])
                best_ask = float(asks_df.iloc[-1]['price'])
                mid_price = (best_bid + best_ask) / 2
                test_price = round(best_bid + 0.01, 4)
                if test_price > 0.99:
                    test_price = 0.99
                print(f"   Using price: {test_price} (best_bid={best_bid}, best_ask={best_ask})")
            else:
                test_price = 0.5
                print(f"   Empty order book, using price: {test_price}")
        except:
            test_price = 0.5
            print(f"   Using default price: {test_price}")
        
        order_args2 = OrderArgs(
            token_id=str(token_yes),
            price=test_price,
            size=1.0,
            side="BUY"
        )
        
        if is_neg_risk:
            signed_order2 = client.client.create_order(
                order_args2,
                options=PartialCreateOrderOptions(neg_risk=True)
            )
        else:
            signed_order2 = client.client.create_order(order_args2)
        
        print(f"\n   Attempting to post order with market price...")
        try:
            resp = client.client.post_order(signed_order2)
            print(f"   ✅✅✅ SUCCESS! Order posted!")
            print(f"   Response: {resp}")
            return
        except Exception as e:
            error_str = str(e)
            print(f"   ❌ Failed: {error_str}")
        
        print(f"\n{'='*60}")
        print("DIAGNOSIS")
        print("=" * 60)
        print("\nBoth tests failed with 'invalid signature'.")
        print("\nPossible causes:")
        print("1. Wallet needs to do a trade specifically through Polymarket's CLOB API")
        print("   (Manual trades through web interface don't count)")
        print("2. There's a bug in py_clob_client library")
        print("3. Polymarket requires additional wallet setup for API orders")
        print("\nNext steps:")
        print("1. Contact Polymarket support about API order requirements")
        print("2. Check py_clob_client GitHub for known issues")
        print("3. Try using Polymarket's official API documentation")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

