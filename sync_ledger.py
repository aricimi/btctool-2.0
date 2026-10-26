"""
sync_ledger.py — Secure Authenticated Cloud-to-Local Ledger Synchronization Client (btctool 2.0)
Pulls live trade_history.json and trade_journal.csv directly from the Render deployment,
guaranteeing local audits always use fresh, authoritative execution data.
Zero public exposure, zero Git commits, and zero container restarts.
"""

import os
import sys
import json
import time
import argparse
import requests

DEFAULT_RENDER_URL = os.environ.get("RENDER_APP_URL", "https://btctool-alerts.onrender.com")
DEFAULT_SYNC_TOKEN = os.environ.get("SYNC_SECRET_TOKEN", "btctool-sync-secret-8922701269")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_HISTORY_FILE = os.path.join(BASE_DIR, "trade_history.json")
LOCAL_CSV_FILE = os.path.join(BASE_DIR, "trade_journal.csv")


def sync_once(render_url: str = DEFAULT_RENDER_URL, token: str = DEFAULT_SYNC_TOKEN) -> bool:
    """Fetches the authoritative trade ledger and CSV from Render and updates local files."""
    clean_url = render_url.rstrip("/")
    ledger_url = f"{clean_url}/api/v1/ledger?token={token}"
    csv_url = f"{clean_url}/api/v1/csv?token={token}"

    print(f"🔄 Connecting to Render deployment: {clean_url}...")
    try:
        # 1. Fetch JSON ledger
        r_hist = requests.get(ledger_url, timeout=12)
        if r_hist.status_code == 403:
            print("❌ Authentication failed: Invalid SYNC_SECRET_TOKEN.")
            return False
        elif r_hist.status_code != 200:
            print(f"⚠️ Render returned HTTP {r_hist.status_code}. (The deployment may still be updating or sleeping).")
            return False

        hist_data = r_hist.json()
        trade_count = len(hist_data.get("trades", []))
        stats = hist_data.get("stats", {})

        # Save to local trade_history.json
        with open(LOCAL_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(hist_data, f, indent=2)
        print(f"✅ Synced trade_history.json ({trade_count} trades, Net Realized: {stats.get('net_cumulative_pct', 0.0):+.2f}%).")

        # 2. Fetch CSV spreadsheet
        r_csv = requests.get(csv_url, timeout=12)
        if r_csv.status_code == 200 and r_csv.text.strip():
            try:
                with open(LOCAL_CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
                    f.write(r_csv.text)
                print(f"✅ Synced trade_journal.csv successfully.")
            except PermissionError:
                fallback_file = os.path.join(BASE_DIR, "trade_journal_latest.csv")
                with open(fallback_file, "w", newline="", encoding="utf-8-sig") as f:
                    f.write(r_csv.text)
                print(f"⚠️ trade_journal.csv is open in Excel. Synced to {fallback_file} instead.")

        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Network error while connecting to Render: {e}")
        return False


def watch_loop(interval: int = 60, render_url: str = DEFAULT_RENDER_URL, token: str = DEFAULT_SYNC_TOKEN):
    """Runs a continuous background sync loop polling Render every `interval` seconds."""
    print(f"📡 Starting continuous sync daemon (polling every {interval}s)... Press Ctrl+C to stop.")
    while True:
        try:
            sync_once(render_url=render_url, token=token)
        except Exception as e:
            print(f"⚠️ Sync error: {e}")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="btctool 2.0 Secure Cloud-to-Local Ledger Synchronizer")
    parser.add_argument("--url", default=DEFAULT_RENDER_URL, help="Render app base URL")
    parser.add_argument("--token", default=DEFAULT_SYNC_TOKEN, help="Sync secret token")
    parser.add_argument("--watch", action="store_true", help="Run as continuous sync daemon")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds for --watch")
    args = parser.parse_args()

    if args.watch:
        watch_loop(interval=args.interval, render_url=args.url, token=args.token)
    else:
        success = sync_once(render_url=args.url, token=args.token)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
