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
            
            # Try multiple ways to extract the address
            # Method 1: Direct attribute
            if hasattr(maker_obj, 'address'):
                addr = maker_obj.address
                if hasattr(addr, '__str__'):
                    return str(addr)
                return str(addr)
            
            # Method 2: Check if it has a value attribute
            if hasattr(maker_obj, 'value'):
                return str(maker_obj.value)
            
            # Method 3: Try to convert to string and parse
            maker_str = str(maker_obj)
            
            # If it's an Address object, try to get the actual address
            if 'Address' in maker_str:
                # Try to access internal attributes
                if hasattr(maker_obj, '__dict__'):
                    for key, value in maker_obj.__dict__.items():
                        if 'addr' in key.lower() or 'value' in key.lower():
                            return str(value)
                
                # Try to call it if it's callable
                try:
                    addr_val = maker_obj()
                    return str(addr_val)
                except:
                    pass
            
            # Method 4: Try hex() if available
            if hasattr(maker_obj, 'hex'):
                return '0x' + maker_obj.hex()
            
            # Method 5: Try __str__ and clean up
            if hasattr(maker_obj, '__str__'):
                addr_str = str(maker_obj)
                # Look for hex pattern
                import re
                hex_match = re.search(r'0x[a-fA-F0-9]{40}', addr_str)
                if hex_match:
                    return hex_match.group(0)
            
            # Last resort: return the string representation
            return maker_str
    
    # Also check if maker is directly on the order
    if hasattr(order, 'maker'):
        return extract_maker_address_from_obj(order.maker)
    
    return None


def extract_maker_address_from_obj(maker_obj):
    """Helper to extract address from maker object."""
    if isinstance(maker_obj, str):
        return maker_obj
    
    # Try all the methods above
    if hasattr(maker_obj, 'address'):
        return str(maker_obj.address)
    if hasattr(maker_obj, 'value'):
        return str(maker_obj.value)
    if hasattr(maker_obj, 'hex'):
        return '0x' + maker_obj.hex()
    
    # Try to access internal state
    if hasattr(maker_obj, '__dict__'):
        for key, value in maker_obj.__dict__.items():
            if isinstance(value, str) and value.startswith('0x') and len(value) == 42:
                return value
    
    return str(maker_obj)


def test_configuration(funder_address, signature_type, description):
    """Test a specific funder configuration."""
    print(f"\n{'='*70}")
    print(f"TESTING: {description}")
    print(f"{'='*70}")
    print(f"Funder: {funder_address}")
    print(f"Signature Type: {signature_type}")
    
    pk = os.getenv("PK", "").strip()
    if pk.startswith('0x') or pk.startswith('0X'):
        pk = pk[2:]
    
    try:
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=POLYGON,
            funder=Web3.to_checksum_address(funder_address),
            signature_type=signature_type
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
        
        # Extract maker address - try multiple methods
        maker_address = extract_maker_address(signed_order)
        
        # Also try to inspect the order structure directly
        print(f"\nInspecting order structure...")
        if hasattr(signed_order, 'order'):
            order_obj = signed_order.order
            print(f"Order object type: {type(order_obj)}")
            if hasattr(order_obj, '__dict__'):
                print(f"Order attributes: {list(order_obj.__dict__.keys())}")
                for key, value in order_obj.__dict__.items():
                    if 'maker' in key.lower() or 'address' in key.lower():
                        print(f"  {key}: {value} (type: {type(value)})")
        
        print(f"\nMaker in order: {maker_address}")
        print(f"Funder used: {funder_address}")
        
        # Try to compare addresses (handle Address objects)
        maker_str = str(maker_address) if maker_address else None
        if maker_str:
            # Extract hex address from string if it's an object representation
            import re
            hex_match = re.search(r'0x[a-fA-F0-9]{40}', maker_str)
            if hex_match:
                maker_str = hex_match.group(0)
        
        if maker_str and maker_str.lower() == funder_address.lower():
            print("✅ Maker matches funder")
        elif maker_str:
            print(f"⚠️  Maker ({maker_str}) doesn't match funder ({funder_address})")
        else:
            print(f"⚠️  Could not extract maker address properly")
        
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
    for funder, sig_type, description in configs:
        if test_configuration(funder, sig_type, description):
            print(f"\n🎉 SUCCESS! Use this configuration:")
            print(f"   Funder: {funder}")
            print(f"   Signature Type: {sig_type}")
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

