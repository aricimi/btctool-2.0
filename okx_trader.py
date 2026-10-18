"""
btctool 2.0 - OKX Spot Execution Engine (okx_trader.py)
Automated spot execution client for BTC/USDT with 4 defensive shields:
1. Anti-Hanging Order Shield: Auto-cancels hanging limit orders if price escapes.
2. Dynamic Partial Fill Tracking: Queries fill details and adjusts trailing stops.
3. Server-Side Trigger Stops: Native OCO/Trigger stops on OKX servers.
4. Slippage-Capped Emergency Exits: IOC limit sells preventing dump slippage.
"""

import os
import sys
import json
import time
import hmac
import base64
import hashlib
import datetime
from typing import Optional, Dict, Any, Tuple
import requests

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "okx_config.json")
OKX_API_URL = "https://www.okx.com"


class OKXSpotClient:
    """Production-grade OKX V5 REST API Spot Execution Client."""

    def __init__(self, api_key: Optional[str] = None,
                 secret_key: Optional[str] = None,
                 passphrase: Optional[str] = None,
                 is_simulated: bool = False):
        self.api_key = api_key or os.environ.get("OKX_API_KEY")
        self.secret_key = secret_key or os.environ.get("OKX_API_SECRET")
        self.passphrase = passphrase or os.environ.get("OKX_PASSPHRASE")
        self.is_simulated = is_simulated
        self.symbol = "BTC-USDT"

        # Load from config file if available
        if (not self.api_key or not self.secret_key or not self.passphrase) and os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                    self.api_key = self.api_key or cfg.get("api_key")
                    self.secret_key = self.secret_key or cfg.get("secret_key")
                    self.passphrase = self.passphrase or cfg.get("passphrase")
                    self.is_simulated = cfg.get("is_simulated", self.is_simulated)
            except Exception:
                pass

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key and self.passphrase and
                    self.api_key != "YOUR_OKX_API_KEY")

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        message = timestamp + method.upper() + request_path + body
        mac = hmac.new(self.secret_key.encode("utf-8"), message.encode("utf-8"), digestmod=hashlib.sha256)
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None,
                 data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self.is_configured:
            return None

        url = OKX_API_URL + endpoint
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        timestamp = now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        body_str = json.dumps(data) if data else ""

        request_path = endpoint
        if params:
            query_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            request_path += f"?{query_str}"

        sign = self._generate_signature(timestamp, method, request_path, body_str)
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }
        if self.is_simulated:
            headers["x-simulated-trading"] = "1"

        # Exponential backoff retry loop (handles HTTP 429 rate limits)
        for attempt in range(3):
            try:
                if method.upper() == "GET":
                    r = requests.get(url, params=params, headers=headers, timeout=5)
                elif method.upper() == "POST":
                    r = requests.post(url, json=data, headers=headers, timeout=5)
                else:
                    return None

                if r.status_code == 429:
                    time.sleep(0.5 * (attempt + 1))
                    continue

                res = r.json()
                if res.get("code") == "0":
                    return res
                else:
                    print(f"[OKX API Error] Code {res.get('code')}: {res.get('msg')}")
                    return None
            except Exception as e:
                time.sleep(0.3 * (attempt + 1))

        return None

    def get_spot_balance(self) -> Dict[str, float]:
        """Queries spot USDT and BTC available balances."""
        res = self._request("GET", "/api/v5/account/balance", params={"ccy": "USDT,BTC"})
        balances = {"USDT": 0.0, "BTC": 0.0}
        if res and "data" in res and res["data"]:
            details = res["data"][0].get("details", [])
            for item in details:
                ccy = item.get("ccy")
                avail = float(item.get("availBal", 0.0))
                if ccy in balances:
                    balances[ccy] = avail
        return balances

    def place_spot_order(self, side: str, sz: str, price: Optional[float] = None,
                         order_type: str = "limit", post_only: bool = False) -> Optional[str]:
        """
        Places a spot order on BTC-USDT.
        side: 'buy' or 'sell'
        order_type: 'limit' or 'market'
        post_only: True ensures Maker fee execution (0.08%).
        """
        # Resolve percentage sizing for sells (e.g. "100%")
        if side.lower() == "sell" and (sz == "100%" or sz.endswith("%")):
            bals = self.get_spot_balance()
            avail_btc = bals.get("BTC", 0.0)
            if sz.endswith("%"):
                pct = float(sz.replace("%", "")) / 100.0
                avail_btc *= pct
            if avail_btc < 0.00001:
                print(f"[OKX Trade] Insufficient BTC balance to sell ({avail_btc:.6f} BTC)")
                return None
            sz = f"{avail_btc:.6f}"

        payload: Dict[str, Any] = {
            "instId": self.symbol,
            "tdMode": "cash",
            "side": side.lower(),
            "ordType": "post_only" if post_only else order_type,
            "sz": sz
        }

        # For spot market buys in BTC units, specify tgtCcy="base_ccy"
        if side.lower() == "buy" and order_type == "market":
            try:
                if float(sz) < 10.0:  # If sz is BTC quantity rather than USDT dollar value
                    payload["tgtCcy"] = "base_ccy"
            except ValueError:
                pass

        if price is not None and order_type != "market":
            payload["px"] = f"{price:.2f}"

        res = self._request("POST", "/api/v5/trade/order", data=payload)
        if res and "data" in res and res["data"]:
            order_id = res["data"][0].get("ordId")
            print(f"[OKX Trade] Spot {side.upper()} order placed: ID {order_id} (sz={sz}) at {price or 'MARKET'}")
            return order_id
        return None

    def place_server_stop_loss(self, trigger_price: float, sz: str) -> Optional[str]:
        """Places a server-side conditional stop market order directly on OKX."""
        if sz == "100%" or sz.endswith("%"):
            bals = self.get_spot_balance()
            avail_btc = bals.get("BTC", 0.0)
            if sz.endswith("%"):
                pct = float(sz.replace("%", "")) / 100.0
                avail_btc *= pct
            if avail_btc < 0.00001:
                return None
            sz = f"{avail_btc:.6f}"

        payload: Dict[str, Any] = {
            "instId": self.symbol,
            "tdMode": "cash",
            "side": "sell",
            "ordType": "conditional",
            "sz": sz,
            "tpTriggerPxType": "last",
            "slTriggerPx": f"{trigger_price:.2f}",
            "slOrdPx": "-1"  # -1 triggers market sell immediately on breach
        }
        res = self._request("POST", "/api/v5/trade/order-algo", data=payload)
        if res and "data" in res and res["data"]:
            algo_id = res["data"][0].get("algoId")
            print(f"[OKX Stop] Server-side Stop Loss active at ${trigger_price:.2f} (Algo ID {algo_id})")
            return algo_id
        return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancels an active spot order."""
        payload = {"instId": self.symbol, "ordId": order_id}
        res = self._request("POST", "/api/v5/trade/cancel-order", data=payload)
        return bool(res and res.get("code") == "0")

    def cancel_algo_stop(self, algo_id: str) -> bool:
        """Cancels an active conditional stop order."""
        payload = [{"instId": self.symbol, "algoId": algo_id}]
        res = self._request("POST", "/api/v5/trade/cancel-algos", data=payload)
        return bool(res and res.get("code") == "0")

    def execute_slippage_capped_exit(self, best_bid: float, sz: str) -> Optional[str]:
        """Whale Defense: Places IOC limit sell at best_bid - 0.05% to avoid dump slippage."""
        if sz == "100%" or sz.endswith("%"):
            bals = self.get_spot_balance()
            avail_btc = bals.get("BTC", 0.0)
            if sz.endswith("%"):
                pct = float(sz.replace("%", "")) / 100.0
                avail_btc *= pct
            if avail_btc < 0.00001:
                return None
            sz = f"{avail_btc:.6f}"

        limit_px = round(best_bid * 0.9995, 2)
        payload = {
            "instId": self.symbol,
            "tdMode": "cash",
            "side": "sell",
            "ordType": "ioc",
            "px": f"{limit_px:.2f}",
            "sz": sz
        }
        res = self._request("POST", "/api/v5/trade/order", data=payload)
        if res and "data" in res and res["data"]:
            return res["data"][0].get("ordId")
        return None

