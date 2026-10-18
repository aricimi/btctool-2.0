"""
btctool 2.0 - Institutional Telegram Mobile Scalping & Ping-Pong Alert Bot
Architecture: Real-time Bybit/OKX order book scanner + 5M/15M ping-pong scalp engine.
Dispatches instant push alerts for entries, target hits (>= +0.20%), and stop invalidations.
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import time
import datetime
import threading
import gc
from http.server import HTTPServer, BaseHTTPRequestHandler
import math
import numpy as np
import requests

from engine import MarketDataService, PredictiveEnsembleEngine, AdvisoryReport


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
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Telegram alert delivered successfully.")
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
        self.active_trade: Optional[Dict[str, Any]] = None
        self.market_state: str = "SCANNING"  # SCANNING, EXPANDING, STALLING, REGRESSING
        self.last_alert_time: float = 0.0
        self.last_reentry_time: float = 0.0
        self.alert_cooldown_seconds: int = 120
        self.tracked_peak: float = 0.0
        self.projected_floor: float = 0.0
        self.repositioned_limit: float = 0.0
        self.last_s_total: float = 0.0

        # Load persisted state if exists
        self._load_state()

    def _save_state(self) -> None:
        state = {
            "market_state": self.market_state,
            "active_trade": self.active_trade,
            "tracked_peak": self.tracked_peak,
            "projected_floor": self.projected_floor,
            "repositioned_limit": self.repositioned_limit,
            "last_alert_time": self.last_alert_time,
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
            self.market_state       = state.get("market_state", "SCANNING")
            self.active_trade       = state.get("active_trade", None)
            self.tracked_peak       = state.get("tracked_peak", 0.0)
            self.projected_floor    = state.get("projected_floor", 0.0)
            self.repositioned_limit = state.get("repositioned_limit", 0.0)
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
        macro = macro or getattr(self, "latest_macro", "Range")
        s_total = s_total if s_total is not None else getattr(self, "last_s_total", 0.0)
        ob = ob or getattr(self, "latest_ob", None)
        td = td or getattr(self, "latest_td", None)

        delta_str = f"{ob.taker_delta:+.2f}" if ob else "+0.00"
        depth_str = f"{ob.imbalance_pct:+.1f}%" if ob else "+0.0%"
        action_str = td.action if td else "SCANNING"

        if self.active_trade:
            t = self.active_trade
            gain_pct = ((curr_price - t['entry']) / t['entry']) * 100.0 if t['entry'] > 0 else 0.0
            pos_str = (
                f"🟢 <b>ACTIVE SPOT POSITION</b>\n"
                f"• Entry: <b>${t['entry']:,.2f}</b> | Current: <b>${curr_price:,.2f}</b> (<b>{gain_pct:+.2f}%</b>)\n"
                f"• Stop Loss: <b>${t['current_stop']:,.2f}</b> ({'🛡️ BREAKEVEN LOCKED' if t.get('breakeven_set') else 'HARD STOP'})\n"
                f"• Target 1: ${t['target_1']:,.2f} | Runner Target 2: ${t['target_2']:,.2f}"
            )
        elif self.market_state in ["STALLING", "REGRESSING"]:
            pos_str = (
                f"🟡 <b>IN CASH · REGRESSION TRACKING ACTIVE</b>\n"
                f"• Tracked Peak: <b>${self.tracked_peak:,.2f}</b>\n"
                f"• Repositioned Buy Zone: <b>${self.repositioned_limit:,.2f}</b>"
            )
        else:
            pos_str = f"⚪ <b>IN CASH · SCANNING FOR DIP & BREAKOUT IGNITION</b>"

        status_msg = (
            f"📡 <b>BTCTOOL: ON-DEMAND ENGINE STATUS</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💵 <b>BTC Price:</b> <b>${curr_price:,.2f}</b>\n"
            f"📊 <b>State:</b> <b>{self.market_state}</b> | 4H Macro: <b>{macro}</b>\n"
            f"🧮 <b>Confluence Score:</b> <b>{s_total:.1f} / 100</b> "
            f"{'🟢 NEAR SIGNAL' if s_total >= 55 else '🟡 BUILDING' if s_total >= 40 else '⚪ QUIET'}\n"
            f"⚡ <b>Order Flow:</b> Taker Delta: <b>{delta_str}</b> | Depth: <b>{depth_str}</b>\n"
            f"🎯 <b>Advisory:</b> {action_str}\n\n"
            f"{pos_str}\n\n"
            f"💡 <i>Running 24/7 in pure Event-Driven mode (Zero clock spam).</i>"
        )
        self.notifier.send_message(status_msg)

    def _compute_confluence_score(self, ob: Any, pct_b_1m: float, pct_b_5m: float, pct_b_15m: float,
                                  wick_rejection_1m: bool, vol_surge_1m: bool, squeeze: str, macro: str) -> Tuple[float, Dict[str, float]]:
        """Computes pure continuous S_total confluence scoring model (0.0 to 100.0)."""
        # S_tape: Continuous sigmoid of taker delta (0.0 to 30.0)
        s_tape = 15.0 * (1.0 + float(np.tanh(2.5 * ob.taker_delta)))

        # S_micro: Wick dynamics + Bollinger position (0.0 to 25.0)
        s_micro_wick = 15.0 if wick_rejection_1m else (7.0 if vol_surge_1m else 0.0)
        pct_b_avg = (pct_b_1m + pct_b_5m) / 2.0
        s_micro_bb = min(10.0 * max(0.0, 1.0 - (pct_b_avg / 0.5)), 10.0)
        s_micro = min(s_micro_wick + s_micro_bb, 25.0)

        # S_depth: tanh of order book imbalance (0.0 to 20.0)
        imbalance_ratio = ob.imbalance_pct / 100.0
        s_depth = 10.0 * (1.0 + float(np.tanh(3.0 * imbalance_ratio)))

        # S_structure: Squeeze state mapped to points (0.0 to 15.0)
        squeeze_map = {"FIRING": 15.0, "LOADED": 12.0, "TRENDING": 10.0, "BUILDING": 8.0, "IDLE": 5.0}
        s_structure = squeeze_map.get(squeeze, 5.0)

        # S_macro: 4H regime score (0.0 to 10.0) - "Trend Down" is 2.0 to preserve limitless property
        macro_map = {"Trend Up": 10.0, "Range": 5.0, "Trend Down": 2.0}
        s_macro = macro_map.get(macro, 5.0)

        s_total = s_tape + s_micro + s_depth + s_structure + s_macro
        sub_scores = {
            "S_tape": s_tape, "S_micro": s_micro, "S_depth": s_depth,
            "S_structure": s_structure, "S_macro": s_macro
        }
        return s_total, sub_scores

    def evaluate_market_cycle(self) -> None:
        """Runs the continuous autonomous loop across the entire market continuum."""
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

        # 1M candle shape dynamics
        lower_shadow_1m = min(o_1m.iloc[-1], c_1m.iloc[-1]) - l_1m.iloc[-1]
        body_1m = abs(c_1m.iloc[-1] - o_1m.iloc[-1])
        wick_rejection_1m = (lower_shadow_1m > body_1m) and (c_1m.iloc[-1] > l_1m.iloc[-1])
        vol_surge_1m = v_1m.iloc[-1] > (v_1m.iloc[-10:].mean() * 1.4)

        now = time.time()

        # Compute continuous multivariate confluence score (0.0 to 100.0)
        s_total, sub_scores = self._compute_confluence_score(
            ob=ob,
            pct_b_1m=pct_b_1m,
            pct_b_5m=pct_b_5m,
            pct_b_15m=pct_b_15m,
            wick_rejection_1m=wick_rejection_1m,
            vol_surge_1m=vol_surge_1m,
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
            self._manage_active_trade(curr_price, ob, atr, oi_conf, pct_b_15m, pct_b_5m, pct_b_1m)
            return

        # 4. Zero-Ego Re-engagement: Breakout Momentum Resumption
        # If in STALLING or REGRESSING and buyers blow through the peak, re-enter immediately!
        if self.market_state in ["STALLING", "REGRESSING"] and self.tracked_peak > 0:
            if curr_price >= (self.tracked_peak * 0.999) and (s_total >= 65.0 or sub_scores["S_tape"] >= 22.0):
                if (now - self.last_reentry_time) > self.alert_cooldown_seconds:
                    self.last_reentry_time = now
                    stop_price = round(curr_price - 1.2 * atr, 2)
                    tp1_price  = round(curr_price + 1.0 * atr, 2)
                    tp2_price  = round(curr_price + 2.2 * atr, 2)
                    tp1_gain_pct = ((tp1_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
                    tp2_gain_pct = ((tp2_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
                    risk_pct     = ((curr_price - stop_price) / curr_price) * 100.0 if curr_price > 0 else 0.0

                    rationale = (
                        f"Breakout above ${self.tracked_peak:,.2f} | "
                        f"S_total={s_total:.1f}/100 | "
                        f"Tape={sub_scores['S_tape']:.1f} | "
                        f"Depth={sub_scores['S_depth']:.1f}"
                    )
                    self.market_state = "EXPANDING"
                    self._trigger_entry(
                        setup_name="SPOT RE-ENGAGEMENT: BREAKOUT MOMENTUM RESUMPTION",
                        price=curr_price,
                        tp1=tp1_price,
                        tp2=tp2_price,
                        stop=stop_price,
                        tp1_gain=tp1_gain_pct,
                        tp2_gain=tp2_gain_pct,
                        risk_pct=risk_pct,
                        rationale=rationale,
                        timeframe="1M/5M BREAKOUT MOMENTUM"
                    )
                    self._save_state()
                    return
            elif curr_price >= (self.tracked_peak * 0.998):
                self.market_state = "SCANNING"
                self.tracked_peak = 0.0
                self.projected_floor = 0.0
                print("[State Machine] Price recovered to peak. Resetting to SCANNING.")
                self._save_state()

        # 5. Dynamic Dip Tracking & Buy Zone Repositioning (During Pullback)
        if self.market_state in ["STALLING", "REGRESSING"] and curr_price < (self.tracked_peak - 0.4 * atr):
            self.market_state = "REGRESSING"
            # If aggressive bids step in above the original projected floor
            if ob.taker_delta >= 0.20 or ob.imbalance_pct >= 8.0:
                new_repositioned_limit = round(curr_price + 0.15 * atr, 2)
                if new_repositioned_limit > (self.repositioned_limit + 0.3 * atr) and (now - self.last_alert_time) > self.alert_cooldown_seconds:
                    self.repositioned_limit = new_repositioned_limit
                    rebound_target = round(self.repositioned_limit + 1.2 * atr, 2)
                    gain_pot = ((rebound_target - self.repositioned_limit) / self.repositioned_limit) * 100.0
                    msg = (
                        f"🎯 <b>BTCTOOL: REGRESSION UPDATE · BUY ZONE REPOSITIONED</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"💵 <b>Current Price:</b> <b>${curr_price:,.2f}</b>\n"
                        f"📊 <b>Tape Shift:</b> Early buyer absorption detected (Delta {ob.taker_delta:+.2f} / Depth +{ob.imbalance_pct:.1f}%).\n"
                        f"📍 <b>Repositioned Action:</b> <b>SET LIMIT BUY AT ${self.repositioned_limit:,.2f}</b>\n"
                        f"🛑 <b>Stop Loss:</b> ${round(self.repositioned_limit - 1.1*atr, 2):,.2f}\n"
                        f"🎯 <b>Rebound Target:</b> ${rebound_target:,.2f} (<b>+{gain_pot:.2f}%</b>)\n\n"
                        f"💡 <i>Buyers absorbing earlier than expected. Move your Limit Buy up to ${self.repositioned_limit:,.2f} to ensure fill.</i>"
                    )
                    if self.notifier.send_message(msg):
                        self.last_alert_time = now
                    self._save_state()
                    return

        # 6. Detect Stalling & Anticipate Regression (At Resistance / Top)
        if pct_b_15m >= 0.78 or pct_b_5m >= 0.80 or pct_b_1m >= 0.85:
            if self.market_state != "STALLING" and (now - self.last_alert_time) > self.alert_cooldown_seconds:
                self.market_state = "STALLING"
                self.tracked_peak = max(curr_price, h_1m.max(), h_5m.max())
                self.projected_floor = round(self.tracked_peak - 1.2 * atr, 2)
                self.repositioned_limit = self.projected_floor

                msg = (
                    f"⚠️ <b>BTCTOOL: MOMENTUM STALLING · REGRESSION EXPECTED</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📈 <b>Local High Reached:</b> <b>${self.tracked_peak:,.2f}</b> | Current: <b>${curr_price:,.2f}</b>\n"
                    f"📉 <b>Tape Condition:</b> Overhead ceiling active. 1M/5M momentum flattening.\n"
                    f"🎯 <b>Projected Regression Target:</b> <b>${self.projected_floor:,.2f}</b>\n\n"
                    f"👉 <b>Tactical Guidance:</b>\n"
                    f"• <b>If you are in Cash/USDT:</b> <b>DO NOT BUY HERE.</b> Bot is actively tracking regression descent toward ${self.projected_floor:,.2f} for next reload."
                )
                if self.notifier.send_message(msg):
                    self.last_alert_time = now
                self._save_state()
                return

        # 7. Pure Probabilistic Confluence Entry Gate (S_total >= 65.0)
        if s_total >= 65.0 and (now - self.last_alert_time) > self.alert_cooldown_seconds:
            stop_price = round(curr_price - 1.2 * atr, 2)
            tp1_price  = round(curr_price + 1.0 * atr, 2)
            tp2_price  = round(curr_price + 2.2 * atr, 2)

            if oi_conf == "EXHAUSTION_SIGNAL" or "EXHAUSTION" in str(oi_conf):
                tp1_price = round(curr_price + (1.0 * atr * 0.75), 2)
                tp2_price = round(curr_price + (2.2 * atr * 0.75), 2)

            tp1_gain_pct = ((tp1_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
            tp2_gain_pct = ((tp2_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
            risk_pct     = ((curr_price - stop_price) / curr_price) * 100.0 if curr_price > 0 else 0.0

            if sub_scores["S_tape"] >= 22.0:
                setup_name = "SPOT BUY: TAKER IGNITION CONFLUENCE"
            elif sub_scores["S_structure"] >= 12.0:
                setup_name = "SPOT BUY: VOLATILITY SQUEEZE RELEASE"
            elif sub_scores["S_depth"] >= 15.0:
                setup_name = "SPOT BUY: INSTITUTIONAL BID ABSORPTION"
            elif sub_scores["S_micro"] >= 18.0:
                setup_name = "SPOT BUY: MICRO-REVERSAL COMPRESSION"
            else:
                setup_name = "SPOT BUY: MULTI-SCALE CONFLUENCE"

            rationale = (
                f"S_total={s_total:.1f}/100 | "
                f"Tape={sub_scores['S_tape']:.1f} "
                f"Micro={sub_scores['S_micro']:.1f} "
                f"Depth={sub_scores['S_depth']:.1f} "
                f"Structure={sub_scores['S_structure']:.1f} "
                f"Macro={sub_scores['S_macro']:.1f}"
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
        """Dispatches an explicit Spot Buy push notification to Telegram."""
        msg = (
            f"🟢 <b>BTCTOOL: {setup_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Action:</b> <b>BUY SPOT NOW (Limit/Market)</b>\n"
            f"💼 <b>Capital Allocation:</b> Tranche 1 (Base Scalp Position)\n"
            f"⏰ <b>Trigger Timeframe:</b> {timeframe.upper()}\n"
            f"💵 <b>Entry Price:</b> <b>${price:,.2f}</b>\n\n"
            f"🎯 <b>Target 1:</b> ${tp1:,.2f} (<b>+{tp1_gain:.2f}%</b> · Breakeven Trigger)\n"
            f"🚀 <b>Target 2 (Runner):</b> ${tp2:,.2f} (<b>+{tp2_gain:.2f}%</b> · Trailing Peak)\n"
            f"🛑 <b>Hard Invalidation Stop:</b> ${stop:,.2f} (<b>-{risk_pct:.2f}%</b>)\n\n"
            f"📊 <b>Execution Rationale:</b>\n"
            f"• <i>{rationale}</i>\n\n"
            f"💡 <i>Place your Spot Limit Buy order on your exchange now. Stop is pre-calculated.</i>"
        )

        sent = self.notifier.send_message(msg)
        if sent:
            self.last_alert_time = time.time()
            self.active_trade = {
                'entry':        price,
                'target_1':     tp1,
                'target_2':     tp2,
                'current_stop': stop,
                'highest_price': price,
                'target_1_hit': False,
                'breakeven_set': False,
                'ratchet_level': 0,
                'timestamp':    time.time()
            }
            # Upgrade 4: Persist trade to disk
            self._save_state()

    def _manage_active_trade(self, curr_price: float, ob: Any, atr: float, oi_conf: str,
                             pct_b_15m: float = 0.5, pct_b_5m: float = 0.5, pct_b_1m: float = 0.5) -> None:
        """
        Manages live spot position: ratcheting trailing stops, breakeven protection,
        early resistance stall profit shields, whale defense, and banked profit alerts.
        """
        t = self.active_trade
        if not t:
            return

        entry = t['entry']
        highest = max(t['highest_price'], curr_price)
        t['highest_price'] = highest

        # Defense: Whale Emergency Invalidation on Violent Orderbook Collapse
        if curr_price >= entry and ob.imbalance_pct <= -25.0:
            gain_pct = ((curr_price - entry) / entry) * 100.0
            msg = (
                f"⚠️ <b>BTCTOOL SPOT ALERT: WHALE DUMP DEFENSE (EXIT NOW)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚨 <b>Microstructure Warning:</b> Heavy overhead ask wall collapse (Imbalance {ob.imbalance_pct:.1f}%).\n"
                f"💵 <b>Current Price:</b> <b>${curr_price:,.2f}</b> ({gain_pct:+.2f}%)\n"
                f"👉 <b>Action:</b> <b>SELL SPOT AT MARKET NOW.</b>\n"
                f"🛡️ <i>Take flat/breakeven exit. Do not wait for hard stop; preserve full capital.</i>"
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            self.market_state = "SCANNING"
            self._save_state()
            return

        # Early Resistance Stall & Peak Profit Shield:
        # If trade is in profit (> +0.35*atr) and price hits upper band (%B >= 0.82) with flattening tape
        if curr_price > (entry + 0.35 * atr) and (pct_b_15m >= 0.82 or pct_b_5m >= 0.85 or pct_b_1m >= 0.88):
            if ob.taker_delta < 0.0 or ob.imbalance_pct < -5.0:
                tight_stop = round(curr_price - 0.35 * atr, 2)
                if tight_stop > t['current_stop']:
                    t['current_stop'] = tight_stop
                    locked_gain = ((tight_stop - entry) / entry) * 100.0
                    gain_now = ((curr_price - entry) / entry) * 100.0
                    msg = (
                        f"⚠️ <b>BTCTOOL: MOMENTUM STALLING AT RESISTANCE · PROFIT SHIELD</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"📈 <b>Current Price:</b> <b>${curr_price:,.2f}</b> (<b>+{gain_now:.2f}% Profit</b>)\n"
                        f"📉 <b>Tape Condition:</b> Overhead ceiling active. Sellers absorbing.\n"
                        f"👉 <b>Action:</b> Ratchet Stop Loss tight to <b>${tight_stop:,.2f}</b> (<b>+{locked_gain:.2f}% Guaranteed</b>), or cash out at market.\n"
                        f"🛡️ <i>Secures peak profits before the regression drop.</i>"
                    )
                    self.notifier.send_message(msg)
                    self._save_state()

        # Target 1 Reached -> Move Stop to Breakeven
        if not t['target_1_hit'] and curr_price >= t['target_1']:
            t['target_1_hit'] = True
            t['breakeven_set'] = True
            new_stop = round(entry + 0.15 * atr, 2)
            t['current_stop'] = max(t['current_stop'], new_stop)
            gain_pct = ((curr_price - entry) / entry) * 100.0
            msg = (
                f"🛡️ <b>BTCTOOL: TARGET 1 REACHED · MOVE STOP TO BREAKEVEN</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📈 <b>Current Price:</b> <b>${curr_price:,.2f}</b> (<b>+{gain_pct:.2f}% PROFIT</b>) ✅\n"
                f"👉 <b>Action on Exchange:</b> Update your Stop Loss order:\n"
                f"🔄 <b>New Stop:</b> <b>${new_stop:,.2f}</b> (Guaranteed Breakeven / Fee Shield)\n"
                f"🔒 <i>Trade is now 100% Risk-Free. Parabolic trailing stop active—let runner ride!</i>"
            )
            self.notifier.send_message(msg)
            self._save_state()

        # Target 2 Hit -> Ratchet Stop High
        if curr_price >= t['target_2'] and t['ratchet_level'] < 1:
            t['ratchet_level'] = 1
            new_stop = round(curr_price - 0.7 * atr, 2)
            t['current_stop'] = max(t['current_stop'], new_stop)
            gain_pct = ((curr_price - entry) / entry) * 100.0
            lock_pct = ((new_stop - entry) / entry) * 100.0
            msg = (
                f"🚀 <b>BTCTOOL: TARGET 2 REACHED · RATCHET STOP HIGH</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📈 <b>Current Price:</b> <b>${curr_price:,.2f}</b> (<b>+{gain_pct:.2f}% GAIN</b>) 🏆\n"
                f"👉 <b>Action:</b> Move Stop Loss to <b>${new_stop:,.2f}</b> (<b>+{lock_pct:.2f}% Guaranteed Profit</b>)\n"
                f"💰 <i>You are guaranteed +{lock_pct:.2f}% profit. Trailing the peak with zero upper cap!</i>"
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
                    f"📈 <b>BTCTOOL: TRAILING STOP RATCHETED HIGHER</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Highest: <b>${highest:,.2f}</b> | Current: <b>${curr_price:,.2f}</b>\n"
                    f"👉 <b>Action:</b> Ratchet Stop Loss up to <b>${dynamic_trail_stop:,.2f}</b>\n"
                    f"🔒 <b>Locked-in Profit:</b> <b>+{locked_gain:.2f}%</b> (Risk-Free Trend Run)"
                )
                self.notifier.send_message(msg)
                self._save_state()

        # Exit on Trailing Stop / Breakeven Hit -> Bank the Gain & Handover to Regression Tracking
        if curr_price <= t['current_stop'] and t['target_1_hit']:
            realized_gain = ((curr_price - entry) / entry) * 100.0
            msg = (
                f"🏁 <b>BTCTOOL: SPOT POSITION CLOSED · PROFIT BANKED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Exit Price:</b> <b>${curr_price:,.2f}</b>\n"
                f"💰 <b>Final Realized Gain:</b> <b>+{realized_gain:.2f}% PROFIT</b> 🏆\n"
                f"💼 <b>Status:</b> In Cash / Capital Secured.\n"
                f"⏳ <i>Immediate transition to regression tracking for dip reload.</i>"
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            self.market_state = "STALLING"
            self.tracked_peak = highest
            self.projected_floor = round(highest - 1.2 * atr, 2)
            self.repositioned_limit = self.projected_floor
            self._save_state()
            return

        # Hard Stop Loss Triggered (Capital Preservation)
        if curr_price <= t['current_stop'] and not t['target_1_hit']:
            loss_pct = abs((curr_price - entry) / entry) * 100.0
            msg = (
                f"🛑 <b>BTCTOOL: SPOT STOP LOSS HIT · CAPITAL PRESERVED</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Exit Price:</b> <b>${curr_price:,.2f}</b>\n"
                f"📉 <b>Loss:</b> <b>-{loss_pct:.2f}%</b>\n\n"
                f"🛡️ <i>Action: Position exited. Hard stop protected capital from further drawdown.</i>"
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            self.market_state = "SCANNING"
            self._save_state()
            return

        # Upgrade 6B: Explicit Telegram Alert on 4H Position Timeout
        if (time.time() - t["timestamp"]) > 14400:
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


def run_bot(interval_seconds: int = 20):
    port = int(os.environ.get("PORT", "10000"))
    start_health_server(port)

    notifier = TelegramNotifier()
    if not notifier.is_configured:
        print("\n⚠️ Telegram credentials not configured yet.")
        print("Run: python alert_bot.py --setup")
        sys.exit(1)

    print("\n" + "="*50)
    print("🚀 btctool 2.0 · Institutional Spot Execution Copilot Running")
    print(f"Scanning: BTC/USDT (15M / Bybit + OKX Order Books)")
    print("Mode: Spot Early Ignition + Dynamic Parabolic Ratchet + Whale Defense")
    print(f"Polling Cadence: every {interval_seconds}s")
    print("="*50 + "\n")

    # If running on cloud (Render or PORT specified), send boot confirmation
    if os.environ.get("RENDER") or os.environ.get("PORT"):
        notifier.send_message(
            "⚡ <b>btctool 2.0 · Spot Execution Copilot Online</b>\n\n"
            "Cloud engine active on Render 24/7!\n"
            "Operating in pure <b>Event-Driven Mode</b> (Zero Clock Spam).\n"
            "Send <code>/status</code> at any time for instant on-demand telemetry."
        )

    engine = AutonomousExecutionEngine(notifier)

    while True:
        try:
            engine.evaluate_market_cycle()
        except KeyboardInterrupt:
            print("\nBot stopped by user.")
            break
        except Exception as e:
            print(f"[Loop Exception] {e}")

        # Garbage collection after each scan cycle
        gc.collect()

        # Responsive 1-second cadence command listener during sleep interval
        for _ in range(interval_seconds):
            try:
                cmd = notifier.poll_incoming_command()
                if cmd:
                    engine._handle_on_demand_status()
            except Exception:
                pass
            time.sleep(1)


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
        # Default run or loop
        run_bot(interval_seconds=20)
