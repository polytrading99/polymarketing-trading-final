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
        # Create empty selection DataFrame with required 'question' column to avoid KeyError
        empty_sel_df = pd.DataFrame(columns=['question'])  # Empty selection - use all markets
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
    
    Note: This function must be called from a synchronous context.
    It uses a thread pool to run async code to avoid event loop conflicts.
    """
    try:
        import asyncio
        import sys
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        
        # Add project root to path
        PROJECT_ROOT = Path(__file__).parent.parent
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        
        async def _load_active_markets():
            try:
                # Bypass Settings validation by using environment variables directly
                import os
                from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
                from sqlalchemy.orm import sessionmaker
                from sqlalchemy import select
                
                # Get database URL directly from environment
                database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://poly:poly@postgres:5432/poly")
                
                # Create engine and session directly (bypassing Settings)
                engine = create_async_engine(database_url, echo=False)
                from sqlalchemy.ext.asyncio import async_sessionmaker
                async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
                
                # Import models
                from app.database.models import Market, MarketConfig, Strategy
                
                market_data = []
                async with async_session_factory() as session:
                    # Get active markets directly
                    from sqlalchemy import and_
                    markets_stmt = select(Market).where(Market.status == "active")
                    markets_result = await session.execute(markets_stmt)
                    markets = markets_result.scalars().all()
                    
                    for market in markets:
                        # Get active config for this market
                        config_stmt = select(MarketConfig).where(
                            MarketConfig.market_id == market.id,
                            MarketConfig.is_active == True
                        )
                        config_result = await session.execute(config_stmt)
                        config = config_result.scalar_one_or_none()
                        
                        if config:
                            # Get strategy name for param_type, default to "default"
                            param_type = "default"
                            if config.strategy_id:
                                strategy_stmt = select(Strategy).where(Strategy.id == config.strategy_id)
                                strategy_result = await session.execute(strategy_stmt)
                                strategy = strategy_result.scalar_one_or_none()
                                if strategy:
                                    param_type = strategy.name
                            
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
                                'param_type': param_type,
                                'answer1': 'YES',  # Default answers
                                'answer2': 'NO',
                            })
                
                await engine.dispose()
                return pd.DataFrame(market_data) if market_data else pd.DataFrame()
                
            except Exception as e:
                # Catch all errors including Settings validation errors
                # Use safe error formatting to avoid TypeError
                try:
                    error_msg = str(e) if e else "Unknown error"
                    error_type = type(e).__name__ if e else "Unknown"
                    print(f"Error loading markets from database: {error_type}: {error_msg}")
                except Exception:
                    print(f"Error loading markets from database: Exception occurred (could not format error)")
                # Don't print full traceback for Settings errors - they're expected
                return pd.DataFrame()
        
        # Use ThreadPoolExecutor to run async code in a separate thread
        # This avoids event loop conflicts when called from an async context
        def run_in_thread():
            # Create a new event loop in this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_load_active_markets())
            finally:
                loop.close()
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result(timeout=30)  # 30 second timeout
            
    except Exception as e:
        # Safe error formatting to avoid TypeError
        try:
            print(f"Error syncing markets from database: {str(e)}")
        except Exception:
            print(f"Error syncing markets from database: Exception occurred")
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
        
        # Ensure all required columns exist with defaults
        required_cols = {
            'trade_size': 1.0,
            'best_bid': 0.5,  # Default mid price
            'best_ask': 0.5,  # Default mid price
            '3_hour': 0.0,  # Default volatility
        }
        for col, default_val in required_cols.items():
            if col not in global_state.df.columns:
                global_state.df[col] = default_val
        
        # Initialize default parameters if not already set
        if not global_state.params:
            # Default trading parameters
            global_state.params = {
                "default": {
                    "stop_loss_threshold": -5.0,  # Stop loss at -5%
                    "take_profit_threshold": 2.0,  # Take profit at +2%
                    "spread_threshold": 0.02,  # Max spread for stop loss (2 cents)
                    "volatility_threshold": 10.0,  # Max volatility
                    "sleep_period": 1,  # Hours to wait after stop loss
                }
            }
        else:
            # Ensure "default" param_type exists
            if "default" not in global_state.params:
                global_state.params["default"] = {
                    "stop_loss_threshold": -5.0,
                    "take_profit_threshold": 2.0,
                    "spread_threshold": 0.02,
                    "volatility_threshold": 10.0,
                    "sleep_period": 1,
                }
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
    
    # Ensure all required columns exist with defaults (for any source)
    required_cols = {
        'trade_size': 1.0,
        'best_bid': 0.5,  # Default mid price
        'best_ask': 0.5,  # Default mid price
        '3_hour': 0.0,  # Default volatility
        'param_type': 'default',
        'answer1': 'YES',
        'answer2': 'NO',
    }
    for col, default_val in required_cols.items():
        if col not in global_state.df.columns:
            global_state.df[col] = default_val

    # Process markets to set up tokens and reverse mappings
    try:
        for idx, row in global_state.df.iterrows():
            try:
                # Access DataFrame directly instead of Series to avoid issues
                token1_val = global_state.df.at[idx, 'token1']
                token2_val = global_state.df.at[idx, 'token2']
                
                # Handle case where values might be None or NaN
                if pd.isna(token1_val) or token1_val is None:
                    print(f"Warning: token1 is None/NaN for row {idx}, skipping")
                    continue
                if pd.isna(token2_val) or token2_val is None:
                    print(f"Warning: token2 is None/NaN for row {idx}, skipping")
                    continue
                
                token1 = str(token1_val)
                token2 = str(token2_val)
                
                # Update DataFrame to ensure strings
                global_state.df.at[idx, 'token1'] = token1
                global_state.df.at[idx, 'token2'] = token2

                if token1 not in global_state.all_tokens:
                    global_state.all_tokens.append(token1)

                if token1 not in global_state.REVERSE_TOKENS:
                    global_state.REVERSE_TOKENS[token1] = token2

                if token2 not in global_state.REVERSE_TOKENS:
                    global_state.REVERSE_TOKENS[token2] = token1
                
                # Store mapping from token to condition_id
                condition_id = str(global_state.df.at[idx, 'condition_id'])
                global_state.TOKEN_TO_CONDITION_ID[token1] = condition_id
                global_state.TOKEN_TO_CONDITION_ID[token2] = condition_id

                for col2 in [f"{token1}_buy", f"{token1}_sell", f"{token2}_buy", f"{token2}_sell"]:
                    if col2 not in global_state.performing:
                        global_state.performing[col2] = set()
            except Exception as e:
                # Safe error formatting
                try:
                    print(f"Error processing market row {idx}: {type(e).__name__}: {str(e)}")
                except Exception:
                    print(f"Error processing market row {idx}: Exception occurred")
                continue
    except Exception as e:
        # Safe error formatting
        try:
            print(f"Error in market processing loop: {str(e)}")
        except Exception:
            print(f"Error in market processing loop: Exception occurred")