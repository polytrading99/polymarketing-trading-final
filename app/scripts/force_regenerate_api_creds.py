"""
Force regenerate API credentials and test order placement with detailed logging.
"""

import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from web3 import Web3

load_dotenv()


def main():
    print("=" * 60)
    print("FORCE REGENERATE API CREDENTIALS")
    print("=" * 60)
    
    pk = os.getenv("PK", "").strip()
    if pk.startswith("0x") or pk.startswith("0X"):
        pk = pk[2:]
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    
    if not pk or not browser_address:
        print("ERROR: PK or BROWSER_ADDRESS not set")
        return
    
    browser_address = Web3.to_checksum_address(browser_address)
    
    print(f"\n1. Creating new ClobClient instance...")
    print(f"   Wallet: {browser_address}")
    print(f"   Chain: POLYGON")
    print(f"   Signature Type: 2")
    
    try:
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=POLYGON,
            funder=browser_address,
            signature_type=2
        )
        print("   ✅ ClobClient created")
    except Exception as e:
        print(f"   ❌ Failed to create ClobClient: {e}")
        return
    
    print(f"\n2. Generating NEW API credentials...")
    try:
        # Force create new credentials (this is deterministic based on PK, but let's try)
        creds = client.create_or_derive_api_creds()
        print(f"   ✅ API credentials generated")
        print(f"   API Key: {creds.api_key}")
        print(f"   API Secret: {creds.api_secret[:20]}...")
        print(f"   API Passphrase: {creds.api_passphrase[:20]}...")
        
        # Set credentials
        client.set_api_creds(creds=creds)
        print(f"   ✅ API credentials set on client")
    except Exception as e:
        print(f"   ❌ Failed to generate API credentials: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n3. Testing API credentials by fetching orders...")
    try:
        orders = client.get_orders()
        print(f"   ✅ API credentials work!")
        print(f"   Current orders: {len(orders)}")
    except Exception as e:
        print(f"   ⚠️  Could not fetch orders: {e}")
        print(f"   This might be OK if you have no orders")
    
    print(f"\n4. Testing order creation (without posting)...")
    try:
        from py_clob_client.clob_types import OrderArgs
        
        # Use a test token (you can replace with a real one)
        test_token = "104173557214744537570424345347209544585775842950109756851652855913015295701992"
        
        order_args = OrderArgs(
            token_id=test_token,
            price=0.5,
            size=1.0,
            side="BUY"
        )
        
        print(f"   Creating signed order (not posting yet)...")
        signed_order = client.create_order(order_args)
        print(f"   ✅ Order signed successfully!")
        print(f"   Order hash: {signed_order.get('hash', 'N/A')}")
        print(f"   Signature: {signed_order.get('signature', 'N/A')[:50]}...")
        
        print(f"\n5. Attempting to POST order to Polymarket...")
        print(f"   This will fail if wallet hasn't done manual trade")
        try:
            resp = client.post_order(signed_order)
            print(f"   ✅✅✅ ORDER POSTED SUCCESSFULLY!")
            print(f"   Response: {resp}")
        except Exception as e:
            error_str = str(e)
            print(f"   ❌ Order post failed: {error_str}")
            
            if "invalid signature" in error_str.lower():
                print(f"\n   🔴 INVALID SIGNATURE - This means:")
                print(f"      1. Wallet hasn't done a manual trade, OR")
                print(f"      2. The trade wasn't confirmed on-chain, OR")
                print(f"      3. The trade was on a different wallet")
                print(f"\n   To fix:")
                print(f"      1. Go to https://polymarket.com")
                print(f"      2. Connect wallet: {browser_address}")
                print(f"      3. Make ONE small manual trade (buy or sell)")
                print(f"      4. Wait for transaction to confirm on Polygon (check on polygonscan.com)")
                print(f"      5. Wait 2-3 minutes for Polymarket to index it")
                print(f"      6. Run this script again")
    except Exception as e:
        print(f"   ❌ Failed to create order: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()

