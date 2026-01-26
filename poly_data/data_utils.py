import poly_data.global_state as global_state
from poly_data.utils import get_sheet_df
import time
import pandas as pd
import traceback

#sth here seems to be removing the position
def update_positions(avgOnly=False):
    pos_df = global_state.client.get_all_positions()

    for idx, row in pos_df.iterrows():
        asset = str(row['asset'])

        if asset in  global_state.positions:
            position = global_state.positions[asset].copy()
        else:
            position = {'size': 0, 'avgPrice': 0}

        position['avgPrice'] = row['avgPrice']

        if not avgOnly:
            position['size'] = row['size']
        else:
            
            for col in [f"{asset}_sell", f"{asset}_buy"]:
                #need to review this
                if col not in global_state.performing or not isinstance(global_state.performing[col], set) or len(global_state.performing[col]) == 0:
                    try:
                        old_size = position['size']
                    except:
                        old_size = 0

                    if asset in  global_state.last_trade_update:
                        if time.time() - global_state.last_trade_update[asset] < 5:
                            print(f"Skipping update for {asset} because last trade update was less than 5 seconds ago")
                            continue

                    if old_size != row['size']:
                        print(f"No trades are pending. Updating position from {old_size} to {row['size']} and avgPrice to {row['avgPrice']} using API")
    
                    position['size'] = row['size']
                else:
                    print(f"ALERT: Skipping update for {asset} because there are trades pending for {col} looking like {global_state.performing[col]}")
    
        global_state.positions[asset] = position

def get_position(token):
    token = str(token)
    if token in global_state.positions:
        return global_state.positions[token]
    else:
        return {'size': 0, 'avgPrice': 0}

def set_position(token, side, size, price, source='websocket'):
    token = str(token)
    size = float(size)
    price = float(price)

    global_state.last_trade_update[token] = time.time()
    
    if side.lower() == 'sell':
        size *= -1

    if token in global_state.positions:
        
        prev_price = global_state.positions[token]['avgPrice']
        prev_size = global_state.positions[token]['size']


        if size > 0:
            if prev_size == 0:
                # Starting a new position
                avgPrice_new = price
            else:
                # Buying more; update average price
                avgPrice_new = (prev_price * prev_size + price * size) / (prev_size + size)
        elif size < 0:
            # Selling; average price remains the same
            avgPrice_new = prev_price
        else:
            # No change in position
            avgPrice_new = prev_price


        global_state.positions[token]['size'] += size
        global_state.positions[token]['avgPrice'] = avgPrice_new
    else:
        global_state.positions[token] = {'size': size, 'avgPrice': price}

    print(f"Updated position from {source}, set to ", global_state.positions[token])

def update_orders():
    all_orders = global_state.client.get_all_orders()

    orders = {}

    if len(all_orders) > 0:
            for token in all_orders['asset_id'].unique():
                
                if token not in orders:
                    orders[str(token)] = {'buy': {'price': 0, 'size': 0}, 'sell': {'price': 0, 'size': 0}}

                curr_orders = all_orders[all_orders['asset_id'] == str(token)]
                
                if len(curr_orders) > 0:
                    sel_orders = {}
                    sel_orders['buy'] = curr_orders[curr_orders['side'] == 'BUY']
                    sel_orders['sell'] = curr_orders[curr_orders['side'] == 'SELL']

                    for type in ['buy', 'sell']:
                        curr = sel_orders[type]

                        if len(curr) > 1:
                            print("Multiple orders found, cancelling")
                            global_state.client.cancel_all_asset(token)
                            orders[str(token)] = {'buy': {'price': 0, 'size': 0}, 'sell': {'price': 0, 'size': 0}}
                        elif len(curr) == 1:
                            orders[str(token)][type]['price'] = float(curr.iloc[0]['price'])
                            orders[str(token)][type]['size'] = float(curr.iloc[0]['original_size'] - curr.iloc[0]['size_matched'])

    global_state.orders = orders

def get_order(token):
    token = str(token)
    if token in global_state.orders:

        if 'buy' not in global_state.orders[token]:
            global_state.orders[token]['buy'] = {'price': 0, 'size': 0}

        if 'sell' not in global_state.orders[token]:
            global_state.orders[token]['sell'] = {'price': 0, 'size': 0}

        return global_state.orders[token]
    else:
        return {'buy': {'price': 0, 'size': 0}, 'sell': {'price': 0, 'size': 0}}
    
def set_order(token, side, size, price):
    curr = {}
    curr = {side: {'price': 0, 'size': 0}}

    curr[side]['size'] = float(size)
    curr[side]['price'] = float(price)

    global_state.orders[str(token)] = curr
    print("Updated order, set to ", curr)

    

