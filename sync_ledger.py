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

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_RENDER_URL = os.environ.get("RENDER_APP_URL", "https://btctool-alerts.onrender.com")
DEFAULT_SYNC_TOKEN = os.environ.get("SYNC_SECRET_TOKEN", "btctool-sync-secret-8922701269")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_HISTORY_FILE = os.path.join(BASE_DIR, "trade_history.json")
LOCAL_CSV_FILE = os.path.join(BASE_DIR, "trade_journal.csv")


def sync_once(render_url: str = DEFAULT_RENDER_URL, token: str = DEFAULT_SYNC_TOKEN, force: bool = False) -> bool:
    """Fetches the authoritative trade ledger and CSV from Render and updates local files."""
    clean_url = render_url.rstrip("/")
    ledger_url = f"{clean_url}/api/v1/ledger?token={token}"
    csv_url = f"{clean_url}/api/v1/csv?token={token}"

    print(f"[SYNC] Connecting to Render deployment: {clean_url}...")
    try:
        # 1. Fetch JSON ledger
        r_hist = requests.get(ledger_url, timeout=12)
        if r_hist.status_code == 403:
            print("[AUTH ERROR] Invalid SYNC_SECRET_TOKEN.")
            return False
        elif r_hist.status_code != 200:
            print(f"[WARN] Render returned HTTP {r_hist.status_code}. (The deployment may still be updating or sleeping).")
            return False

        hist_data = r_hist.json()
        if not isinstance(hist_data, dict) or "trades" not in hist_data:
            print("[WARN] Render returned a non-ledger health response (v3.4.1 deployment may still be building). Local ledger unchanged.")
            return False

        trade_count = len(hist_data.get("trades", []))
        stats = hist_data.get("stats", {})

        # Check local count to prevent accidental downgrade/wiping
        local_count = 0
        if os.path.exists(LOCAL_HISTORY_FILE):
            try:
                with open(LOCAL_HISTORY_FILE, "r", encoding="utf-8") as f:
                    local_count = len(json.load(f).get("trades", []))
            except Exception:
                local_count = 0

        if trade_count < local_count and not force:
            print(f"[RETAIN] Cloud ledger has {trade_count} trades while local has {local_count}. Retaining local ledger (use --force to overwrite).")
            return True

        # Save to local trade_history.json
        with open(LOCAL_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(hist_data, f, indent=2)
        print(f"[OK] Synced trade_history.json ({trade_count} trades, Net Realized: {stats.get('net_cumulative_pct', 0.0):+.2f}%).")

        # 2. Fetch CSV spreadsheet
        r_csv = requests.get(csv_url, timeout=12)
        if r_csv.status_code == 200 and r_csv.text.strip():
            csv_content = r_csv.text
            # Validate that returned content looks like CSV rather than JSON or HTML
            if "Trade ID" in csv_content or "ID" in csv_content:
                try:
                    with open(LOCAL_CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
                        f.write(csv_content)
                    print(f"[OK] Synced trade_journal.csv successfully.")
                except PermissionError:
                    fallback_file = os.path.join(BASE_DIR, "trade_journal_latest.csv")
                    with open(fallback_file, "w", newline="", encoding="utf-8-sig") as f:
                        f.write(csv_content)
                    print(f"[WARN] trade_journal.csv is open in Excel. Synced to {fallback_file} instead.")
            else:
                print("[WARN] Cloud CSV payload did not contain expected CSV header. Skipping CSV update.")

        return True

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Network error while connecting to Render: {e}")
        return False


def watch_loop(interval: int = 60, render_url: str = DEFAULT_RENDER_URL, token: str = DEFAULT_SYNC_TOKEN):
    """Runs a continuous background sync loop polling Render every `interval` seconds."""
    print(f"[DAEMON] Starting continuous sync daemon (polling every {interval}s)... Press Ctrl+C to stop.")
    while True:
        try:
            sync_once(render_url=render_url, token=token)
        except Exception as e:
            print(f"[WARN] Sync error: {e}")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="btctool 2.0 Secure Cloud-to-Local Ledger Synchronizer")
    parser.add_argument("--url", default=DEFAULT_RENDER_URL, help="Render app base URL")
    parser.add_argument("--token", default=DEFAULT_SYNC_TOKEN, help="Sync secret token")
    parser.add_argument("--force", action="store_true", help="Force overwrite even if cloud ledger has fewer trades")
    parser.add_argument("--watch", action="store_true", help="Run as continuous sync daemon")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval in seconds for --watch")
    args = parser.parse_args()

    if args.watch:
        watch_loop(interval=args.interval, render_url=args.url, token=args.token)
    else:
        success = sync_once(render_url=args.url, token=args.token, force=args.force)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
