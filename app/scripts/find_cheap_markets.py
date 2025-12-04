"""
Find markets with low minimum order sizes ($1-10) for testing.
"""

import os
import sys
from dotenv import load_dotenv
from data_updater.trading_utils import get_clob_client

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()


def main():
    print("=" * 70)
    print("FINDING MARKETS WITH LOW MINIMUM ORDER SIZES")
    print("=" * 70)
    
    clob_client = get_clob_client()
    if not clob_client:
        print("ERROR: Failed to initialize CLOB client")
        return
    
    max_price = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    print(f"\nSearching for markets with min_size ≤ ${max_price}...")
    print(f"Checking up to 1000 markets...\n")
    
    try:
        markets = clob_client.get_sampling_markets()
        if not markets or 'data' not in markets:
            print("ERROR: No markets found")
            return
        
        found_markets = []
        checked = 0
        max_to_check = 1000
        
        # Check first batch
        for market in markets['data'][:max_to_check]:
            checked += 1
            rewards = market.get('rewards', {})
            min_size_raw = rewards.get('min_size')
            max_spread = rewards.get('max_spread')
            
            # Determine if neg-risk: has min_size OR max_spread in rewards
            is_neg_risk = bool(min_size_raw or max_spread)
            
            # Regular markets (non-neg-risk) typically have $1 minimum
            # They don't have min_size in rewards, so min_size is None/0
            if not is_neg_risk:
                # Regular market - assume $1 minimum (standard for Polymarket)
                min_size = 1.0
                found_markets.append((market, min_size, False))
            elif min_size_raw:
                # Neg-risk market with explicit min_size
                min_size = float(min_size_raw)
                if min_size <= max_price:
                    found_markets.append((market, min_size, True))
            # If neg-risk but no min_size, skip (likely has high minimum)
            
            # Show progress every 100 markets
            if checked % 100 == 0:
                print(f"   Checked {checked} markets, found {len(found_markets)} so far...")
        
        # Sort by min_size (lowest first)
        found_markets.sort(key=lambda x: x[1])
        
        print(f"Checked {checked} markets")
        print(f"Found {len(found_markets)} markets with min_size ≤ ${max_price}\n")
        
        if found_markets:
            print("=" * 70)
            print("TOP 10 MARKETS (LOWEST MINIMUM)")
            print("=" * 70)
            
            for i, (market, min_size, is_neg_risk) in enumerate(found_markets[:10], 1):
                question = market.get('question', 'Unknown')
                condition_id = market.get('condition_id', '')
                tokens = market.get('tokens', [])
                token_yes = tokens[0].get('token_id') if tokens else 'N/A'
                
                print(f"\n{i}. {question[:60]}...")
                print(f"   Min Size: ${min_size}")
                print(f"   Neg Risk: {is_neg_risk}")
                print(f"   Condition ID: {condition_id}")
                print(f"   Token YES: {token_yes}")
            
            # Show how to use
            best_market = found_markets[0]
            question = best_market[0].get('question', 'Unknown')
            print(f"\n{'='*70}")
            print("TO PLACE ORDER ON BEST MARKET:")
            print("=" * 70)
            print(f"docker exec -it BACKEND_CONTAINER python -m app.scripts.place_test_order \"{question[:30]}...\"")
        else:
            print(f"❌ No markets found with min_size ≤ ${max_price}")
            print(f"   Try increasing the limit or add more USDC to your wallet")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

