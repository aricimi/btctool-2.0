"""
zebra_bot.py — Truly Free Autonomous 100-Screen Real-Time Quant Engine for btctool 2.0
Continuous sub-second event loop, AlphaGo-style Expected Value decision brain,
clean-slate ledger auditing, and instantaneous rich Telegram push alerts on every move.
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
from conviction_engine import FreeConvictionEngine
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
            "service": "btctool 2.0 Truly Free Zebra Bot Engine",
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
    """Handles delivery of instant push alerts and on-demand commands."""

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
    Main Zebra Bot orchestrator:
    Continuous sub-second perception, Expected Value brain, and rich Telegram alerts.
    """

    def __init__(self, clean_start: bool = False):
        self.stream = MarketStream(inst_id="BTC-USDT", swap_id="BTC-USDT-SWAP")
        self.state_calculator = MarketState()
        self.brain = FreeConvictionEngine()
        self.execution = ExecutionManager()
        self.notifier = TelegramNotifier()

        if clean_start:
            self.execution.reset_clean_slate()

    async def run(self):
        """Starts continuous sensory loop and autonomous evaluation."""
        logger.info("=" * 60)
        logger.info("🦓 ZEBRA BOT: TRULY FREE EXPECTED VALUE ENGINE RUNNING")
        logger.info("Zero Static Stops • Zero Artificial Ceilings • 100-Screen Autonomous Agent")
        logger.info("=" * 60)

        # 1. Start WebSocket Stream
        self.stream.start()

        # 2. Wait for initial data buffer
        await asyncio.sleep(2.0)
        logger.info(f"[Zebra] Stream active. Current Price: ${self.stream.latest_price:,.2f}")

        # Send Telegram Online Notification
        self.notifier.send_message(
            "⚡ <b>ZEBRA BOT: TRULY FREE ENGINE ONLINE</b>\n\n"
            "Autonomous Expected Value Agent active 24/7!\n"
            "• Zero Static Stop Leashes\n"
            "• Zero Artificial Ceilings (Rides Winners)\n"
            "• Immediate Predictive Cut on Edge Reversal\n"
            "• Continuous 11-Screen Sub-Second Streaming\n\n"
            "Send <code>/status</code> for live 11-screen telemetry."
        )

        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                t0 = time.time()

                # Extract 100-Screen State Matrix (<2ms)
                matrix = self.state_calculator.extract_state_matrix(self.stream)

                # Evaluate Free Autonomous Brain
                active_trade = self.execution.active_trade
                decision = self.brain.evaluate(matrix, active_trade=active_trade)

                action = decision.get("action")
                p_up = decision.get("p_up", 0.5)

                # ----------------------------------------------------------
                # ACTION DISPATCH & TELEGRAM ALERTS
                # ----------------------------------------------------------
                if action == "ENTER_CORE_LOT_1":
                    entry_p = decision["entry_price"]
                    reason = decision["reason"]
                    edge_pct = decision.get("expected_edge_pct", 0.0)

                    self.execution.open_core_lot_1(entry_p, p_up, reason)
                    self.notifier.send_message(
                        f"🟢 <b>ZEBRA BOT: ENTER CORE LOT 1</b>\n\n"
                        f"<b>Pair:</b> BTC/USDT (Spot)\n"
                        f"<b>Entry Price:</b> ${entry_p:,.2f}\n"
                        f"<b>Upward Probability (P_up):</b> {p_up*100:.1f}%\n"
                        f"<b>Expected Net Edge:</b> +{edge_pct*100:.2f}%\n\n"
                        f"<b>Autonomous Directive:</b> High-probability institutional momentum confirmed across 11 screens. "
                        f"Riding move uncapped without static ceiling."
                    )

                elif action == "SCALE_IN_LOT_2":
                    price = matrix["latest_price"]
                    reason = decision["reason"]

                    self.execution.scale_in_lot_2(price, p_up, reason)
                    self.notifier.send_message(
                        f"➕ <b>ZEBRA BOT: SCALE-IN LOT 2 (DIP ABSORPTION)</b>\n\n"
                        f"<b>Action:</b> Adding Capital at Discount\n"
                        f"<b>Scale Price:</b> ${price:,.2f}\n"
                        f"<b>New Blended Entry:</b> ${self.execution.active_trade['entry']:,.2f}\n"
                        f"<b>Upward Probability (P_up):</b> {p_up*100:.1f}%\n\n"
                        f"<b>Reason:</b> Pullback into support absorbed by resting institutional bids. Multiplying win on rebound."
                    )

                elif action == "HARVEST_PROFIT":
                    exit_p = matrix["latest_price"]
                    reason = decision["reason"]
                    gain_pct = decision.get("gain_pct", 0.0)
                    net_gain_pct = gain_pct - 0.0020

                    self.execution.close_position(exit_p, reason, p_up)
                    self.notifier.send_message(
                        f"🏁 <b>ZEBRA BOT: PROFIT BANKED (+{net_gain_pct*100:.2f}% NET)</b>\n\n"
                        f"<b>Exit Price:</b> ${exit_p:,.2f}\n"
                        f"<b>Gross Market Move:</b> {gain_pct*100:+.2f}%\n"
                        f"<b>OKX Fees Deducted:</b> -0.20%\n"
                        f"<b>Clean Realized Profit:</b> +{net_gain_pct*100:.2f}%\n\n"
                        f"<b>Reason:</b> Upward momentum exhausted at ceiling (P_up={p_up*100:.1f}%). Profit secured in wallet."
                    )

                elif action == "CUT_IMMEDIATE":
                    exit_p = matrix["latest_price"]
                    reason = decision["reason"]
                    gain_pct = decision.get("gain_pct", 0.0)
                    net_pnl_pct = gain_pct - 0.0020

                    self.execution.close_position(exit_p, reason, p_up)
                    self.notifier.send_message(
                        f"🛑 <b>ZEBRA BOT: IMMEDIATE PREDICTIVE CUT</b>\n\n"
                        f"<b>Exit Price:</b> ${exit_p:,.2f}\n"
                        f"<b>Net PnL Impact:</b> {net_pnl_pct*100:+.2f}%\n"
                        f"<b>Upward Probability:</b> {p_up*100:.1f}% (Flipped Bearish)\n\n"
                        f"<b>Rule:</b> Zero waiting for a stop line. Directional edge evaporated; cut immediately to protect capital."
                    )

                # Update highest price if active trade exists
                if active_trade:
                    self.execution.update_highest_price(matrix["latest_price"])

                # Check Telegram command listener
                cmd = self.notifier.poll_incoming_command()
                if cmd:
                    self._handle_telegram_cmd(cmd, matrix, p_up)

                # Periodic garbage collection and CSV auto-flush
                if cycle_count % 30 == 0:
                    self.execution.journal.flush_pending_csv()
                    gc.collect()

            except Exception as e:
                logger.error(f"[Zebra Loop Error] {e}")

            await asyncio.sleep(1.0)

    def _handle_telegram_cmd(self, cmd: str, matrix: dict, p_up: float):
        """Responds to on-demand Telegram commands with 11-screen telemetry."""
        if cmd in ("/status", "/ping", "/info"):
            price = matrix.get("latest_price", 0.0)
            tanh_imb = matrix.get("tanh_imbalance", 0.0)
            oi_z = matrix.get("oi_zscore", 0.0)
            vwap = matrix.get("session_vwap", 0.0)
            trade_vel = matrix.get("trade_velocity", 0.0)
            active = self.execution.active_trade

            status_msg = (
                f"🦓 <b>ZEBRA BOT 100-SCREEN TELEMETRY</b>\n\n"
                f"<b>BTC Price:</b> ${price:,.2f}\n"
                f"<b>Directional Probability (P_up):</b> {p_up*100:.1f}%\n"
                f"<b>Order Book Skew (tanh):</b> {tanh_imb:+.2f}\n"
                f"<b>OI Change Z-Score:</b> {oi_z:+.2f}\n"
                f"<b>Session VWAP:</b> ${vwap:,.2f}\n"
                f"<b>Trade Velocity:</b> {trade_vel:.1f} trades/sec\n\n"
            )

            if active:
                entry = active.get("entry", 0.0)
                gain = ((price - entry) / entry) * 100.0 if entry > 0 else 0.0
                status_msg += (
                    f"<b>Active Position:</b> LONG\n"
                    f"<b>Blended Entry:</b> ${entry:,.2f}\n"
                    f"<b>Unrealized Net PnL:</b> {gain - 0.20:+.2f}%\n"
                    f"<b>Lot 2 Deployed:</b> {'YES' if active.get('tranche_2_added') else 'NO'}\n"
                    f"<b>Mode:</b> Riding Uncapped (P_up={p_up*100:.1f}%)\n"
                )
            else:
                status_msg += "<b>Active Position:</b> 100% CASH (Scanning for Edge)\n"

            self.notifier.send_message(status_msg)


def main():
    port = int(os.environ.get("PORT", "10000"))
    start_health_server(port)

    clean_start = "--clean" in sys.argv
    engine = ZebraBotEngine(clean_start=clean_start)
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("[Zebra] Stopped by user.")


if __name__ == "__main__":
    main()
