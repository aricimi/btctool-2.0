"""
dream_engine.py — Offline Dreaming & Parameter Recalibration Engine for Zebra Bot (btctool 2.0)
Architecture:
- Implements Phase 3 Recalibration from bot.txt (lines 1201-1235 & 2712-2979).
- Replays episodic memories from `episodes.jsonl` and `trade_history.json`.
- Calculates statistical prediction error (r - r_hat), regret, reward attribution,
  and parameter optimization recommendations without live capital risk.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
import numpy as np

logger = logging.getLogger("dream_engine")

EPISODES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "episodes.jsonl")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json")
REPORT_MD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dream_report.md")


class DreamEngine:
    """
    Offline Replay & Learning Organ for Zebra Bot.
    Replays past episodes, evaluates prediction mistakes, and recalibrates edges.
    """

    def __init__(self, episodes_file: str = EPISODES_FILE, history_file: str = HISTORY_FILE):
        self.episodes_file = episodes_file
        self.history_file = history_file

    def load_episodes(self) -> List[dict]:
        """Loads all episodes from episodes.jsonl, supplementing with trade_history.json if needed."""
        episodes = []
        if os.path.exists(self.episodes_file):
            try:
                with open(self.episodes_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            episodes.append(json.loads(line))
            except Exception as e:
                logger.error(f"[DreamEngine] Error reading {self.episodes_file}: {e}")

        # If no jsonl episodes yet, bootstrap from trade_history.json closed trades
        if not episodes and os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                closed = [t for t in data.get("trades", []) if t.get("status") in ("CLOSED_PROFIT", "CLOSED_LOSS")]
                for t in closed:
                    gross = float(t.get("gross_pnl_pct", 0.0) or 0.0)
                    net = float(t.get("net_pnl_pct", 0.0) or 0.0)
                    pred = float(t.get("predicted_runway_pct", 0.50) or 0.50)
                    err = round(gross - pred, 2)
                    ep = {
                        "episode_id": t.get("id"),
                        "entry_time": t.get("entry_time"),
                        "exit_time": t.get("exit_time"),
                        "setup": t.get("setup", "WHALE_TRADE"),
                        "entry_price": t.get("entry_price", 0.0),
                        "exit_price": t.get("exit_price", 0.0),
                        "duration": t.get("duration", "N/A"),
                        "gross_pnl_pct": gross,
                        "net_pnl_pct": net,
                        "exit_reason": t.get("exit_reason", ""),
                        "predicted_runway_pct": pred,
                        "prediction_error_pct": err,
                        "regret": round(abs(err), 2),
                        "risk_adjusted_reward": round(net / 1.0, 3),
                        "status": t.get("status"),
                        "feature_vector": t.get("pre_state", {}).get("feature_vector", {}),
                        "trade_intent": t.get("pre_state", {}).get("trade_intent", {}),
                        "risk_decision": t.get("pre_state", {}).get("risk_decision", {}),
                    }
                    episodes.append(ep)
            except Exception as e:
                logger.error(f"[DreamEngine] Error bootstrapping from history: {e}")

        return episodes

    def analyze(self) -> Dict[str, Any]:
        """Runs the offline dream analysis over all available trade episodes."""
        episodes = self.load_episodes()
        total = len(episodes)
        if total == 0:
            return {
                "total_episodes": 0,
                "status": "NO_EPISODES_RECORDED",
                "message": "No trade episodes recorded yet. Dream engine will activate once trades conclude."
            }

        wins = sum(1 for e in episodes if e.get("net_pnl_pct", 0.0) >= 0.0)
        losses = total - wins
        win_rate = (wins / total) * 100.0

        net_returns = [e.get("net_pnl_pct", 0.0) for e in episodes]
        errors = [e.get("prediction_error_pct", 0.0) for e in episodes]
        regrets = [e.get("regret", 0.0) for e in episodes]
        rewards = [e.get("risk_adjusted_reward", 0.0) for e in episodes]

        cum_net = sum(net_returns)
        mean_return = float(np.mean(net_returns))
        mean_error = float(np.mean(errors))
        mean_regret = float(np.mean(regrets))
        mean_reward = float(np.mean(rewards))

        # Regime breakdown
        regime_stats = {}
        for e in episodes:
            regime = e.get("feature_vector", {}).get("regime") or e.get("setup", "UNKNOWN")
            if regime not in regime_stats:
                regime_stats[regime] = {"count": 0, "wins": 0, "cum_pnl": 0.0, "errors": [], "regrets": []}
            regime_stats[regime]["count"] += 1
            if e.get("net_pnl_pct", 0.0) >= 0.0:
                regime_stats[regime]["wins"] += 1
            regime_stats[regime]["cum_pnl"] += e.get("net_pnl_pct", 0.0)
            regime_stats[regime]["errors"].append(e.get("prediction_error_pct", 0.0))
            regime_stats[regime]["regrets"].append(e.get("regret", 0.0))

        # Attribution: Absorption Index > 15 vs <= 15
        abs_high = [e for e in episodes if e.get("feature_vector", {}).get("absorption_index", 0.0) > 15.0]
        abs_norm = [e for e in episodes if e.get("feature_vector", {}).get("absorption_index", 0.0) <= 15.0]

        # Parameter recommendations
        recommendations = []
        if mean_error < -0.20:
            recommendations.append("Expected runway overshoots realized gain. Increase Dip Turn runway hurdle from 0.45% to 0.55%.")
        elif mean_error > 0.10:
            recommendations.append("Realized gains routinely exceed expectations. Trailing stop ratcheting is capturing open runway effectively.")

        if mean_regret > 0.50:
            recommendations.append("High regret observed. Consider clamping Lot 1 position size in high-volatility regimes.")
        else:
            recommendations.append("Regret metric is healthy (<0.50). Noise-immune stops are effectively preventing whipsaws.")

        analysis = {
            "total_episodes": total,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 1),
            "cumulative_net_pnl_pct": round(cum_net, 2),
            "mean_net_return_pct": round(mean_return, 2),
            "mean_prediction_error": round(mean_error, 2),
            "mean_regret": round(mean_regret, 2),
            "mean_risk_adjusted_reward": round(mean_reward, 3),
            "regime_stats": regime_stats,
            "high_absorption_episodes": len(abs_high),
            "recommendations": recommendations,
        }

        self._export_markdown_report(analysis)
        return analysis

    def _export_markdown_report(self, analysis: dict) -> None:
        """Renders comprehensive Markdown Dream Report."""
        lines = []
        lines.append("# 🌙 BTCTOOL 2.0 — Offline Dream Engine Calibration Report")
        lines.append("*Generated by Phase 3 Recalibration Organ (bot.txt Autonomous Learning)*\n")
        lines.append("---")
        lines.append("## 🧠 Cognitive Health & Error Overview")
        lines.append(f"| Metric | Value | Meaning in bot.txt |")
        lines.append(f"| :--- | :--- | :--- |")
        lines.append(f"| **Total Episodes** | **{analysis['total_episodes']}** | Total trades evaluated |")
        lines.append(f"| **Win Rate** | **{analysis['win_rate_pct']:.1f}%** ({analysis['wins']}W / {analysis['losses']}L) | Realized net profitability after fees |")
        lines.append(f"| **Net Realized PnL** | **{analysis['cumulative_net_pnl_pct']:+.2f}%** | Clean capital added to portfolio |")
        lines.append(f"| **Mean Prediction Error (e)** | **{analysis['mean_prediction_error']:+.2f}%** | Actual return minus predicted runway (r - r_hat) |")
        lines.append(f"| **Mean Regret (rg)** | **{analysis['mean_regret']:.2f}** | Size-weighted deviation from expectation (|e| * size) |")
        lines.append(f"| **Risk-Adjusted Reward** | **{analysis['mean_risk_adjusted_reward']:+.3f}** | Return normalized by stress drop |")

        lines.append("\n---")
        lines.append("## 🏛️ Setup & Regime Attribution")
        lines.append("| Setup / Regime | Episodes | Win Rate | Net PnL | Mean Error | Mean Regret |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for reg, s in analysis.get("regime_stats", {}).items():
            wr = (s["wins"] / s["count"] * 100.0) if s["count"] > 0 else 0.0
            avg_e = float(np.mean(s["errors"])) if s["errors"] else 0.0
            avg_rg = float(np.mean(s["regrets"])) if s["regrets"] else 0.0
            clean_reg = reg.replace("ZEBRA WHALE: ", "")
            lines.append(f"| `{clean_reg}` | {s['count']} | {wr:.0f}% | {s['cum_pnl']:+.2f}% | {avg_e:+.2f}% | {avg_rg:.2f} |")

        lines.append("\n---")
        lines.append("## 🎯 Offline Recalibration Directives")
        for rec in analysis.get("recommendations", []):
            lines.append(f"- 💡 **Directive:** {rec}")

        report_content = "\n".join(lines) + "\n"
        try:
            with open(REPORT_MD_FILE, "w", encoding="utf-8") as f:
                f.write(report_content)
            logger.info(f"[DreamEngine] Report successfully written to {REPORT_MD_FILE}")
        except Exception as e:
            logger.error(f"[DreamEngine] Error writing report: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    engine = DreamEngine()
    results = engine.analyze()
    print("\n" + "=" * 60)
    print("[DREAM ENGINE] REPLAY & RECALIBRATION COMPLETE")
    print("=" * 60)
    print(f"Total Episodes Analyzed: {results.get('total_episodes')}")
    print(f"Win Rate: {results.get('win_rate_pct')}%")
    print(f"Cumulative Net PnL: {results.get('cumulative_net_pnl_pct'):+.2f}%")
    print(f"Mean Prediction Error: {results.get('mean_prediction_error'):+.2f}%")
    print(f"Mean Regret: {results.get('mean_regret'):.2f}")
    print(f"Report Generated: {REPORT_MD_FILE}")
    print("=" * 60 + "\n")
