"""
btctool 2.0 - Trade Journal & Audit Ledger (trade_logger.py)
Maintains persistent trade_history.json and auto-renders human-readable trade_journal.md.
Factors in OKX Spot round-trip fees (0.10% entry taker + 0.10% exit taker = 0.20% total).
"""

import os
import json
import time
import datetime
from typing import Optional, Dict, Any, List

JOURNAL_MD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_journal.md")
HISTORY_JSON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json")

OKX_ROUNDTRIP_FEE_PCT = 0.20  # 0.10% buy + 0.10% sell


class TradeJournal:
    """Manages trade recording, PnL accounting, and Markdown journal publishing."""

    def __init__(self):
        self.history_file = HISTORY_JSON_FILE
        self.journal_file = JOURNAL_MD_FILE
        self._load_or_init()

    def _load_or_init(self) -> None:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                    return
            except Exception as e:
                print(f"[Journal] Error loading history: {e}")

        # Seed with initial historical record
        self.data: Dict[str, Any] = {
            "trades": [
                {
                    "id": 1,
                    "type": "SPOT_BUY",
                    "setup": "MULTI-SCALE CONFLUENCE",
                    "entry_time": "2026-10-18 22:26:54",
                    "entry_price": 80938.79,
                    "exit_time": "2026-10-18 23:40:19",
                    "exit_price": 81133.34,
                    "duration": "1h 13m",
                    "gross_pnl_pct": 0.24,
                    "okx_fee_pct": -0.20,
                    "net_pnl_pct": 0.04,
                    "exit_reason": "1M Thrust Exhaustion at Resistance",
                    "status": "CLOSED_PROFIT"
                },
                {
                    "id": 2,
                    "type": "SPOT_BUY",
                    "setup": "BREAKOUT RE-ENGAGEMENT",
                    "entry_time": "2026-10-18 23:53:30",
                    "entry_price": 81175.20,
                    "exit_time": "2026-10-19 00:55:00",
                    "exit_price": 81750.00,
                    "duration": "1h 01m",
                    "gross_pnl_pct": 0.71,
                    "okx_fee_pct": -0.20,
                    "net_pnl_pct": 0.51,
                    "exit_reason": "Trailing Stop Locked Profit",
                    "status": "CLOSED_PROFIT"
                },
                {
                    "id": 3,
                    "type": "SPOT_BUY",
                    "setup": "TAKER IGNITION CONFLUENCE",
                    "entry_time": "2026-10-19 01:28:25",
                    "entry_price": 82130.00,
                    "exit_time": "2026-10-19 03:43:49",
                    "exit_price": 82522.00,
                    "duration": "2h 15m",
                    "gross_pnl_pct": 0.48,
                    "okx_fee_pct": -0.20,
                    "net_pnl_pct": 0.28,
                    "exit_reason": "1M Volume/Thrust Stalled at Resistance",
                    "status": "CLOSED_PROFIT"
                },
                {
                    "id": 4,
                    "type": "SPOT_BUY",
                    "setup": "MULTI-SCALE CONFLUENCE (DIP REVERSAL)",
                    "entry_time": "2026-10-19 05:24:23",
                    "entry_price": 82585.10,
                    "exit_time": "2026-10-19 06:47:30",
                    "exit_price": 82810.10,
                    "duration": "1h 23m",
                    "gross_pnl_pct": 0.27,
                    "okx_fee_pct": -0.20,
                    "net_pnl_pct": 0.07,
                    "exit_reason": "1M Volume/Thrust Stalled at Resistance",
                    "status": "CLOSED_PROFIT"
                },
                {
                    "id": 5,
                    "type": "SPOT_BUY",
                    "setup": "RE-ENGAGEMENT: BREAKOUT MOMENTUM RESUMPTION",
                    "entry_time": "2026-10-19 06:56:54",
                    "entry_price": 82786.10,
                    "exit_time": None,
                    "exit_price": None,
                    "duration": None,
                    "target_1": 83472.91,
                    "target_2": 84068.15,
                    "stop_loss": 82328.22,
                    "gross_pnl_pct": None,
                    "okx_fee_pct": -0.20,
                    "net_pnl_pct": None,
                    "exit_reason": None,
                    "status": "ACTIVE_OPEN"
                }
            ],
            "stats": {}
        }
        self._recalculate_and_save()

    def record_entry(self, setup_name: str, entry_price: float, stop_loss: float,
                     target_1: float, target_2: float, rationale: str = "") -> int:
        """Records a new open trade."""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trade_id = len(self.data["trades"]) + 1
        new_trade = {
            "id": trade_id,
            "type": "SPOT_BUY",
            "setup": setup_name,
            "entry_time": now_str,
            "entry_price": round(entry_price, 2),
            "exit_time": None,
            "exit_price": None,
            "duration": None,
            "target_1": round(target_1, 2),
            "target_2": round(target_2, 2),
            "stop_loss": round(stop_loss, 2),
            "gross_pnl_pct": None,
            "okx_fee_pct": -OKX_ROUNDTRIP_FEE_PCT,
            "net_pnl_pct": None,
            "exit_reason": None,
            "rationale": rationale,
            "status": "ACTIVE_OPEN"
        }
        self.data["trades"].append(new_trade)
        self._recalculate_and_save()
        return trade_id

    def record_exit(self, exit_price: float, exit_reason: str) -> None:
        """Closes the current active open trade with realized PnL calculations."""
        now_dt = datetime.datetime.now()
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Find the active open trade
        open_trade = None
        for t in reversed(self.data["trades"]):
            if t["status"] == "ACTIVE_OPEN":
                open_trade = t
                break

        if not open_trade:
            # Fallback: create closed trade if missed
            return

        entry_p = open_trade["entry_price"]
        exit_p = round(exit_price, 2)
        gross_pct = round(((exit_p - entry_p) / entry_p) * 100.0, 2) if entry_p > 0 else 0.0
        net_pct = round(gross_pct - OKX_ROUNDTRIP_FEE_PCT, 2)

        # Duration calculation
        duration_str = "N/A"
        try:
            entry_dt = datetime.datetime.strptime(open_trade["entry_time"], "%Y-%m-%d %H:%M:%S")
            diff = now_dt - entry_dt
            hours = int(diff.total_seconds() // 3600)
            minutes = int((diff.total_seconds() % 3600) // 60)
            duration_str = f"{hours}h {minutes:02d}m" if hours > 0 else f"{minutes}m"
        except Exception:
            pass

        open_trade["exit_time"] = now_str
        open_trade["exit_price"] = exit_p
        open_trade["duration"] = duration_str
        open_trade["gross_pnl_pct"] = gross_pct
        open_trade["net_pnl_pct"] = net_pct
        open_trade["exit_reason"] = exit_reason
        open_trade["status"] = "CLOSED_PROFIT" if net_pct >= 0 else "CLOSED_LOSS"

        self._recalculate_and_save()

    def _recalculate_and_save(self) -> None:
        """Calculates running stats, persists JSON, and renders Markdown."""
        closed = [t for t in self.data["trades"] if t.get("status") in ("CLOSED_PROFIT", "CLOSED_LOSS")]
        total_closed = len(closed)
        wins = sum(1 for t in closed if (t.get("net_pnl_pct") or 0.0) >= 0.0)
        losses = sum(1 for t in closed if (t.get("net_pnl_pct") or 0.0) < 0.0)
        win_rate = round((wins / total_closed * 100.0), 1) if total_closed > 0 else 0.0

        gross_cum = round(sum(t.get("gross_pnl_pct", 0.0) or 0.0 for t in closed), 2)
        total_fees = round(-OKX_ROUNDTRIP_FEE_PCT * total_closed, 2)
        net_cum = round(sum(t.get("net_pnl_pct", 0.0) or 0.0 for t in closed), 2)

        self.data["stats"] = {
            "total_closed_trades": total_closed,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": win_rate,
            "gross_cumulative_pct": gross_cum,
            "total_fees_pct": total_fees,
            "net_cumulative_pct": net_cum
        }

        # Save JSON
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[Journal] Save error: {e}")

        # Render Markdown
        self._render_markdown()

    def _render_markdown(self) -> None:
        """Generates formatted GitHub-style Markdown trade journal."""
        stats = self.data["stats"]
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = []
        lines.append("# 📜 BTCTOOL 2.0 · Autonomous Spot Trading Journal")
        lines.append(f"*Last Updated: {now_str} (Local) | Symbol: BTC/USDT (Spot) | Fee Standard: OKX 0.20% Round-Trip*\n")
        lines.append("---")
        lines.append("## 📊 Executive Performance Summary")
        lines.append("| Metric | Performance Value | Note |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **Total Closed Trades** | **{stats['total_closed_trades']}** | All trades since bot activation |")
        lines.append(f"| **Win Rate** | **{stats['win_rate_pct']:.1f}%** ({stats['wins']} Wins / {stats['losses']} Losses) | Factoring all exchange fees |")
        lines.append(f"| **Gross Realized Gain** | **+{stats['gross_cumulative_pct']:.2f}%** | Raw market price movement |")
        lines.append(f"| **OKX Fees Deducted** | **{stats['total_fees_pct']:.2f}%** | 0.10% buy taker + 0.10% sell taker |")
        lines.append(f"| **Net Realized Profit** | **+{stats['net_cumulative_pct']:.2f}% NET** 🏆 | Clean profit in your wallet |")

        # Active trade section
        active = [t for t in self.data["trades"] if t.get("status") == "ACTIVE_OPEN"]
        lines.append("\n---")
        if active:
            act = active[0]
            lines.append("## 🟢 Current Live Position (Open)")
            lines.append(f"- **Trade ID:** #{act['id']}")
            lines.append(f"- **Setup:** `{act['setup']}`")
            lines.append(f"- **Entry Time:** `{act['entry_time']}`")
            lines.append(f"- **Entry Price:** **${act['entry_price']:,.2f}**")
            lines.append(f"- **Target 1:** **${act.get('target_1', 0):,.2f}** (Breakeven Trigger)")
            lines.append(f"- **Runner Target 2:** **${act.get('target_2', 0):,.2f}**")
            lines.append(f"- **Memory Stop Loss:** **${act.get('stop_loss', 0):,.2f}**")
            lines.append(f"- **Status:** **🟢 ACTIVE SPOT HOLD · MANAGING CONTINUOUSLY**")
        else:
            lines.append("## 🟡 Position Status: IN DEFENSIVE CASH")
            lines.append("- Scanning order book and multi-scale momentum for next confluence entry trigger.")

        lines.append("\n---")
        lines.append("## 📋 Historical Trade Ledger")
        lines.append("| # | Entry Time | Exit Time | Duration | Setup | Entry Price | Exit Price | Gross PnL | Fees | Net PnL | Result | Exit Rationale |")
        lines.append("| :-: | :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")

        for t in self.data["trades"]:
            if t.get("status") == "ACTIVE_OPEN":
                lines.append(
                    f"| **{t['id']}** | {t['entry_time']} | *OPEN* | *Holding* | `{t['setup']}` | "
                    f"${t['entry_price']:,.2f} | — | — | -0.20% | — | 🟢 **ACTIVE** | Open Position |"
                )
            else:
                net_pnl = t.get("net_pnl_pct", 0.0)
                badge = "WIN 🏆" if net_pnl >= 0.10 else "WIN ✅" if net_pnl >= 0 else "LOSS 🛑"
                gross_str = f"+{t['gross_pnl_pct']:.2f}%" if t['gross_pnl_pct'] >= 0 else f"{t['gross_pnl_pct']:.2f}%"
                net_str = f"+{net_pnl:.2f}%" if net_pnl >= 0 else f"{net_pnl:.2f}%"
                lines.append(
                    f"| **{t['id']}** | {t['entry_time']} | {t['exit_time']} | {t.get('duration', 'N/A')} | "
                    f"`{t['setup']}` | ${t['entry_price']:,.2f} | ${t['exit_price']:,.2f} | "
                    f"{gross_str} | -0.20% | **{net_str}** | {badge} | {t.get('exit_reason', 'N/A')} |"
                )

        lines.append("\n---\n*BTCTOOL 2.0 Autonomous Spot Execution Engine · Pure Event-Driven Architecture*")

        try:
            with open(self.journal_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print(f"[Journal] Updated {self.journal_file}")
        except Exception as e:
            print(f"[Journal] Markdown render error: {e}")


# Self-test when executed directly
if __name__ == "__main__":
    j = TradeJournal()
    print("TradeJournal initialized successfully. Stats:", j.data["stats"])
