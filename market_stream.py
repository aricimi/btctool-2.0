"""
market_stream.py — Institutional Asynchronous Sensory Ingestion Engine for Zebra Bot (btctool 2.0)
Streams real-time public trades, L2 order book (50 levels), derivatives open interest & funding rates,
and aggregates ticks into 11-timeframe in-memory rolling ring buffers without sleep blindness.
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Dict, List, Optional, Tuple
import numpy as np
import requests
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("market_stream")

# OKX Public Endpoints
OKX_WS_PUBLIC = "wss://ws.okx.com:8443/ws/v5/public"
OKX_REST_CANDLES = "https://www.okx.com/api/v5/market/candles"
OKX_REST_BOOKS = "https://www.okx.com/api/v5/market/books"

# Supported 11 Timeframes in seconds
TIMEFRAME_SECONDS = {
    "1s": 1,
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "1D": 86400,
}

OKX_BAR_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "6h": "6H",
    "1D": "1D",
}


class MarketStream:
    """
    Sub-second sensory ingestion engine for Zebra Bot.
    Streams trades, order books, derivatives metrics, and maintains 11-timeframe buffers.
    """

    def __init__(self, inst_id: str = "BTC-USDT", swap_id: str = "BTC-USDT-SWAP", max_bars: int = 300):
        self.inst_id = inst_id
        self.swap_id = swap_id
        self.max_bars = max_bars

        # Latest Price & Ticker
        self.latest_price = 0.0
        self.best_bid = 0.0
        self.best_ask = 0.0
        self.last_update_ts = 0.0

        # Live Order Book: {price: size}
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.book_snapshots: deque = deque(maxlen=3)  # 3-snapshot anti-spoofing queue

        # Tape & Flow (Recent trades)
        self.recent_trades: deque = deque(maxlen=1000)
        self.cvd = 0.0  # Cumulative Volume Delta
        self.trade_count_1s = 0
        self.trade_velocity = 0.0  # Trades per second

        # Derivatives Fuel
        self.open_interest = 0.0
        self.oi_history: deque = deque(maxlen=30)  # For rolling Z-score
        self.funding_rate = 0.0
        self.next_funding_time = 0

        # Multi-Timeframe Ring Buffers: tf -> deque of dict(o, h, l, c, v, ts)
        self.buffers: Dict[str, deque] = {tf: deque(maxlen=max_bars) for tf in TIMEFRAME_SECONDS}
        self.current_candles: Dict[str, dict] = {}

        self.running = False
        self._ws = None

    def seed_initial_history(self):
        """Seed initial candle history for all timeframes via REST API so the engine is immediately full."""
        logger.info("[Stream] Seeding historical candle buffers via REST...")
        for tf, okx_bar in OKX_BAR_MAP.items():
            try:
                url = f"{OKX_REST_CANDLES}?instId={self.inst_id}&bar={okx_bar}&limit=100"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    # OKX returns reverse chronological order (newest first); reverse to chronological
                    for row in reversed(data):
                        # row: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                        candle = {
                            "ts": int(row[0]) / 1000.0,
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "vol": float(row[5]),
                        }
                        self.buffers[tf].append(candle)
                    logger.info(f"[Stream] Seeded {len(self.buffers[tf])} bars for {tf}")
            except Exception as e:
                logger.warning(f"[Stream] Failed seeding {tf}: {e}")

        # Seed L2 Book Snapshot
        try:
            book_url = f"{OKX_REST_BOOKS}?instId={self.inst_id}&sz=50"
            b_resp = requests.get(book_url, timeout=5)
            if b_resp.status_code == 200:
                b_data = b_resp.json().get("data", [{}])[0]
                self.bids = {float(p): float(s) for p, s, *_ in b_data.get("bids", [])}
                self.asks = {float(p): float(s) for p, s, *_ in b_data.get("asks", [])}
                if self.bids and self.asks:
                    self.best_bid = max(self.bids.keys())
                    self.best_ask = min(self.asks.keys())
                    self.latest_price = (self.best_bid + self.best_ask) / 2.0
                logger.info(f"[Stream] Initial L2 book seeded: {len(self.bids)} bids, {len(self.asks)} asks")
        except Exception as e:
            logger.warning(f"[Stream] Failed seeding L2 book: {e}")

    def on_trade_tick(self, price: float, size: float, side: str, ts: float):
        """Process a single trade tick from the tape."""
        self.latest_price = price
        self.last_update_ts = ts
        signed_vol = size if side == "buy" else -size
        self.cvd += signed_vol

        trade_item = {"price": price, "size": size, "side": side, "ts": ts}
        self.recent_trades.append(trade_item)
        self.trade_count_1s += 1

        # Aggregate tick into all 11 timeframe buffers
        for tf, sec in TIMEFRAME_SECONDS.items():
            candle_start = int(ts // sec) * sec
            curr = self.current_candles.get(tf)

            if curr is None or curr["start_ts"] != candle_start:
                # Close previous candle if exists
                if curr is not None:
                    self.buffers[tf].append({
                        "ts": curr["start_ts"],
                        "open": curr["open"],
                        "high": curr["high"],
                        "low": curr["low"],
                        "close": curr["close"],
                        "vol": curr["vol"],
                    })
                # Start new candle
                self.current_candles[tf] = {
                    "start_ts": candle_start,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "vol": size,
                }
            else:
                # Update current active candle
                curr["high"] = max(curr["high"], price)
                curr["low"] = min(curr["low"], price)
                curr["close"] = price
                curr["vol"] += size

    def on_orderbook_update(self, bids_data: list, asks_data: list, action: str):
        """Process L2 order book delta or snapshot."""
        if action == "snapshot":
            self.bids = {float(p): float(s) for p, s, *_ in bids_data if float(s) > 0}
            self.asks = {float(p): float(s) for p, s, *_ in asks_data if float(s) > 0}
        else:
            for p, s, *_ in bids_data:
                pf, sf = float(p), float(s)
                if sf == 0:
                    self.bids.pop(pf, None)
                else:
                    self.bids[pf] = sf
            for p, s, *_ in asks_data:
                pf, sf = float(p), float(s)
                if sf == 0:
                    self.asks.pop(pf, None)
                else:
                    self.asks[pf] = sf

        if self.bids:
            self.best_bid = max(self.bids.keys())
        if self.asks:
            self.best_ask = min(self.asks.keys())

        # Store for 3-snapshot anti-spoofing
        self.book_snapshots.append({
            "ts": time.time(),
            "bids": dict(self.bids),
            "asks": dict(self.asks),
        })

    def on_derivatives_update(self, channel: str, data: list):
        """Process real-time Open Interest and Funding Rate."""
        for item in data:
            if channel == "open-interest":
                oi = float(item.get("oi", 0.0))
                if oi > 0:
                    self.open_interest = oi
                    self.oi_history.append((time.time(), oi))
            elif channel == "funding-rate":
                fr = float(item.get("fundingRate", 0.0))
                self.funding_rate = fr
                self.next_funding_time = int(item.get("fundingTime", 0))

    async def _listen_ws(self):
        """Internal asynchronous WebSocket loop with automatic reconnect."""
        sub_msg = {
            "op": "subscribe",
            "args": [
                {"channel": "trades", "instId": self.inst_id},
                {"channel": "books", "instId": self.inst_id},
                {"channel": "open-interest", "instId": self.swap_id},
                {"channel": "funding-rate", "instId": self.swap_id},
                {"channel": "tickers", "instId": self.inst_id},
            ],
        }

        while self.running:
            try:
                logger.info(f"[Stream] Connecting to OKX WebSocket: {OKX_WS_PUBLIC}")
                async with websockets.connect(OKX_WS_PUBLIC, ping_interval=20, ping_timeout=10) as ws:
                    self._ws = ws
                    await ws.send(json.dumps(sub_msg))
                    logger.info("[Stream] Subscribed to trades, books, OI, funding-rate, tickers.")

                    # Start velocity timer task
                    asyncio.create_task(self._velocity_ticker())

                    async for message in ws:
                        if not self.running:
                            break
                        try:
                            msg = json.loads(message)
                            arg = msg.get("arg", {})
                            channel = arg.get("channel")
                            data = msg.get("data", [])
                            action = msg.get("action", "update")

                            if channel == "trades":
                                for trade in data:
                                    p = float(trade["px"])
                                    s = float(trade["sz"])
                                    side = trade["side"]
                                    ts = int(trade["ts"]) / 1000.0
                                    self.on_trade_tick(p, s, side, ts)

                            elif channel == "books":
                                for item in data:
                                    self.on_orderbook_update(item.get("bids", []), item.get("asks", []), action)

                            elif channel in ("open-interest", "funding-rate"):
                                self.on_derivatives_update(channel, data)

                            elif channel == "tickers":
                                for item in data:
                                    if "last" in item:
                                        self.latest_price = float(item["last"])

                        except Exception as e:
                            logger.error(f"[Stream] Error parsing WS message: {e}")

            except (websockets.ConnectionClosed, websockets.WebSocketException, Exception) as e:
                logger.warning(f"[Stream] WS connection lost: {e}. Reconnecting in 3 seconds...")
                await asyncio.sleep(3)

    async def _velocity_ticker(self):
        """Compute trades per second every second."""
        while self.running:
            await asyncio.sleep(1.0)
            self.trade_velocity = float(self.trade_count_1s)
            self.trade_count_1s = 0

    def get_oi_zscore(self) -> float:
        """Calculate the statistical Z-score of recent Open Interest changes."""
        if len(self.oi_history) < 10:
            return 0.0
        ois = [x[1] for x in self.oi_history]
        diffs = np.diff(ois)
        if len(diffs) < 5 or np.std(diffs) == 0:
            return 0.0
        latest_diff = diffs[-1]
        mean_diff = np.mean(diffs)
        std_diff = np.std(diffs)
        return float((latest_diff - mean_diff) / std_diff)

    def get_anti_spoof_depth(self, distance_pct: float = 0.005) -> Tuple[float, float, float]:
        """
        Calculates Bid and Ask depth within distance_pct using the 3-Snapshot Anti-Spoofing Filter.
        A wall must persist across snapshots to be counted.
        Returns: (bid_depth, ask_depth, tanh_imbalance)
        """
        if not self.bids or not self.asks or self.latest_price <= 0:
            return 0.0, 0.0, 0.0

        mid = self.latest_price
        bid_limit = mid * (1.0 - distance_pct)
        ask_limit = mid * (1.0 + distance_pct)

        # Base depth from current book
        curr_bids = {p: s for p, s in self.bids.items() if p >= bid_limit}
        curr_asks = {p: s for p, s in self.asks.items() if p <= ask_limit}

        # 3-Snapshot persistence filter: if we have 3 snapshots, wall must exist in at least 2
        if len(self.book_snapshots) >= 3:
            filtered_bids = {}
            for p, s in curr_bids.items():
                seen_count = sum(1 for snap in self.book_snapshots if any(abs(bp - p) / p < 0.0002 for bp in snap["bids"]))
                if seen_count >= 2:
                    filtered_bids[p] = s
            curr_bids = filtered_bids

            filtered_asks = {}
            for p, s in curr_asks.items():
                seen_count = sum(1 for snap in self.book_snapshots if any(abs(ap - p) / p < 0.0002 for ap in snap["asks"]))
                if seen_count >= 2:
                    filtered_asks[p] = s
            curr_asks = filtered_asks

        bid_vol = sum(curr_bids.values())
        ask_vol = sum(curr_asks.values())
        total = bid_vol + ask_vol

        # tanh-normalized imbalance ratio: [-1.0, +1.0]
        if total > 0:
            ratio = (bid_vol - ask_vol) / total
            tanh_imbalance = float(np.tanh(2.5 * ratio))
        else:
            tanh_imbalance = 0.0

        return bid_vol, ask_vol, tanh_imbalance

    def get_candles(self, tf: str) -> List[dict]:
        """Returns the chronological list of completed candles for a timeframe."""
        return list(self.buffers.get(tf, []))

    def start(self):
        """Start the stream asynchronously in an event loop."""
        self.running = True
        self.seed_initial_history()
        asyncio.create_task(self._listen_ws())

    def stop(self):
        """Stop the stream."""
        self.running = False
        if self._ws:
            asyncio.create_task(self._ws.close())
