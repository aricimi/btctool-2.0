"""
btctool 2.0 - Institutional Telegram Mobile Scalping & Ping-Pong Alert Bot
Architecture: Real-time Bybit/OKX order book scanner + 5M/15M ping-pong scalp engine.
Dispatches instant push alerts for entries, target hits (>= +0.20%), and stop invalidations.
"""

import os
import sys
import json
import time
import datetime
from typing import Dict, Any, Optional
import requests

from engine import MarketDataService, PredictiveEnsembleEngine, AdvisoryReport


CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_config.json")


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


class ScalpAlertEngine:
    """
    Monitors 5M & 15M market microstructure for ping-pong scalps >= +0.20%.
    Tracks active positions to trigger automated mobile exit alerts.
    """

    def __init__(self, notifier: TelegramNotifier, min_scalp_pct: float = 0.20):
        self.notifier = notifier
        self.min_scalp_pct = min_scalp_pct
        self.active_trade: Optional[Dict[str, Any]] = None
        self.last_alert_time: float = 0.0
        self.alert_cooldown_seconds: int = 180  # 3 min cooldown between entry alerts

    def evaluate_market_cycle(self, timeframe: str = "15m") -> None:
        """Runs a quantitative cycle scan and sends alerts if conditions trigger."""
        try:
            report: AdvisoryReport = PredictiveEnsembleEngine.generate_advisory(symbol="BTCUSDT", timeframe=timeframe)
        except Exception as e:
            print(f"[Engine Scan Error] {e}")
            return

        curr_price = report.latest_price
        ob = report.orderbook
        td = report.trade_directive
        pct_b = report.statistical_brain.details["percent_b"]
        atr = report.atr_value

        # 1. Check Active Trade Exit Triggers first
        if self.active_trade is not None:
            self._check_trade_exits(curr_price)
            return  # Avoid opening new entry until previous is closed or managed

        # 2. Check for New Ping-Pong Scalp Opportunity (>= +0.20% gain)
        now = time.time()
        if (now - self.last_alert_time) < self.alert_cooldown_seconds:
            return

        # PING-PONG LONG SCALP CONDITIONS:
        # 1. Price is in lower channel (%B <= 0.35) or swept bottom low
        # 2. Order book shows bid absorption (imbalance > +12%)
        # 3. Target 1 offers at least min_scalp_pct gain
        long_target_pct = ((td.take_profit_1 - curr_price) / curr_price) * 100.0 if curr_price > 0 else 0.0
        
        if pct_b <= 0.35 and ob.imbalance_pct >= 12.0 and long_target_pct >= self.min_scalp_pct:
            self._trigger_entry_alert(
                direction="LONG",
                timeframe=timeframe,
                price=curr_price,
                tp1=td.take_profit_1,
                tp2=td.take_profit_2,
                stop=td.invalidation_stop,
                gain_pct=long_target_pct,
                imbalance=ob.imbalance_pct,
                bid_depth=ob.bid_depth_usd,
                rationale=td.rationale,
                is_counter_trend=td.is_counter_trend
            )
            return

        # PING-PONG SHORT SCALP CONDITIONS:
        # 1. Price is in upper channel (%B >= 0.65) or testing ceiling
        # 2. Order book shows heavy overhead ask wall (imbalance < -12%)
        # 3. Target 1 offers at least min_scalp_pct gain
        short_target_pct = ((curr_price - td.take_profit_1) / curr_price) * 100.0 if curr_price > 0 else 0.0

        if pct_b >= 0.65 and ob.imbalance_pct <= -12.0 and short_target_pct >= self.min_scalp_pct:
            self._trigger_entry_alert(
                direction="SHORT",
                timeframe=timeframe,
                price=curr_price,
                tp1=td.take_profit_1,
                tp2=td.take_profit_2,
                stop=td.invalidation_stop,
                gain_pct=short_target_pct,
                imbalance=ob.imbalance_pct,
                bid_depth=ob.ask_depth_usd,
                rationale=td.rationale,
                is_counter_trend=False if report.macro_regime_4h == "Trend Down" else True
            )
            return

    def _trigger_entry_alert(self, direction: str, timeframe: str, price: float,
                             tp1: float, tp2: float, stop: float, gain_pct: float,
                             imbalance: float, bid_depth: float, rationale: str,
                             is_counter_trend: bool) -> None:
        """Builds and sends the entry signal."""
        color_emoji = "🟢" if direction == "LONG" else "🔴"
        trend_warning = "⚠️ <i>Counter-trend (4H Bearish). Strict scalp.</i>" if is_counter_trend else "✅ <i>Aligned with higher structure.</i>"

        msg = (
            f"🚨 <b>BTCTOOL PING-PONG SCALP ALERT!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Direction: {color_emoji} <b>{direction} SCALP</b>\n"
            f"Timeframe: <b>{timeframe.upper()}</b>\n"
            f"Current Price: <b>${price:,.2f}</b>\n\n"
            f"🎯 <b>Target 1:</b> ${tp1:,.2f} (<b>+{gain_pct:.2f}%</b>)\n"
            f"🎯 <b>Target 2:</b> ${tp2:,.2f}\n"
            f"🛑 <b>Invalidation Stop:</b> ${stop:,.2f}\n\n"
            f"📊 <b>Order Book Microstructure:</b>\n"
            f"• Imbalance: <b>{imbalance:+.1f}%</b>\n"
            f"• Supporting Depth: <b>${bid_depth:,.0f}</b>\n"
            f"• Regime: {trend_warning}\n\n"
            f"💡 <i>Manual Execution: Place your limit/market order on your exchange app.</i>"
        )

        sent = self.notifier.send_message(msg)
        if sent:
            self.last_alert_time = time.time()
            self.active_trade = {
                "direction": direction,
                "entry_price": price,
                "tp1": tp1,
                "tp2": tp2,
                "stop": stop,
                "tp1_hit": False,
                "timestamp": time.time()
            }

    def _check_trade_exits(self, curr_price: float) -> None:
        """Evaluates price against active scalp targets and stops."""
        t = self.active_trade
        if not t:
            return

        direction = t["direction"]
        entry = t["entry_price"]

        # 1. Target 1 Hit
        if not t["tp1_hit"]:
            hit_tp1 = (curr_price >= t["tp1"]) if direction == "LONG" else (curr_price <= t["tp1"])
            if hit_tp1:
                t["tp1_hit"] = True
                gain_pct = abs((curr_price - entry) / entry) * 100.0
                msg = (
                    f"🎯 <b>PING-PONG TARGET 1 HIT!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Direction: <b>{direction}</b>\n"
                    f"Exit Price: <b>${curr_price:,.2f}</b>\n"
                    f"Gain: <b>+{gain_pct:.2f}% PROFIT</b> ✅\n\n"
                    f"Action: <i>Take profit or move your stop to breakeven (${entry:,.2f}) to ride Target 2!</i>"
                )
                self.notifier.send_message(msg)

        # 2. Target 2 Hit (Final Exit)
        hit_tp2 = (curr_price >= t["tp2"]) if direction == "LONG" else (curr_price <= t["tp2"])
        if hit_tp2:
            gain_pct = abs((curr_price - entry) / entry) * 100.0
            msg = (
                f"🚀 <b>PING-PONG TARGET 2 (RUNNER) HIT!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Final Exit: <b>${curr_price:,.2f}</b>\n"
                f"Total Gain: <b>+{gain_pct:.2f}% PROFIT</b> 🏆\n\n"
                f"<i>Trade lifecycle complete. Bot resetting for next opportunity.</i>"
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            return

        # 3. Stop Invalidation Hit
        hit_stop = (curr_price <= t["stop"]) if direction == "LONG" else (curr_price >= t["stop"])
        if hit_stop:
            loss_pct = abs((curr_price - entry) / entry) * 100.0
            msg = (
                f"🛑 <b>STOP LOSS INVALIDATION TRIGGERED</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Exit Price: <b>${curr_price:,.2f}</b>\n"
                f"Loss: <b>-{loss_pct:.2f}%</b>\n\n"
                f"<i>Action: Close position to preserve capital. Waiting for clean structural reset.</i>"
            )
            self.notifier.send_message(msg)
            self.active_trade = None
            return

        # 4. Timeout safety (Trade open > 2 hours without hitting target or stop)
        if (time.time() - t["timestamp"]) > 7200:
            print("[Trade Tracker] Scalp timeout (>2h). Clearing active position.")
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


def run_bot(interval_seconds: int = 20, min_scalp: float = 0.20):
    notifier = TelegramNotifier()
    if not notifier.is_configured:
        print("\n⚠️ Telegram credentials not configured yet.")
        print("Run: python alert_bot.py --setup")
        sys.exit(1)

    print("\n" + "="*50)
    print("🚀 btctool 2.0 · Mobile Scalping Bot Running")
    print(f"Scanning: BTC/USDT (15M / Bybit + OKX Order Books)")
    print(f"Minimum Scalp Trigger: >= +{min_scalp:.2f}%")
    print(f"Polling Cadence: every {interval_seconds}s")
    print("="*50 + "\n")

    engine = ScalpAlertEngine(notifier, min_scalp_pct=min_scalp)

    while True:
        try:
            engine.evaluate_market_cycle(timeframe="15m")
        except KeyboardInterrupt:
            print("\nBot stopped by user.")
            break
        except Exception as e:
            print(f"[Loop Exception] {e}")

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
        run_bot(interval_seconds=20, min_scalp=0.20)
