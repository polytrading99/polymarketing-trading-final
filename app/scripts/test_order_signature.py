"""
Test order signature generation with detailed debugging.
Tries different approaches to identify the signature issue.
"""

import os
from dotenv import load_dotenv
from poly_data.polymarket_client import PolymarketClient
from data_updater.trading_utils import get_clob_client
from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions

load_dotenv()


def main():
    print("=" * 60)
    print("TESTING ORDER SIGNATURE GENERATION")
    print("=" * 60)
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    print(f"\nWallet: {browser_address}\n")
    
    # Initialize client
    try:
        client = PolymarketClient()
        print(f"✅ PolymarketClient initialized")
        print(f"   Wallet: {client.browser_wallet}")
        print(f"   API Key: {client.creds.api_key[:20]}...")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return
    
    # Find a market
    clob_client = get_clob_client()
    if not clob_client:
        print(f"❌ Could not get CLOB client")
        return
    
    try:
        print(f"\nFetching markets...")
        markets = clob_client.get_sampling_markets()
        
        if not markets or 'data' not in markets or len(markets['data']) == 0:
            print(f"❌ No markets found")
            return
        
        # Try to find both neg-risk and non-neg-risk markets
        neg_risk_market = None
        simple_market = None
        
        for market in markets.get('data', [])[:50]:
            rewards = market.get('rewards', {})
            is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
            
            if is_neg_risk and not neg_risk_market:
                neg_risk_market = market
            elif not is_neg_risk and not simple_market:
                simple_market = market
            
            if neg_risk_market and simple_market:
                break
        
        # Test 1: Try simple market (non-neg-risk) first
        if simple_market:
            print(f"\n{'='*60}")
            print("TEST 1: Simple Market (Non-Neg-Risk)")
            print("=" * 60)
            
            tokens = simple_market.get('tokens', [])
            if tokens:
                token_yes = tokens[0].get('token_id')
                question = simple_market.get('question', 'Unknown')
                
                print(f"Market: {question}")
                print(f"Token: {token_yes}")
                print(f"Neg Risk: False")
                
                # Get order book
                try:
                    bids_df, asks_df = client.get_order_book(token_yes)
                    if len(bids_df) > 0 and len(asks_df) > 0:
                        best_bid = float(bids_df.iloc[-1]['price'])
                        best_ask = float(asks_df.iloc[-1]['price'])
                        price = round(best_bid + 0.01, 4)
                        if price > 0.99:
                            price = 0.99
                        if price < 0.01:
                            price = 0.01
                    else:
                        price = 0.5
                except:
                    price = 0.5
                
                print(f"Price: {price}")
                print(f"Size: 1.0 USDC")
                
                try:
                    resp = client.create_order(
                        marketId=str(token_yes),
                        action="BUY",
                        price=price,
                        size=1.0,
                        neg_risk=False
                    )
                    print(f"\n✅✅✅ SUCCESS! Order placed on simple market!")
                    print(f"Response: {resp}")
                    return
                except Exception as e:
                    error_str = str(e)
                    print(f"\n❌ Failed: {error_str}")
                    if "invalid signature" not in error_str.lower():
                        print(f"This is a different error - might be fixable")
        
        # Test 2: Try neg-risk market
        if neg_risk_market:
            print(f"\n{'='*60}")
            print("TEST 2: Neg-Risk Market")
            print("=" * 60)
            
            tokens = neg_risk_market.get('tokens', [])
            if tokens:
                token_yes = tokens[0].get('token_id')
                question = neg_risk_market.get('question', 'Unknown')
                
                print(f"Market: {question}")
                print(f"Token: {token_yes}")
                print(f"Neg Risk: True")
                
                # Get order book
                try:
                    bids_df, asks_df = client.get_order_book(token_yes)
                    if len(bids_df) > 0 and len(asks_df) > 0:
                        best_bid = float(bids_df.iloc[-1]['price'])
                        best_ask = float(asks_df.iloc[-1]['price'])
                        price = round(best_bid + 0.01, 4)
                        if price > 0.99:
                            price = 0.99
                        if price < 0.01:
                            price = 0.01
                    else:
                        price = 0.5
                except:
                    price = 0.5
                
                print(f"Price: {price}")
                print(f"Size: 1.0 USDC")
                
                try:
                    resp = client.create_order(
                        marketId=str(token_yes),
                        action="BUY",
                        price=price,
                        size=1.0,
                        neg_risk=True
                    )
                    print(f"\n✅✅✅ SUCCESS! Order placed on neg-risk market!")
                    print(f"Response: {resp}")
                    return
                except Exception as e:
                    error_str = str(e)
                    print(f"\n❌ Failed: {error_str}")
        
        # Test 3: Try using ClobClient directly (bypass our wrapper)
        print(f"\n{'='*60}")
        print("TEST 3: Direct ClobClient (bypass wrapper)")
        print("=" * 60)
        
        test_market = simple_market or neg_risk_market or markets['data'][0]
        tokens = test_market.get('tokens', [])
        if tokens:
            token_yes = tokens[0].get('token_id')
            rewards = test_market.get('rewards', {})
            is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
            
            print(f"Trying direct ClobClient approach...")
            print(f"Token: {token_yes}")
            print(f"Neg Risk: {is_neg_risk}")
            
            try:
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
                
                print(f"Order signed successfully")
                print(f"Order type: {type(signed_order)}")
                print(f"Order hash: {getattr(signed_order, 'hash', 'N/A')}")
                
                resp = client.client.post_order(signed_order)
                print(f"\n✅✅✅ SUCCESS! Order placed via direct ClobClient!")
                print(f"Response: {resp}")
                return
            except Exception as e:
                error_str = str(e)
                print(f"\n❌ Failed: {error_str}")
                import traceback
                traceback.print_exc()
        
        print(f"\n{'='*60}")
        print("ALL TESTS FAILED")
        print("=" * 60)
        print("\nPossible solutions:")
        print("1. Try regenerating API credentials")
        print("2. Make a NEW trade on polymarket.com (even if you've done trades before)")
        print("3. Check if there's a wallet approval needed")
        print("4. Verify the PK and BROWSER_ADDRESS match exactly")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

