import time

import poly_data.global_state as global_state
from app.services.persistence import persist_position_state
from poly_data.utils import get_sheet_df

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

        condition_id = global_state.TOKEN_MARKETS.get(asset)
        if condition_id:
            persist_position_state(
                condition_id,
                asset,
                global_state.positions[asset]['size'],
                global_state.positions[asset]['avgPrice'],
            )

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

    condition_id = global_state.TOKEN_MARKETS.get(str(token))
    if condition_id:
        persist_position_state(
            condition_id,
            str(token),
            global_state.positions[token]['size'],
            global_state.positions[token]['avgPrice'],
        )

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

    

def update_active_markets():
    """
    Check database for active markets with running bots.
    Updates global_state.active_condition_ids.
    Uses a lock to prevent concurrent database operations.
    """
    # Use lock to prevent concurrent database operations
    # Wait for other operations to finish (blocking=True) so we always get the query done
    global_state.db_lock.acquire(blocking=True, timeout=30)
    
    try:
        import asyncio
        from app.database.session import get_session
        from app.database.models import Market, BotRun
        from sqlalchemy import select, text
        
        async def _fetch_active():
            try:
                async with get_session() as session:
                    # Get condition_ids of markets with running bots
                    stmt = (
                        select(Market.condition_id)
                        .join(BotRun, BotRun.market_id == Market.id)
                        .where(
                            Market.status == "active",
                            text("CAST(bot_run.status AS TEXT) = 'running'")
                        )
                    )
                    result = await session.execute(stmt)
                    condition_ids = {row[0] for row in result.all()}
                    return condition_ids
            except Exception as db_error:
                # Handle connection errors gracefully - re-raise to trigger fallback
                error_msg = str(db_error)
                if "ConnectionClosedError" in error_msg or "websocket" in error_msg.lower():
                    print(f"Database connection closed, will try fallback method")
                else:
                    print(f"Database query error: {db_error}")
                raise  # Re-raise to trigger fallback
        
        # Always create a new event loop to avoid conflicts with existing async operations
        import concurrent.futures
        
        def run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(_fetch_active())
            finally:
                new_loop.close()
        
        # Run in a separate thread to avoid blocking and connection conflicts
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop)
            try:
                active_ids = future.result(timeout=10)
            except concurrent.futures.TimeoutError:
                print("Timeout waiting for active markets query")
                active_ids = set()
            except Exception as e:
                error_msg = str(e)
                if "another operation is in progress" in error_msg:
                    print(f"Database operation conflict detected, will retry on next cycle")
                else:
                    print(f"Database query error: {e}")
                active_ids = set()
        
        # If async query failed, the error was already logged
        # We'll keep the previous active_condition_ids and retry on next cycle
        # This prevents clearing active markets on transient connection errors
        
        # Only update if query succeeded (even if result is empty)
        # On error, keep previous state to avoid clearing active markets
        if 'active_ids' in locals():
            global_state.active_condition_ids = active_ids
            print(f"Updated active markets: {len(active_ids)} markets with running bots")
            if active_ids:
                print(f"Active condition_ids: {list(active_ids)[:5]}...")  # Show first 5
            elif len(active_ids) == 0:
                print("WARNING: No active markets found. Make sure:")
                print("  1. At least one market has status='active' in database")
                print("  2. At least one bot_run has status='running' for that market")
                print("  3. Check with: ./check_why_no_active_markets.sh")
        else:
            print("Query failed, keeping previous active_condition_ids")
    except Exception as e:
        print(f"Failed to update active markets from database: {e}")
        # Don't clear active_condition_ids on error, keep previous state
        print("Keeping previous active_condition_ids due to error")
    finally:
        # Always release the lock
        global_state.db_lock.release()

def update_markets():
    # Get markets from database (which already filters for active markets with running bots)
    # This avoids a separate query that conflicts with the config loading
    received_df, received_params = get_sheet_df()

    if len(received_df) > 0:
        global_state.df, global_state.params = received_df.copy(), received_params
    
    # Extract condition_ids from loaded markets
    # If from database: will have only active markets (typically 1-10)
    # If from Google Sheets: will have all markets (~2607) - we'll filter by checking database separately
    if global_state.df is not None and 'condition_id' in global_state.df.columns:
        num_markets = len(global_state.df)
        
        # If we have a small number of markets (< 100), they're from database - use them directly
        if num_markets < 100:
            active_condition_ids = set(global_state.df['condition_id'].dropna().unique())
            global_state.active_condition_ids = active_condition_ids
            print(f"Updated active markets from loaded config: {len(active_condition_ids)} markets with running bots")
            if active_condition_ids:
                print(f"Active condition_ids: {list(active_condition_ids)[:5]}...")  # Show first 5
        else:
            # Too many markets = Google Sheets fallback
            # Don't query database (causes conflicts) - just keep previous active_condition_ids
            # The bot will only trade markets that are in both the dataframe AND active_condition_ids
            print(f"Google Sheets fallback detected ({num_markets} markets). Keeping previous active markets.")
            if len(global_state.active_condition_ids) == 0:
                print("WARNING: No active markets cached. Bot will not trade until database query succeeds.")
    else:
        # No condition_ids in dataframe - keep previous state
        print("No condition_ids in dataframe, keeping previous active markets")

    # Clear and rebuild all_tokens, but only for active markets
    global_state.all_tokens = []
    
    for _, row in global_state.df.iterrows():
        condition_id = row.get('condition_id')
        
        # Only process markets that are active (have running bot)
        if condition_id and condition_id not in global_state.active_condition_ids:
            continue  # Skip inactive markets
        
        for col in ['token1', 'token2']:
            row[col] = str(row[col])

        if row['token1'] not in global_state.all_tokens:
            global_state.all_tokens.append(row['token1'])

        if row['token1'] not in global_state.REVERSE_TOKENS:
            global_state.REVERSE_TOKENS[row['token1']] = row['token2']

        if row['token2'] not in global_state.REVERSE_TOKENS:
            global_state.REVERSE_TOKENS[row['token2']] = row['token1']

        global_state.TOKEN_MARKETS[row['token1']] = row['condition_id']
        global_state.TOKEN_MARKETS[row['token2']] = row['condition_id']

        for col2 in [f"{row['token1']}_buy", f"{row['token1']}_sell", f"{row['token2']}_buy", f"{row['token2']}_sell"]:
            if col2 not in global_state.performing:
                global_state.performing[col2] = set()
    
    print(f"Subscribing to {len(global_state.all_tokens)} tokens from {len(global_state.active_condition_ids)} active markets")