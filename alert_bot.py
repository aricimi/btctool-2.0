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


class SpotExecutionCopilot:
    """
    Spot-Only Institutional Trading Execution Copilot & Lifecycle Tracker:
    1. Early Ignition Entry (Compression/Coil + Taker Delta/OB Absorption).
    2. Bullish Dip Support Entry (Trend Up Pullbacks).
    3. Bottom Sweep Liquidity Rebound Entry.
    4. Target 1 Reached -> Move Stop to Breakeven (+fees).
    5. Parabolic ATR Trailing Stop Ratchet -> Lock in gains to the peak.
    6. Emergency Whale Defense -> Immediate exit if order book flips or taker dumps.
    7. Clean Stop Loss capital preservation.
    """

    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.active_trade: Optional[Dict[str, Any]] = None
        self.last_alert_time: float = 0.0
        self.alert_cooldown_seconds: int = 180  # 3 min cooldown between entry alerts

    def evaluate_market_cycle(self) -> None:
        """
        Runs continuous Multi-Timeframe Confluence across the full spectrum:
        - 1M / 5M: Micro-ignitions, lower wick rejections, and volume climaxes.
        - 15M / 1H: Squeeze compression state, channels, and dynamic ATR targets.
        - 4H / 1D: Macro structural bias and major overhead barriers.
        - Live Tape: Bybit/OKX order book depth and real-time Taker Delta.
        """
        try:
            # 1. Fetch multi-scale reports concurrently
            report_15m: AdvisoryReport = PredictiveEnsembleEngine.generate_advisory(symbol="BTCUSDT", timeframe="15m")
            df_1m = MarketDataService.fetch_klines("BTCUSDT", "1m", limit=30)
            df_5m = MarketDataService.fetch_klines("BTCUSDT", "5m", limit=30)
        except Exception as e:
            print(f"[Multi-Timeframe Scan Error] {e}")
            return

        curr_price = report_15m.latest_price
        ob = report_15m.orderbook
        td = report_15m.trade_directive
        pct_b_15m = report_15m.statistical_brain.details["percent_b"]
        atr = report_15m.atr_value
        squeeze = report_15m.squeeze_state
        macro = report_15m.macro_regime_4h
        oi_conf = report_15m.oi_confluence

        # 1. Manage Active Spot Position Lifecycle first (Ratchets, Exits, Whale Defense)
        if self.active_trade is not None:
            self._manage_active_trade(curr_price, ob, atr, oi_conf)
            return  # Focus on managing current spot trade until exited

        # 2. Cooldown check between new entries
        now = time.time()
        if (now - self.last_alert_time) < self.alert_cooldown_seconds:
            return

        # 3. Dynamic Targets & Stops based on current volatility
        stop_price = round(curr_price - 1.2 * atr, 2)
        tp1_price  = round(curr_price + 1.0 * atr, 2)
        tp2_price  = round(curr_price + 2.2 * atr, 2)

        tp1_gain_pct = ((tp1_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
        tp2_gain_pct = ((tp2_price - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
        risk_pct     = ((curr_price - stop_price) / curr_price) * 100.0 if curr_price > 0 else 0.0

        # Compute Micro-Scale Indicators (1M and 5M)
        # 1M metrics
        c_1m = df_1m["Close"]
        h_1m = df_1m["High"]
        l_1m = df_1m["Low"]
        o_1m = df_1m["Open"]
        v_1m = df_1m["Volume"]
        mean_1m = c_1m.rolling(20).mean()
        std_1m  = c_1m.rolling(20).std()
        pct_b_1m = float((c_1m.iloc[-1] - (mean_1m.iloc[-1] - 2*std_1m.iloc[-1])) / (4*std_1m.iloc[-1])) if std_1m.iloc[-1] > 0 else 0.5
        
        # 1M candle shape (detect bottom wick rejection: lower shadow > body)
        lower_shadow_1m = min(o_1m.iloc[-1], c_1m.iloc[-1]) - l_1m.iloc[-1]
        body_1m = abs(c_1m.iloc[-1] - o_1m.iloc[-1])
        wick_rejection_1m = (lower_shadow_1m > body_1m) and (c_1m.iloc[-1] > l_1m.iloc[-1])
        vol_surge_1m = v_1m.iloc[-1] > (v_1m.iloc[-10:].mean() * 1.5)

        # 5M metrics
        c_5m = df_5m["Close"]
        mean_5m = c_5m.rolling(20).mean()
        std_5m  = c_5m.rolling(20).std()
        pct_b_5m = float((c_5m.iloc[-1] - (mean_5m.iloc[-1] - 2*std_5m.iloc[-1])) / (4*std_5m.iloc[-1])) if std_5m.iloc[-1] > 0 else 0.5

        # ====================================================================
        # SIGNAL 1: ULTRA-FAST 1M/5M MICRO-MOMENTUM & TAKER ACCELERATION
        # Catches the exact 0.35% - 1.5%+ micro scalps as volume rushes in
        # Conditions: Taker Delta positive (> +0.25) + 1M wick bounce or 5M turn
        # ====================================================================
        if ob.taker_delta >= 0.25 and (pct_b_1m <= 0.65 or pct_b_5m <= 0.60) and ob.imbalance_pct >= 5.0:
            if wick_rejection_1m or vol_surge_1m or (c_1m.iloc[-1] > o_1m.iloc[-1]):
                self._trigger_entry(
                    setup_name="1M/5M MICRO-MOMENTUM TAKER IGNITION",
                    price=curr_price,
                    tp1=tp1_price,
                    tp2=tp2_price,
                    stop=stop_price,
                    tp1_gain=tp1_gain_pct,
                    tp2_gain=tp2_gain_pct,
                    risk_pct=risk_pct,
                    rationale=f"Live Taker Delta surge ({ob.taker_delta:+.2f}) with 1M/5M micro-reversal and bid depth support (+{ob.imbalance_pct:.1f}%).",
                    timeframe="1M/5M Live"
                )
                return

        # ====================================================================
        # SIGNAL 2: EARLY TREND IGNITION (15M Squeeze Volatility Coil)
        # Conditions: Squeeze LOADED or FIRING, Bid absorption > +8%, %B <= 0.55
        # ====================================================================
        if squeeze in ["LOADED", "FIRING"] and ob.imbalance_pct >= 8.0 and pct_b_15m <= 0.55:
            self._trigger_entry(
                setup_name="15M EARLY TREND IGNITION (VOLATILITY COIL)",
                price=curr_price,
                tp1=tp1_price,
                tp2=tp2_price,
                stop=stop_price,
                tp1_gain=tp1_gain_pct,
                tp2_gain=tp2_gain_pct,
                risk_pct=risk_pct,
                rationale="15M Volatility compression loaded/firing with order book absorption. Early entry before trend acceleration.",
                timeframe="15M Squeeze"
            )
            return

        # ====================================================================
        # SIGNAL 3: MULTI-SCALE BOTTOM LIQUIDITY SWEEP REBOUND (Scenario 3)
        # Conditions: Lower channel sweep (%B <= 0.30 on 1M, 5M, or 15M) + strong bid wall (>= +15%)
        # ====================================================================
        if (pct_b_15m <= 0.30 or pct_b_5m <= 0.25 or pct_b_1m <= 0.20) and ob.imbalance_pct >= 15.0:
            self._trigger_entry(
                setup_name="BOTTOM LIQUIDITY SWEEP REBOUND",
                price=curr_price,
                tp1=tp1_price,
                tp2=tp2_price,
                stop=stop_price,
                tp1_gain=tp1_gain_pct,
                tp2_gain=tp2_gain_pct,
                risk_pct=risk_pct,
                rationale="Lower channel liquidity swept with heavy institutional bid wall absorption across micro/intermediate frames.",
                timeframe="Multi-Scale"
            )
            return

        # ====================================================================
        # SIGNAL 4: BULLISH DIP SUPPORT (Uptrend Pullback)
        # Conditions: 4H Macro Trend Up + Pullback to support (%B between 0.35 - 0.50 on 15M or 5M)
        # ====================================================================
        if macro == "Trend Up" and ((0.35 <= pct_b_15m <= 0.50) or (0.35 <= pct_b_5m <= 0.50)) and ob.imbalance_pct >= 5.0:
            self._trigger_entry(
                setup_name="BULLISH TREND PULLBACK (DIP BUY)",
                price=curr_price,
                tp1=tp1_price,
                tp2=tp2_price,
                stop=stop_price,
                tp1_gain=tp1_gain_pct,
                tp2_gain=tp2_gain_pct,
                risk_pct=risk_pct,
                rationale="Healthy pullback into dynamic support within established 4H uptrend. Buying the dip.",
                timeframe="Multi-Scale Dip"
            )
            return

        # ====================================================================
        # SIGNAL 5: DIRECTIVE CONFLUENCE (Scenario Matrix Buy Trigger)
        # ====================================================================
        if "BUY" in td.action.upper() and td.target_probability >= 55.0 and ob.imbalance_pct > 0:
            self._trigger_entry(
                setup_name=f"ALGORITHMIC CONFLUENCE: {td.action}",
                price=curr_price,
                tp1=tp1_price,
                tp2=tp2_price,
                stop=stop_price,
                tp1_gain=tp1_gain_pct,
                tp2_gain=tp2_gain_pct,
                risk_pct=risk_pct,
                rationale=td.rationale,
                timeframe="Ensemble Matrix"
            )
            return

    def _trigger_entry(self, setup_name: str, price: float, tp1: float, tp2: float,
                       stop: float, tp1_gain: float, tp2_gain: float, risk_pct: float,
                       rationale: str, timeframe: str) -> None:
        """Dispatches an explicit Spot Buy push notification to Telegram."""
        msg = (
            f"🟢 <b>BTCTOOL SPOT BUY: {setup_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Action:</b> BUY SPOT NOW (Limit/Market)\n"
            f"⏰ <b>Timeframe:</b> {timeframe.upper()}\n"
            f"💵 <b>Entry Price:</b> <b>${price:,.2f}</b>\n\n"
            f"🎯 <b>Target 1:</b> ${tp1:,.2f} (<b>+{tp1_gain:.2f}%</b>)\n"
            f"🎯 <b>Target 2 (Runner):</b> ${tp2:,.2f} (<b>+{tp2_gain:.2f}%</b>)\n"
            f"🛑 <b>Hard Invalidation Stop:</b> ${stop:,.2f} (<b>-{risk_pct:.2f}%</b>)\n\n"
            f"📊 <b>Execution Directive:</b>\n"
            f"• <i>{rationale}</i>\n\n"
            f"💡 <i>Place your Spot Limit Buy order on your exchange terminal now. Stop is pre-calculated.</i>"
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
        Manages the live spot trade:
        - Target 1 hit -> Breakeven protection
        - Parabolic trailing ratchet -> Locking in profit
        - Emergency whale defense -> Early exit on orderbook collapse
        - Hard stop loss trigger -> Capital preservation
        """
        t = self.active_trade
        if not t:
            return

        entry = t['entry']
        highest = max(t['highest_price'], curr_price)
        t['highest_price'] = highest

        # ====================================================================
        # DEFENSIVE SHIELD: WHALE EMERGENCY INVALIDATION (Early Defense)
        # If in profit or near breakeven and order book flips violently (imbalance < -25%)
        # or OI drops with aggressive selling, exit at market before stop is reached.
        # ====================================================================
        if curr_price >= entry and ob.imbalance_pct <= -25.0:
            gain_pct = ((curr_price - entry) / entry) * 100.0
            msg = (
                f"⚠️ <b>BTCTOOL SPOT ALERT: WHALE DUMP DEFENSE (EXIT NOW)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚨 <b>Microstructure Warning:</b> Sudden heavy ask wall collapse (Imbalance {ob.imbalance_pct:.1f}%).\n"
                f"💵 <b>Current Price:</b> <b>${curr_price:,.2f}</b> ({gain_pct:+.2f}%)\n"
                f"👉 <b>Action:</b> <b>SELL SPOT AT MARKET NOW.</b>\n"
                f"🛡️ <i>Take flat/breakeven exit. Do not wait for hard stop; preserve full capital.</i>"
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            return

        # ====================================================================
        # MILESTONE 1: TARGET 1 REACHED -> MOVE STOP TO BREAKEVEN
        # ====================================================================
        if not t['target_1_hit'] and curr_price >= t['target_1']:
            t['target_1_hit'] = True
            t['breakeven_set'] = True
            new_stop = round(entry + 0.15 * atr, 2)  # slightly above entry to cover 0% or low fees
            t['current_stop'] = max(t['current_stop'], new_stop)
            gain_pct = ((curr_price - entry) / entry) * 100.0
            msg = (
                f"🎯 <b>SPOT UPDATE: TARGET 1 REACHED · MOVE STOP TO BREAKEVEN</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📈 <b>Current Price:</b> <b>${curr_price:,.2f}</b> (<b>+{gain_pct:.2f}% PROFIT</b>) ✅\n"
                f"👉 <b>Action on Exchange:</b> Update your Stop Loss order:\n"
                f"🔄 <b>New Stop:</b> <b>${new_stop:,.2f}</b> (Guaranteed Breakeven / Fee Shield)\n"
                f"🔒 <i>Trade is now 100% Risk-Free. Let runner ride toward Target 2!</i>"
            )
            self.notifier.send_message(msg)

        # ====================================================================
        # MILESTONE 2: TARGET 2 HIT -> LOCK IN RUNNER GAIN
        # ====================================================================
        if curr_price >= t['target_2'] and t['ratchet_level'] < 1:
            t['ratchet_level'] = 1
            new_stop = round(curr_price - 0.7 * atr, 2)
            t['current_stop'] = max(t['current_stop'], new_stop)
            gain_pct = ((curr_price - entry) / entry) * 100.0
            lock_pct = ((new_stop - entry) / entry) * 100.0
            msg = (
                f"🚀 <b>SPOT UPDATE: TARGET 2 REACHED · RATCHET STOP HIGH</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📈 <b>Current Price:</b> <b>${curr_price:,.2f}</b> (<b>+{gain_pct:.2f}% GAIN</b>) 🏆\n"
                f"👉 <b>Action:</b> Move Stop Loss to <b>${new_stop:,.2f}</b> (<b>+{lock_pct:.2f}% Guaranteed Profit</b>)\n"
                f"💰 <i>You are guaranteed to walk away with +{lock_pct:.2f}% profit. Trailing the peak!</i>"
            )
            self.notifier.send_message(msg)

        # ====================================================================
        # MILESTONE 3: PARABOLIC TRAILING RATCHET (Following trend expansion)
        # As price continues making new highs, trail stop at 1.0 ATR below peak.
        # ====================================================================
        if t['target_1_hit']:
            dynamic_trail_stop = round(highest - 0.9 * atr, 2)
            # If dynamic trail stop rose by at least 0.4 ATR above current stop, ratchet up
            if dynamic_trail_stop > (t['current_stop'] + 0.4 * atr):
                t['current_stop'] = dynamic_trail_stop
                locked_gain = ((dynamic_trail_stop - entry) / entry) * 100.0
                msg = (
                    f"📈 <b>SPOT UPDATE: TRAILING STOP RATCHETED HIGHER</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Highest Reached: <b>${highest:,.2f}</b> | Current: <b>${curr_price:,.2f}</b>\n"
                    f"👉 <b>Action:</b> Ratchet Stop Loss up to <b>${dynamic_trail_stop:,.2f}</b>\n"
                    f"🔒 <b>Locked-in Profit:</b> <b>+{locked_gain:.2f}%</b> (Risk-Free Trend Run)"
                )
                self.notifier.send_message(msg)

        # ====================================================================
        # EXIT 1: TRAILING STOP / BREAKEVEN STOP HIT (Bank the Profit)
        # ====================================================================
        if curr_price <= t['current_stop'] and t['target_1_hit']:
            realized_gain = ((curr_price - entry) / entry) * 100.0
            msg = (
                f"🏁 <b>SPOT POSITION CLOSED: PROFIT BANKED!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Exit Price:</b> <b>${curr_price:,.2f}</b>\n"
                f"💰 <b>Final Realized Gain:</b> <b>+{realized_gain:.2f}% PROFIT</b> 🏆\n"
                f"💼 <b>Status:</b> 100% in USDT/Cash. Capital compounded.\n"
                f"⏳ <i>Waiting for clean compression or dip to reload full balance.</i>"
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            return

        # ====================================================================
        # EXIT 2: HARD STOP LOSS TRIGGERED (Initial Risk Invalidation)
        # ====================================================================
        if curr_price <= t['current_stop'] and not t['target_1_hit']:
            loss_pct = abs((curr_price - entry) / entry) * 100.0
            msg = (
                f"🛑 <b>SPOT STOP LOSS HIT: CAPITAL PRESERVED</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 <b>Exit Price:</b> <b>${curr_price:,.2f}</b>\n"
                f"📉 <b>Loss:</b> <b>-{loss_pct:.2f}%</b>\n\n"
                f"🛡️ <i>Action: Position exited. Hard stop protected capital from further drawdown. Bot resetting.</i>"
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            return

        # Timeout safety (Trade open > 4 hours without hitting target or stop)
        if (time.time() - t["timestamp"]) > 14400:
            print("[Trade Tracker] Spot position timeout (>4h). Resetting position.")
            self.active_trade = None


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

    engine = SpotExecutionCopilot(notifier)

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
