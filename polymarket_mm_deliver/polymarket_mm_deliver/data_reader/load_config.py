# load_config.py
# -*- coding: utf-8 -*-
"""
Configuration loader for time-bucket MM strategy.

- Provides a DEFAULT_CONFIG that matches the current hard-coded behavior.
- Optionally loads a JSON config file and recursively overrides defaults.
- File path resolution:
    1) If load_config(path=...) is called with an explicit path, use that.
    2) Otherwise, check env var TIME_BUCKET_MM_CONFIG.
    3) Otherwise, fall back to "time_bucket_mm_config.json" in current directory.

Usage in strategy code:

    from load_config import CONFIG

    ENTRY_BID_THRESHOLD = CONFIG["entry_exit"]["ENTRY_BID_THRESHOLD"]

The JSON file is expected to be standard JSON (no comments). If you want
to keep a commented JSONC version for documentation, store it separately
and strip comments before using, or maintain a clean runtime JSON file.
"""

import copy
import json
import logging
import os
from typing import Any, Dict, Optional


# -----------------------------------------------------------------------------
# Default config (matches current behavior)
# -----------------------------------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "api": {
        "PRIVATE_KEY": "",
        "PROXY_ADDRESS": None,
        "SIGNATURE_TYPE": 1,
        "CHAIN_ID": 137,
    },
    "entry_exit": {
        # Open position only if bid >= ENTRY_BID_THRESHOLD
        "ENTRY_BID_THRESHOLD": 0.6,
        # Take-profit must be at least entry_price + MIN_TP_INCREMENT
        "MIN_TP_INCREMENT": 0.01,
        # If entry_price > 0.7, stop_loss_trigger = max(entry_price - SL_OFFSET, SL_FLOOR)
        "SL_OFFSET": 0.2,
        # Lower bound for stop_loss_trigger
        "SL_FLOOR": 0.5,
        # Upper bound for TP price, to avoid hitting protocol max price (e.g. 0.99)
        "MAX_TP_PRICE": 0.99,
        # Actual price used when placing SL orders (normal exit SL and late SL)
        "SL_ORDER_PRICE": 0.01,
    },
    "time_windows": {
        # Total duration of a round (seconds) – 15 minutes
        "CONTRACT_DURATION_SEC": 15 * 60,
        # Length of the "late" window, in seconds (last 2 minutes)
        "LATE_WINDOW_SEC": 120,
        # ENTRY re-quote wait time: only consider cancel & re-enter
        # if no fill for more than this many seconds
        "ENTRY_REQUOTE_WAIT_SEC": 2.0,
    },
    "late_mode": {
        # In LATE_HOLD, trigger SL when bid <= LATE_SL_TRIGGER
        "LATE_SL_TRIGGER": 0.7,
        # Late re-entry only when bid >= this threshold
        "LATE_REENTRY_ENTRY_THRESHOLD": 0.9,
        # Global switch for late re-entry behavior
        "ENABLE_LATE_REENTRY": True,
        # Max number of allowed late re-entries per leg (current logic: 1)
        "MAX_LATE_REENTRIES": 1,
    },
    "position_control": {
        # Time-bucketed cap schedule, based on elapsed seconds within the round
        # elapsed = now - bucket_ts
        # pick the first interval where start_sec <= elapsed < end_sec
        "CAP_SCHEDULE": [
            {"start_sec": 0, "end_sec": 300, "cap_usd": 7.0},
            {"start_sec": 300, "end_sec": 600, "cap_usd": 7.5},
            {"start_sec": 600, "end_sec": 900, "cap_usd": 8.0},
        ],
        # If dust_size + current on_pos < MIN_TRADE_SIZE → treat as dust only,
        # do not place EXIT orders in this round
        "MIN_TRADE_SIZE": 5.0,
        # Whether to merge cross-round dust positions into the current round EXIT
        "ENABLE_DUST_MERGE": True,
    },
    "micro_tuning": {
        # Minimal bid improvement required to cancel & re-enter an ENTRY order
        "ENTRY_REQUOTE_MIN_IMPROVE": 0.03,
        # Size threshold used when querying remote leg positions; positions smaller
        # than this may be ignored by the API (current logic uses 0.0)
        "REMOTE_POS_SIZE_THRESHOLD": 0.0,
        # Leg selection strategy when choosing between YES/NO at the start of the round:
        #   "HIGHEST_BID" (current behavior) – choose the leg with the higher bid,
        #       among those with bid >= ENTRY_BID_THRESHOLD.
        #   "YES_ONLY"    – only trade the YES leg.
        #   "NO_ONLY"     – only trade the NO leg.
        #   "FIXED_PRIORITY" – future extension; choose according to a fixed list.
        "LEG_SELECTION_MODE": "HIGHEST_BID",
    },
}


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively update dict `base` with values from `override`.

    - If a key exists in both and both values are dicts -> recurse.
    - Otherwise, the value from `override` replaces the one in `base`.
    - Lists and scalars in override fully replace the base value.
    """
    for k, v in override.items():
        if (
            k in base
            and isinstance(base[k], dict)
            and isinstance(v, dict)
        ):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def get_default_config() -> Dict[str, Any]:
    """
    Return a deep copy of DEFAULT_CONFIG, so callers can safely mutate it.
    """
    return copy.deepcopy(DEFAULT_CONFIG)


def load_config(
    path: Optional[str] = None,
    *,
    env_var: str = "TIME_BUCKET_MM_CONFIG",
) -> Dict[str, Any]:
    """
    Load configuration from JSON file and merge it into DEFAULT_CONFIG.

    Precedence:
        1) If `path` is provided, use that path.
        2) Else, if env var `env_var` (default: TIME_BUCKET_MM_CONFIG) is set,
           use that as the path.
        3) Else, use "time_bucket_mm_config.json" in current working directory.

    If the file is missing or invalid, DEFAULT_CONFIG is returned.
    Only keys present in the JSON are overridden; everything else falls back
    to DEFAULT_CONFIG.
    """
    config = get_default_config()

    if path is None:
        path = os.getenv(env_var, "config.json")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.info("Config file not found: %s; using DEFAULT_CONFIG", path)
        return config
    except json.JSONDecodeError as e:
        logging.error("Failed to parse JSON config %s: %s; using DEFAULT_CONFIG", path, e)
        return config
    except Exception as e:
        logging.error("Error loading config %s: %s; using DEFAULT_CONFIG", path, e)
        return config

    if not isinstance(data, dict):
        logging.error("Top-level config in %s is not a JSON object; using DEFAULT_CONFIG", path)
        return config

    _deep_update(config, data)
    return config


# Module-level config: convenient default
CONFIG: Dict[str, Any] = load_config()