"""
zebra_bot.py — The Institutional 100-Screen Real-Time Quant Engine for btctool 2.0
Continuous sub-second event loop, zero sleep blindness, multi-lot capital management,
Kinetic Push vs Structural Barrier model, and Windows Excel lock-proof trade auditing.
"""

import asyncio
import datetime
import gc
import json
import logging
import os
import re
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

import requests

from market_stream import MarketStream
from market_state import MarketState
from conviction_engine import ConvictionEngine
from execution_manager import ExecutionManager
from trade_logger import TradeJournal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("zebra_bot")

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_config.json")
DEFAULT_BOT_TOKEN = "8981948899:AAFqJwDyX1_ZMnXRQSp2m6yNk9HuHJ9A7h0"
DEFAULT_CHAT_ID = "8922701269"


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
            "service": "btctool 2.0 Zebra Bot 100-Screen Engine",
            "utc_time": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format, *args):
        return


def start_health_server(port: int = 10000) -> Optional[HTTPServer]:
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"[HealthServer] Running on port {port}")
        return server
    except Exception as e:
        logger.warning(f"[HealthServer] Could not start HTTP server on port {port}: {e}")
        return None


class TelegramNotifier:
    """Handles secure delivery of instant push alerts and on-demand commands."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

        if (not self.bot_token or not self.chat_id) and os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                    self.bot_token = self.bot_token or cfg.get("bot_token")
                    self.chat_id = self.chat_id or cfg.get("chat_id")
            except Exception:
                pass

        self.bot_token = self.bot_token or DEFAULT_BOT_TOKEN
        self.chat_id = self.chat_id or DEFAULT_CHAT_ID
        self.last_update_id = 0

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and self.bot_token != "YOUR_BOT_TOKEN_HERE")

    def send_message(self, text: str) -> bool:
        """Sends an HTML formatted push message directly to Telegram."""
        if not self.is_configured:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                clean_title = text.split("\n")[0]
                clean_title = re.sub(r'<[^>]+>', '', clean_title)
                logger.info(f"[Telegram] Sent: {clean_title}")
                return True
            else:
                logger.error(f"[Telegram Error] HTTP {r.status_code}: {r.text}")
                return False
        except Exception as e:
            logger.error(f"[Telegram Network Error] {e}")
            return False

    def poll_incoming_command(self) -> Optional[str]:
        """Polls Telegram getUpdates for on-demand user commands."""
        if not self.is_configured:
            return None
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 0, "limit": 5}
        try:
            r = requests.get(url, params=params, timeout=3)
            if r.status_code == 200:
                updates = r.json().get("result", [])
                for u in updates:
                    self.last_update_id = max(self.last_update_id, u.get("update_id", 0))
                    msg = u.get("message", {})
                    text = msg.get("text", "").strip()
                    if text.startswith("/"):
                        return text
        except Exception:
            pass
        return None


class ZebraBotEngine:
    """
    Main Zebra Bot orchestrator.
    Manages sensory ingestion, state matrix, kinetic brain, execution, and alerts.
    """

    def __init__(self):
        self.stream = MarketStream(inst_id="BTC-USDT", swap_id="BTC-USDT-SWAP")
        self.state_calculator = MarketState()
        self.brain = ConvictionEngine()
        self.execution = ExecutionManager()
        self.notifier = TelegramNotifier()
        self.last_status_alert_time = 0.0

    async def run(self):
        """Starts the continuous sensory loop and evaluation engine."""
        logger.info("=" * 60)
        logger.info("🦓 ZEBRA BOT 100-SCREEN ENGINE INITIALIZING (btctool 2.0)")
        logger.info("Continuous Sub-Second Ingestion • Zero Sleep Blindness • Multi-Lot Sizing")
        logger.info("=" * 60)

        # 1. Start WebSocket Stream
        self.stream.start()

        # 2. Wait for initial tick & book
        await asyncio.sleep(2.0)
        logger.info(f"[Zebra] Stream active. Current Price: ${self.stream.latest_price:,.2f}")

        # 3. Main Continuous Evaluation Loop (Sub-second cadence, NO 20-second sleep!)
        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                t0 = time.time()

                # Extract 100-Screen State Matrix (<5ms)
                matrix = self.state_calculator.extract_state_matrix(self.stream)

                # Evaluate Decision Brain
                active_trade = self.execution.active_trade
                decision = self.brain.evaluate(matrix, active_trade=active_trade)

                # Process Decision Directive
                action = decision.get("action")

                if action == "ENTER_CORE_LOT_1":
                    entry_p = decision["entry_price"]
                    sl = decision["stop_loss"]
                    t1 = decision["target_1"]
                    t2 = decision["target_2"]
                    reason = decision["reason"]

                    self.execution.open_core_lot_1(entry_p, sl, t1, t2, reason)
                    self.notifier.send_message(
                        f"🟢 <b>ZEBRA BOT: ENTER CORE LOT 1</b>\n\n"
                        f"<b>Pair:</b> BTC/USDT\n"
                        f"<b>Entry:</b> ${entry_p:,.2f}\n"
                        f"<b>Target 1:</b> ${t1:,.2f}\n"
                        f"<b>Target 2:</b> ${t2:,.2f} (Uncapped Runner)\n"
                        f"<b>Structural Stop:</b> ${sl:,.2f}\n\n"
                        f"<b>Brain Rationale:</b> {reason}"
                    )

                elif action == "SCALE_IN_LOT_2":
                    price = matrix["latest_price"]
                    new_stop = decision.get("new_stop", price - 100.0)
                    reason = decision["reason"]

                    self.execution.scale_in_lot_2(price, new_stop, reason)
                    self.notifier.send_message(
                        f"➕ <b>ZEBRA BOT: BUY MORE SPOT (SCALE-IN LOT 2)</b>\n\n"
                        f"<b>Reason:</b> Bullish Absorption Dip at Support\n"
                        f"<b>Scale Price:</b> ${price:,.2f}\n"
                        f"<b>Blended Entry:</b> ${self.execution.active_trade['entry']:,.2f}\n"
                        f"<b>New Ratcheted Stop:</b> ${new_stop:,.2f}\n\n"
                        f"<i>Inventory increased at discount before continuation run.</i>"
                    )

                elif action == "RATCHET_BREAKEVEN":
                    new_stop = decision["new_stop"]
                    reason = decision["reason"]
                    self.execution.ratchet_stop(new_stop, reason, is_breakeven=True)
                    self.notifier.send_message(
                        f"🛡️ <b>ZEBRA BOT: STOP MOVED TO BREAKEVEN</b>\n\n"
                        f"<b>New Stop Floor:</b> ${new_stop:,.2f}\n"
                        f"<b>Protection:</b> Position is 100% risk-free + OKX fee shield."
                    )

                elif action == "RATCHET_TRAILING_STOP":
                    new_stop = decision["new_stop"]
                    reason = decision["reason"]
                    self.execution.ratchet_stop(new_stop, reason)
                    self.notifier.send_message(
                        f"📈 <b>ZEBRA BOT: TRAILING STOP HIGHER</b>\n\n"
                        f"<b>New Structural Floor:</b> ${new_stop:,.2f}\n"
                        f"<b>Reason:</b> Trailing behind 5M higher-low shelf."
                    )

                elif action == "HARVEST_PROFIT":
                    exit_p = matrix["latest_price"]
                    reason = decision["reason"]
                    gain_pct = decision.get("gain_pct", 0.0)

                    self.execution.close_position(exit_p, reason)
                    self.notifier.send_message(
                        f"🏁 <b>ZEBRA BOT: PROFIT BANKED (+{gain_pct*100:.2f}%)</b>\n\n"
                        f"<b>Exit Price:</b> ${exit_p:,.2f}\n"
                        f"<b>Rationale:</b> {reason}\n"
                        f"<b>Ledger:</b> Flushed to trade_journal.csv & trade_journal.md"
                    )

                elif action == "EXIT_STRUCTURAL_STOP":
                    exit_p = matrix["latest_price"]
                    reason = decision["reason"]
                    gain_pct = decision.get("gain_pct", 0.0)

                    self.execution.close_position(exit_p, reason)
                    self.notifier.send_message(
                        f"🛑 <b>ZEBRA BOT: STRUCTURAL STOP EXIT ({gain_pct*100:.2f}%)</b>\n\n"
                        f"<b>Exit Price:</b> ${exit_p:,.2f}\n"
                        f"<b>Reason:</b> {reason}\n"
                        f"<b>Rule:</b> Zero bag-holding. Capital preserved for next setup."
                    )

                # Update highest price if active trade exists
                if active_trade:
                    self.execution.update_highest_price(matrix["latest_price"])

                # Check Telegram command listener
                cmd = self.notifier.poll_incoming_command()
                if cmd:
                    self._handle_telegram_cmd(cmd, matrix)

                # Periodic garbage collection and CSV auto-flush
                if cycle_count % 30 == 0:
                    self.execution.journal.flush_pending_csv()
                    gc.collect()

            except Exception as e:
                logger.error(f"[Zebra Loop Error] {e}")

            # Sleep only 1.0 second between evaluation ticks (zero 20-second blindness!)
            await asyncio.sleep(1.0)

    def _handle_telegram_cmd(self, cmd: str, matrix: dict):
        """Responds to on-demand Telegram commands."""
        if cmd in ("/status", "/ping", "/info"):
            price = matrix.get("latest_price", 0.0)
            tanh_imb = matrix.get("tanh_imbalance", 0.0)
            oi_z = matrix.get("oi_zscore", 0.0)
            vwap = matrix.get("session_vwap", 0.0)
            active = self.execution.active_trade

            status_msg = (
                f"🦓 <b>ZEBRA BOT 100-SCREEN TELEMETRY</b>\n\n"
                f"<b>BTC Price:</b> ${price:,.2f}\n"
                f"<b>Session VWAP:</b> ${vwap:,.2f}\n"
                f"<b>Order Book Imbalance (tanh):</b> {tanh_imb:+.2f}\n"
                f"<b>OI Change Z-Score:</b> {oi_z:+.2f}\n"
                f"<b>Trade Velocity:</b> {self.stream.trade_velocity:.1f} trades/sec\n\n"
            )

            if active:
                entry = active.get("entry", 0.0)
                stop = active.get("current_stop", 0.0)
                gain = ((price - entry) / entry) * 100.0 if entry > 0 else 0.0
                status_msg += (
                    f"<b>Active Position:</b> LONG\n"
                    f"<b>Entry:</b> ${entry:,.2f}\n"
                    f"<b>Current Stop:</b> ${stop:,.2f}\n"
                    f"<b>Unrealized PnL:</b> {gain:+.2f}%\n"
                    f"<b>Lot 2 Added:</b> {'YES' if active.get('tranche_2_added') else 'NO'}\n"
                )
            else:
                status_msg += "<b>Active Position:</b> 100% CASH (Scanning)\n"

            self.notifier.send_message(status_msg)


def main():
    port = int(os.environ.get("PORT", "10000"))
    start_health_server(port)

    engine = ZebraBotEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("[Zebra] Stopped by user.")


if __name__ == "__main__":
    main()
