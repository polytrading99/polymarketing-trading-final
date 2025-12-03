"""
Verify Polymarket account status using their actual APIs.
This checks positions, portfolio value, and tries to place a real order.
"""

import os
from dotenv import load_dotenv
from poly_data.polymarket_client import PolymarketClient
from data_updater.trading_utils import get_clob_client
import pandas as pd

load_dotenv()


def main():
    print("=" * 60)
    print("VERIFY POLYMARKET ACCOUNT & PLACE TEST ORDER")
    print("=" * 60)
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    if not browser_address:
        print("ERROR: BROWSER_ADDRESS not set")
        return
    
    print(f"\nWallet: {browser_address}")
    
    # Initialize client
    try:
        client = PolymarketClient()
        print(f"✅ PolymarketClient initialized")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return
    
    # 1. Check USDC balance
    print(f"\n1. Checking USDC balance...")
    try:
        usdc_balance = client.get_usdc_balance()
        print(f"   USDC Balance: {usdc_balance:.6f} USDC")
        if usdc_balance < 1.0:
            print(f"   ⚠️  You need at least 1 USDC to place orders")
        else:
            print(f"   ✅ You have enough USDC")
    except Exception as e:
        print(f"   ⚠️  Could not check USDC balance: {e}")
    
    # 2. Check portfolio value (positions)
    print(f"\n2. Checking portfolio value (positions)...")
    try:
        portfolio_value = client.get_pos_balance()
        print(f"   Portfolio Value: ${portfolio_value:.2f}")
        if portfolio_value > 0:
            print(f"   ✅ You have positions on Polymarket!")
        else:
            print(f"   ⚠️  No positions found")
    except Exception as e:
        print(f"   ⚠️  Could not check portfolio: {e}")
    
    # 3. Check all positions
    print(f"\n3. Checking all positions...")
    try:
        positions_df = client.get_all_positions()
        if len(positions_df) > 0:
            print(f"   ✅ Found {len(positions_df)} positions:")
            for idx, row in positions_df.head(5).iterrows():
                market = row.get('market', 'Unknown')
                size = row.get('size', 0)
                avg_price = row.get('avgPrice', 0)
                print(f"      - {market}: {size:.2f} shares @ ${avg_price:.2f}")
        else:
            print(f"   ⚠️  No positions found")
    except Exception as e:
        print(f"   ⚠️  Could not fetch positions: {e}")
    
    # 4. Check total balance
    print(f"\n4. Checking total account value...")
    try:
        total_balance = client.get_total_balance()
        print(f"   Total Account Value: ${total_balance:.2f}")
        print(f"   (USDC + Positions)")
    except Exception as e:
        print(f"   ⚠️  Could not check total balance: {e}")
    
    # 5. Try to place a REAL order
    print(f"\n5. Attempting to place a REAL order...")
    
    # Find a market
    clob_client = get_clob_client()
    if not clob_client:
        print(f"   ❌ Could not get CLOB client")
        return
    
    try:
        print(f"   Fetching markets...")
        markets = clob_client.get_sampling_markets()
        
        if not markets or 'data' not in markets or len(markets['data']) == 0:
            print(f"   ❌ No markets found")
            return
        
        # Use first market
        market = markets['data'][0]
        question = market.get('question', 'Unknown')
        tokens = market.get('tokens', [])
        
        if not tokens:
            print(f"   ❌ Market has no tokens")
            return
        
        token_yes = tokens[0].get('token_id')
        rewards = market.get('rewards', {})
        is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
        
        # Get minimum order size from market
        min_size = rewards.get('min_size', 0)
        if min_size and min_size > 0:
            min_size = float(min_size)
        else:
            min_size = 5.0  # Default minimum is usually 5 USDC
        
        print(f"   Market: {question}")
        print(f"   Token: {token_yes}")
        print(f"   Neg Risk: {is_neg_risk}")
        print(f"   Min Order Size: {min_size} USDC")
        
        # Get order book to find good price
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
                print(f"   Order book: bid={best_bid:.4f}, ask={best_ask:.4f}")
                print(f"   Using price: {price:.4f}")
            else:
                price = 0.5
                print(f"   Empty order book, using price: {price}")
        except Exception as e:
            price = 0.5
            print(f"   Could not get order book: {e}, using price: {price}")
        
        # Use minimum order size
        order_size = max(min_size, 5.0)  # At least 5 USDC, or market minimum if higher
        
        print(f"\n   Placing BUY order:")
        print(f"      Token: {token_yes}")
        print(f"      Price: {price}")
        print(f"      Size: {order_size} USDC (minimum: {min_size} USDC)")
        print(f"      Neg Risk: {is_neg_risk}")
        
        resp = client.create_order(
            marketId=str(token_yes),
            action="BUY",
            price=price,
            size=order_size,
            neg_risk=is_neg_risk
        )
        
        print(f"\n   ✅✅✅ ORDER PLACED SUCCESSFULLY!")
        print(f"   Response: {resp}")
        print(f"\n   🎉 SUCCESS! Your bot can place orders!")
        print(f"   Check your orders at: https://polymarket.com/account/orders")
        
    except Exception as e:
        error_str = str(e)
        print(f"\n   ❌ Order failed: {error_str}")
        
        if "invalid signature" in error_str.lower():
            print(f"\n   🔴 INVALID SIGNATURE ERROR")
            print(f"\n   Since you have positions and portfolio value, this is strange.")
            print(f"   Possible causes:")
            print(f"   1. The positions were created through a different method (not CLOB)")
            print(f"   2. There's a bug in signature generation for this specific order")
            print(f"   3. The wallet needs to do a NEW trade (recent trades might be required)")
            print(f"\n   Try:")
            print(f"   1. Make a NEW small trade on polymarket.com (even $1)")
            print(f"   2. Wait 2-3 minutes")
            print(f"   3. Run this script again")
        else:
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()

