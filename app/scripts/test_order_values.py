"""
Test if we can extract the actual values from the order and verify they're correct.
The inspection showed the values dict has the correct maker address.
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions, OrderType

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()


def main():
    print("=" * 70)
    print("VERIFY ORDER VALUES AND TEST POSTING")
    print("=" * 70)
    
    pk = os.getenv("PK", "").strip()
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    
    if pk.startswith('0x') or pk.startswith('0X'):
        pk = pk[2:]
    
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    
    proxy_address = Web3.to_checksum_address(browser_address)
    
    # Get MetaMask address
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    wallet = web3.eth.account.from_key(pk)
    metamask_address = wallet.address
    
    print(f"\nMetaMask: {metamask_address}")
    print(f"Proxy: {proxy_address}\n")
    
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
        min_size = float(rewards.get('min_size', 5.0)) if rewards.get('min_size') else 5.0
        
        print(f"Market: {market.get('question', 'Unknown')[:50]}...")
        print(f"Min Size: {min_size} USDC")
        print(f"Neg Risk: {is_neg_risk}\n")
        
        # Create order
        order_args = OrderArgs(
            token_id=str(token_yes),
            price=0.5,
            size=max(min_size, 5.0),
            side="BUY"
        )
        
        if is_neg_risk:
            signed_order = client.create_order(
                order_args,
                options=PartialCreateOrderOptions(neg_risk=True)
            )
        else:
            signed_order = client.create_order(order_args)
        
        # Extract values from order
        if hasattr(signed_order, 'order') and hasattr(signed_order.order, 'values'):
            values = signed_order.order.values
            print("=" * 70)
            print("ORDER VALUES VERIFICATION")
            print("=" * 70)
            print(f"Maker: {values.get('maker')}")
            print(f"Signer: {values.get('signer')}")
            print(f"Signature Type: {values.get('signatureType')}")
            print(f"Token ID: {values.get('tokenId')}")
            print(f"Price: {values.get('makerAmount')} / {values.get('takerAmount')} = {values.get('makerAmount') / values.get('takerAmount')}")
            print(f"Size: {values.get('makerAmount') / 1e6} USDC")
            
            # Verify addresses match
            print(f"\n{'='*70}")
            print("ADDRESS VERIFICATION")
            print("=" * 70)
            maker = values.get('maker', '').lower()
            signer = values.get('signer', '').lower()
            
            if maker == proxy_address.lower():
                print(f"✅ Maker matches proxy: {maker}")
            else:
                print(f"❌ Maker mismatch! Expected: {proxy_address.lower()}, Got: {maker}")
            
            if signer == metamask_address.lower():
                print(f"✅ Signer matches MetaMask: {signer}")
            else:
                print(f"❌ Signer mismatch! Expected: {metamask_address.lower()}, Got: {signer}")
            
            if values.get('signatureType') == 2:
                print(f"✅ Signature type is 2 (Browser Wallet)")
            else:
                print(f"❌ Signature type is {values.get('signatureType')}, expected 2")
        
        # Check signature
        if hasattr(signed_order, 'signature'):
            sig = signed_order.signature
            print(f"\n{'='*70}")
            print("SIGNATURE VERIFICATION")
            print("=" * 70)
            print(f"Signature: {sig[:50]}...{sig[-20:]}")
            print(f"Length: {len(sig)} characters")
            if sig.startswith('0x'):
                print(f"✅ Signature starts with 0x")
                if len(sig) == 132:  # 0x + 130 hex chars = 65 bytes
                    print(f"✅ Signature length is correct (132 chars = 65 bytes)")
                else:
                    print(f"⚠️  Signature length is {len(sig)}, expected 132")
            else:
                print(f"❌ Signature doesn't start with 0x")
        
        # Try to post
        print(f"\n{'='*70}")
        print("ATTEMPTING TO POST ORDER")
        print("=" * 70)
        
        try:
            resp = client.post_order(signed_order, OrderType.GTC)
            print(f"✅✅✅ SUCCESS! Order posted!")
            print(f"Response: {resp}")
        except Exception as e:
            error_str = str(e)
            print(f"❌ Failed: {error_str}")
            
            if "invalid signature" in error_str.lower():
                print(f"\n{'='*70}")
                print("INVALID SIGNATURE ANALYSIS")
                print("=" * 70)
                print(f"Even though:")
                print(f"  ✅ Maker is correct: {values.get('maker')}")
                print(f"  ✅ Signer is correct: {values.get('signer')}")
                print(f"  ✅ Signature type is correct: {values.get('signatureType')}")
                print(f"  ✅ Signature format looks correct")
                print(f"\nThis suggests the issue might be:")
                print(f"  1. Polymarket's API validation is rejecting the signature")
                print(f"  2. The signature was generated with wrong parameters")
                print(f"  3. There's a mismatch in how the order is serialized")
                print(f"  4. The wallet needs to be 'activated' for API orders")
                print(f"\nSince you've done trades, try:")
                print(f"  - Check if those trades were done through CLOB API or website")
                print(f"  - Verify the proxy address on Polymarket.com matches exactly")
                print(f"  - Check if there are any API restrictions on your account")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

