# polymarket_client.py
from typing import Optional, Dict, Any, List

import logging
import requests
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

logger = logging.getLogger(__name__)

DATA_API_BASE = "https://data-api.polymarket.com"


class PolymarketClient:
    """
    Thin wrapper around py_clob_client.

    The gateway / strategies talk to this class only and do not worry about:
    - signing / nonces / salts
    - L2 headers
    - low-level CLOB details

    Additionally exposes:
    - self.api_key / api_secret / api_passphrase: used for user WebSocket auth
    - self.client: the underlying ClobClient instance for low-level calls
    - self.wallet_address: address used for data-api queries (typically funder)
    """

    def __init__(
        self,
        host: str,
        private_key: str,
        chain_id: int = 137,
        signature_type: Optional[int] = None,
        funder: Optional[str] = None,
    ):
        """
        Parameters
        ----------
        host:
            CLOB HTTP base URL (e.g. https://clob.polymarket.com)
        private_key:
            Private key used by py_clob_client.
        chain_id:
            EVM chain id, default 137 (Polygon).
        signature_type:
            - 1: email / magic link login (proxy signer)
            - 2: browser wallet (proxy signer)
            - None: direct EOA (no proxy signer)
        funder:
            Funder / proxy address used for gas and trading. This is also used
            as the default wallet address for the data-api.
        """
        kwargs: Dict[str, Any] = dict(host=host, key=private_key, chain_id=chain_id)
        if signature_type is not None:
            kwargs["signature_type"] = signature_type
        if funder is not None:
            kwargs["funder"] = funder

        self.client = ClobClient(**kwargs)

        # Standard pattern from py_clob_client examples:
        #   creds = client.create_or_derive_api_creds()
        #   client.set_api_creds(creds)
        creds = self.client.create_or_derive_api_creds()
        self.client.set_api_creds(creds)

        # Expose creds for WebSocket auth
        self.api_key: str = creds.api_key
        self.api_secret: str = creds.api_secret
        self.api_passphrase: str = creds.api_passphrase

        # Wallet used for data-api queries (positions, orders, etc.)
        # By default we assume funder is the trading wallet.
        self.wallet_address: Optional[str] = funder
        self.data_api_base: str = DATA_API_BASE

    # -------------------------------------------------------------------------
    # WebSocket auth helper
    # -------------------------------------------------------------------------

    def ws_auth(self) -> Dict[str, str]:
        """
        Return auth dict required by user WebSocket:

            {"apiKey": ..., "secret": ..., "passphrase": ...}
        """
        return {
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "passphrase": self.api_passphrase,
        }

    # -------------------------------------------------------------------------
    # Order placement / cancellation
    # -------------------------------------------------------------------------

    def place_limit(
        self,
        token_id: str,
        side: str,      # "BUY" or "SELL"
        price: float,
        size: float,
        order_type: str = "GTC",  # "GTC" / "FOK" / "GTD"
    ) -> dict:
        """
        Submit a limit order via py_clob_client.

        Parameters
        ----------
        token_id:
            CLOB token id of the contract leg.
        side:
            "BUY" or "SELL".
        price:
            Limit price.
        size:
            Order size.
        order_type:
            "GTC", "FOK", or "GTD".

        Returns
        -------
        dict
            Raw response from post_order (includes success / errorMsg / orderId / orderHashes).
        """
        side_const = BUY if side.upper() == "BUY" else SELL
        order_args = OrderArgs(
            price=price,
            size=size,
            side=side_const,
            token_id=token_id,
        )
        signed_order = self.client.create_order(order_args)

        ot_map = {
            "GTC": OrderType.GTC,
            "FOK": OrderType.FOK,
            "GTD": OrderType.GTD,
        }
        ot_enum = ot_map[order_type]

        resp = self.client.post_order(signed_order, ot_enum)
        return resp

    def cancel(self, order_id: str) -> dict:
        """Cancel a single order by order_id."""
        return self.client.cancel(order_id=order_id)

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a single order by order_id."""
        return self.client.cancel(order_id=order_id)

    def cancel_orders(self, order_ids: list[str]) -> dict:
        """Cancel multiple orders by their ids."""
        return self.client.cancel_orders(order_ids)

    def cancel_all(self) -> dict:
        """Cancel all open orders for the current user."""
        return self.client.cancel_all()

    def cancel_market_orders(
        self,
        market: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> dict:
        """
        Cancel all open orders in a specific market / asset pair.

        Parameters follow py_clob_client's cancel_market_orders.
        """
        return self.client.cancel_market_orders(market=market, asset_id=asset_id)

    # -------------------------------------------------------------------------
    # Open orders query
    # -------------------------------------------------------------------------

    def get_open_orders_raw(
        self,
        market_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        limit: int = 200,
    ) -> dict:
        """
        Low-level "open orders" query, mostly for logging / debugging.

        Resolution order:
        1) Try py_clob_client built-in helper (get_open_orders / get_orders).
        2) If unavailable, fall back to data-api /orders.

        Returns
        -------
        dict
            Raw data as returned by the underlying API.
        """
        client = self.client

        # Prefer native client helpers if available.
        if hasattr(client, "get_open_orders"):
            logger.debug(
                "Fetching open orders via client.get_open_orders market_id=%s asset_id=%s limit=%s",
                market_id,
                asset_id,
                limit,
            )
            # Adjust parameter names to match your local py_clob_client version.
            return client.get_open_orders(
                market=market_id,
                asset_id=asset_id,
                limit=limit,
            )

        if hasattr(client, "get_orders"):
            logger.debug(
                "Fetching open orders via client.get_orders status=open market_id=%s asset_id=%s limit=%s",
                market_id,
                asset_id,
                limit,
            )
            # Adjust parameter names according to your local implementation.
            return client.get_orders(
                status="open",
                market=market_id,
                asset_id=asset_id,
                limit=limit,
            )

        # Fall back to data-api /orders.
        params: Dict[str, object] = {
            "limit": limit,
            "status": "open",
        }

        if self.wallet_address:
            params["user"] = self.wallet_address
        if market_id:
            params["market"] = market_id
        if asset_id:
            params["asset"] = asset_id

        url = f"{self.data_api_base}/orders"
        logger.info(
            "Fetching open orders via data-api: GET %s params=%s",
            url,
            params,
        )
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        logger.debug(
            "data-api /orders response: count=%s raw_type=%s",
            len(data) if isinstance(data, list) else "n/a",
            type(data),
        )

        return data

    def get_positions_raw(self) -> dict:
        """
        Directly expose the underlying py_clob_client positions response.

        Field names and shape are determined by py_clob_client. This method is
        intended for diagnostics / logging.
        """
        # If this raises AttributeError, the method name might differ in your
        # local py_clob_client build; check dir(self.client) and adjust.
        return self.client.get_positions()

    def get_market_open_orders(
        self,
        market_id: str,
        yes_token_id: str,
        no_token_id: str,
        limit: int = 200,
    ) -> Dict[str, List[dict]]:
        """
        Get open orders for a specific market and split them into YES / NO legs.

        This is built on top of get_open_orders_raw and tries to normalize
        the following fields for each order:
        - _norm_id
        - _norm_side  ("BUY"/"SELL")
        - _norm_price (float)
        - _norm_size  (float)

        Returns
        -------
        dict
            {
                "yes": [ order_dict, ... ],
                "no":  [ order_dict, ... ],
            }
        """
        raw = self.get_open_orders_raw(market_id=market_id, asset_id=None, limit=limit)

        # Some implementations return {"orders":[...]}, others return a bare list.
        if isinstance(raw, dict):
            orders = raw.get("orders") or raw.get("data") or []
        else:
            orders = raw

        if not isinstance(orders, list):
            logger.warning("Unexpected open orders payload: %r", raw)
            return {"yes": [], "no": []}

        yes_orders: List[dict] = []
        no_orders: List[dict] = []

        for o in orders:
            if not isinstance(o, dict):
                continue

            # 1) Filter by market id
            cond = str(
                o.get("market")
                or o.get("conditionId")
                or o.get("condition_id")
                or o.get("id")
                or ""
            )
            if cond and cond != str(market_id):
                continue

            # 2) Decide which leg this order belongs to
            asset = str(
                o.get("asset")
                or o.get("asset_id")
                or o.get("token_id")
                or o.get("clobTokenId")
                or ""
            )

            leg_key: Optional[str] = None
            if asset == str(yes_token_id):
                leg_key = "yes"
            elif asset == str(no_token_id):
                leg_key = "no"
            else:
                # Token not matching either leg; skip.
                continue

            # 3) Normalize standard fields
            oid = (
                o.get("id")
                or o.get("order_id")
                or o.get("orderId")
            )

            side_raw = (o.get("side") or o.get("direction") or "").upper()
            if side_raw.startswith("B"):
                side_norm = "BUY"
            elif side_raw.startswith("S"):
                side_norm = "SELL"
            else:
                side_norm = side_raw

            try:
                price = float(o.get("price", 0.0) or 0.0)
            except (TypeError, ValueError):
                price = 0.0

            raw_size = (
                o.get("size")
                or o.get("remainingSize")
                or o.get("remaining")
                or o.get("openSize")
            )
            try:
                size = float(raw_size or 0.0)
            except (TypeError, ValueError):
                size = 0.0

            norm = dict(o)  # copy original fields
            norm["_norm_id"] = str(oid) if oid is not None else None
            norm["_norm_side"] = side_norm
            norm["_norm_price"] = price
            norm["_norm_size"] = size

            if leg_key == "yes":
                yes_orders.append(norm)
            elif leg_key == "no":
                no_orders.append(norm)

        logger.debug(
            "Market open orders: market_id=%s yes_count=%d no_count=%d",
            market_id,
            len(yes_orders),
            len(no_orders),
        )

        return {
            "yes": yes_orders,
            "no": no_orders,
        }

    # -------------------------------------------------------------------------
    # Positions helpers
    # -------------------------------------------------------------------------

    def get_market_net_position(
        self,
        market_id: str,
        yes_token_id: str,
        no_token_id: str,
    ) -> dict:
        """
        Derive net positions for YES/NO legs for a given market from
        get_positions_raw().

        Returns
        -------
        dict
            {"yes": float, "no": float}
        """
        data = self.get_positions_raw()

        yes_pos = 0.0
        no_pos = 0.0

        # Field names here are a template; adjust to match your actual payload.
        # Common shapes:
        #   {"positions": [...]} / {"data": [...]} / a bare list.
        positions = data.get("positions") or data.get("data") or data

        if isinstance(positions, list):
            for p in positions:
                if not isinstance(p, dict):
                    continue

                # Try common market / conditionId field variants
                mkt = str(p.get("market") or p.get("condition_id") or p.get("id") or "")
                if mkt != str(market_id):
                    continue

                asset_id = str(
                    p.get("asset_id")
                    or p.get("token_id")
                    or p.get("clobTokenId")
                    or p.get("id")
                    or ""
                )

                try:
                    # These field names are examples; adapt to actual schema
                    sz = float(
                        p.get("net_position")
                        or p.get("position")
                        or p.get("size")
                        or 0.0
                    )
                except (TypeError, ValueError):
                    sz = 0.0

                if asset_id == str(yes_token_id):
                    yes_pos += sz
                elif asset_id == str(no_token_id):
                    no_pos += sz

        return {"yes": yes_pos, "no": no_pos}

    def get_positions(
        self,
        user: Optional[str] = None,
        market_id: Optional[str] = None,
        size_threshold: float = 0.0,
        limit: int = 100,
    ) -> List[dict]:
        """
        Call Polymarket data-api /positions and return the raw list.

        Parameters
        ----------
        user:
            Wallet address (0x...). If omitted, uses self.wallet_address.
        market_id:
            conditionId / market id.
        size_threshold:
            Filter out very small positions on the server side if supported.
        limit:
            Max number of positions to fetch.

        Returns
        -------
        list of dict
            Raw position entries returned by the data-api.
        """
        if user is None:
            if not self.wallet_address:
                raise ValueError("get_positions: user address is required")
            user = self.wallet_address

        params = {
            "user": user,
            "limit": limit,
        }
        if market_id:
            # In data-api docs this parameter is commonly called "market"
            params["market"] = market_id
        if size_threshold is not None:
            params["sizeThreshold"] = size_threshold

        url = f"{self.data_api_base}/positions"
        logger.debug("GET %s params=%s", url, params)
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            raise RuntimeError(f"positions response not a list: {data!r}")

        return data

    def get_market_leg_positions(
        self,
        market_id: str,
        yes_token_id: str,
        no_token_id: str,
        size_threshold: float = 0.0,
        limit: int = 100,
    ) -> dict:
        """
        Compute YES/NO position sizes and weighted average prices for a market
        using data-api /positions.

        Returns
        -------
        dict
            {
                "yes_size": float,
                "yes_avg_price": Optional[float],
                "no_size": float,
                "no_avg_price": Optional[float],
            }
        """
        positions = self.get_positions(
            user=None,
            market_id=market_id,
            size_threshold=size_threshold,
            limit=limit,
        )

        yes_size = 0.0
        no_size = 0.0
        yes_notional = 0.0
        no_notional = 0.0

        for p in positions:
            if not isinstance(p, dict):
                continue

            # conditionId / market / id: adapt to real payload
            cond = str(
                p.get("conditionId")
                or p.get("market")
                or p.get("id")
                or ""
            )
            if cond and cond != str(market_id):
                continue

            asset = str(
                p.get("asset")
                or p.get("asset_id")
                or p.get("token_id")
                or ""
            )

            try:
                size = float(p.get("size", 0.0) or 0.0)
            except (TypeError, ValueError):
                size = 0.0

            if size <= 0.0:
                continue

            # In data-api docs the field is typically avgPrice
            raw_avg = p.get("avgPrice") or p.get("avg_price")
            try:
                avg_price = float(raw_avg) if raw_avg is not None else None
            except (TypeError, ValueError):
                avg_price = None

            if asset == str(yes_token_id):
                yes_size += size
                if avg_price is not None:
                    yes_notional += size * avg_price

            elif asset == str(no_token_id):
                no_size += size
                if avg_price is not None:
                    no_notional += size * avg_price

        yes_avg = yes_notional / yes_size if yes_size > 0 and yes_notional > 0 else None
        no_avg = no_notional / no_size if no_size > 0 and no_notional > 0 else None

        return {
            "yes_size": yes_size,
            "yes_avg_price": yes_avg,
            "no_size": no_size,
            "no_avg_price": no_avg,
        }