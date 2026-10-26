"""
btctool 2.0 - Institutional Telegram Mobile Scalping & Zebra Bot Daemon
Architecture: Real-time OKX order book and WebSocket stream scanner.
Dispatches instant push alerts for entries, target hits, and stop invalidations.
"""

import os
import sys
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import datetime
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import asyncio

from zebra_bot import (
    ZebraBotEngine,
    TelegramNotifier,
    HealthCheckHandler,
    start_health_server,
    CONFIG_FILE,
    DEFAULT_BOT_TOKEN,
    DEFAULT_CHAT_ID,
)


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
