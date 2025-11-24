#!/usr/bin/env python3
"""
Script to fetch and display currently open markets from Polymarket.

This script connects to Polymarket's API and fetches all currently active/open markets,
then displays them in a readable format.
"""

import pandas as pd
from data_updater.trading_utils import get_clob_client
from dotenv import load_dotenv

load_dotenv()


def fetch_all_markets(limit=None):
    """
    Fetch all currently open markets from Polymarket.
    
    Args:
        limit: Optional limit on number of markets to fetch (None = all)
    
    Returns:
        DataFrame: All markets with key information
    """
    client = get_clob_client()
    
    if client is None:
        print("Error: Could not create Polymarket client. Check your .env file has PK set.")
        return pd.DataFrame()
    
    print("Fetching markets from Polymarket...")
    cursor = ""
    all_markets = []
    count = 0
    
    while True:
        try:
            # Fetch markets from Polymarket API
            markets = client.get_sampling_markets(next_cursor=cursor)
            
            if not markets or 'data' not in markets:
                break
                
            markets_df = pd.DataFrame(markets['data'])
            all_markets.append(markets_df)
            count += len(markets_df)
            
            print(f"Fetched {count} markets so far...")
            
            # Check if we've reached the limit
            if limit and count >= limit:
                break
            
            # Get next cursor for pagination
            cursor = markets.get('next_cursor')
            
            if cursor is None:
                break
                
        except Exception as e:
            print(f"Error fetching markets: {e}")
            break
    
    if not all_markets:
        print("No markets found.")
        return pd.DataFrame()
    
    # Combine all markets into one DataFrame
    all_df = pd.concat(all_markets, ignore_index=True)
    
    # Remove duplicates if any
    all_df = all_df.drop_duplicates(subset=['condition_id'], ignore_index=True)
    
    if limit:
        all_df = all_df.head(limit)
    
    return all_df


def display_markets(markets_df):
    """
    Display markets in a readable format.
    
    Args:
        markets_df: DataFrame containing market data
    """
    if markets_df.empty:
        print("No markets to display.")
        return
    
    print(f"\n{'='*80}")
    print(f"FOUND {len(markets_df)} OPEN MARKETS ON POLYMARKET")
    print(f"{'='*80}\n")
    
    # Select and format key columns for display
    display_cols = ['question', 'condition_id', 'end_date_iso', 'market_slug']
    
    # Check which columns exist
    available_cols = [col for col in display_cols if col in markets_df.columns]
    
    if not available_cols:
        print("Available columns:", list(markets_df.columns))
        return
    
    # Display markets
    for idx, row in markets_df.iterrows():
        print(f"\n{idx + 1}. {row.get('question', 'N/A')}")
        print(f"   Condition ID: {row.get('condition_id', 'N/A')}")
        print(f"   End Date: {row.get('end_date_iso', 'N/A')}")
        print(f"   Market Slug: {row.get('market_slug', 'N/A')}")
        
        # Display token information if available
        if 'tokens' in row and isinstance(row['tokens'], list):
            print(f"   Outcomes:")
            for token in row['tokens']:
                if isinstance(token, dict):
                    outcome = token.get('outcome', 'N/A')
                    token_id = token.get('token_id', 'N/A')
                    print(f"     - {outcome} (Token: {token_id})")
        
        # Display rewards if available
        if 'rewards' in row and isinstance(row['rewards'], dict):
            rewards = row['rewards']
            if 'rewards_daily_rate' in rewards:
                print(f"   Daily Reward Rate: {rewards.get('rewards_daily_rate', 0)}")
            if 'min_size' in rewards:
                print(f"   Min Size: {rewards.get('min_size', 0)}")
        
        print("-" * 80)


def save_to_csv(markets_df, filename='current_polymarket_markets.csv'):
    """
    Save markets to a CSV file.
    
    Args:
        markets_df: DataFrame containing market data
        filename: Output filename
    """
    if markets_df.empty:
        print("No markets to save.")
        return
    
    # Flatten nested columns for CSV
    flat_df = markets_df.copy()
    
    # Extract token information
    if 'tokens' in flat_df.columns:
        flat_df['token_yes'] = flat_df['tokens'].apply(
            lambda x: x[0].get('token_id', '') if isinstance(x, list) and len(x) > 0 else ''
        )
        flat_df['token_no'] = flat_df['tokens'].apply(
            lambda x: x[1].get('token_id', '') if isinstance(x, list) and len(x) > 1 else ''
        )
        flat_df['outcome_yes'] = flat_df['tokens'].apply(
            lambda x: x[0].get('outcome', '') if isinstance(x, list) and len(x) > 0 else ''
        )
        flat_df['outcome_no'] = flat_df['tokens'].apply(
            lambda x: x[1].get('outcome', '') if isinstance(x, list) and len(x) > 1 else ''
        )
    
    # Extract reward information
    if 'rewards' in flat_df.columns:
        flat_df['rewards_daily_rate'] = flat_df['rewards'].apply(
            lambda x: x.get('rewards_daily_rate', 0) if isinstance(x, dict) else 0
        )
        flat_df['min_size'] = flat_df['rewards'].apply(
            lambda x: x.get('min_size', 0) if isinstance(x, dict) else 0
        )
        flat_df['max_spread'] = flat_df['rewards'].apply(
            lambda x: x.get('max_spread', 0) if isinstance(x, dict) else 0
        )
    
    # Select key columns for CSV
    csv_cols = ['question', 'condition_id', 'end_date_iso', 'market_slug', 
                'token_yes', 'token_no', 'outcome_yes', 'outcome_no',
                'rewards_daily_rate', 'min_size', 'max_spread']
    
    # Only include columns that exist
    csv_cols = [col for col in csv_cols if col in flat_df.columns]
    
    flat_df[csv_cols].to_csv(filename, index=False)
    print(f"\n✅ Saved {len(flat_df)} markets to {filename}")


def main():
    """Main function to fetch and display markets."""
    import sys
    
    # Check for command line arguments
    limit = None
    save_csv = False
    
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print("Usage: python fetch_current_markets.py [limit] [--save-csv]")
            print("  limit: Optional number of markets to fetch (default: all)")
            print("  --save-csv: Save results to CSV file")
            return
    
    if '--save-csv' in sys.argv:
        save_csv = True
    
    # Fetch markets
    markets_df = fetch_all_markets(limit=limit)
    
    if markets_df.empty:
        print("No markets found. Check your connection and API credentials.")
        return
    
    # Display markets
    display_markets(markets_df)
    
    # Save to CSV if requested
    if save_csv:
        save_to_csv(markets_df)
    
    print(f"\n✅ Total markets found: {len(markets_df)}")


if __name__ == "__main__":
    main()

