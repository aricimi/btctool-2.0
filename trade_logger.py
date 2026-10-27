"""
btctool 2.0 - Trade Journal & Audit Ledger (trade_logger.py)
Maintains persistent trade_history.json and auto-renders human-readable trade_journal.md.
Factors in OKX Spot round-trip fees (0.10% entry taker + 0.10% exit taker = 0.20% total).
"""

import os
import csv
import json
import time
import datetime
from typing import Optional, Dict, Any, List

JOURNAL_MD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_journal.md")
JOURNAL_CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_journal.csv")
HISTORY_JSON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json")
EPISODES_JSONL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "episodes.jsonl")

OKX_ROUNDTRIP_FEE_PCT = 0.20  # 0.10% buy + 0.10% sell


class TradeJournal:
    """Manages trade recording, PnL accounting, and Markdown/CSV journal publishing."""

    def __init__(self):
        self.history_file = HISTORY_JSON_FILE
        self.journal_file = JOURNAL_MD_FILE
        self.csv_file = JOURNAL_CSV_FILE
        self.episodes_file = EPISODES_JSONL_FILE
        self.pending_csv_update = False
        self._load_or_init()

    def _load_or_init(self) -> None:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                self._recalculate_and_save()
                return
            except Exception as e:
                print(f"[Journal] Error loading history: {e}")

        # Clean slate default initialization
        self.data: Dict[str, Any] = {
            "trades": [],
            "stats": {
                "total_closed_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_pct": 0.0,
                "gross_cumulative_pct": 0.0,
                "total_fees_pct": 0.0,
                "net_cumulative_pct": 0.0,
            },
        }
        self._recalculate_and_save()

    def record_entry(
        self,
        setup_name: str,
        entry_price: float,
        stop_loss: float,
        target_1: float,
        target_2: float,
        rationale: str = "",
        lot_1_scale_pct: Optional[float] = None,
        feature_vector: Optional[dict] = None,
        trade_intent: Optional[dict] = None,
        risk_decision: Optional[dict] = None,
    ) -> int:
        """Records a new open trade with pre-trade cognitive and risk state."""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trade_id = len(self.data["trades"]) + 1

        pred_runway = 0.0
        if trade_intent and trade_intent.get("expected_runway_pct"):
            pred_runway = float(trade_intent["expected_runway_pct"])
        elif entry_price > 0 and target_1 > entry_price:
            pred_runway = ((target_1 - entry_price) / entry_price) * 100.0

        scale_pct = lot_1_scale_pct
        if scale_pct is None and risk_decision and "approved_size_factor" in risk_decision:
            scale_pct = round(float(risk_decision["approved_size_factor"]) * 100.0, 1)

        new_trade = {
            "id": trade_id,
            "type": "SPOT_BUY",
            "setup": setup_name,
            "entry_time": now_str,
            "lot_1_entry": round(entry_price, 2),
            "lot_1_scale_pct": scale_pct,
            "scale_in_time": None,
            "lot_2_entry": None,
            "blended_entry": round(entry_price, 2),
            "entry_price": round(entry_price, 2),
            "exit_time": None,
            "exit_price": None,
            "duration": None,
            "target_1": round(target_1, 2),
            "target_2": round(target_2, 2),
            "stop_loss": round(stop_loss, 2),
            "predicted_runway_pct": round(pred_runway, 2),
            "prediction_error_pct": None,
            "regret": None,
            "gross_pnl_pct": None,
            "okx_fee_pct": -OKX_ROUNDTRIP_FEE_PCT,
            "net_pnl_pct": None,
            "exit_reason": None,
            "rationale": rationale,
            "pre_state": {
                "feature_vector": feature_vector or {},
                "trade_intent": trade_intent or {},
                "risk_decision": risk_decision or {},
            },
            "status": "ACTIVE_OPEN",
        }
        self.data["trades"].append(new_trade)
        self._recalculate_and_save()
        return trade_id

    def record_scale_in(
        self,
        lot_2_price: float,
        scale_time: Optional[str] = None,
        scale_reason: str = ""
    ) -> None:
        """Records Lot 2 scale-in addition and computes blended entry price."""
        open_trade = None
        for t in reversed(self.data["trades"]):
            if t.get("status") == "ACTIVE_OPEN":
                open_trade = t
                break

        if not open_trade:
            return

        now_str = scale_time or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        open_trade["scale_in_time"] = now_str
        open_trade["lot_2_entry"] = round(lot_2_price, 2)

        lot_1_p = open_trade.get("lot_1_entry", open_trade.get("entry_price", lot_2_price))
        blended = round((lot_1_p + lot_2_price) / 2.0, 2)
        open_trade["blended_entry"] = blended
        open_trade["entry_price"] = blended  # Updates active entry price so record_exit uses blended

        if scale_reason:
            open_trade["scale_in_reason"] = scale_reason

        self._recalculate_and_save()

    def record_exit(
        self,
        exit_price: float,
        exit_reason: str,
        feature_vector: Optional[dict] = None,
        trade_intent: Optional[dict] = None,
        risk_decision: Optional[dict] = None,
    ) -> None:
        """
        Closes the active open trade, computes prediction error and mathematical regret,
        and records a complete EpisodeLog in episodes.jsonl (bot.txt Memory Layer).
        """
        now_dt = datetime.datetime.now()
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Find the active open trade
        open_trade = None
        for t in reversed(self.data["trades"]):
            if t["status"] == "ACTIVE_OPEN":
                open_trade = t
                break

        if not open_trade:
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

        # Retrieve pre-trade state
        saved_pre = open_trade.get("pre_state", {})
        f_vec = feature_vector or saved_pre.get("feature_vector", {})
        t_intent = trade_intent or saved_pre.get("trade_intent", {})
        r_decision = risk_decision or saved_pre.get("risk_decision", {})

        # Prediction Error & Regret Math (bot.txt lines 2615-2691)
        pred_runway = float(open_trade.get("predicted_runway_pct", 0.0) or t_intent.get("expected_runway_pct", 0.0))
        error_pct = round(gross_pct - pred_runway, 2)
        size_factor = float(r_decision.get("approved_size_factor", 1.0))
        regret = round(abs(error_pct) * size_factor, 2)
        stress_loss = float(r_decision.get("stress_loss_pct", 1.0))
        risk_adj_reward = round(net_pct / max(stress_loss, 1.0), 3)

        open_trade["exit_time"] = now_str
        open_trade["exit_price"] = exit_p
        open_trade["duration"] = duration_str
        open_trade["gross_pnl_pct"] = gross_pct
        open_trade["net_pnl_pct"] = net_pct
        open_trade["prediction_error_pct"] = error_pct
        open_trade["regret"] = regret
        open_trade["risk_adjusted_reward"] = risk_adj_reward
        open_trade["exit_reason"] = exit_reason
        open_trade["status"] = "CLOSED_PROFIT" if net_pct >= 0 else "CLOSED_LOSS"

        # Persist full episodic memory to episodes.jsonl
        episode_log = {
            "episode_id": open_trade["id"],
            "entry_time": open_trade["entry_time"],
            "exit_time": now_str,
            "setup": open_trade.get("setup", "WHALE_TRADE"),
            "entry_price": entry_p,
            "exit_price": exit_p,
            "duration": duration_str,
            "gross_pnl_pct": gross_pct,
            "net_pnl_pct": net_pct,
            "exit_reason": exit_reason,
            "predicted_runway_pct": pred_runway,
            "prediction_error_pct": error_pct,
            "regret": regret,
            "risk_adjusted_reward": risk_adj_reward,
            "status": open_trade["status"],
            "feature_vector": f_vec,
            "trade_intent": t_intent,
            "risk_decision": r_decision,
        }
        try:
            with open(self.episodes_file, "a", encoding="utf-8") as ef:
                ef.write(json.dumps(episode_log) + "\n")
        except Exception as e:
            print(f"[Journal] Error writing episode log: {e}")

        self._recalculate_and_save()

    def get_episodes(self, limit: int = 100) -> List[dict]:
        """Reads recent episodes from episodes.jsonl."""
        if not os.path.exists(self.episodes_file):
            return []
        episodes = []
        try:
            with open(self.episodes_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        episodes.append(json.loads(line))
        except Exception as e:
            print(f"[Journal] Error reading episodes: {e}")
        return episodes[-limit:]

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
        # Render CSV
        self._render_csv()

    def _render_markdown(self) -> None:
        """Generates formatted GitHub-style Markdown trade journal."""
        stats = self.data["stats"]
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        gross_cum = stats.get("gross_cumulative_pct", 0.0)
        gross_sign = "+" if gross_cum >= 0 else ""
        net_cum = stats.get("net_cumulative_pct", 0.0)
        net_sign = "+" if net_cum >= 0 else ""
        net_badge = "🏆" if net_cum >= 0 else "⚠️"

        lines = []
        lines.append("# 📜 BTCTOOL 2.0 · Autonomous Spot Trading Journal")
        lines.append(f"*Last Updated: {now_str} (Local) | Symbol: BTC/USDT (Spot) | Fee Standard: OKX 0.20% Round-Trip*\n")
        lines.append("---")
        lines.append("## 📊 Executive Performance Summary")
        lines.append("| Metric | Performance Value | Note |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **Total Closed Trades** | **{stats['total_closed_trades']}** | All trades since bot activation |")
        lines.append(f"| **Win Rate** | **{stats['win_rate_pct']:.1f}%** ({stats['wins']} Wins / {stats['losses']} Losses) | Factoring all exchange fees |")
        lines.append(f"| **Gross Realized Gain** | **{gross_sign}{gross_cum:.2f}%** | Raw market price movement |")
        lines.append(f"| **OKX Fees Deducted** | **{stats['total_fees_pct']:.2f}%** | 0.10% buy taker + 0.10% sell taker |")
        lines.append(f"| **Net Realized Profit** | **{net_sign}{net_cum:.2f}% NET** {net_badge} | Clean profit in your wallet |")

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
        lines.append("| # | Lot 1 Entry Time | Lot 1 Price | Scale % | Scale-In Time | Lot 2 Price | Blended Entry | Exit Time | Duration | Exit Price | Target | Floor | Gross PnL | Net PnL | Result | Exit Reason / Rectification |")
        lines.append("| :-: | :--- | :---: | :---: | :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |")

        for t in self.data["trades"]:
            lot_1_p = t.get("lot_1_entry", t.get("entry_price", 0))
            lot_1_str = f"${lot_1_p:,.2f}" if lot_1_p else "—"
            scale_pct = t.get("lot_1_scale_pct")
            scale_pct_str = f"{scale_pct}%" if scale_pct is not None else "—"
            lot_2_ts = t.get("scale_in_time") or "—"
            lot_2_p = t.get("lot_2_entry")
            lot_2_str = f"${lot_2_p:,.2f}" if lot_2_p else "—"
            blended_p = t.get("blended_entry", t.get("entry_price", 0))
            blended_str = f"${blended_p:,.2f}" if blended_p else "—"
            target_str = f"${t.get('target_1', 0):,.2f}" if t.get('target_1') else "—"
            floor_str = f"${t.get('stop_loss', 0):,.2f}" if t.get('stop_loss') else "—"

            if t.get("status") == "ACTIVE_OPEN":
                lines.append(
                    f"| **{t['id']}** | {t['entry_time']} | {lot_1_str} | {scale_pct_str} | "
                    f"{lot_2_ts} | {lot_2_str} | {blended_str} | *OPEN* | *Holding* | — | {target_str} | {floor_str} | — | — | 🟢 **ACTIVE** | Open Position |"
                )
            else:
                net_pnl = t.get("net_pnl_pct", 0.0)
                badge = "WIN 🏆" if net_pnl >= 0.10 else "WIN ✅" if net_pnl >= 0 else "LOSS 🛑"
                gross_str = f"+{t['gross_pnl_pct']:.2f}%" if t['gross_pnl_pct'] >= 0 else f"{t['gross_pnl_pct']:.2f}%"
                net_str = f"+{net_pnl:.2f}%" if net_pnl >= 0 else f"{net_pnl:.2f}%"
                lines.append(
                    f"| **{t['id']}** | {t['entry_time']} | {lot_1_str} | {scale_pct_str} | "
                    f"{lot_2_ts} | {lot_2_str} | {blended_str} | {t['exit_time']} | {t.get('duration', 'N/A')} | "
                    f"${t['exit_price']:,.2f} | {target_str} | {floor_str} | {gross_str} | **{net_str}** | {badge} | {t.get('exit_reason', 'N/A')} |"
                )

        lines.append("\n---\n*BTCTOOL 2.0 Autonomous Spot Execution Engine · Pure Event-Driven Architecture*")

        try:
            with open(self.journal_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print(f"[Journal] Updated {self.journal_file}")
        except Exception as e:
            print(f"[Journal] Markdown render error: {e}")

    def _render_csv(self) -> None:
        """Generates clean CSV spreadsheet ready for Microsoft Excel."""
        stats = self.data.get("stats", {})
        headers = [
            "Trade #",
            "Status",
            "Type",
            "Setup",
            "Lot 1 Entry Time",
            "Lot 1 Entry Price ($)",
            "Lot 1 Scale (%)",
            "Lot 2 Scale-In Time",
            "Lot 2 Entry Price ($)",
            "Blended Entry Price ($)",
            "Target 1 ($)",
            "Invalidation Floor ($)",
            "Exit Time",
            "Hold Duration",
            "Exit Price ($)",
            "Gross PnL (%)",
            "OKX Fee (%)",
            "Net PnL (%)",
            "Result",
            "Whale Thesis",
            "Exit Reason / Rectification",
        ]
        rows = [headers]
        for t in self.data["trades"]:
            is_open = t.get("status") == "ACTIVE_OPEN"
            net_pnl = t.get("net_pnl_pct")
            if is_open:
                result = "ACTIVE"
                exit_price = ""
                exit_time = ""
                duration = "Holding"
                gross_str = ""
                net_str = ""
            else:
                result = "WIN" if (net_pnl is not None and net_pnl >= 0) else "LOSS"
                exit_price = f"{t.get('exit_price', 0):.2f}"
                exit_time = t.get("exit_time", "")
                duration = t.get("duration", "")
                gross_str = f"{t.get('gross_pnl_pct', 0.0):+.2f}%" if t.get('gross_pnl_pct') is not None else ""
                net_str = f"{net_pnl:+.2f}%" if net_pnl is not None else ""

            lot_1_p = t.get("lot_1_entry", t.get("entry_price", 0))
            lot_1_str = f"{lot_1_p:.2f}" if lot_1_p else ""
            scale_pct = t.get("lot_1_scale_pct")
            scale_pct_str = f"{scale_pct}%" if scale_pct is not None else ""
            lot_2_ts = t.get("scale_in_time", "")
            lot_2_p = t.get("lot_2_entry")
            lot_2_str = f"{lot_2_p:.2f}" if lot_2_p is not None else ""
            blended_p = t.get("blended_entry", t.get("entry_price", 0))
            blended_str = f"{blended_p:.2f}" if blended_p else ""

            row = [
                t.get("id"),
                t.get("status"),
                t.get("type", "SPOT_BUY"),
                t.get("setup", ""),
                t.get("entry_time", ""),
                lot_1_str,
                scale_pct_str,
                lot_2_ts,
                lot_2_str,
                blended_str,
                f"{t.get('target_1', 0):.2f}" if t.get('target_1') else "",
                f"{t.get('stop_loss', 0):.2f}" if t.get('stop_loss') else "",
                exit_time,
                duration,
                exit_price,
                gross_str,
                f"{-OKX_ROUNDTRIP_FEE_PCT:.2f}%",
                net_str,
                result,
                t.get("rationale", ""),
                t.get("exit_reason", ""),
            ]
            rows.append(row)

        # Blank line and Excel Summary Block
        gross_cum = stats.get("gross_cumulative_pct", 0.0)
        gross_sign = "+" if gross_cum >= 0 else ""
        net_cum = stats.get("net_cumulative_pct", 0.0)
        net_sign = "+" if net_cum >= 0 else ""

        rows.append([])
        rows.append(["=== SUMMARY PERFORMANCE ==="])
        rows.append(["Total Closed Trades", stats.get("total_closed_trades", 0)])
        rows.append(["Win Rate", f"{stats.get('win_rate_pct', 0.0):.1f}%"])
        rows.append(["Wins", stats.get("wins", 0)])
        rows.append(["Losses", stats.get("losses", 0)])
        rows.append(["Gross Cumulative Gain", f"{gross_sign}{gross_cum:.2f}%"])
        rows.append(["Total OKX Fees Deducted", f"{stats.get('total_fees_pct', 0.0):.2f}%"])
        rows.append(["Net Realized Profit", f"{net_sign}{net_cum:.2f}%"])

        try:
            with open(self.csv_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerows(rows)

            self.pending_csv_update = False
            print(f"[Journal] Updated {self.csv_file}")
        except PermissionError:
            self.pending_csv_update = True
            fallback_file = os.path.join(os.path.dirname(self.csv_file), "trade_journal_latest.csv")
            try:
                with open(fallback_file, "w", newline="", encoding="utf-8-sig") as f_fb:
                    writer = csv.writer(f_fb)
                    writer.writerows(rows)
                print(f"[Journal Notice] {self.csv_file} is locked (open in Excel). Written to {fallback_file} and queued for primary update once Excel is closed.")
            except Exception as e_fb:
                print(f"[Journal Notice] Fallback write error: {e_fb}")
        except Exception as e:
            print(f"[Journal] CSV render error: {e}")

    def flush_pending_csv(self) -> bool:
        """Automatically flushes any pending CSV updates once Excel releases the file lock."""
        if self.pending_csv_update:
            self._render_csv()
            return not self.pending_csv_update
        return True


# Self-test when executed directly
if __name__ == "__main__":
    j = TradeJournal()
    print("TradeJournal initialized successfully. Stats:", j.data["stats"])
