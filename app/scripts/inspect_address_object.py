"""
Deep inspection of the Address object to understand how to extract the actual address.
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()


def deep_inspect(obj, name="Object", depth=0, max_depth=3):
    """Recursively inspect an object."""
    indent = "  " * depth
    print(f"{indent}{name}:")
    print(f"{indent}  Type: {type(obj)}")
    
    if depth >= max_depth:
        return
    
    # Try common methods
    for method in ['__str__', '__repr__', 'hex', 'address', 'value']:
        if hasattr(obj, method):
            try:
                result = getattr(obj, method)
                if callable(result):
                    result = result()
                print(f"{indent}  {method}(): {result}")
            except Exception as e:
                print(f"{indent}  {method}(): ERROR - {e}")
    
    # Try __dict__
    if hasattr(obj, '__dict__'):
        print(f"{indent}  __dict__ keys: {list(obj.__dict__.keys())}")
        for key, value in obj.__dict__.items():
            if not key.startswith('_'):
                if isinstance(value, (str, int, float, bool)):
                    print(f"{indent}    {key}: {value}")
                else:
                    deep_inspect(value, key, depth+1, max_depth)


def main():
    print("=" * 70)
    print("DEEP INSPECTION OF ADDRESS OBJECT")
    print("=" * 70)
    
    pk = os.getenv("PK", "").strip()
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    
    if pk.startswith('0x') or pk.startswith('0X'):
        pk = pk[2:]
    
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    
    proxy_address = Web3.to_checksum_address(browser_address)
    
    print(f"\nCreating test order...")
    
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
        
        # Get a test market
        markets = client.get_sampling_markets()
        market = markets['data'][0]
        tokens = market.get('tokens', [])
        token_yes = tokens[0].get('token_id')
        rewards = market.get('rewards', {})
        is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
        
        # Create order
        order_args = OrderArgs(
            token_id=str(token_yes),
            price=0.5,
            size=5.0,
            side="BUY"
        )
        
        if is_neg_risk:
            signed_order = client.create_order(
                order_args,
                options=PartialCreateOrderOptions(neg_risk=True)
            )
        else:
            signed_order = client.create_order(order_args)
        
        print(f"\n{'='*70}")
        print("INSPECTING SIGNED ORDER")
        print("="*70)
        deep_inspect(signed_order, "SignedOrder", max_depth=4)
        
        if hasattr(signed_order, 'order'):
            print(f"\n{'='*70}")
            print("INSPECTING ORDER OBJECT")
            print("="*70)
            deep_inspect(signed_order.order, "Order", max_depth=4)
            
            if hasattr(signed_order.order, 'maker'):
                print(f"\n{'='*70}")
                print("INSPECTING MAKER (ADDRESS OBJECT)")
                print("="*70)
                deep_inspect(signed_order.order.maker, "Maker", max_depth=5)
                
                # Try to get the actual address
                maker = signed_order.order.maker
                print(f"\n{'='*70}")
                print("ATTEMPTING TO EXTRACT ACTUAL ADDRESS")
                print("="*70)
                
                methods_to_try = [
                    ('str(maker)', lambda: str(maker)),
                    ('maker.__str__()', lambda: maker.__str__()),
                    ('maker.__repr__()', lambda: maker.__repr__()),
                    ('maker.hex', lambda: maker.hex if hasattr(maker, 'hex') else 'N/A'),
                    ('maker.address', lambda: maker.address if hasattr(maker, 'address') else 'N/A'),
                    ('maker.value', lambda: maker.value if hasattr(maker, 'value') else 'N/A'),
                ]
                
                for method_name, method_func in methods_to_try:
                    try:
                        result = method_func()
                        if callable(result):
                            result = result()
                        print(f"{method_name}: {result}")
                    except Exception as e:
                        print(f"{method_name}: ERROR - {e}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

