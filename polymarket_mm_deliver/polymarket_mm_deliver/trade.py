#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polymarket WS -> shared-memory ring (fixed 64-byte struct, single-producer, multi-consumer-friendly)

Frame schema (64 bytes, little-endian):
{
  int64  date_time_ms      # publish time in ns (monotonic_ns)
  float64 yes_bid
  float64 yes_ask
  float64 no_bid
  float64 no_ask
  int64  bucket_ts         # 15m contract UTC bucket start (seconds)
  16 bytes padding         # reserved
}
"""

import json, time, threading, math, logging
from typing import List, Optional, Dict, Tuple
from multiprocessing import shared_memory

import numpy as np
import requests
from websocket import WebSocketApp

# =========================
# Logger
# =========================
logger = logging.getLogger("BinanceTradeCollector")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)

# =========================
# Parameters
# =========================
DEMO_SHM_NAME   = "poly_tob_shm"    # shared memory name
RING_CAPACITY   = 1 << 17           # 131072 slots
RING_MASK       = RING_CAPACITY - 1
HDR_SIZE        = 64                # header bytes
PING_INTERVAL_S = 10.0              # send "PING" every 10s (keepalive)
LIMIT_ASSETS_TO = 2                 # subscribe first 2 token ids (YES/NO)
DEBUG_PREVIEW_N = 4                 # show first N emitted frames

# =========================
# Frame dtype (64 bytes)
# =========================
FRAME_DTYPE = np.dtype([
    ('date_time_ms',        '<i8'),
    ('yes_bid',             '<f8'),
    ('yes_ask',             '<f8'),
    ('no_bid',              '<f8'),
    ('no_ask',              '<f8'),
    ('bucket_ts',           '<i8'),
    ('_pad',                'V16'),
], align=True)
assert FRAME_DTYPE.itemsize == 64, FRAME_DTYPE.itemsize

# =========================
# Polymarket endpoints & helpers
# =========================
WSS_BASE   = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_BASE = "https://gamma-api.polymarket.com"

def _parse_clob_ids_and_side(ev: dict) -> Tuple[List[str], Dict[str,str]]:
    """
    Parse event JSON to extract:
    - asset ids (clobTokenIds)
    - side mapping (yes/no) inferred from outcome names
    """
    assets:set[str] = set()
    side:Dict[str,str] = {}

    def _take(x):
        if x is not None:
            assets.add(str(x))

    def _name_to_side(name:str)->Optional[str]:
        if not isinstance(name,str): return None
        n=name.strip().lower()
        if n in ("yes","y","up","higher","above"): return "yes"
        if n in ("no","n","down","lower","below"): return "no"
        return None

    markets = ev.get("markets") or []
    if isinstance(markets, dict):
        markets=[markets]
    for m in markets:
        if not isinstance(m, dict):
            continue

        # clobTokenIds may be stringified JSON, list or dict
        ct = m.get("clobTokenIds")
        if isinstance(ct, str):
            try:
                arr=json.loads(ct)
                if isinstance(arr,list):
                    for v in arr: _take(v)
                else:
                    parts=[p.strip() for p in ct.strip("[]").replace('"',"").split(",") if p.strip()]
                    for p in parts: _take(p)
            except Exception:
                parts=[p.strip() for p in ct.strip("[]").replace('"',"").split(",") if p.strip()]
                for p in parts: _take(p)
        elif isinstance(ct, list):
            for v in ct: _take(v)
        elif isinstance(ct, dict):
            for v in ct.values(): _take(v)

        # outcomes may carry yes/no semantic names
        outs = m.get("outcomes")
        if isinstance(outs, list):
            for o in outs:
                if isinstance(o, dict):
                    tid = o.get("clobTokenId") or o.get("token_id") or o.get("tokenId")
                    nm  = o.get("name") or o.get("label") or o.get("outcome") or o.get("ticker")
                    if tid:
                        _take(tid)
                        s=_name_to_side(nm)
                        if s: side[str(tid)] = s
                elif isinstance(o,(str,int)):
                    _take(o)
        elif isinstance(outs, dict):
            for _,v in outs.items():
                if isinstance(v,(str,int)):
                    _take(v)
                elif isinstance(v,dict):
                    tid = v.get("clobTokenId") or v.get("token_id") or v.get("tokenId")
                    nm  = v.get("name") or v.get("label") or v.get("outcome") or v.get("ticker")
                    if tid:
                        _take(tid)
                        s=_name_to_side(nm)
                        if s: side[str(tid)]=s

    return list(assets), side

def get_assets_and_side_from_slug(slug: str) -> Tuple[List[str], Dict[str, str]]:
    """
    直接用 Gamma 的 outcomes + clobTokenIds：
      - 名字里含 "Up" 的那个 token 视为 YES
      - 名字里含 "Down" 的那个 token 视为 NO
    返回:
      ids: [yes_token_id, no_token_id]
      side: {yes_token_id: "yes", no_token_id: "no"}
    """
    r = requests.get(f"{GAMMA_BASE}/events/slug/{slug}", timeout=10)
    r.raise_for_status()
    data = r.json()

    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected event json (not dict): {data!r}")

    markets = data.get("markets") or []
    if not markets:
        raise RuntimeError(f"no markets in event json: {data!r}")
    m0 = markets[0]

    outcomes_raw = m0.get("outcomes")
    tokens_raw   = m0.get("clobTokenIds") or m0.get("clob_token_ids")

    def _ensure_list(x):
        if isinstance(x, list):
            return x
        if isinstance(x, str):
            try:
                return json.loads(x)
            except Exception:
                return [s.strip() for s in x.strip("[]").replace('"', "").split(",") if s.strip()]
        return []

    outcomes = _ensure_list(outcomes_raw)   # ["Up", "Down"]
    tokens   = _ensure_list(tokens_raw)     # [token_up, token_down]

    if not outcomes or not tokens or len(outcomes) != len(tokens):
        raise RuntimeError(f"cannot parse outcomes/tokens: outcomes={outcomes_raw!r}, tokens={tokens_raw!r}")

    up_idx = down_idx = None
    for i, name in enumerate(outcomes):
        if not isinstance(name, str):
            continue
        lower = name.lower()
        if "up" in lower and up_idx is None:
            up_idx = i
        if "down" in lower and down_idx is None:
            down_idx = i

    # fallback: 如果没匹配上，就按 0/1
    if up_idx is None:
        up_idx = 0
    if down_idx is None:
        down_idx = 1 if len(tokens) > 1 else 0

    yes_token = str(tokens[up_idx])
    no_token  = str(tokens[down_idx])

    ids  = [yes_token, no_token]
    side = {
        yes_token: "yes",
        no_token:  "no",
    }

    logger.info(f"[resolve] slug={slug} yes_token={yes_token} no_token={no_token} outcomes={outcomes}")
    return ids, side

def _to_f(x):
    try:
        return float(x)
    except:
        return math.nan

def _best_from_book(obj:dict):
    """
    Compute best bid/ask from a snapshot-like order book object.
    """
    bids = obj.get("bids") or obj.get("buys") or []
    asks = obj.get("asks") or obj.get("sells") or []
    bb = max((_to_f(x.get("price")) for x in bids if x and x.get("price") is not None), default=math.nan)
    ba = min((_to_f(x.get("price")) for x in asks if x and x.get("price") is not None), default=math.nan)
    return bb, ba

# =========================
# Producer (aggregate YES/NO frame -> 64B shm ring)
# =========================
class MarketWSProducer:
    def __init__(self, assets_ids:List[str], side_map:Dict[str,str], shm_name:str, bucket_ts:int):
        # logger instance
        self.logger = logger

        # asset ids / yes-no mapping
        self.assets_ids = assets_ids[:2] if LIMIT_ASSETS_TO and len(assets_ids)>LIMIT_ASSETS_TO else assets_ids
        self.side_map   = dict(side_map)
        self.bucket_ts  = int(bucket_ts)

        # === SHARED MEMORY RING SETUP (64B header + N*64B frames) ===
        self.RING_NAME     = shm_name
        self.RING_CAPACITY = RING_CAPACITY
        self.RING_MASK     = RING_MASK
        self._frame_dtype  = FRAME_DTYPE
        self._hdr_size     = HDR_SIZE
        self._ring_bytes   = self._hdr_size + self.RING_CAPACITY * self._frame_dtype.itemsize

        try:
            # create new shared memory region
            self.shm = shared_memory.SharedMemory(
                name=self.RING_NAME, create=True, size=self._ring_bytes
            )
            hdr = memoryview(self.shm.buf)[:self._hdr_size]
            hdr[:8]    = (0).to_bytes(8, 'little')                   # write_idx
            hdr[8:16]  = (0).to_bytes(8, 'little')                   # read_idx (reserved, currently unused)
            hdr[16:24] = (self.RING_CAPACITY).to_bytes(8, 'little')  # capacity
            hdr[24:64] = b'\x00' * 40
            self.logger.info(f"[shm] created name={self.RING_NAME}, size={self._ring_bytes}")
        except FileExistsError:
            # attach to existing shared memory region
            self.shm = shared_memory.SharedMemory(name=self.RING_NAME, create=False)
            self.logger.info(f"[shm] attached existing name={self.RING_NAME}")

        self._hdr  = memoryview(self.shm.buf)[:self._hdr_size]
        self._ring = np.ndarray(
            (self.RING_CAPACITY,),
            dtype=self._frame_dtype,
            buffer=self.shm.buf[self._hdr_size:]
        )

        def _ring_widx():
            return int.from_bytes(self._hdr[:8], 'little', signed=False)

        def _ring_set_widx(v: int):
            self._hdr[:8] = int(v).to_bytes(8, 'little', signed=False)

        self._ring_widx     = _ring_widx
        self._ring_set_widx = _ring_set_widx
        self._ring_lock     = threading.Lock()  # single writer; lock kept for robustness

        # === WS & state ===
        self.ws:Optional[WebSocketApp] = None
        self._stop = False
        self._dbg  = DEBUG_PREVIEW_N
        self.tob: Dict[str, Tuple[float,float]] = {}
        self.market_id: Optional[str] = None

    # ------- external control -------
    def stop(self):
        """Request graceful shutdown of this producer (close WS, exit run loop)."""
        self._stop = True
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:
            pass

    # ------- shm write -------
    def _write_ring(self, yb: float, ya: float, nb: float, na: float) -> int:
        """
        Write one TOB frame into the ring and return publish timestamp (ns).
        """
        widx   = self._ring_widx()
        idx    = widx & self.RING_MASK

        with self._ring_lock:
            slot = self._ring[idx]
            slot['yes_bid']      = yb
            slot['yes_ask']      = ya
            slot['no_bid']       = nb
            slot['no_ask']       = na
            slot['bucket_ts']    = self.bucket_ts
            pub_ns = time.monotonic_ns()      # monotonic publish time, in ns
            slot['date_time_ms'] = pub_ns     # stored as ns, despite field name
            self._ring_set_widx(widx + 1)

        return pub_ns

    # ------- ws callbacks helpers -------
    def _maybe_emit(self):
        """
        If we have both YES and NO sides with valid TOB, write a single frame into the ring.
        """
        yes_id = next((aid for aid,s in self.side_map.items() if s=="yes" and aid in self.tob), None)
        no_id  = next((aid for aid,s in self.side_map.items() if s=="no"  and aid in self.tob), None)

        # Fallback: infer yes/no by smaller ask if side mapping is incomplete
        if (yes_id is None or no_id is None) and len(self.tob) >= 2:
            pairs = [(aid, self.tob[aid][1]) for aid in self.tob if self.tob[aid][1]==self.tob[aid][1]]
            if len(pairs) >= 2:
                pairs.sort(key=lambda x: (math.isnan(x[1]), x[1]))
                yes_id = yes_id or pairs[0][0]
                for aid,_ in pairs:
                    if aid != yes_id:
                        no_id = no_id or aid
                        break

        if yes_id is None or no_id is None:
            return

        yb, ya = self.tob.get(yes_id, (math.nan, math.nan))
        nb, na = self.tob.get(no_id , (math.nan, math.nan))
        if any(math.isnan(x) for x in (yb,ya,nb,na)):
            return

        ts_ns = self._write_ring(yb, ya, nb, na)

        if self._dbg > 0:
            self.logger.debug(
                f"[debug] ts={ts_ns} yes(bid={yb:.6f},ask={ya:.6f}) "
                f"no(bid={nb:.6f},ask={na:.6f}) bucket_ts={self.bucket_ts}"
            )
            self._dbg -= 1

    def _ingest_book_obj(self, obj:dict):
        """
        Handle a full-book snapshot object for one asset_id.
        """
        aid = obj.get("asset_id")
        if not aid:
            return
        self.market_id = self.market_id or obj.get("market") or self.market_id
        bb, ba = _best_from_book(obj)
        if not math.isnan(bb) or not math.isnan(ba):
            ob = self.tob.get(aid, (math.nan, math.nan))
            self.tob[aid] = (bb if not math.isnan(bb) else ob[0],
                             ba if not math.isnan(ba) else ob[1])

    def _ingest_price_change(self, obj:dict):
        """
        Handle a price_change batch: update TOB per asset using best_bid / best_ask.
        """
        self.market_id = self.market_id or obj.get("market") or self.market_id
        pcs = obj.get("price_changes") or []
        for pc in pcs:
            aid = str(pc.get("asset_id"))
            if not aid:
                continue
            bb = _to_f(pc.get("best_bid"))
            ba = _to_f(pc.get("best_ask"))
            ob = self.tob.get(aid, (math.nan, math.nan))
            self.tob[aid] = (bb if not math.isnan(bb) else ob[0],
                             ba if not math.isnan(ba) else ob[1])

    def _handle_obj(self, obj:dict):
        """
        Generic message dispatcher for a single event object.
        """
        et = obj.get("event_type") or obj.get("type")
        if not et and ("bids" in obj or "asks" in obj):
            et="book"
        if et == "book":
            self._ingest_book_obj(obj)
        elif et == "price_change":
            self._ingest_price_change(obj)
        self._maybe_emit()

    # ------- ws callbacks -------
    def on_open(self, ws:WebSocketApp):
        self.ws = ws
        sub={"assets_ids": self.assets_ids, "type":"market"}
        ws.send(json.dumps(sub))
        self.logger.info(f"[producer] subscribed: {sub}")

        def ping_loop():
            while not self._stop:
                try:
                    ws.send("PING")
                except Exception:
                    break
                time.sleep(PING_INTERVAL_S)

        threading.Thread(target=ping_loop, daemon=True).start()

    def on_message(self, ws, message):
        """
        WebSocket on_message callback: decode JSON, route events, ignore PONGs.
        """
        if isinstance(message,(bytes,bytearray)):
            try:
                message=message.decode("utf-8","ignore")
            except Exception:
                return

        if isinstance(message,str) and message.strip().upper()=="PONG":
            if self._dbg>0:
                self.logger.debug("[debug] <- PONG")
                self._dbg-=1
            return

        try:
            data=json.loads(message)
        except Exception:
            if self._dbg>0:
                self.logger.debug("[debug] non-JSON")
                self._dbg-=1
            return

        if isinstance(data,list):
            for obj in data:
                if isinstance(obj,dict):
                    self._handle_obj(obj)
        elif isinstance(data,dict):
            evs=None
            for k in ("events","data"):
                v=data.get(k)
                if isinstance(v,list):
                    evs=v; break
            if evs is not None:
                for obj in evs:
                    if isinstance(obj,dict):
                        self._handle_obj(obj)
            else:
                self._handle_obj(data)

    def on_error(self, ws, err):
        self.logger.error(f"[producer] ws error: {err}")

    def on_close(self, ws, code, msg):
        self.logger.info(f"[producer] ws closed: code={code} msg={msg}")
        self.ws = None

    def run(self):
        """
        Main WS loop:
        - While self._stop is False, keep a single WS session alive.
        - On disconnection, reconnect with exponential backoff: 0.1s -> 0.2s -> 0.4s ... up to 2s.
        - schedule_rotate_btc_15m calls stop(), which flips self._stop=True and exits the loop.
        """
        base_delay = 0.1         # initial reconnect delay
        max_delay  = 2.0         # max reconnect delay
        reconnect_delay = base_delay

        try:
            while not self._stop:
                self.ws = WebSocketApp(
                    WSS_BASE,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )

                try:
                    self.ws.run_forever()
                except Exception as e:
                    self.logger.error(f"[producer] run_forever exception: {e}")

                self.ws = None

                if self._stop:
                    break

                self.logger.warning(f"[producer] disconnected, will reconnect in {reconnect_delay:.2f}s...")
                time.sleep(reconnect_delay)

                # exponential backoff up to max_delay
                reconnect_delay = min(reconnect_delay * 2.0, max_delay)
        finally:
            # only close local shm handle; do not unlink
            self.shm.close()
            self.logger.info("[producer] shm handle closed, producer thread exit")

# =========================
# 15m rotation logic (time-based)
# =========================
def current_15m_bucket() -> int:
    """Return current UTC 15m bucket start timestamp (seconds)."""
    now = int(time.time())
    return now - (now % 900)  # 900 seconds = 15 minutes

def build_btc_15m_slug_from_bucket(bucket: int) -> str:
    """Build the BTC up/down 15m Polymarket slug for the given bucket."""
    return f"btc-updown-15m-{bucket}"

def start_producer_for_slug(slug: str, shm_name: str, bucket_ts: int) -> Tuple[Optional[MarketWSProducer], Optional[threading.Thread]]:
    """
    Start a new MarketWSProducer thread for a given slug.
    If the Gamma API is not ready for this slug (e.g. market not yet listed),
    return (None, None).
    """
    try:
        ids, side = get_assets_and_side_from_slug(slug)
    except Exception as e:
        logger.error(f"[resolve] failed for slug={slug}: {e}")
        return None, None

    if LIMIT_ASSETS_TO and len(ids) > LIMIT_ASSETS_TO:
        ids = ids[:LIMIT_ASSETS_TO]
    logger.info(f"[resolve] slug={slug} assets={ids} side_map={side or '(unknown yet)'}")

    producer = MarketWSProducer(ids, side, shm_name, bucket_ts=bucket_ts)
    t = threading.Thread(target=producer.run, daemon=True)
    t.start()
    return producer, t

def schedule_rotate_btc_15m(shm_name: str):
    """
    Time-based rotation:
    - Determine current 15m bucket and start WS for the corresponding slug.
    - Compute this bucket's end time: next_boundary = bucket + 900.
    - Within the current bucket, if Gamma resolution fails, retry every 5 seconds
      until success or until we cross into the next bucket.
    - Once crossing a 15m boundary, stop the old producer and start a new one.
    """
    bucket = current_15m_bucket()
    slug = build_btc_15m_slug_from_bucket(bucket)
    next_boundary = bucket + 900  # end of current bucket (seconds)
    logger.info(f"[init] bucket={bucket}, slug={slug}")

    # Initial start: if Gamma resolution fails, retry every 5s within this bucket
    current_producer, current_thread = start_producer_for_slug(slug, shm_name, bucket_ts=bucket)
    while current_producer is None and time.time() < next_boundary:
        logger.warning("[init] start_producer_for_slug failed, retry in 5s...")
        time.sleep(5.0)
        current_producer, current_thread = start_producer_for_slug(slug, shm_name, bucket_ts=bucket)

    while True:
        now = time.time()
        if now >= next_boundary:
            # Crossed 15m boundary: rotate to next bucket
            bucket = next_boundary
            slug = build_btc_15m_slug_from_bucket(bucket)
            new_boundary = bucket + 900  # end of new bucket
            logger.info(f"[rotate] now={now:.3f} >= boundary={next_boundary}, new bucket={bucket}, slug={slug}")

            # Stop old producer
            if current_producer is not None:
                logger.info("[rotate] stopping old producer...")
                try:
                    current_producer.stop()
                except Exception as e:
                    logger.error(f"[rotate] error stopping producer: {e}")

            # Start new producer; retry Gamma within this bucket if needed
            current_producer, current_thread = start_producer_for_slug(slug, shm_name, bucket_ts=bucket)
            while current_producer is None and time.time() < new_boundary:
                logger.warning("[rotate] start_producer_for_slug failed, retry in 5s...")
                time.sleep(5.0)
                current_producer, current_thread = start_producer_for_slug(slug, shm_name, bucket_ts=bucket)

            # Move to next boundary
            next_boundary = new_boundary
            continue

        # Not yet at boundary: sleep a short while (max 1s or until boundary)
        sleep_for = min(1.0, max(0.0, next_boundary - now))
        time.sleep(sleep_for)

# =========================
# Main
# =========================
def main():
    schedule_rotate_btc_15m(DEMO_SHM_NAME)

if __name__=="__main__":
    main()