"""
Deep diagnostic to find why orders fail despite having trades and USDC.
"""

import os
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs
from poly_data.abis import erc20_abi
import requests

load_dotenv()


def main():
    print("=" * 60)
    print("DEEP DIAGNOSTIC - Finding the Real Issue")
    print("=" * 60)
    
    pk = os.getenv("PK", "").strip()
    if pk.startswith("0x") or pk.startswith("0X"):
        pk = pk[2:]
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    browser_address = Web3.to_checksum_address(browser_address)
    
    print(f"\nWallet: {browser_address}")
    
    # 1. Check USDC balance more carefully
    print(f"\n1. Checking USDC balance (detailed)...")
    try:
        web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        usdc_contract = web3.eth.contract(address=usdc_address, abi=erc20_abi)
        
        balance_raw = usdc_contract.functions.balanceOf(browser_address).call()
        balance_usdc = balance_raw / 10**6
        
        print(f"   USDC balance (raw): {balance_raw}")
        print(f"   USDC balance: {balance_usdc:.6f} USDC")
        
        if balance_usdc < 1.0:
            print(f"   ⚠️  Balance is less than 1 USDC - you need at least 1 USDC to place orders")
        else:
            print(f"   ✅ You have enough USDC to place orders")
    except Exception as e:
        print(f"   ❌ Error checking balance: {e}")
        import traceback
        traceback.print_exc()
    
    # 2. Check Polymarket trades via their data API
    print(f"\n2. Checking Polymarket trades via their API...")
    try:
        # Try multiple endpoints
        trades_url = f"https://data-api.polymarket.com/trades?user={browser_address}&limit=50"
        response = requests.get(trades_url, timeout=10)
        
        if response.status_code == 200:
            trades = response.json()
            if isinstance(trades, list):
                print(f"   Found {len(trades)} trades via data-api.polymarket.com")
                if len(trades) > 0:
                    print(f"   ✅ Wallet HAS trades on Polymarket!")
                    print(f"   Latest trade: {trades[0]}")
                else:
                    print(f"   ⚠️  No trades found (but you said you did trades)")
            else:
                print(f"   Response format: {type(trades)}")
                print(f"   Response: {trades}")
        else:
            print(f"   API returned status {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 3. Try placing a SIMPLE order (non-neg-risk first)
    print(f"\n3. Testing order placement with SIMPLE market (non-neg-risk)...")
    try:
        client = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=POLYGON,
            funder=browser_address,
            signature_type=2
        )
        
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds=creds)
        
        # Find a simple market (not neg-risk)
        print(f"   Fetching markets to find a simple one...")
        markets = client.get_sampling_markets()
        
        simple_market = None
        for market in markets.get('data', [])[:20]:
            rewards = market.get('rewards', {})
            # Neg-risk markets have rewards with min_size/max_spread
            is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
            if not is_neg_risk:
                simple_market = market
                break
        
        if not simple_market:
            print(f"   ⚠️  Could not find a simple market, using first market")
            if markets.get('data'):
                simple_market = markets['data'][0]
            else:
                print(f"   ❌ No markets found")
                return
        
        tokens = simple_market.get('tokens', [])
        if not tokens:
            print(f"   ❌ Market has no tokens")
            return
        
        token_yes = tokens[0].get('token_id')
        question = simple_market.get('question', 'Unknown')
        
        print(f"   Using market: {question}")
        print(f"   Token: {token_yes}")
        print(f"   Neg Risk: False (simple market)")
        
        # Get order book
        try:
            order_book = client.get_order_book(token_yes)
            if order_book.bids and order_book.asks:
                best_bid = float(order_book.bids[-1].price)
                best_ask = float(order_book.asks[-1].price)
                mid = (best_bid + best_ask) / 2
                price = round(best_bid + 0.01, 4)
                if price > 0.99:
                    price = 0.99
                print(f"   Order book: bid={best_bid:.4f}, ask={best_ask:.4f}, using price={price:.4f}")
            else:
                price = 0.5
                print(f"   Using default price: {price}")
        except:
            price = 0.5
            print(f"   Using default price: {price}")
        
        print(f"\n   Placing BUY order (simple market, no neg-risk)...")
        order_args = OrderArgs(
            token_id=str(token_yes),
            price=price,
            size=1.0,
            side="BUY"
        )
        
        signed_order = client.create_order(order_args)
        print(f"   ✅ Order signed")
        
        resp = client.post_order(signed_order)
        print(f"   ✅✅✅ ORDER PLACED SUCCESSFULLY!")
        print(f"   Response: {resp}")
        print(f"\n   🎉 SUCCESS! The issue might be with neg-risk markets specifically")
        return
        
    except Exception as e:
        error_str = str(e)
        print(f"   ❌ Order failed: {error_str}")
        
        if "invalid signature" in error_str.lower():
            print(f"\n   🔴 Still getting invalid signature even with simple market")
            print(f"   This suggests the issue is NOT with neg-risk markets")
            
            # Try checking if maybe the API key is wrong
            print(f"\n4. Checking API credentials...")
            try:
                orders = client.get_orders()
                print(f"   ✅ Can fetch orders via API (credentials work)")
                print(f"   Current orders: {len(orders)}")
            except Exception as e2:
                print(f"   ⚠️  Could not fetch orders: {e2}")
            
            print(f"\n   Possible causes:")
            print(f"   1. Trades were done on a DIFFERENT wallet address")
            print(f"   2. Trades were done but Polymarket hasn't indexed them")
            print(f"   3. There's a bug in the signature generation")
            print(f"   4. The wallet needs to do a NEW trade (old trades don't count?)")
            
            print(f"\n   Let's verify the wallet address:")
            print(f"   - Check your trades on: https://polymarket.com/account/trades")
            print(f"   - Make sure the wallet address matches: {browser_address}")
            print(f"   - If different, update BROWSER_ADDRESS in .env")
        
        import traceback
        traceback.print_exc()
    
    # 4. Try neg-risk order if simple worked
    print(f"\n4. If simple order worked, trying neg-risk order...")
    # (This would run if simple order succeeded)


if __name__ == "__main__":
    main()

