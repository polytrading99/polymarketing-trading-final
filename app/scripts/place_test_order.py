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
    
    # Find market
    market = None
    if search_text:
        print(f"Searching for market containing: '{search_text}'")
        market = find_market_by_question(clob_client, search_text)
        if not market:
            print(f"ERROR: No market found containing '{search_text}'")
            print("Try a shorter search term or check the market name on polymarket.com")
            return
    else:
        # Use first market from API
        try:
            markets = clob_client.get_sampling_markets()
            if markets and 'data' in markets and len(markets['data']) > 0:
                market = markets['data'][0]
            else:
                print("ERROR: No markets found from Polymarket API")
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
    
    # Check if neg_risk (has rewards)
    rewards = market.get('rewards', {})
    neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
    
    print(f"\n{'='*60}")
    print(f"Selected Market:")
    print(f"  Question: {question}")
    print(f"  Condition ID: {condition_id}")
    print(f"  Token YES: {token_yes}")
    print(f"  Token NO: {token_no}")
    print(f"  Neg Risk: {neg_risk}")
    print(f"{'='*60}\n")
    
    # Initialize Polymarket client
    try:
        client = PolymarketClient()
    except Exception as e:
        print(f"ERROR: Failed to initialize PolymarketClient: {e}")
        print("\nMake sure:")
        print("  1. PK is set in .env (64 hex chars, no 0x prefix)")
        print("  2. BROWSER_ADDRESS is set in .env (0x + 40 hex chars)")
        return
    
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
    
    # Real order size (1 USDC)
    size = 1.0
    
    print(f"\nPlacing REAL BUY order:")
    print(f"  Token: {token_yes}")
    print(f"  Price: {price}")
    print(f"  Size: {size} USDC")
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
        else:
            print("Check the error message above for details.")
        
        raise


if __name__ == "__main__":
    asyncio.run(main())


