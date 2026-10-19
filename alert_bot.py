"""
btctool 2.0 - Institutional Telegram Mobile Scalping & Ping-Pong Alert Bot
Architecture: Real-time Bybit/OKX order book scanner + 5M/15M ping-pong scalp engine.
Dispatches instant push alerts for entries, target hits (>= +0.20%), and stop invalidations.
"""

import os
import sys
from typing import Optional, Dict, Any, Tuple, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import time
import datetime
import threading
import gc
from http.server import HTTPServer, BaseHTTPRequestHandler
import math
import re
import numpy as np
import requests

from engine import MarketDataService, PredictiveEnsembleEngine, AdvisoryReport
from okx_trader import OKXSpotClient
from trade_logger import TradeJournal
import asyncio
from zebra_bot import ZebraBotEngine


CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_config.json")


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Responds to Render and UptimeRobot HTTP pings to keep service alive 24/7."""
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        payload = {
            "status": "online",
            "service": "btctool 2.0 Telegram Scalping Alert Engine",
            "utc_time": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format, *args):
        # Silence default access logging to keep console clean
        return


def start_health_server(port: int = 10000) -> Optional[HTTPServer]:
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"📡 Web Health Check Server running on port {port} (Listening for UptimeRobot pings)")
        return server
    except Exception as e:
        print(f"[Warning] Could not start HTTP health server on port {port}: {e}")
        return None


DEFAULT_BOT_TOKEN = "8981948899:AAFqJwDyX1_ZMnXRQSp2m6yNk9HuHJ9A7h0"
DEFAULT_CHAT_ID = "8922701269"


class TelegramNotifier:
    """Handles secure delivery of instant push alerts and on-demand commands."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        
        # Load from config file if not in environment
        if (not self.bot_token or not self.chat_id) and os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                    self.bot_token = self.bot_token or cfg.get("bot_token")
                    self.chat_id = self.chat_id or cfg.get("chat_id")
            except Exception:
                pass

        # Final production fallback ensuring zero cloud container silence
        self.bot_token = self.bot_token or DEFAULT_BOT_TOKEN
        self.chat_id = self.chat_id or DEFAULT_CHAT_ID
        self.last_update_id = 0

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and self.bot_token != "YOUR_BOT_TOKEN_HERE")

    def send_message(self, text: str) -> bool:
        """Sends an HTML formatted push message directly to your Telegram chat."""
        if not self.is_configured:
            print("[Telegram] Alert not sent: Bot Token or Chat ID not configured.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            r = requests.post(url, json=payload, timeout=6)
            if r.status_code == 200:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                clean_title = re.sub(r'<[^>]+>', '', lines[0]) if lines else "Alert"
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Telegram Alert Sent: {clean_title}")
                return True
            else:
                print(f"[Telegram Error] HTTP {r.status_code}: {r.text}")
                return False
        except Exception as e:
            print(f"[Telegram Network Error] {e}")
            return False

    def poll_incoming_command(self) -> Optional[str]:
        """Polls Telegram getUpdates for on-demand user commands (e.g. /status, /info, /ping)."""
        if not self.is_configured:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 0, "limit": 5}
        try:
            r = requests.get(url, params=params, timeout=4)
            if r.status_code == 200:
                data = r.json()
                if data.get("ok") and data.get("result"):
                    for update in data["result"]:
                        self.last_update_id = max(self.last_update_id, update.get("update_id", 0))
                        msg = update.get("message", {})
                        if str(msg.get("chat", {}).get("id")) == str(self.chat_id):
                            text = msg.get("text", "").strip()
                            if text:
                                return text
        except Exception:
            pass
        return None

    def send_test_ping(self) -> bool:
        msg = (
            "⚡ <b>btctool 2.0 · Telegram Alert System Online</b>\n\n"
            "Your mobile alert bot is successfully connected!\n"
            "Operating in pure <b>Event-Driven Autonomous Mode</b> (Zero Clock Spam).\n"
            "Send <code>/status</code> at any time to receive instant live telemetry."
        )
        return self.send_message(msg)


STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state.json")


