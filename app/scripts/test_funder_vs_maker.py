"""
Test different funder/maker combinations to find the correct setup.
The issue is that order maker doesn't match funder, causing invalid signature.
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


def extract_maker_address(order):
    """Extract maker address from order object."""
    if hasattr(order, 'order'):
        order_obj = order.order
        if hasattr(order_obj, 'maker'):
            maker_obj = order_obj.maker
            if hasattr(maker_obj, 'address'):
                return str(maker_obj.address)
            else:
                return str(maker_obj).replace('Address(', '').replace(')', '').strip("'\"")
    return None


def test_configuration(funder_address, description):
    """Test a specific funder configuration."""
    print(f"\n{'='*70}")
    print(f"TESTING: {description}")
    print(f"{'='*70}")
    print(f"Funder: {funder_address}")
    
    pk = os.getenv("PK", "").strip()
    if pk.startswith('0x') or pk.startswith('0X'):
        pk = pk[2:]
    
    try:
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=POLYGON,
            funder=Web3.to_checksum_address(funder_address),
            signature_type=2
        )
        
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)
        
        # Get a test market
        markets = client.get_sampling_markets()
        if not markets or 'data' not in markets:
            print("❌ No markets found")
            return False
        
        market = markets['data'][0]
        tokens = market.get('tokens', [])
        if not tokens:
            print("❌ No tokens in market")
            return False
        
        token_yes = tokens[0].get('token_id')
        rewards = market.get('rewards', {})
        is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
        min_size = float(rewards.get('min_size', 5.0)) if rewards.get('min_size') else 5.0
        
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
        
        # Extract maker address
        maker_address = extract_maker_address(signed_order)
        print(f"Maker in order: {maker_address}")
        print(f"Funder used: {funder_address}")
        
        if maker_address and maker_address.lower() == funder_address.lower():
            print("✅ Maker matches funder")
        else:
            print(f"⚠️  Maker ({maker_address}) doesn't match funder ({funder_address})")
        
        # Try to post
        try:
            resp = client.post_order(signed_order, OrderType.GTC)
            print(f"✅✅✅ SUCCESS! Order posted!")
            print(f"Response: {resp}")
            return True
        except Exception as e:
            error_str = str(e)
            print(f"❌ Failed: {error_str}")
            if "invalid signature" in error_str.lower():
                print(f"   Still getting invalid signature with this configuration")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 70)
    print("TESTING DIFFERENT FUNDER CONFIGURATIONS")
    print("=" * 70)
    
    pk = os.getenv("PK", "").strip()
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    
    if not pk or not browser_address:
        print("❌ PK or BROWSER_ADDRESS not set")
        return
    
    # Clean addresses
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    
    proxy_address = Web3.to_checksum_address(browser_address)
    
    # Get MetaMask address from PK
    if pk.startswith('0x') or pk.startswith('0X'):
        pk_clean = pk[2:]
    else:
        pk_clean = pk
    
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    wallet = web3.eth.account.from_key(pk_clean)
    metamask_address = wallet.address
    
    print(f"\nMetaMask Address: {metamask_address}")
    print(f"Proxy Address: {proxy_address}\n")
    
    # Test different configurations
    configs = [
        (proxy_address, "Proxy address as funder (current setup)"),
        (metamask_address, "MetaMask address as funder (alternative)"),
    ]
    
    success = False
    for funder, description in configs:
        if test_configuration(funder, description):
            print(f"\n🎉 SUCCESS! Use this configuration:")
            print(f"   Funder: {funder}")
            print(f"   Description: {description}")
            success = True
            break
    
    if not success:
        print(f"\n{'='*70}")
        print("ALL CONFIGURATIONS FAILED")
        print("="*70)
        print(f"\nBoth configurations resulted in 'invalid signature' errors.")
        print(f"This suggests:")
        print(f"  1. The wallet needs a fresh manual trade on Polymarket.com")
        print(f"  2. There's a bug in py-clob-client for this proxy type")
        print(f"  3. The signature_type might need to be different")
        print(f"\nTry making a NEW manual trade on Polymarket.com and test again.")


if __name__ == "__main__":
    main()

