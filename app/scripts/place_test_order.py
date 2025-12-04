import asyncio
import sys
from typing import Optional

from poly_data.polymarket_client import PolymarketClient
from data_updater.trading_utils import get_clob_client


def find_market_by_question(client, search_text: str, limit: int = 100):
    """
    Search for markets from Polymarket API by question text.
    Returns the first market that contains the search text (case-insensitive).
    """
    cursor = ""
    all_markets = []
    count = 0
    
    while count < limit:
        try:
            markets = client.get_sampling_markets(next_cursor=cursor)
            if not markets or 'data' not in markets:
                break
            
            all_markets.extend(markets['data'])
            count = len(all_markets)
            
            cursor = markets.get('next_cursor')
            if cursor is None:
                break
        except Exception as e:
            print(f"Error fetching markets: {e}")
            break
    
    # Search for market matching the question
    search_lower = search_text.lower()
    for market in all_markets:
        question = market.get('question', '')
        if search_lower in question.lower():
            return market
    
    return None


async def main() -> None:
    """
    Place a real BUY order on a live Polymarket market.
    
    Usage:
        python -m app.scripts.place_test_order [search_text]
    
    Examples:
        python -m app.scripts.place_test_order "ligher airdrop"
        python -m app.scripts.place_test_order "Will ligher perform an airdrop"
    
    If no search text provided, uses the first market from the API.
    
    Requirements:
      - PK and BROWSER_ADDRESS are set in the environment (or .env)
      - Wallet has done at least ONE manual trade on Polymarket (required for API orders)
    """
    # Get search text from command line
    search_text = None
    if len(sys.argv) > 1:
        search_text = " ".join(sys.argv[1:])
    
    # Initialize CLOB client to fetch markets
    clob_client = get_clob_client()
    if not clob_client:
        print("ERROR: Failed to initialize CLOB client. Check PK in .env")
        return
    
    print("Fetching markets from Polymarket...")
    
    # Initialize client first to check balance
    try:
        client = PolymarketClient()
    except Exception as e:
        print(f"ERROR: Failed to initialize PolymarketClient: {e}")
        return
    
    # Check balance first
    try:
        usdc_balance = client.get_usdc_balance()
        print(f"USDC Balance: ${usdc_balance:.2f}")
    except Exception as e:
        print(f"⚠️  Could not check balance: {e}")
        usdc_balance = 5.0  # Fallback minimum
    
    # Find market that fits balance
    market = None
    if search_text:
        print(f"Searching for market containing: '{search_text}'")
        market = find_market_by_question(clob_client, search_text)
        if not market:
            print(f"ERROR: No market found containing '{search_text}'")
            print("Try a shorter search term or check the market name on polymarket.com")
            return
    else:
        # Search for a market that fits the balance
        print(f"Searching for market with minimum ≤ ${usdc_balance:.2f}...")
        try:
            markets = clob_client.get_sampling_markets()
            if not markets or 'data' not in markets:
                print("ERROR: No markets found from Polymarket API")
                return
            
            # Find first REGULAR market (non-neg-risk) which has $1 minimum
            # Keep searching through ALL markets until we find one
            markets_checked = 0
            all_markets = markets['data']
            
            print(f"   Searching through ALL markets for a REGULAR (non-neg-risk) market...")
            print(f"   (Regular markets have $1 minimum, perfect for testing)\n")
            
            # First pass: look for regular markets (non-neg-risk) in current batch
            for m in all_markets:
                markets_checked += 1
                rewards = m.get('rewards', {})
                min_size_raw = rewards.get('min_size')
                max_spread = rewards.get('max_spread')
                is_neg_risk = bool(min_size_raw or max_spread)
                
                if not is_neg_risk:
                    # Found a regular market! These have $1 minimum
                    market = m
                    print(f"✅ Found REGULAR market (min_size: $1.00)")
                    print(f"   Checked {markets_checked} markets")
                    break
                
                # Show progress every 200 markets
                if markets_checked % 200 == 0:
                    print(f"   Checked {markets_checked} markets... still searching...")
            
            # If no regular market found, try pagination to get more markets
            if not market:
                print(f"\n   No regular markets found in first {markets_checked} markets")
                print(f"   Trying to fetch more markets with pagination...\n")
                
                cursor = markets.get('next_cursor')
                max_pages = 10  # Check up to 10 pages
                page = 0
                
                while cursor and page < max_pages and not market:
                    page += 1
                    try:
                        more_markets = clob_client.get_sampling_markets(next_cursor=cursor)
                        if not more_markets or 'data' not in more_markets:
                            break
                        
                        for m in more_markets['data']:
                            markets_checked += 1
                            rewards = m.get('rewards', {})
                            min_size_raw = rewards.get('min_size')
                            max_spread = rewards.get('max_spread')
                            is_neg_risk = bool(min_size_raw or max_spread)
                            
                            if not is_neg_risk:
                                market = m
                                print(f"✅ Found REGULAR market (min_size: $1.00)")
                                print(f"   Checked {markets_checked} markets across {page+1} pages")
                                break
                        
                        cursor = more_markets.get('next_cursor')
                        if markets_checked % 200 == 0:
                            print(f"   Checked {markets_checked} markets across {page+1} pages...")
                    except Exception as e:
                        print(f"   Error fetching page {page+1}: {e}")
                        break
            
            # If still no regular market, try neg-risk markets with low min_size
            if not market:
                print(f"\n   No regular markets found after checking {markets_checked} markets")
                print(f"   Searching for neg-risk markets with low minimum...\n")
                
                best_market = None
                best_min_size = float('inf')
                
                for m in all_markets:
                    rewards = m.get('rewards', {})
                    min_size_raw = rewards.get('min_size')
                    if min_size_raw:
                        min_size = float(min_size_raw)
                        if min_size < best_min_size:
                            best_min_size = min_size
                            best_market = m
                        if min_size <= usdc_balance:
                            market = m
                            print(f"✅ Found neg-risk market with min_size ${min_size} (fits balance)")
                            break
                
                if not market and best_market:
                    market = best_market
                    print(f"⚠️  Using neg-risk market with lowest min_size: ${best_min_size}")
                    if best_min_size > usdc_balance:
                        print(f"   This is above your balance - order will likely fail")
            
            # Final check
            if not market:
                print(f"\n❌ ERROR: Could not find any suitable market after checking {markets_checked} markets")
                print(f"   This is unusual - most markets should be regular (non-neg-risk) with $1 minimum")
                print(f"   Please check Polymarket.com to see if there are active markets")
                return
        except Exception as e:
            print(f"ERROR: Failed to fetch markets: {e}")
            return
    
    # Extract market details
    question = market.get('question', 'Unknown')
    condition_id = market.get('condition_id', '')
    
    # Get tokens
    tokens = market.get('tokens', [])
    if not tokens or len(tokens) < 2:
        print(f"ERROR: Market '{question}' doesn't have valid tokens")
        return
    
    token_yes = tokens[0].get('token_id')
    token_no = tokens[1].get('token_id')
    
    # Check if neg_risk (has rewards) and get minimum order size
    rewards = market.get('rewards', {})
    is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
    min_size_raw = rewards.get('min_size')
    
    # Regular markets (non-neg-risk) typically have $1 minimum
    # Neg-risk markets have min_size in rewards (often $20-200)
    if is_neg_risk and min_size_raw:
        min_size = float(min_size_raw)
    elif not is_neg_risk:
        # Regular market - standard minimum is $1
        min_size = 1.0
    else:
        # Neg-risk but no min_size specified - assume $5
        min_size = 5.0
    
    neg_risk = is_neg_risk
    
    print(f"\n{'='*60}")
    print(f"Selected Market:")
    print(f"  Question: {question}")
    print(f"  Condition ID: {condition_id}")
    print(f"  Token YES: {token_yes}")
    print(f"  Token NO: {token_no}")
    print(f"  Neg Risk: {neg_risk}")
    print(f"  Min Order Size: {min_size} USDC")
    print(f"{'='*60}\n")
    
    # Client already initialized above for balance check
    
    # Get current order book to find a reasonable price
    try:
        order_book = client.get_order_book(token_yes)
        bids_df, asks_df = order_book
        
        if len(bids_df) > 0 and len(asks_df) > 0:
            best_bid = float(bids_df.iloc[-1]['price'])
            best_ask = float(asks_df.iloc[-1]['price'])
            mid_price = (best_bid + best_ask) / 2
            print(f"Order book: best_bid={best_bid:.4f}, best_ask={best_ask:.4f}, mid={mid_price:.4f}")
            # Use a price slightly above best bid to ensure it's competitive
            price = round(best_bid + 0.01, 4)
            if price > 0.99:
                price = 0.99
            if price < 0.01:
                price = 0.01
        else:
            print("Warning: Empty order book, using default price 0.5")
            price = 0.5
    except Exception as e:
        print(f"Warning: Could not fetch order book: {e}")
        print("Using default price 0.5")
        price = 0.5
    
    # Check balance and calculate order size
    # IMPORTANT: size parameter in OrderArgs is TOKEN AMOUNT, not USDC amount
    # For BUY orders: token_amount = usdc_amount / price
    try:
        usdc_balance = client.get_usdc_balance()
        print(f"USDC Balance: ${usdc_balance:.2f}")
        
        # For testing: ALWAYS use your available balance (90% for safety)
        # Don't try to meet market minimum if you don't have enough
        max_usdc = usdc_balance * 0.9  # Use 90% of balance for safety
        
        if min_size > usdc_balance:
            print(f"\n⚠️  WARNING: Market requires ${min_size} USDC minimum")
            print(f"   But you only have ${usdc_balance:.2f} USDC")
            print(f"   Using ${max_usdc:.2f} USDC for testing (90% of your balance)")
            print(f"   Order may fail if market enforces minimum, but we'll try anyway")
            usdc_to_spend = max_usdc
        else:
            # We have enough - use smaller of: min_size or max_usdc
            usdc_to_spend = min(min_size, max_usdc)
            print(f"   Will use ${usdc_to_spend:.2f} USDC")
        
        # Convert USDC amount to token amount: tokens = usdc / price
        # For BUY orders, we're buying tokens, so size = usdc_amount / price
        size = usdc_to_spend / price
        
        print(f"   Will spend: ${usdc_to_spend:.2f} USDC")
        print(f"   Token amount: {size:.2f} tokens (at price {price})")
        print(f"   USDC value: ${size * price:.2f}")
        
    except Exception as e:
        print(f"⚠️  Could not check balance: {e}")
        # Fallback: use min_size converted to tokens
        size = min_size / price
    
    print(f"\nPlacing REAL BUY order:")
    print(f"  Token: {token_yes}")
    print(f"  Price: {price}")
    print(f"  Size: {size:.2f} tokens (${size * price:.2f} USDC)")
    print(f"  Market minimum: ${min_size} USDC")
    print(f"  Neg Risk: {neg_risk}")
    print()
    
    try:
        resp = client.create_order(
            marketId=str(token_yes),
            action="BUY",
            price=price,
            size=size,
            neg_risk=neg_risk,
        )
        print(f"\n{'='*60}")
        print("✅ ORDER PLACED SUCCESSFULLY!")
        print(f"{'='*60}")
        print("Order response:", resp)
        print("\nYou should now see this order on polymarket.com")
        print(f"Check your orders at: https://polymarket.com/account/orders")
    except Exception as e:
        error_str = str(e)
        print(f"\n{'='*60}")
        print("❌ ORDER FAILED")
        print(f"{'='*60}")
        print(f"Error: {error_str}\n")
        
        if "invalid signature" in error_str.lower():
            print("🔴 INVALID SIGNATURE ERROR")
            print("\nThis means your wallet hasn't done a manual trade on Polymarket yet.")
            print("Polymarket requires at least ONE manual trade before API orders work.\n")
            print("SOLUTION:")
            print("  1. Go to https://polymarket.com")
            print(f"  2. Connect your wallet: {client.browser_wallet}")
            print("  3. Make ONE small manual trade (buy or sell ANY market, even $1)")
            print("  4. Wait for the transaction to confirm on Polygon")
            print("  5. Then run this script again\n")
            print("This is a Polymarket security requirement - once you do one manual trade,")
            print("all future API orders will work automatically.")
        elif "lower than the minimum" in error_str.lower() or "minimum:" in error_str.lower():
            print("🔴 MINIMUM ORDER SIZE ERROR")
            print("\nThe order size is below the market's minimum requirement.")
            print(f"Market minimum: {min_size} USDC")
            print(f"Attempted size: {size} USDC")
            print("\nThe script should automatically use the correct minimum size.")
            print("If you see this error, there may be a bug in size calculation.")
        else:
            print("Check the error message above for details.")
        
        raise


if __name__ == "__main__":
    asyncio.run(main())


