#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main entry: run time_bucket_mm.run_single_round() round by round.

This version does the following:

- In main:
    * Create and reuse a single ShmRingReader(SHM_NAME) for all rounds.
    * For each round:
        - Read one frame `first_frame` from shm, obtain bucket_ts.
        - Call resolve_market_for_bucket(bucket_ts) to get (market_id, yes_token, no_token).
        - Pass shm_reader + first_frame + market_info into run_single_round().

- In time_bucket_mm:
    * run_single_round(...) :
        - If these parameters are provided, it will NOT re-parse bucket/market or close shm_reader.
        - If no parameters are provided (e.g. running `python time_bucket_mm.py` directly),
          it keeps the old behavior: create its own shm_reader and resolve everything itself.
"""

import time
import traceback

from data_reader.shm_reader import ShmRingReader
from strategy.time_bucket_mm import (
    run_single_round,
    resolve_market_for_bucket,
    SHM_NAME,
)


def main_loop():
    round_id = 0

    # Create a single shm_reader for the whole process and reuse it across rounds
    shm_reader = ShmRingReader(SHM_NAME)

    try:
        while True:
            round_id += 1
            print("\n" + "=" * 80)
            print(f"[MAIN-LOOP] >>>>>>> START ROUND #{round_id} <<<<<<<")
            print("=" * 80 + "\n")

            try:
                # Read one frame from shm to determine the current 15m bucket
                first_frame = shm_reader.read_next_blocking()
                bucket_ts = int(first_frame["bucket_ts"])
                yes_bid = float(first_frame["yes_bid"])
                no_bid = float(first_frame["no_bid"])

                print(
                    f"[MAIN-LOOP] first_frame: bucket_ts={bucket_ts}, "
                    f"yes_bid={yes_bid:.2f}, no_bid={no_bid:.2f}"
                )

                # Resolve the BTC 15m contract in main
                market_id, yes_token_id, no_token_id = resolve_market_for_bucket(bucket_ts)
                print(
                    f"[MAIN-LOOP] market resolved: market_id={market_id}, "
                    f"yes_token={yes_token_id}, no_token={no_token_id}"
                )

                # Pass environment (shm_reader + first_frame + market info) into the strategy
                run_single_round(
                    shm_reader=shm_reader,
                    first_frame=first_frame,
                    market_info=(market_id, yes_token_id, no_token_id),
                )

            except KeyboardInterrupt:
                print("\n[MAIN-LOOP] KeyboardInterrupt captured, exiting gracefully...")
                break
            except Exception as e:
                # Prevent a single round exception from crashing the whole process
                print(f"[MAIN-LOOP][ERROR] ROUND #{round_id} raised exception: {e!r}")
                traceback.print_exc()

            print("\n" + "-" * 80)
            print(f"[MAIN-LOOP] <<<<<<< END ROUND #{round_id} >>>>>>>")
            print("-" * 80 + "\n")

            # Short pause before starting the next round
            time.sleep(0.3)

    finally:
        try:
            shm_reader.close()
        except Exception as e:
            print(f"[MAIN-LOOP][WARN] shm_reader.close failed: {e!r}")


if __name__ == "__main__":
    main_loop()