"""
alert_bot_futures.py — Dedicated Institutional Telegram Alert & Execution Daemon for Futures 2.1
Target Instrument: OKX BTC-USDT-SWAP (Perpetual Futures)
Margin Architecture: Isolated Margin (2.5x Default Leverage)
Execution Mode: Paper Simulation / Push Notification Daemon
Runs in complete isolation from Spot alert_bot.py.
"""

import os
import sys
import json
import time
import datetime
import logging
from typing import Dict, Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from conviction_engine_futures import ConvictionEngineFutures, FuturesSignal, DEFAULT_ISOLATED_LEVERAGE

logger = logging.getLogger("alert_bot_futures")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

FUTURES_CONFIG_FILE = "futures_config.json"


class FuturesTelegramNotifier:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token
        self.chat_id = chat_id
        if not self.token or not self.chat_id:
            self._load_config()

    def _load_config(self):
        if os.path.exists(FUTURES_CONFIG_FILE):
            try:
                with open(FUTURES_CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                    self.token = cfg.get("bot_token")
                    self.chat_id = cfg.get("chat_id")
            except Exception as e:
                logger.error(f"Error loading {FUTURES_CONFIG_FILE}: {e}")
        elif os.path.exists("telegram_config.json"):
            try:
                with open("telegram_config.json", "r") as f:
                    cfg = json.load(f)
                    self.token = cfg.get("bot_token")
                    self.chat_id = cfg.get("chat_id")
            except Exception as e:
                logger.error(f"Error loading fallback telegram_config.json: {e}")

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str) -> bool:
        if not self.is_configured:
            logger.info(f"[SIMULATED TELEGRAM]: {text}")
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            r = requests.post(url, json=payload, timeout=8)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"Telegram dispatch error: {e}")
            return False

    def notify_entry(self, sig: FuturesSignal, balance: float = 1000.0):
        side_icon = "🟢 LONG" if sig.side == "LONG" else "🔴 SHORT"
        pos_size_usd = balance * sig.leverage
        msg = (
            f"⚡ *[FUTURES 2.1 — OKX BTC-USDT-SWAP]* ⚡\n\n"
            f"Action: *{sig.action}*\n"
            f"Direction: *{side_icon}*\n"
            f"Setup: `{sig.setup_type}`\n"
            f"Entry Fill: `${sig.price:,.1f}`\n"
            f"Hard Stop: `${sig.hard_stop:,.1f}`\n"
            f"Target: `${sig.take_profit:,.1f}`\n" if sig.take_profit else f"Target: `Trailing Runner`\n"
            f"Isolated Leverage: *{sig.leverage:.1f}x*\n"
            f"Est. Liq Price: `${sig.liquidation_estimate:,.1f}`\n"
            f"Position Size: `${pos_size_usd:,.1f} USD`\n"
            f"Reason: _{sig.reason}_\n"
            f"Timestamp: `{datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
        )
        self.send_message(msg)

    def notify_exit(self, sig: FuturesSignal, pnl_pct: float, pnl_eur: float, balance: float):
        result_icon = "💰 PROFIT" if pnl_pct > 0 else "🛑 LOSS"
        msg = (
            f"🔔 *[FUTURES 2.1 — EXIT NOTIFICATION]* 🔔\n\n"
            f"Result: *{result_icon}*\n"
            f"Side: *{sig.side}*\n"
            f"Setup: `{sig.setup_type}`\n"
            f"Exit Price: `${sig.price:,.1f}`\n"
            f"Net PnL %: *{pnl_pct:+.2f}%*\n"
            f"Realized PnL: *€{pnl_eur:+.2f}*\n"
            f"Account Capital: *€{balance:,.2f}*\n"
            f"Reason: _{sig.reason}_\n"
            f"Timestamp: `{datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}`"
        )
        self.send_message(msg)


def run_futures_daemon(poll_interval_sec: int = 15):
    print("="*65)
    print("🏛️ btctool 2.0 / BTC_BOT 2.1 · Futures Autonomous Daemon")
    print("Instrument: OKX BTC-USDT-SWAP | Leverage: 2.5x Isolated")
    print("="*65)
    notifier = FuturesTelegramNotifier()
    engine = ConvictionEngineFutures(leverage=DEFAULT_ISOLATED_LEVERAGE)
    print("Futures Daemon initialized successfully. Listening for live 15M market cycles...")
    # In live deployment, connects to OKX WebSocket/REST ticker and candles
    # For now, ready for loop ingestion


if __name__ == "__main__":
    run_futures_daemon()
