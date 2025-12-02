"""
Deep dive into the order structure to see what we're sending vs what Polymarket expects.
"""

import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions
from web3 import Web3
import json

load_dotenv()


def inspect_order(signed_order):
    """Inspect all attributes of a signed order."""
    print("\n" + "="*70)
    print("ORDER STRUCTURE INSPECTION")
    print("="*70)
    
    # Get all attributes
    attrs = dir(signed_order)
    print(f"\nSignedOrder attributes: {len([a for a in attrs if not a.startswith('_')])}")
    
    # Check for common attributes
    important_attrs = ['order', 'signature', 'hash', 'expiration', 'nonce', 'maker']
    for attr in important_attrs:
        if hasattr(signed_order, attr):
            value = getattr(signed_order, attr)
            print(f"\n{attr}:")
            print(f"  Type: {type(value)}")
            if attr == 'order' and hasattr(value, '__dict__'):
                print(f"  Order attributes: {list(value.__dict__.keys())}")
                for k, v in value.__dict__.items():
                    print(f"    {k}: {v}")
            elif attr == 'signature':
                print(f"  Value: {value[:50]}... (length: {len(value)})")
            else:
                print(f"  Value: {value}")
        else:
            print(f"\n{attr}: ❌ NOT FOUND")
    
    # Try to get the order dict if possible
    if hasattr(signed_order, 'order'):
        order = signed_order.order
        print(f"\n{'='*70}")
        print("ORDER OBJECT DETAILS")
        print("="*70)
        try:
            # Try to convert to dict
            if hasattr(order, '__dict__'):
                order_dict = order.__dict__
                print(json.dumps({k: str(v) for k, v in order_dict.items()}, indent=2))
        except Exception as e:
            print(f"Could not serialize order: {e}")


def main():
    print("=" * 70)
    print("DEBUG ORDER STRUCTURE")
    print("=" * 70)
    
    # Get credentials
    key = os.getenv("PK", "").strip()
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    
    if key.startswith('0x'):
        key = key[2:]
    
    browser_address = Web3.to_checksum_address(browser_address)
    
    print(f"\nWallet: {browser_address}")
    
    # Create client
    print("\n1. Creating ClobClient...")
    try:
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=key,
            chain_id=POLYGON,
            funder=browser_address,
            signature_type=2
        )
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)
        print("   ✅ Client created")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return
    
    # Get a test market
    print("\n2. Fetching test market...")
    try:
        markets = client.get_sampling_markets()
        if not markets or 'data' not in markets or len(markets['data']) == 0:
            print("   ❌ No markets found")
            return
        
        test_market = markets['data'][0]
        tokens = test_market.get('tokens', [])
        if not tokens:
            print("   ❌ No tokens in market")
            return
        
        token_yes = tokens[0].get('token_id')
        rewards = test_market.get('rewards', {})
        is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
        
        print(f"   Market: {test_market.get('question', 'N/A')}")
        print(f"   Token: {token_yes}")
        print(f"   Neg Risk: {is_neg_risk}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Create order
    print("\n3. Creating order...")
    try:
        order_args = OrderArgs(
            token_id=str(token_yes),
            price=0.5,
            size=1.0,
            side="BUY"
        )
        
        if is_neg_risk:
            signed_order = client.create_order(
                order_args,
                options=PartialCreateOrderOptions(neg_risk=True)
            )
        else:
            signed_order = client.create_order(order_args)
        
        print("   ✅ Order created")
        
        # Inspect the order
        inspect_order(signed_order)
        
        # Try to post
        print(f"\n{'='*70}")
        print("ATTEMPTING TO POST ORDER")
        print("="*70)
        
        try:
            resp = client.post_order(signed_order)
            print(f"\n✅✅✅ SUCCESS! Order posted!")
            print(f"Response: {json.dumps(resp, indent=2)}")
        except Exception as e:
            error_str = str(e)
            print(f"\n❌ Failed to post: {error_str}")
            
            # Check if it's an invalid signature error
            if "invalid signature" in error_str.lower():
                print(f"\n{'='*70}")
                print("INVALID SIGNATURE DIAGNOSIS")
                print("="*70)
                print("\nThe order structure looks correct, but Polymarket rejects it.")
                print("\nMost likely causes:")
                print("1. ❌ Contract approvals missing (run check_contract_approvals.py)")
                print("2. ❌ Wallet not activated for API orders (need manual trade)")
                print("3. ❌ API credentials invalid (try regenerating)")
                print("\nNext steps:")
                print("1. Run: docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.check_contract_approvals")
                print("2. If contracts not approved, approve them manually or via script")
                print("3. Make a NEW trade on Polymarket.com")
                print("4. Wait 2-3 minutes and try again")
            
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

