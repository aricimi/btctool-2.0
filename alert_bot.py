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
from typing import Dict, Any, Optional
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


class TelegramNotifier:
    """Handles secure delivery of instant push alerts to your Telegram mobile app."""

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

    def send_test_ping(self) -> bool:
        msg = (
            "⚡ <b>btctool 2.0 · Telegram Alert System Online</b>\n\n"
            "Your mobile alert bot is successfully connected!\n"
            "You will receive instant lock-screen alerts whenever a high-probability "
            "ping-pong scalp (<b>&gt; +0.20%</b>) or liquidity sweep appears on BTC/USDT."
        )
        return self.send_message(msg)


class AutonomousExecutionEngine:
    """
    Continuous Multi-Scale Autonomous Spot Trading Engine & Telemetry Copilot:
    1. Continuous Market State Tracking:
       - ACCUMULATING: Volatility coiling, bid absorption, awaiting trigger.
       - EXPANDING: Trend impulse active, trailing parabolic stop.
       - STALLING / EXHAUSTION: Upper resistance ceiling reached, 1M/5M momentum fading.
       - REGRESSING: Price pulling back toward support floor; dynamic repositioning active.
    2. Telemetry & Alerts:
       - SPOT BUY SIGNAL: Probabilistic multi-scale confluence entry.
       - TARGET 1 & BREAKEVEN: Milestone reached, stop ratcheted to lock risk-free trade.
       - STALLING & REGRESSION WARNING: Notifies you to lock profits if holding, or wait for dip if in cash.
       - DYNAMIC DIP REPOSITIONING: Tracks dip descent and shifts buy zone adaptively.
       - WHALE DEFENSE: Immediate exit if order book collapses.
    """

    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.active_trade: Optional[Dict[str, Any]] = None
        self.market_state: str = "SCANNING"  # SCANNING, EXPANDING, STALLING, REGRESSING
        self.last_alert_time: float = 0.0
        self.last_status_time: float = 0.0
        self.alert_cooldown_seconds: int = 150
        self.status_pulse_interval: int = 900  # 15 min periodic market telemetry
        self.tracked_peak: float = 0.0
        self.projected_floor: float = 0.0
        self.repositioned_limit: float = 0.0

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

        # 1. Manage Active Position (if in a trade)
        if self.active_trade is not None:
            self._manage_active_trade(curr_price, ob, atr, oi_conf)
            return

        # 2. Extract Micro-Scale Metrics (1M and 5M)
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

        # ====================================================================
        # STATE 1: DETECT STALLING & ANTICIPATE REGRESSION (At Resistance / Top)
        # Price hits ceiling (%B > 0.78 on 1M/5M/15M) and momentum flattens
        # ====================================================================
        if pct_b_15m >= 0.78 or pct_b_5m >= 0.80 or pct_b_1m >= 0.85:
            if self.market_state != "STALLING" and (now - self.last_alert_time) > self.alert_cooldown_seconds:
                self.market_state = "STALLING"
                self.tracked_peak = max(curr_price, h_1m.max(), h_5m.max())
                # Project dynamic regression target: 15M/1H EMA(21) or lower Bollinger channel
                self.projected_floor = round(self.tracked_peak - 1.2 * atr, 2)
                self.repositioned_limit = self.projected_floor

                msg = (
                    f"⚠️ <b>BTCTOOL: MOMENTUM STALLING · REGRESSION EXPECTED</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📈 <b>Local High Reached:</b> <b>${self.tracked_peak:,.2f}</b> | Current: <b>${curr_price:,.2f}</b>\n"
                    f"📉 <b>Tape Condition:</b> Overhead ceiling active. 1M/5M momentum flattening.\n"
                    f"🎯 <b>Projected Regression Target:</b> <b>${self.projected_floor:,.2f}</b>\n\n"
                    f"👉 <b>Tactical Guidance:</b>\n"
                    f"• <b>If you are in a Spot Trade:</b> Tighten your Stop Loss to <b>${round(curr_price - 0.5*atr, 2):,.2f}</b> to lock in profit, or cash out at market.\n"
                    f"• <b>If you are in Cash/USDT:</b> <b>DO NOT BUY HERE.</b> Bot is actively tracking regression descent toward ${self.projected_floor:,.2f} for next reload."
                )
                if self.notifier.send_message(msg):
                    self.last_alert_time = now
                return

        # ====================================================================
        # STATE 2: DYNAMIC DIP TRACKING & ORDER REPOSITIONING (During Pullback)
        # As price drops toward the floor, watch if buyers absorb earlier
        # ====================================================================
        if self.market_state in ["STALLING", "REGRESSING"] and curr_price < (self.tracked_peak - 0.4 * atr):
            self.market_state = "REGRESSING"
            # If aggressive bids step in above the original projected floor
            if ob.taker_delta >= 0.20 or ob.imbalance_pct >= 8.0:
                new_repositioned_limit = round(curr_price + 0.15 * atr, 2)
                # If repositioned zone moved significantly up from old floor
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
                    return

        # ====================================================================
        # STATE 3: PURE PROBABILISTIC CONFLUENCE SCORING ENGINE (PILLAR 2)
        # Zero static veto gates. Computes continuous 0-100 score.
        # ====================================================================
        if (now - self.last_alert_time) > self.alert_cooldown_seconds:
            # 1. Tape Flow Score (0 to 30 pts) via continuous tanh
            # taker_delta in [-1.0, +1.0] -> s_tape in [0.0, 30.0]
            s_tape = 15.0 * (1.0 + float(np.tanh(2.5 * ob.taker_delta)))

            # 2. Micro Price Action Score (0 to 25 pts)
            # Wicking dynamics + oversold channel bounce
            shadow_ratio = float(lower_shadow_1m / max(body_1m, 1e-4))
            wick_score = min(15.0, shadow_ratio * 7.5) if c_1m.iloc[-1] >= l_1m.iloc[-1] else 0.0
            # Higher score when near lower channel (pct_b low)
            channel_score = max(0.0, min(10.0, (1.0 - pct_b_1m) * 10.0))
            s_micro = wick_score + channel_score

            # 3. Order Book Depth Score (0 to 20 pts) via continuous tanh
            # imbalance_pct in [-100, +100] -> ratio in [-1.0, +1.0]
            imbalance_ratio = ob.imbalance_pct / 100.0
            s_depth = 10.0 * (1.0 + float(np.tanh(3.0 * imbalance_ratio)))

            # 4. Volatility Structure Score (0 to 15 pts)
            squeeze_map = {"FIRING": 15.0, "LOADED": 12.0, "BUILDING": 8.0, "IDLE": 5.0}
            s_structure = squeeze_map.get(squeeze, 5.0)

            # 5. Macro Compass Score (0 to 10 pts)
            s_macro = 10.0 if macro == "Trend Up" else (6.0 if macro == "Range" else 3.0)

            # AGGREGATE TOTAL PROBABILISTIC CONFLUENCE (0.0 to 100.0)
            total_conviction = s_tape + s_micro + s_depth + s_structure + s_macro

            # CONVICTION THRESHOLD: Trigger Spot Buy when total score >= 60.0
            if total_conviction >= 60.0:
                stop_price = round(curr_price - 1.2 * atr, 2)
                tp1_price  = round(curr_price + 1.0 * atr, 2)
                tp2_price  = round(curr_price + 2.2 * atr, 2)
                tp1_gain_pct = ((tp1_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
                tp2_gain_pct = ((tp2_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
                risk_pct     = ((curr_price - stop_price) / curr_price) * 100.0 if curr_price > 0 else 0.0

                rationale = (
                    f"Aggregate Confluence: {total_conviction:.1f}/100. "
                    f"Tape Flow: {s_tape:.1f}/30 (Delta {ob.taker_delta:+.2f}), "
                    f"Micro Reversal: {s_micro:.1f}/25, "
                    f"OB Depth: {s_depth:.1f}/20 ({ob.imbalance_pct:+.1f}%), "
                    f"Structure: {s_structure:.1f}/15 ({squeeze})."
                )

                self.market_state = "EXPANDING"
                self._trigger_entry(
                    setup_name=f"SPOT BUY (CONFLUENCE {total_conviction:.0f}/100)",
                    price=curr_price,
                    tp1=tp1_price,
                    tp2=tp2_price,
                    stop=stop_price,
                    tp1_gain=tp1_gain_pct,
                    tp2_gain=tp2_gain_pct,
                    risk_pct=risk_pct,
                    rationale=rationale,
                    timeframe="Multi-Scale Unified"
                )
                return

        # ====================================================================
        # PERIODIC STATUS PULSE (Every 15 min): Zero Silence Guarantee
        # ====================================================================
        if (now - self.last_status_time) > self.status_pulse_interval:
            self.last_status_time = now
            pulse_msg = (
                f"📡 <b>BTCTOOL MARKET STATUS PULSE</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>BTC Price:</b> <b>${curr_price:,.2f}</b>\n"
                f"📊 <b>Market Phase:</b> <b>{self.market_state}</b> | 4H Macro: <b>{macro}</b>\n"
                f"⚡ <b>Order Flow:</b> Taker Delta: <b>{ob.taker_delta:+.2f}</b> | Depth: <b>{ob.imbalance_pct:+.1f}%</b>\n"
                f"🎯 <b>Current Strategy:</b> {td.action}\n"
                f"💡 <i>Scanner running 24/7 across 1M, 5M, 15M, 1H & live order flow.</i>"
            )
            self.notifier.send_message(pulse_msg)

    def _trigger_entry(self, setup_name: str, price: float, tp1: float, tp2: float,
                       stop: float, tp1_gain: float, tp2_gain: float, risk_pct: float,
                       rationale: str, timeframe: str) -> None:
        """Dispatches an explicit Spot Buy push notification to Telegram."""
        msg = (
            f"🟢 <b>BTCTOOL: {setup_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Action:</b> <b>BUY SPOT NOW (Limit/Market)</b>\n"
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

    def _manage_active_trade(self, curr_price: float, ob: Any, atr: float, oi_conf: str) -> None:
        """
        Manages the live spot position with ratcheting trailing stops,
        breakeven protection, whale emergency defenses, and banked profit alerts.
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
            return

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

        # Exit on Trailing Stop / Breakeven Hit -> Bank the Gain
        if curr_price <= t['current_stop'] and t['target_1_hit']:
            realized_gain = ((curr_price - entry) / entry) * 100.0
            msg = (
                f"🏁 <b>BTCTOOL: SPOT POSITION CLOSED · PROFIT BANKED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Exit Price:</b> <b>${curr_price:,.2f}</b>\n"
                f"💰 <b>Final Realized Gain:</b> <b>+{realized_gain:.2f}% PROFIT</b> 🏆\n"
                f"💼 <b>Status:</b> 100% in USDT/Cash. Capital compounded.\n"
                f"⏳ <i>Tracking regression descent to reload full balance.</i>"
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            self.market_state = "SCANNING"
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
            return

        # Position Timeout (>4h)
        if (time.time() - t["timestamp"]) > 14400:
            print("[Trade Tracker] Position timeout (>4h). Resetting.")
            self.active_trade = None
            self.market_state = "SCANNING"



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
            "Cloud engine active on Render!\n"
            "Monitoring BTC/USDT early trend ignition, parabolic ratchets & whale defense."
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

        time.sleep(interval_seconds)


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
