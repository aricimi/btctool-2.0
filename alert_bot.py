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


