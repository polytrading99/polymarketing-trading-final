# ws_client.py
"""
User WebSocket client for the Polymarket CLOB.

- Connects to: wss://ws-subscriptions-clob.polymarket.com/ws/user
- Sends a subscription payload on open:
    {
        "markets": [...],
        "type": "user",
        "auth": {
            "apiKey": ...,
            "secret": ...,
            "passphrase": ...
        }
    }
- For each JSON message received, calls on_message_callback(msg_dict).

This module does NOT know anything about your state machine. It only
parses WebSocket frames and forwards decoded JSON messages.
"""

import json
import threading
import time
from typing import Callable, Iterable, Optional

import logging
from websocket import WebSocketApp  # pip install websocket-client

USER_WS_URL: str = "wss://ws-subscriptions-clob.polymarket.com/ws/user"

logger = logging.getLogger(__name__)


class UserWebSocketClient:
    """
    Simple client for the Polymarket CLOB `user` WebSocket channel.

    Typical usage
    -------------
        client = UserWebSocketClient(
            api_key=...,
            api_secret=...,
            api_passphrase=...,
            markets=[...],          # list of conditionIds you care about, can be []
            on_message=callback,    # function(msg_dict) -> None
            verbose=True,
        )
        client.run_forever()
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        markets: Optional[Iterable[str]],
        on_message: Callable[[dict], None],
        verbose: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        api_key / api_secret / api_passphrase:
            API credentials created by py_clob_client, used for user WS auth.
        markets:
            Iterable of conditionIds to subscribe to. If empty, the server
            typically sends all user events.
        on_message:
            Callback invoked for every decoded JSON message.
        verbose:
            If True, raw WebSocket messages are logged at DEBUG level.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.markets = list(markets or [])
        self.on_message_callback = on_message
        self.verbose = verbose

        self.ws = WebSocketApp(
            USER_WS_URL,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )

    # ------------------------------------------------------------------
    # WebSocket callbacks
    # ------------------------------------------------------------------

    def _on_message(self, ws, message: str) -> None:
        if self.verbose:
            logger.debug("WS raw message: %s", message)

        # Heartbeat frame
        if message == "PONG":
            return

        try:
            msg = json.loads(message)
        except json.JSONDecodeError:
            # Non-JSON payloads are unexpected but not fatal.
            logger.debug("WS non-JSON message: %r", message)
            return

        try:
            self.on_message_callback(msg)
        except Exception:
            # Do not let user callback exceptions crash the WS loop.
            logger.error("Exception in on_message_callback", exc_info=True)

    def _on_error(self, ws, error) -> None:
        # Underlying connection / protocol errors.
        logger.error("WebSocket error: %r", error)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logger.info(
            "WebSocket closed: code=%s, msg=%s",
            close_status_code,
            close_msg,
        )

    def _on_open(self, ws) -> None:
        logger.info("WebSocket opened, subscribing to user channel")

        auth = {
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "passphrase": self.api_passphrase,
        }

        sub_msg = {
            "markets": self.markets,  # can be [] for all markets
            "type": "user",
            "auth": auth,
        }

        ws.send(json.dumps(sub_msg))

        # Start a ping loop to keep the connection alive.
        def ping_loop():
            while True:
                try:
                    ws.send("PING")
                except Exception:
                    logger.error("WebSocket ping failed", exc_info=True)
                    break
                time.sleep(10)

        threading.Thread(target=ping_loop, daemon=True).start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_forever(self) -> None:
        """
        Blocking call that runs the WebSocket event loop until the
        connection is closed or an unrecoverable error occurs.
        """
        self.ws.run_forever()