def fetch_markets_from_polymarket():
    """
    Fetch markets directly from Polymarket API instead of Google Sheets.
    Returns DataFrame with market data and empty params dict.
    """
    try:
        if not hasattr(global_state, 'client') or global_state.client is None:
            print("Warning: PolymarketClient not initialized, cannot fetch markets")
            return pd.DataFrame(), {}
        
        from data_updater.find_markets import get_all_markets, get_all_results, get_markets
        
        # Fetch all markets from Polymarket
        print("Fetching markets from Polymarket API...")
        all_markets_df = get_all_markets(global_state.client.client)
        
        if len(all_markets_df) == 0:
            print("No markets fetched from Polymarket API")
            return pd.DataFrame(), {}
        
        # Process markets to get order book data
        print(f"Processing {len(all_markets_df)} markets...")
        all_results = get_all_results(all_markets_df, global_state.client.client, max_workers=5)
        
        if len(all_results) == 0:
            print("No market results processed")
            return pd.DataFrame(), {}
        
        # Convert to DataFrame and format
        empty_sel_df = pd.DataFrame()  # Empty selection - use all markets
        all_data, markets_df = get_markets(all_results, empty_sel_df, maker_reward=0.75)
        
        # Format columns to match expected structure
        if len(markets_df) > 0:
            # Ensure required columns exist
            required_cols = ['question', 'token1', 'token2', 'condition_id', 'neg_risk', 'tick_size', 'min_size', 'max_size', 'max_spread']
            for col in required_cols:
                if col not in markets_df.columns:
                    if col == 'neg_risk':
                        markets_df[col] = False
                    elif col in ['tick_size', 'min_size', 'max_size', 'max_spread']:
                        markets_df[col] = 0.01 if col == 'tick_size' else 0
                    else:
                        markets_df[col] = ''
            
            print(f"Successfully fetched {len(markets_df)} markets from Polymarket API")
            return markets_df, {}
        else:
            print("No markets returned after processing")
            return pd.DataFrame(), {}
            
    except Exception as e:
        print(f"Error fetching markets from Polymarket API: {e}")
        print(traceback.format_exc())
        return pd.DataFrame(), {}


def sync_markets_from_database():
    """
    Sync active markets from database to bot's trading list.
    This allows markets activated in the UI to be traded by the bot.
    """
    try:
        import asyncio
        import sys
        from pathlib import Path
        
        # Add project root to path
        PROJECT_ROOT = Path(__file__).parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        
        async def _load_active_markets():
            from app.config import ConfigRepository
            from app.database.session import get_session
            from app.database.models import MarketConfig
            
            repository = ConfigRepository()
            markets = await repository.list_markets(active_only=True)
            
            # Get market configs with their parameters
            async with get_session() as session:
                from sqlalchemy import select
                
                market_data = []
                for market in markets:
                    # Get active config for this market
                    config_stmt = select(MarketConfig).where(
                        MarketConfig.market_id == market.id,
                        MarketConfig.is_active == True
                    )
                    config = await session.scalar(config_stmt)
                    
                    if config:
                        market_data.append({
                            'question': market.question,
                            'condition_id': market.condition_id,
                            'token1': market.token_yes,
                            'token2': market.token_no,
                            'neg_risk': market.neg_risk,
                            'tick_size': float(config.tick_size) if config.tick_size else 0.01,
                            'min_size': float(config.min_size) if config.min_size else 0,
                            'max_size': float(config.max_size) if config.max_size else None,
                            'max_spread': float(config.max_spread) if config.max_spread else 5.0,
                            'trade_size': float(config.trade_size) if config.trade_size else 1.0,
                        })
                
                return pd.DataFrame(market_data) if market_data else pd.DataFrame()
        
        # Run async function
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop.is_running():
            # If loop is already running, we need to use a different approach
            # For now, return empty DataFrame - will be handled by fallback
            return pd.DataFrame()
        else:
            db_df = loop.run_until_complete(_load_active_markets())
            return db_df
            
    except Exception as e:
        print(f"Error syncing markets from database: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def update_markets():
    """
    Update market data from database (active markets) and Polymarket API.
    Database markets take priority - if there are active markets in DB, use those.
    Falls back to Polymarket API if no active DB markets.
    """
    # First, try to sync active markets from database
    db_df = sync_markets_from_database()
    
    if len(db_df) > 0:
        print(f"Loaded {len(db_df)} active markets from database")
        # Use database markets
        global_state.df = db_df.copy()
        global_state.params = {}  # No params from database for now
    else:
        # Fallback to Polymarket API or Google Sheets
        received_df, received_params = fetch_markets_from_polymarket()
        
        # Fallback to Google Sheets if API fetch failed or returned empty
        if len(received_df) == 0:
            print("Falling back to Google Sheets for market data...")
            try:
                received_df, received_params = get_sheet_df()
            except Exception as e:
                print(f"Error fetching from Google Sheets: {e}")
                received_params = {}

        if len(received_df) > 0:
            global_state.df, global_state.params = received_df.copy(), received_params
        else:
            print("Warning: No market data available")
            return

    # Process markets to set up tokens and reverse mappings
    for _, row in global_state.df.iterrows():
        for col in ['token1', 'token2']:
            row[col] = str(row[col])

        if row['token1'] not in global_state.all_tokens:
            global_state.all_tokens.append(row['token1'])

        if row['token1'] not in global_state.REVERSE_TOKENS:
            global_state.REVERSE_TOKENS[row['token1']] = row['token2']

        if row['token2'] not in global_state.REVERSE_TOKENS:
            global_state.REVERSE_TOKENS[row['token2']] = row['token1']

        for col2 in [f"{row['token1']}_buy", f"{row['token1']}_sell", f"{row['token2']}_buy", f"{row['token2']}_sell"]:
            if col2 not in global_state.performing:
                global_state.performing[col2] = set()