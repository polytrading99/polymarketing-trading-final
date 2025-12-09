#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging

from time_bucket_mm import (
    CLOB_HOST,
    PRIVATE_KEY,
    PROXY_ADDRESS,
    SIGNATURE_TYPE,
    CHAIN_ID,
)
from state_machine.polymarket_client import PolymarketClient

# 你刚才那个 market 的 Up leg token_id（yes_token）
YES_TOKEN_ID = "60856705925472585869452640239518911807306195562524192889110937395249823404692"

# 想平的价格和数量
EXIT_PRICE = 0.01
EXIT_SIZE = 10.0  # 10 share


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    client = PolymarketClient(
        host=CLOB_HOST,
        private_key=PRIVATE_KEY,
        chain_id=CHAIN_ID,
        signature_type=SIGNATURE_TYPE,
        funder=PROXY_ADDRESS,
    )

    print(
        f"[EMERGENCY] placing EXIT SELL {EXIT_SIZE} @ {EXIT_PRICE} "
        f"on YES_TOKEN_ID={YES_TOKEN_ID}"
    )

    try:
        resp = client.place_limit(
            token_id=YES_TOKEN_ID,
            side="SELL",
            price=EXIT_PRICE,
            size=EXIT_SIZE,
        )
    except Exception as e:
        print("[EMERGENCY][ERROR] exception when placing exit order:", e)
        return

    print("[EMERGENCY] exit_resp =", resp)

    if not resp.get("success", False):
        print("[EMERGENCY][ERROR] exit order not successful")
        return

    order_id = (
        resp.get("orderID")
        or resp.get("orderId")
        or resp.get("order_id")
        or (resp.get("data") or {}).get("orderID")
        or (resp.get("data") or {}).get("orderId")
    )

    print(
        f"[EMERGENCY] exit order sent successfully, order_id={order_id}, "
        f"status={resp.get('status')}"
    )


if __name__ == "__main__":
    main()