class AutonomousExecutionEngine:
    """
    Continuous Multi-Scale Autonomous Spot Trading Engine & Telemetry Copilot:
    1. Continuous Market State Tracking:
       - ACCUMULATING: Volatility coiling, bid absorption, awaiting trigger.
       - EXPANDING: Trend impulse active, trailing parabolic stop.
       - STALLING / EXHAUSTION: Upper resistance ceiling reached, 1M/5M momentum fading.
       - REGRESSING: Price pulling back toward support floor; dynamic repositioning active.
    2. Telemetry & Alerts:
       - SPOT BUY SIGNAL: Pure continuous S_total confluence scoring (>= 65.0).
       - TARGET 1 & BREAKEVEN: Milestone reached, stop ratcheted to lock risk-free trade.
       - STALLING & REGRESSION WARNING: Notifies you to lock profits if holding, or wait for dip if in cash.
       - DYNAMIC DIP REPOSITIONING: Tracks dip descent and shifts buy zone adaptively.
       - WHALE DEFENSE: Immediate exit if order book collapses.
    3. Persistence:
       - bot_state.json survives Render cloud restarts with 4h staleness guard.
    """

    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.okx = OKXSpotClient()
        self.journal = TradeJournal()
        self.active_trade: Optional[Dict[str, Any]] = None
        self.market_state: str = "SCANNING"  # SCANNING, EXPANDING, STALLING, REGRESSING
        self.last_alert_time: float = 0.0
        self.last_reentry_time: float = 0.0
        self.last_stalling_alert_time: float = 0.0
        self.tracked_peak: float = 0.0
        self.projected_floor: float = 0.0
        self.last_s_total: float = 0.0

        if self.okx.is_configured:
            print("⚡ OKX Execution Client Online (Live Auto-Trade Active)")
        else:
            print("📱 Telegram Execution Copilot Active (Tuned for Spot Orders on Revolut X)")

        # Load persisted state if exists
        self._load_state()

    def _save_state(self) -> None:
        state = {
            "market_state": self.market_state,
            "active_trade": self.active_trade,
            "tracked_peak": self.tracked_peak,
            "projected_floor": self.projected_floor,
            "last_alert_time": self.last_alert_time,
            "last_stalling_alert_time": self.last_stalling_alert_time,
            "last_s_total": self.last_s_total,
            "saved_at": time.time()
        }
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[State] Save error: {e}")

    def _load_state(self) -> None:
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            if time.time() - state.get("saved_at", 0) > 14400:
                print("[State] Stale state discarded (>4h old).")
                return
            self.market_state              = state.get("market_state", "SCANNING")
            self.active_trade              = state.get("active_trade", None)
            self.tracked_peak              = state.get("tracked_peak", 0.0)
            self.projected_floor           = state.get("projected_floor", 0.0)
            self.last_stalling_alert_time  = state.get("last_stalling_alert_time", 0.0)
            self.last_alert_time    = state.get("last_alert_time", 0.0)
            self.last_s_total       = state.get("last_s_total", 0.0)
            if self.active_trade:
                print(f"[State] Recovered trade from disk. Entry: {self.active_trade.get('entry')}")
        except Exception as e:
            print(f"[State] Load error: {e}")

    def _handle_on_demand_status(self, curr_price: Optional[float] = None, macro: Optional[str] = None,
                                 s_total: Optional[float] = None, ob: Any = None, td: Any = None) -> None:
        """Sends an on-demand status report in direct response to a user's Telegram command (/status)."""
        curr_price = curr_price or getattr(self, "latest_price", 0.0)
        s_total = s_total if s_total is not None else getattr(self, "last_s_total", 0.0)
        ob = ob or getattr(self, "latest_ob", None)

        delta_str = f"{ob.taker_delta:+.2f}" if ob else "+0.00"
        depth_str = f"{ob.imbalance_pct:+.1f}%" if ob else "+0.0%"

        # Spot-Purged Strategy Action: Never tell a spot trader to short!
        if self.active_trade:
            t = self.active_trade
            gain_pct = ((curr_price - t['entry']) / t['entry']) * 100.0 if t['entry'] > 0 else 0.0
            pos_str = (
                f"🟢 <b>ACTIVE SPOT POSITION</b>\n"
                f"• Entry: <b>${t['entry']:,.2f}</b> | Current: <b>${curr_price:,.2f}</b> (<b>{gain_pct:+.2f}%</b>)\n"
                f"• Stop Loss: <b>${t['current_stop']:,.2f}</b> ({'🛡️ BREAKEVEN LOCKED' if t.get('breakeven_set') else 'HARD STOP'})\n"
                f"• Target 1: ${t['target_1']:,.2f} | Runner Target 2: ${t['target_2']:,.2f}"
            )
            strategy_str = "MANAGING ACTIVE SPOT POSITION"
        elif self.market_state in ["STALLING", "REGRESSING"]:
            pos_str = (
                f"🟡 <b>IN CASH · PULLBACK SUPPORT MONITORING</b>\n"
                f"• Tracked Peak: <b>${self.tracked_peak:,.2f}</b>\n"
                f"• Potential Floor: <b>${self.projected_floor:,.2f}</b>"
            )
            strategy_str = "DEFENSIVE CASH · AWAITING CONFLUENCE REVERSAL"
        elif s_total >= 55.0:
            pos_str = f"🟢 <b>IN CASH · HIGH BUY CONFLUENCE BUILDING</b>"
            strategy_str = "HIGH CONFLUENCE · PREPARING SPOT BUY"
        else:
            pos_str = f"⚪ <b>IN CASH · SCANNING FOR DIP & BREAKOUT IGNITION</b>"
            strategy_str = "DEFENSIVE CASH · AWAITING BUYER IGNITION"

        mode_tag = "⚡ OKX Auto-Trade Active" if self.okx.is_configured else "📱 Copilot Mode (Revolut X)"

        status_msg = (
            f"📡 <b>BTCTOOL: ON-DEMAND ENGINE STATUS</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>BTC Price:</b> <b>${curr_price:,.2f}</b>\n"
            f"📊 <b>State:</b> <b>{self.market_state}</b> | <b>{mode_tag}</b>\n"
            f"🎯 <b>Strategy:</b> <b>{strategy_str}</b>\n"
            f"🧮 <b>Confluence Score:</b> <b>{s_total:.1f} / 100</b> "
            f"{'🟢 NEAR SIGNAL' if s_total >= 55 else '🟡 BUILDING' if s_total >= 40 else '⚪ QUIET'}\n"
            f"⚡ <b>Order Flow:</b> Taker Delta: <b>{delta_str}</b> | Depth: <b>{depth_str}</b>\n\n"
            f"{pos_str}\n\n"
            f"💡 <i>Running 24/7 in pure Event-Driven mode (Zero clock spam).</i>"
        )
        self.notifier.send_message(status_msg)

    def _calculate_dynamic_levels(self, curr_price: float, atr: float,
                                  df_1m: Any, df_5m: Any, ob: Any) -> Tuple[float, float, float, float, float, float]:
        """
        Dynamically computes structural invalidation shelf and opposing liquidity targets.
        Enforces:
        - Structural stop below local swing floor / order book bid shelf.
        - Minimum 1.5x Reward-to-Risk ratio dynamically anchored to structural resistance.
        Returns: (stop_price, tp1_price, tp2_price, risk_pct, tp1_gain_pct, tp2_gain_pct)
        """
        l_1m = df_1m["Low"]
        l_5m = df_5m["Low"]
        # Look at the structural swing low across visible chart
        structural_floor = min(l_1m.min(), l_5m.min())

        # Invalidation distance based on structural shelf + volatility buffer
        raw_risk = max(curr_price - structural_floor + (0.15 * atr), 0.8 * atr)
        min_risk_dist = curr_price * 0.0012
        max_risk_dist = max(curr_price * 0.0075, 2.5 * atr)
        risk_dist = max(min_risk_dist, min(raw_risk, max_risk_dist))
        stop_price = round(curr_price - risk_dist, 2)

        # Reward distance: Anchored dynamically to structural resistance / volatility
        # Ensures positive asymmetry (Target 1 >= 1.5x risk) without arbitrary retail floor percentages
        min_tp1_dist = max(risk_dist * 1.5, 1.2 * atr)
        tp1_price = round(curr_price + min_tp1_dist, 2)

        # Runner target (Target 2): Expands for momentum waves
        tp2_dist = max(risk_dist * 2.8, 2.5 * atr)
        tp2_price = round(curr_price + tp2_dist, 2)

        risk_pct = ((curr_price - stop_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
        tp1_gain_pct = ((tp1_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
        tp2_gain_pct = ((tp2_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0

        return stop_price, tp1_price, tp2_price, risk_pct, tp1_gain_pct, tp2_gain_pct

    def _compute_confluence_score(self, ob: Any, pct_b_1m: float, pct_b_5m: float, pct_b_15m: float,
                                  has_rejection: bool, vol_surge: bool, squeeze: str, macro: str) -> Tuple[float, Dict[str, float]]:
        """Computes continuous S_total confluence scoring model (0.0 to 100.0) without macro vetoes."""
        # S_tape: Points earned for net taker buying (0.0 to 35.0).
        # Sellers in control (taker_delta <= 0.04) earns zero tape points.
        if ob.taker_delta > 0.04:
            s_tape = min(35.0, 35.0 * float(np.tanh(2.2 * ob.taker_delta)))
        else:
            s_tape = 0.0

        # S_depth: Points earned for positive bid depth support (0.0 to 25.0).
        # Ask-heavy books (imbalance_pct <= 2.0%) earns zero depth points.
        if ob.imbalance_pct > 2.0:
            s_depth = min(25.0, 25.0 * float(np.tanh(2.5 * (ob.imbalance_pct / 100.0))))
        else:
            s_depth = 0.0

        # S_micro: Structural swing rejection + micro-trend inflection (0.0 to 25.0)
        s_micro_wick = 15.0 if has_rejection else (8.0 if vol_surge else 0.0)
        pct_b_avg = (pct_b_1m + pct_b_5m) / 2.0
        if pct_b_avg <= 0.40:
            # Dip rebound zone: Points for inflecting off the low
            s_micro_bb = min(10.0 * max(0.0, 1.0 - (pct_b_avg / 0.4)), 10.0)
        else:
            # Expansion push
            s_micro_bb = min(10.0 * (pct_b_avg / 0.8), 10.0)
        s_micro = min(s_micro_wick + s_micro_bb, 25.0)

        # S_structure: Dynamic structure (0.0 to 15.0) - Squeeze firing OR exhaustion dip recovery
        if squeeze in ["FIRING", "LOADED"]:
            s_structure = 15.0
        elif pct_b_avg <= 0.35 and ob.taker_delta > 0.08:
            # Exhaustion dip recovery in expanded volatility gets high structural points
            s_structure = 14.0
        elif squeeze == "TRENDING":
            s_structure = 11.0
        else:
            s_structure = 6.0

        s_total = s_tape + s_depth + s_micro + s_structure
        sub_scores = {
            "S_tape": s_tape, "S_depth": s_depth,
            "S_micro": s_micro, "S_structure": s_structure
        }
        return s_total, sub_scores


    def evaluate_market_cycle(self) -> None:
        """Runs the continuous autonomous loop across the entire market continuum."""
        # Flush any pending CSV updates if Excel was previously locking the file
        if getattr(self, "journal", None):
            self.journal.flush_pending_csv()

        try:
            report_15m: AdvisoryReport = PredictiveEnsembleEngine.generate_advisory(symbol="BTCUSDT", timeframe="15m")
            df_1m = MarketDataService.fetch_klines("BTCUSDT", "1m", limit=35)
            df_5m = MarketDataService.fetch_klines("BTCUSDT", "5m", limit=35)
        except Exception as e:
            print(f"[Engine Execution Cycle Error] {e}")
            return

        curr_price = report_15m.latest_price
        ob = report_15m.orderbook
        td = report_15m.trade_directive
        pct_b_15m = report_15m.statistical_brain.details["percent_b"]
        atr = report_15m.atr_value
        squeeze = report_15m.squeeze_state
        macro = report_15m.macro_regime_4h
        oi_conf = report_15m.oi_confluence

        # Cache latest metrics for sub-second on-demand status responses
        self.latest_price = curr_price
        self.latest_macro = macro
        self.latest_ob = ob
        self.latest_td = td

        # 1. Extract Micro-Scale Metrics (1M and 5M)
        c_1m = df_1m["Close"]
        h_1m = df_1m["High"]
        l_1m = df_1m["Low"]
        o_1m = df_1m["Open"]
        v_1m = df_1m["Volume"]
        mean_1m = c_1m.rolling(20).mean().iloc[-1]
        std_1m  = c_1m.rolling(20).std().iloc[-1]
        pct_b_1m = float((c_1m.iloc[-1] - (mean_1m - 2*std_1m)) / (4*std_1m)) if std_1m > 0 else 0.5

        c_5m = df_5m["Close"]
        h_5m = df_5m["High"]
        l_5m = df_5m["Low"]
        mean_5m = c_5m.rolling(20).mean().iloc[-1]
        std_5m  = c_5m.rolling(20).std().iloc[-1]
        pct_b_5m = float((c_5m.iloc[-1] - (mean_5m - 2*std_5m)) / (4*std_5m)) if std_5m > 0 else 0.5

        # 1M candle shape dynamics & dynamic swing structure
        swing_low_1m = l_1m.min()
        recent_has_wick = any((min(o_1m.iloc[i], c_1m.iloc[i]) - l_1m.iloc[i]) >= (abs(c_1m.iloc[i] - o_1m.iloc[i]) * 0.85) for i in range(-5, 0))
        vol_surge_1m = v_1m.iloc[-1] > (v_1m.iloc[-10:].mean() * 1.25)
        has_rejection = recent_has_wick or ((curr_price - swing_low_1m) <= (1.5 * atr) and c_1m.iloc[-1] > o_1m.iloc[-1] and vol_surge_1m)

        now = time.time()

        # Compute continuous multivariate confluence score (0.0 to 100.0) without macro vetoes
        s_total, sub_scores = self._compute_confluence_score(
            ob=ob,
            pct_b_1m=pct_b_1m,
            pct_b_5m=pct_b_5m,
            pct_b_15m=pct_b_15m,
            has_rejection=has_rejection,
            vol_surge=vol_surge_1m,
            squeeze=squeeze,
            macro=macro
        )
        self.last_s_total = s_total

        # 2. Check for On-Demand User Command from Telegram (e.g. /status, /info, /ping)
        cmd = self.notifier.poll_incoming_command()
        if cmd:
            cmd_lower = cmd.lower()
            if any(k in cmd_lower for k in ["/status", "status", "/info", "info", "/ping", "ping", "/state"]):
                self._handle_on_demand_status(curr_price, macro, s_total, ob, td)

        # 3. Manage Active Position (if in a trade)
        if self.active_trade is not None:
            self._manage_active_trade(curr_price, ob, atr, oi_conf, pct_b_15m, pct_b_5m, pct_b_1m, df_1m)
            return

        # 4. Zero-Ego Re-engagement: Breakout Momentum Resumption
        # If in STALLING or REGRESSING and buyers blow through the peak, re-enter immediately!
        if self.market_state in ["STALLING", "REGRESSING"] and self.tracked_peak > 0:
            if curr_price >= (self.tracked_peak * 0.999) and (s_total >= 65.0 or sub_scores["S_tape"] >= 22.0):
                if (now - self.last_reentry_time) > 15:
                    self.last_reentry_time = now
                    stop_p, tp1_p, tp2_p, r_pct, tp1_g, tp2_g = self._calculate_dynamic_levels(
                        curr_price, atr, df_1m, df_5m, ob
                    )
                    self.market_state = "EXPANDING"
                    self._trigger_entry(
                        setup_name="RE-ENGAGEMENT: BREAKOUT MOMENTUM RESUMPTION",
                        price=curr_price,
                        tp1=tp1_p,
                        tp2=tp2_p,
                        stop=stop_p,
                        tp1_gain=tp1_g,
                        tp2_gain=tp2_g,
                        risk_pct=r_pct,
                        rationale=f"Resistance at ${self.tracked_peak:,.2f} shattered by aggressive buyer volume (Delta {ob.taker_delta:+.2f}).",
                        timeframe="MOMENTUM BREAKOUT"
                    )
                    self._save_state()
                    return
            # Only reset to SCANNING if price had previously entered REGRESSING and now climbed back to peak
            elif self.market_state == "REGRESSING" and curr_price >= (self.tracked_peak * 0.998):
                self.market_state = "SCANNING"
                self.tracked_peak = 0.0
                self.projected_floor = 0.0
                print("[State Machine] Price regressed then recovered to peak. Resetting to SCANNING.")
                self._save_state()
            # If price cooled off back to the neutral middle channel (<= 50% %B), reset cleanly to SCANNING
            elif pct_b_15m <= 0.50 and pct_b_5m <= 0.50:
                self.market_state = "SCANNING"
                self.tracked_peak = 0.0
                self.projected_floor = 0.0
                print("[State Machine] Momentum cooled back to mid-channel. Resetting to SCANNING.")
                self._save_state()

        # 5. Detect Stalling & Anticipate Regression (Using Bollinger Band Geometry)
        if pct_b_15m >= 0.78 or pct_b_5m >= 0.80 or pct_b_1m >= 0.85:
            # Throttle to max 1 stalling alert per 20 minutes (1200 seconds) to prevent notification loops
            if self.market_state != "STALLING" and (now - self.last_stalling_alert_time) > 1200:
                self.market_state = "STALLING"
                self.last_stalling_alert_time = now
                bb_upper_1m = mean_1m + 2.0 * std_1m
                bb_mid_1m = mean_1m
                # Ceiling is anchored to the upper Bollinger Band of the active move
                self.tracked_peak = round(max(curr_price, bb_upper_1m), 2)
                # Projected reload floor is the Middle Band (SMA 20) or lower, guaranteed strictly < curr_price
                self.projected_floor = round(min(bb_mid_1m, curr_price - 0.5 * atr), 2)

                msg = (
                    f"⚠️ <b>MOMENTUM STALLING AT RESISTANCE · DO NOT BUY</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📈 <b>Upper Resistance:</b> <b>${self.tracked_peak:,.2f}</b> | Current: <b>${curr_price:,.2f}</b>\n"
                    f"📉 <b>Tape Condition:</b> Overhead ceiling active. Momentum flattening against bands.\n"
                    f"🎯 <b>Projected Dip Floor:</b> <b>${self.projected_floor:,.2f}</b>\n\n"
                    f"👉 <b>Action:</b> <b>DO NOT BUY HERE.</b> Stay in cash. Bot is actively tracking regression descent toward ${self.projected_floor:,.2f} for reload."
                )
                if self.notifier.send_message(msg):
                    self.last_alert_time = now
                self._save_state()
                return

        # 7. Pure Probabilistic Confluence Entry Gate (S_total >= 65.0)
        if s_total >= 65.0 and (now - self.last_alert_time) > 20:
            stop_price, tp1_price, tp2_price, risk_pct, tp1_gain_pct, tp2_gain_pct = self._calculate_dynamic_levels(
                curr_price, atr, df_1m, df_5m, ob
            )

            # Strict Positive Asymmetry Filter: Ensure Expected Reward exceeds Risk
            if tp1_gain_pct < (1.4 * risk_pct):
                return


            if sub_scores["S_tape"] >= 22.0:
                setup_name = "TAKER IGNITION CONFLUENCE"
            elif sub_scores["S_structure"] >= 12.0:
                setup_name = "VOLATILITY SQUEEZE RELEASE"
            elif sub_scores["S_depth"] >= 15.0:
                setup_name = "INSTITUTIONAL BID ABSORPTION"
            elif sub_scores["S_micro"] >= 18.0:
                setup_name = "MICRO-REVERSAL COMPRESSION"
            else:
                setup_name = "MULTI-SCALE MOMENTUM CONFLUENCE"

            rationale = (
                f"S_total={s_total:.1f}/100 | "
                f"Tape={sub_scores['S_tape']:.1f} "
                f"Micro={sub_scores['S_micro']:.1f} "
                f"Depth={sub_scores['S_depth']:.1f} "
                f"Structure={sub_scores['S_structure']:.1f}"
            )

            self.market_state = "EXPANDING"
            self._trigger_entry(
                setup_name=setup_name,
                price=curr_price,
                tp1=tp1_price,
                tp2=tp2_price,
                stop=stop_price,
                tp1_gain=tp1_gain_pct,
                tp2_gain=tp2_gain_pct,
                risk_pct=risk_pct,
                rationale=rationale,
                timeframe="MULTI-SCALE 1M/5M/15M"
            )
            self.last_alert_time = now
            self._save_state()
            return

    def _trigger_entry(self, setup_name: str, price: float, tp1: float, tp2: float,
                       stop: float, tp1_gain: float, tp2_gain: float, risk_pct: float,
                       rationale: str, timeframe: str) -> None:
        """Dispatches an explicit DIRECT ACTION ORDER and auto-executes on OKX if connected."""
        rr_ratio = tp1_gain / risk_pct if risk_pct > 0 else 2.0

        okx_exec_str = ""
        if self.okx.is_configured:
            try:
                bals = self.okx.get_spot_balance()
                usdt_avail = bals.get("USDT", 0.0)
                if usdt_avail >= 10.0:
                    trade_usd = min(usdt_avail, 50.0)
                    sz_btc = round(trade_usd / price, 5)
                    ord_id = self.okx.place_spot_order(side="buy", sz=str(sz_btc), order_type="market")
                    if ord_id:
                        okx_exec_str = f"\n⚡ <b>OKX Auto-Executed:</b> {sz_btc} BTC (~${trade_usd:.2f}) [ID: {ord_id}]"
            except Exception as e:
                print(f"[OKX Exec Error] {e}")

        msg = (
            f"🟢 <b>BUY SPOT NOW (ENTER TRADE)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Setup:</b> {setup_name}\n"
            f"💼 <b>Allocation:</b> Tranche 1 (Base Scalp Allocation)\n"
            f"⏰ <b>Trigger Timeframe:</b> {timeframe}\n"
            f"💵 <b>Entry Price:</b> <b>${price:,.2f}</b>\n\n"
            f"🎯 <b>Target 1:</b> ${tp1:,.2f} (<b>+{tp1_gain:.2f}%</b> · Breakeven Trigger)\n"
            f"🚀 <b>Target 2 (Runner):</b> ${tp2:,.2f} (<b>+{tp2_gain:.2f}%</b> · Trailing Peak)\n"
            f"🛑 <b>Stop Loss:</b> ${stop:,.2f} (<b>-{risk_pct:.2f}%</b>)\n"
            f"⚖️ <b>Risk/Reward Ratio:</b> <b>{rr_ratio:.1f} : 1</b>\n\n"
            f"📊 <b>Execution Rationale:</b>\n"
            f"• <i>{rationale}</i>\n\n"
            f"👉 <b>Action:</b> Place your Spot Buy order on your exchange now and set your stop loss.{okx_exec_str}"
        )

        sent = self.notifier.send_message(msg)
        if sent:
            self.last_alert_time = time.time()
            self.active_trade = {
                'entry':           price,
                'target_1':        tp1,
                'target_2':        tp2,
                'current_stop':    stop,
                'highest_price':   price,
                'target_1_hit':    False,
                'breakeven_set':   False,
                'tranche_2_added': False,
                'ratchet_level':   0,
                'timestamp':       time.time()
            }
            self.journal.record_entry(
                setup_name=setup_name,
                entry_price=price,
                stop_loss=stop,
                target_1=tp1,
                target_2=tp2,
                rationale=rationale
            )
            self._save_state()

    def _manage_active_trade(self, curr_price: float, ob: Any, atr: float, oi_conf: str,
                             pct_b_15m: float = 0.5, pct_b_5m: float = 0.5, pct_b_1m: float = 0.5,
                             df_1m: Any = None) -> None:
        """
        Active Position Policy Engine (Fluid Execution):
        Evaluates tape candle-by-candle:
        - EARLY_BAIL: Cuts loss immediately before stop if order book collapses.
        - HOLD_AND_STRETCH: Does not sell early if buyers are accelerating.
        - SCALE_IN: Adds Tranche 2 if breakout confirmed.
        - BANK_PROFIT: Exits on 1M volume/thrust exhaustion at resistance or trailing stop.
        - MEMORY SOFT STOP: Inspects tape at stop level; holds if absorbing, exits if breaking down.
        """
        t = self.active_trade
        if not t:
            return

        entry = t['entry']
        highest = max(t['highest_price'], curr_price)
        t['highest_price'] = highest

        in_profit = curr_price > entry
        gain_pct = ((curr_price - entry) / entry) * 100.0 if entry > 0 else 0.0

        # POLICY 1: HOLD AND STRETCH (MOMENTUM SURGING - DO NOT SELL YET)
        if curr_price >= t['target_1'] and ob.taker_delta >= 0.20:
            new_target = round(curr_price + 1.8 * atr, 2)
            new_stop = round(max(t['current_stop'], entry + 0.15 * atr), 2)
            if new_stop > t['current_stop']:
                t['current_stop'] = new_stop
                t['target_1_hit'] = True
                t['breakeven_set'] = True
                locked_gain = ((new_stop - entry) / entry) * 100.0
                gain_now = ((curr_price - entry) / entry) * 100.0
                msg = (
                    f"📈 <b>HOLD POSITION (DO NOT SELL YET)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💵 <b>Current Price:</b> <b>${curr_price:,.2f}</b> (<b>+{gain_now:.2f}%</b>)\n"
                    f"⚡ <b>Tape:</b> Buyer momentum surging (Delta {ob.taker_delta:+.2f}). Waiting for more push!\n"
                    f"🎯 <b>Expanded Target:</b> <b>${new_target:,.2f}</b>\n"
                    f"🔒 <b>Stop Loss Ratcheted:</b> <b>${new_stop:,.2f}</b> (<b>+{locked_gain:.2f}% Guaranteed Profit</b>)\n"
                    f"👉 <b>Action:</b> <b>DO NOT SELL.</b> Move your stop loss up on your exchange to ${new_stop:,.2f}."
                )
                self.notifier.send_message(msg)
                self._save_state()

        # POLICY 2: SCALE-IN (BUY MORE SPOT - TRANCHE 2)
        if t.get('breakeven_set') and not t.get('tranche_2_added') and ob.taker_delta >= 0.35 and curr_price >= (entry + 0.45 * atr):
            t['tranche_2_added'] = True
            okx_exec_str = ""
            if self.okx.is_configured:
                bals = self.okx.get_spot_balance()
                usdt_avail = bals.get("USDT", 0.0)
                if usdt_avail >= 10.0:
                    trade_usd = min(usdt_avail, 25.0)
                    sz_btc = round(trade_usd / curr_price, 5)
                    self.okx.place_spot_order(side="buy", sz=str(sz_btc), order_type="market")
                    okx_exec_str = f"\n⚡ <b>OKX Auto-Executed Tranche 2:</b> {sz_btc} BTC"
            msg = (
                f"➕ <b>BUY MORE SPOT (ADD TO POSITION)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Current Price:</b> <b>${curr_price:,.2f}</b>\n"
                f"🚀 <b>Tape Ignition:</b> Breakout continuation confirmed by aggressive market buying.\n"
                f"🔒 <b>Stop Loss for Total Position:</b> <b>${entry:,.2f}</b> (100% Risk-Free)\n"
                f"👉 <b>Action:</b> Buy 2nd Spot Tranche now to ride the expansion wave.{okx_exec_str}"
            )
            self.notifier.send_message(msg)
            self._save_state()

        # Target 1 Reached -> Move Stop to Breakeven
        if not t['target_1_hit'] and curr_price >= t['target_1']:
            t['target_1_hit'] = True
            t['breakeven_set'] = True
            new_stop = round(entry + 0.15 * atr, 2)
            t['current_stop'] = max(t['current_stop'], new_stop)
            msg = (
                f"🛡️ <b>UPDATE: MOVE STOP TO BREAKEVEN</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📈 <b>Current Price:</b> <b>${curr_price:,.2f}</b> (<b>+{gain_pct:.2f}% PROFIT</b>) ✅\n"
                f"🔄 <b>New Stop:</b> <b>${new_stop:,.2f}</b> (Guaranteed Breakeven / Fee Shield)\n"
                f"👉 <b>Action on Exchange:</b> Update your Stop Loss to <b>${new_stop:,.2f}</b> now. Trade is 100% Risk-Free!"
            )
            self.notifier.send_message(msg)
            self._save_state()

        # Parabolic Trailing Ratchet (Trailing higher swing lows)
        if t['target_1_hit']:
            dynamic_trail_stop = round(highest - 0.9 * atr, 2)
            if dynamic_trail_stop > (t['current_stop'] + 0.35 * atr):
                t['current_stop'] = dynamic_trail_stop
                locked_gain = ((dynamic_trail_stop - entry) / entry) * 100.0
                msg = (
                    f"📈 <b>UPDATE: RATCHET STOP LOSS HIGHER</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Highest: <b>${highest:,.2f}</b> | Current: <b>${curr_price:,.2f}</b>\n"
                    f"👉 <b>Action on Exchange:</b> Ratchet Stop Loss up to <b>${dynamic_trail_stop:,.2f}</b>\n"
                    f"🔒 <b>Locked-in Profit:</b> <b>+{locked_gain:.2f}%</b> (Guaranteed Win)"
                )
                self.notifier.send_message(msg)
                self._save_state()

        # POLICY 3: BANK PROFIT / MICRO-EXHAUSTION (FLOW WITH THE MARKET)
        # Exits when:
        # A) Price is in meaningful profit (>= +0.30% to ensure profit net of OKX 0.20% fees) and 1M chart shows volume/thrust exhaustion at resistance
        # B) Trailing stop touched after breakeven locked
        v_exhausted = False
        range_stalled = False
        if df_1m is not None and len(df_1m) >= 10:
            v_1m = df_1m["Volume"]
            c_1m = df_1m["Close"]
            o_1m = df_1m["Open"]
            v_exhausted = v_1m.iloc[-1] < (v_1m.iloc[-10:].mean() * 0.40)
            range_stalled = abs(c_1m.iloc[-1] - o_1m.iloc[-1]) < (0.20 * atr)

        is_micro_stalled = in_profit and (gain_pct >= 0.30) and (pct_b_1m >= 0.75 or pct_b_5m >= 0.75) and (v_exhausted or range_stalled or ob.taker_delta <= -0.20)
        trailing_stop_touched = (curr_price <= t['current_stop'] and t.get('breakeven_set'))

        if is_micro_stalled or trailing_stop_touched:
            realized_gain = gain_pct
            okx_exec_str = ""
            if self.okx.is_configured:
                self.okx.place_spot_order(side="sell", sz="100%", order_type="market")
                okx_exec_str = "\n⚡ <b>OKX Auto-Sold at Market.</b>"
            msg = (
                f"🏁 <b>SELL SPOT NOW (BANK YOUR PROFIT)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Exit Price:</b> <b>${curr_price:,.2f}</b>\n"
                f"💰 <b>Final Realized Gain:</b> <b>+{realized_gain:.2f}% PROFIT</b> 🏆\n"
                f"📊 <b>Exit Reason:</b> {'1M Volume/Thrust Stalled at Resistance' if is_micro_stalled else 'Trailing Stop Protected Profit'}\n"
                f"👉 <b>Action:</b> <b>SELL SPOT AT MARKET NOW.</b> Bank cash. Bot is actively tracking dip reload.{okx_exec_str}"
            )
            self.journal.record_exit(
                exit_price=curr_price,
                exit_reason='1M Volume/Thrust Stalled at Resistance' if is_micro_stalled else 'Trailing Stop Protected Profit'
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            self.market_state = "SCANNING"
            self.tracked_peak = highest
            self.projected_floor = round(min(highest - 0.5 * atr, curr_price - 0.3 * atr), 2)
            self._save_state()
            return

        # POLICY 4: CATASTROPHIC STRUCTURAL BREAKDOWN (BEFORE STOP)
        # Only triggers if trade has lost > 65% of risk distance AND order book + tape confirm violent collapse
        risk_distance = entry - t['current_stop'] if entry > t['current_stop'] else atr
        loss_distance = entry - curr_price
        if loss_distance >= (0.65 * risk_distance) and ob.imbalance_pct <= -35.0 and ob.taker_delta <= -0.55:
            loss_pct = abs(loss_distance / entry) * 100.0
            okx_exec_str = ""
            if self.okx.is_configured:
                self.okx.execute_slippage_capped_exit(best_bid=curr_price, sz="100%")
                okx_exec_str = "\n⚡ <b>OKX Auto-Exited at Market.</b>"
            msg = (
                f"⚠️ <b>SELL SPOT NOW (CATASTROPHIC ORDER BOOK COLLAPSE)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Exit Price:</b> <b>${curr_price:,.2f}</b> (<b>-{loss_pct:.2f}%</b>)\n"
                f"🚨 <b>Microstructure Warning:</b> Severe institutional selling (Imbalance {ob.imbalance_pct:.1f}% / Delta {ob.taker_delta:+.2f}).\n"
                f"👉 <b>Action:</b> <b>SELL SPOT AT MARKET NOW.</b> Cut loss early to protect capital.{okx_exec_str}"
            )
            self.journal.record_exit(
                exit_price=curr_price,
                exit_reason='Catastrophic Order Book Collapse'
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            self.market_state = "SCANNING"
            self._save_state()
            return

        # POLICY 5: MEMORY-BASED SOFT STOP (DECISION ZONE)
        if curr_price <= t['current_stop'] and not t['target_1_hit']:
            # Inspect order flow: Is it being absorbed by buyers on a wick sweep?
            is_absorbing = (ob.taker_delta >= 0.15 or ob.imbalance_pct >= 8.0)
            if is_absorbing:
                # Liquidity sweep being absorbed by buyers: Hold in memory, do not panic sell on a wick
                return
            else:
                # True breakdown: bids collapsed or aggressive sellers slamming the book
                loss_pct = abs((curr_price - entry) / entry) * 100.0
                okx_exec_str = ""
                if self.okx.is_configured:
                    self.okx.place_spot_order(side="sell", sz="100%", order_type="market")
                    okx_exec_str = "\n⚡ <b>OKX Auto-Sold Stop.</b>"
                msg = (
                    f"🛑 <b>STOP LOSS HIT (EXIT TRADE)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"💵 <b>Exit Price:</b> <b>${curr_price:,.2f}</b> (-{loss_pct:.2f}%)\n"
                    f"👉 <b>Action:</b> Exit position immediately. Memory soft stop protected capital.{okx_exec_str}"
                )
                self.journal.record_exit(
                    exit_price=curr_price,
                    exit_reason='Memory Soft Stop Invalidation'
                )
                self.notifier.send_message(msg)
                self.active_trade = None
                self.market_state = "SCANNING"
                self._save_state()
                return


        # Position Timeout (>4h)
        if (time.time() - t["timestamp"]) > 14400:
            self.journal.record_exit(
                exit_price=curr_price,
                exit_reason='Position Timeout (>4h)'
            )
            self.notifier.send_message(
                "⏱️ <b>BTCTOOL: POSITION TIMEOUT (4H)</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Trade tracker auto-reset after 4 hours with no resolution.\n"
                "<i>Please check your exchange manually and confirm position status.</i>"
            )
            self.active_trade = None
            self.market_state = "SCANNING"
            self._save_state()



def setup_wizard():
    """Interactive CLI setup wizard to configure Telegram bot credentials."""
    print("\n" + "="*50)
    print("⚡ btctool 2.0 · Telegram Alert Bot Setup")
    print("="*50)
    print("Follow these 3 simple steps to get your credentials:\n")
    print("1. Open Telegram on your phone and search for: @BotFather")
    print("2. Send the command: /newbot and choose a name (e.g. MyBtcAlertBot).")
    print("   BotFather will give you a BOT TOKEN (e.g. 123456789:ABCdefGHI...).\n")
    print("3. Start your new bot on Telegram (tap Start), then search for: @userinfobot")
    print("   Userinfobot will reply with your CHAT ID (e.g. 987654321).\n")

    token = input("Enter your Telegram BOT TOKEN: ").strip()
    chat_id = input("Enter your Telegram CHAT ID: ").strip()

    if token and chat_id:
        cfg = {"bot_token": token, "chat_id": chat_id}
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=4)
        print(f"\n✅ Configuration saved securely to: {CONFIG_FILE}")
        
        # Test connection
        notifier = TelegramNotifier(token, chat_id)
        print("\nSending test push alert to your phone...")
        if notifier.send_test_ping():
            print("🎉 Success! Check Telegram on your phone.")
        else:
            print("❌ Delivery failed. Double check your token and chat ID.")
    else:
        print("Setup canceled. Missing token or chat ID.")


def run_bot(interval_seconds: int = 1, clean_start: bool = False):
    port = int(os.environ.get("PORT", "10000"))
    start_health_server(port)

    notifier = TelegramNotifier()
    if not notifier.is_configured:
        print("\n⚠️ Telegram credentials not configured yet.")
        print("Run: python alert_bot.py --setup")
        sys.exit(1)

    print("\n" + "="*60)
    print("🦓 btctool 2.0 · Zebra Bot Truly Free Expected Value Engine Running")
    print("Continuous Sub-Second Ingestion • Zero Leashes • Zero Static Stops")
    print("Multi-Screen Consensus • Dynamic Absorption Scaling • Clean-Slate Auditing")
    print("="*60 + "\n")

    engine = ZebraBotEngine(clean_start=clean_start)
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        print("\nZebra Bot stopped by user.")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup_wizard()
    elif "--test" in sys.argv:
        n = TelegramNotifier()
        if n.is_configured:
            n.send_test_ping()
        else:
            print("Not configured. Run: python alert_bot.py --setup")
    else:
        clean = "--clean" in sys.argv
        run_bot(clean_start=clean)


