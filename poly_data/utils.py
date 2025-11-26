import asyncio
import json
from typing import Optional

import pandas as pd

from app.config import (
    BotConfigSnapshot,
    DatabaseConfigProvider,
    GoogleSheetConfigProvider,
)


def pretty_print(txt, dic):
    print("\n", txt, json.dumps(dic, indent=4))


def _load_snapshot() -> BotConfigSnapshot:
    async def _load() -> BotConfigSnapshot:
        # Use database lock to prevent conflicts with other DB operations
        import poly_data.global_state as global_state
        global_state.db_lock.acquire(blocking=True, timeout=30)
        try:
            provider = DatabaseConfigProvider()
            try:
                # Load only active markets from database
                from app.config.repository import ConfigRepository
                repo = ConfigRepository()
                config = await repo.load_configuration(active_only=True)
                from app.config.repository import to_snapshot
                snapshot = to_snapshot(config)
                if snapshot.markets:
                    print(f"Loaded {len(snapshot.markets)} active markets from database")
                    return snapshot
            except Exception as exc:
                print(f"Database configuration load failed: {exc}. Falling back to Google Sheets.")
        finally:
            global_state.db_lock.release()

        sheet_provider = GoogleSheetConfigProvider()
        snapshot = await sheet_provider.fetch()
        print(f"Loaded {len(snapshot.markets)} markets from Google Sheets (fallback)")
        return snapshot

    # Check if there's already a running event loop
    try:
        loop = asyncio.get_running_loop()
        # If we're in a running loop, create a new event loop in a new thread
        import concurrent.futures
        
        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(_load())
            finally:
                new_loop.close()
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            return future.result()
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        return asyncio.run(_load())


def _snapshot_to_frames(snapshot: BotConfigSnapshot) -> tuple[pd.DataFrame, dict[str, dict]]:
    def _to_float(value: Optional[object], default: Optional[object]) -> Optional[float]:
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            try:
                return float(default) if default is not None else None
            except (TypeError, ValueError):
                return None

    market_records = []
    for market in snapshot.markets:
        metadata = dict(market.metadata or {})

        record = {
            "question": market.question,
            "answer1": metadata.get("answer1") or metadata.get("answer_yes"),
            "answer2": metadata.get("answer2") or metadata.get("answer_no"),
            "neg_risk": "TRUE" if market.neg_risk else "FALSE",
            "trade_size": _to_float(metadata.get("trade_size"), market.trade_size),
            "min_size": _to_float(metadata.get("min_size"), market.min_size) or 0,
            "max_spread": _to_float(metadata.get("max_spread"), market.max_spread) or 0,
            "tick_size": _to_float(metadata.get("tick_size"), market.tick_size) or 0.01,
            "max_size": _to_float(metadata.get("max_size"), market.max_size),
            "param_type": market.param_type,
            "token1": market.token_yes,
            "token2": market.token_no,
            "condition_id": market.condition_id,
            "market_slug": metadata.get("market_slug"),
        }

        for key, value in metadata.items():
            if key not in record or record[key] is None:
                record[key] = value

        market_records.append(record)

    df = pd.DataFrame(market_records)
    if not df.empty and "question" in df.columns:
        df = df[df["question"] != ""].reset_index(drop=True)

    strategies = {
        name: strategy.values for name, strategy in snapshot.strategies.items()
    }
    return df, strategies


def get_sheet_df(read_only: Optional[bool] = None):
    """
    Load configuration data from the database (preferred) or Google Sheets fallback.
    Returns a tuple of (markets dataframe, hyperparameters dict) to maintain compatibility
    with the legacy trading code.
    """
    snapshot = _load_snapshot()
    return _snapshot_to_frames(snapshot)
