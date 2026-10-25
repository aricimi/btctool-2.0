"""
backtest.py — Rigorous Historical Backtesting Engine for Zebra Bot (btctool 2.0)
Simulates multi-screen price action, dynamic runway hurdles, classical EV gates,
noise-immune trailing stops, OKX round-trip fees (0.20%), and spread-based slippage.

Evaluates two configurations:
1. Belief System ON  (Temporal hysteresis lambda=0.85, persistence multiplier, dynamic hurdles)
2. Belief System OFF (Raw un-smoothed edge, zero persistence multiplier, fixed baseline hurdles)
"""

import json
import math
import os
import sys
import time
from typing import Dict, List, Optional, Tuple
import numpy as np

from market_state import MarketState
from conviction_engine import FreeConvictionEngine, TradeIntent
from risk_engine import RiskEngine, RiskDecision

HISTORICAL_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "historical_btc_5m.json")


def load_historical_data(filepath: str = HISTORICAL_DATA_FILE) -> List[dict]:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Historical data file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


class CandleBuffer:
    """Maintains multi-timeframe rolling candles resampled from base 5m bars."""

    def __init__(self, max_bars: int = 150):
        self.max_bars = max_bars
        self.candles_5m: List[dict] = []
        self.candles_15m: List[dict] = []
        self.candles_1h: List[dict] = []
        self.candles_4h: List[dict] = []

    def update(self, bar: dict):
        self.candles_5m.append(bar)
        if len(self.candles_5m) > self.max_bars:
            self.candles_5m = self.candles_5m[-self.max_bars:]

        # Resample to 15m (every 3 bars)
        ts = bar["ts"]
        if len(self.candles_5m) >= 3 and int(ts) % 900 < 300:
            c3 = self.candles_5m[-3:]
            c15 = {
                "ts": c3[-1]["ts"],
                "open": c3[0]["open"],
                "high": max(c["high"] for c in c3),
                "low": min(c["low"] for c in c3),
                "close": c3[-1]["close"],
                "vol": sum(c["vol"] for c in c3),
            }
            if not self.candles_15m or self.candles_15m[-1]["ts"] != c15["ts"]:
                self.candles_15m.append(c15)
                if len(self.candles_15m) > self.max_bars:
                    self.candles_15m = self.candles_15m[-self.max_bars:]

        # Resample to 1h (every 12 bars)
        if len(self.candles_5m) >= 12 and int(ts) % 3600 < 300:
            c12 = self.candles_5m[-12:]
            c1h = {
                "ts": c12[-1]["ts"],
                "open": c12[0]["open"],
                "high": max(c["high"] for c in c12),
                "low": min(c["low"] for c in c12),
                "close": c12[-1]["close"],
                "vol": sum(c["vol"] for c in c12),
            }
            if not self.candles_1h or self.candles_1h[-1]["ts"] != c1h["ts"]:
                self.candles_1h.append(c1h)
                if len(self.candles_1h) > self.max_bars:
                    self.candles_1h = self.candles_1h[-self.max_bars:]

        # Resample to 4h (every 48 bars)
        if len(self.candles_5m) >= 48 and int(ts) % 14400 < 300:
            c48 = self.candles_5m[-48:]
            c4h = {
                "ts": c48[-1]["ts"],
                "open": c48[0]["open"],
                "high": max(c["high"] for c in c48),
                "low": min(c["low"] for c in c48),
                "close": c48[-1]["close"],
                "vol": sum(c["vol"] for c in c48),
            }
            if not self.candles_4h or self.candles_4h[-1]["ts"] != c4h["ts"]:
                self.candles_4h.append(c4h)
                if len(self.candles_4h) > self.max_bars:
                    self.candles_4h = self.candles_4h[-self.max_bars:]


class MockStreamAdapter:
    """Adapts historical candle buffers for MarketState calculation without WebSockets."""

    def __init__(self, buffer: CandleBuffer, current_bar: dict):
        self.buffer = buffer
        self.latest_price = float(current_bar["close"])
        self.spread_pct = 0.02  # 0.02% typical BTC/USDT spread
        spread_usd = self.latest_price * (self.spread_pct / 100.0)
        self.best_bid = self.latest_price - (spread_usd / 2.0)
        self.best_ask = self.latest_price + (spread_usd / 2.0)
        self.last_update_ts = 0.0
        self.trade_velocity = 8.0
        self.cvd = (current_bar["close"] - current_bar["open"]) * current_bar["vol"]
        self.funding_rate = 0.0001
        self.buffers = {
            "5m": buffer.candles_5m,
            "15m": buffer.candles_15m or buffer.candles_5m,
            "1h": buffer.candles_1h or buffer.candles_5m,
            "4h": buffer.candles_4h or buffer.candles_5m,
        }
        self.recent_trades = []

    def get_candles(self, tf: str) -> List[dict]:
        return self.buffers.get(tf, self.buffers["5m"])

    def get_oi_zscore(self) -> float:
        return 0.5

    def get_anti_spoof_depth(self, distance_pct: float = 0.005) -> Tuple[float, float, float]:
        # Microstructure volume proxy: lower vs upper wick volume imbalance
        bar = self.buffer.candles_5m[-1] if self.buffer.candles_5m else {"open": 1, "close": 1, "high": 1, "low": 1, "vol": 1}
        rng = max(bar["high"] - bar["low"], 0.1)
        lower_wick = max(min(bar["open"], bar["close"]) - bar["low"], 0.0)
        upper_wick = max(bar["high"] - max(bar["open"], bar["close"]), 0.0)
        imbalance = float(np.clip((lower_wick - upper_wick) / rng, -1.0, 1.0))
        bid_vol = float(bar["vol"] * 5.0 * (1.0 + imbalance))
        ask_vol = float(bar["vol"] * 5.0 * (1.0 - imbalance))
        return bid_vol, ask_vol, float(np.tanh(imbalance * 2.0))


class BacktestRunner:
    """Executes discrete event-driven backtest across historical bars."""

    def __init__(
        self,
        bars: List[dict],
        use_belief_system: bool = True,
        fee_pct: float = 0.20,
        slippage_mult: float = 1.25,
    ):
        self.bars = bars
        self.use_belief = use_belief_system
        self.fee_pct = fee_pct
        self.slippage_mult = slippage_mult

        self.brain = FreeConvictionEngine(decay_rate=0.85 if use_belief_system else 0.0)
        self.risk_gate = RiskEngine()
        self.state_calc = MarketState()
        self.buffer = CandleBuffer(max_bars=120)

        # Performance tracking
        self.trades: List[dict] = []
        self.equity_curve: List[float] = [100.0]  # Starting capital base 100%
        self.active_trade: Optional[dict] = None
        self.daily_drawdown_tracker: Dict[int, float] = {}

    def run(self, start_idx: int = 100, end_idx: Optional[int] = None) -> dict:
        total_bars = len(self.bars)
        end = end_idx or total_bars

        # Pre-seed buffer with initial 100 bars for indicators
        for b in self.bars[:start_idx]:
            self.buffer.update(b)

        for i in range(start_idx, end):
            current_bar = self.bars[i]
            next_bar = self.bars[i + 1] if i + 1 < total_bars else None
            self.buffer.update(current_bar)

            ts = current_bar["ts"]
            day_key = int(ts // 86400)
            daily_dd = self.daily_drawdown_tracker.get(day_key, 0.0)

            # Build sensory matrix
            adapter = MockStreamAdapter(self.buffer, current_bar)
            matrix = self.state_calc.extract_state_matrix(adapter)
            matrix["timestamp"] = ts

            # --------------------------------------------------------------
            # ACTIVE TRADE LIFECYCLE MANAGEMENT
            # --------------------------------------------------------------
            if self.active_trade:
                trade = self.active_trade
                entry_p = trade["entry"]
                target_p = trade["target_price"]
                stop_p = trade["trailing_stop"]
                bar_low = current_bar["low"]
                bar_high = current_bar["high"]

                # 1. Check Stop Hit
                if bar_low <= stop_p:
                    exit_p = min(current_bar["open"], stop_p)
                    gross_pnl = ((exit_p - entry_p) / entry_p) * 100.0
                    slip = max(0.02, (matrix["spread_pct"] / 2.0) * self.slippage_mult)
                    net_pnl = gross_pnl - self.fee_pct - slip

                    trade.update({
                        "exit_price": exit_p,
                        "exit_ts": ts,
                        "exit_reason": "STOP_INVALIDATION",
                        "gross_pnl_pct": gross_pnl,
                        "net_pnl_pct": net_pnl,
                        "status": "CLOSED_LOSS" if net_pnl <= 0 else "CLOSED_PROFIT",
                    })
                    self.trades.append(trade)
                    self.risk_gate.record_trade_outcome(
                        trade["scenario"], net_pnl, timestamp=ts,
                        entry_price=entry_p, radius=matrix.get("composite_atr", 150.0) * 1.0
                    )
                    self.equity_curve.append(self.equity_curve[-1] * (1.0 + (net_pnl / 100.0)))
                    self.active_trade = None
                    continue

                # 2. Check Target Hit
                elif bar_high >= target_p:
                    exit_p = target_p
                    gross_pnl = ((exit_p - entry_p) / entry_p) * 100.0
                    slip = max(0.02, (matrix["spread_pct"] / 2.0) * self.slippage_mult)
                    net_pnl = gross_pnl - self.fee_pct - slip

                    trade.update({
                        "exit_price": exit_p,
                        "exit_ts": ts,
                        "exit_reason": "TARGET_PROFIT",
                        "gross_pnl_pct": gross_pnl,
                        "net_pnl_pct": net_pnl,
                        "status": "CLOSED_PROFIT",
                    })
                    self.trades.append(trade)
                    self.risk_gate.record_trade_outcome(
                        trade["scenario"], net_pnl, timestamp=ts,
                        entry_price=entry_p, radius=matrix.get("composite_atr", 150.0) * 1.0
                    )
                    self.equity_curve.append(self.equity_curve[-1] * (1.0 + (net_pnl / 100.0)))
                    self.active_trade = None
                    continue

                # 3. Ratchet Trailing Stop higher
                current_gain = ((bar_high - entry_p) / entry_p) * 100.0
                if current_gain >= 0.60 and stop_p < (entry_p * 1.0025):
                    trade["trailing_stop"] = round(entry_p * 1.0025, 2)
                if current_gain >= 1.20:
                    sup = matrix["multi_screen_bounds"]["nearest_support"]
                    atr = matrix["composite_atr"]
                    if sup > entry_p and (sup - 0.8 * atr) > trade["trailing_stop"]:
                        trade["trailing_stop"] = round(sup - 0.8 * atr, 2)

                continue

            # --------------------------------------------------------------
            # IN CASH: COGNITION & RISK GATING
            # --------------------------------------------------------------
            if not self.use_belief:
                # Bypass belief system: evaluate raw instant edge without hysteresis
                raw_edge = (
                    0.35 * float(np.tanh(400.0 * matrix["feature_vector"]["trend_strength"]))
                    + 0.25 * float(matrix["tanh_imbalance"])
                    + 0.20 * min(matrix["absorption_index"] / 20.0, 1.0)
                    - 0.15 * matrix["feature_vector"]["entropy"]
                )
                self.brain.belief_system.state.directional_bias = float(np.clip(raw_edge, -1.0, 1.0))
                self.brain.belief_system.state.conviction = abs(raw_edge) / (1.0 + matrix["feature_vector"]["entropy"])
                self.brain.belief_system.state.persistence_ticks = 10  # Permissive persistence
                self.brain.belief_system.state.regime_belief = "BULL_ACCELERATION" if raw_edge > 0.15 else "NEUTRAL_WAIT"
                self.brain.belief_system.state.adaptive_runway_hurdle = 0.45  # Fixed baseline
                self.brain.belief_system.state.adaptive_conf_hurdle = 0.55    # Fixed baseline

            intent = self.brain.evaluate(matrix, active_trade=None, governor=self.risk_gate.governor)
            decision = self.risk_gate.evaluate(
                intent,
                matrix,
                active_trade=None,
                daily_drawdown_pct=daily_dd,
                max_daily_drawdown=2.0,
            )

            if decision.action == "ENTER_CORE_LOT_1" and next_bar:
                # Fill at next bar open with realistic dynamic slippage
                fill_price = next_bar["open"]
                slip = max(0.02, (matrix["spread_pct"] / 2.0) * self.slippage_mult)
                entry_with_slip = fill_price * (1.0 + (slip / 100.0))

                self.active_trade = {
                    "entry": entry_with_slip,
                    "entry_ts": next_bar["ts"],
                    "scenario": decision.scenario,
                    "target_price": decision.target_price,
                    "invalidation_floor": decision.trailing_stop,
                    "trailing_stop": decision.trailing_stop,
                    "size_factor": decision.approved_size_factor,
                    "reason": decision.reason,
                }

        return self.compute_metrics()

    def compute_metrics(self) -> dict:
        total_trades = len(self.trades)
        if total_trades == 0:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "net_profit_pct": 0.0,
                "expectancy_pct": 0.0,
                "profit_factor": 0.0,
                "max_drawdown_pct": 0.0,
                "longest_losing_streak": 0,
                "total_fees_pct": 0.0,
            }

        wins = [t for t in self.trades if t["net_pnl_pct"] > 0]
        losses = [t for t in self.trades if t["net_pnl_pct"] <= 0]
        win_rate = (len(wins) / total_trades) * 100.0
        net_pnls = [t["net_pnl_pct"] for t in self.trades]
        total_net_pct = sum(net_pnls)
        expectancy = total_net_pct / total_trades
        total_fees = total_trades * self.fee_pct

        gross_win_sum = sum(t["gross_pnl_pct"] for t in wins) if wins else 0.0
        gross_loss_sum = abs(sum(t["gross_pnl_pct"] for t in losses)) if losses else 0.0
        profit_factor = (gross_win_sum / gross_loss_sum) if gross_loss_sum > 0 else (99.0 if gross_win_sum > 0 else 0.0)

        # Max drawdown
        peak = 100.0
        max_dd = 0.0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = ((peak - eq) / peak) * 100.0
            if dd > max_dd:
                max_dd = dd

        # Longest losing streak
        cur_streak = 0
        max_streak = 0
        for t in self.trades:
            if t["net_pnl_pct"] <= 0:
                cur_streak += 1
                if cur_streak > max_streak:
                    max_streak = cur_streak
            else:
                cur_streak = 0

        return {
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(win_rate, 2),
            "net_profit_pct": round(total_net_pct, 3),
            "expectancy_pct": round(expectancy, 3),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "longest_losing_streak": max_streak,
            "total_fees_pct": round(total_fees, 2),
        }


def main():
    print("=" * 70)
    print("ZEBRA BOT: HISTORICAL REPRODUCIBLE BACKTEST & EMPIRICAL AUDIT")
    print("Chronological Execution • Dynamic Slippage • 0.20% Round-Trip Fees")
    print("=" * 70)

    bars = load_historical_data()
    total_bars = len(bars)
    split_idx = int(100 + (total_bars - 100) * 0.60)  # 60% In-Sample, 40% Out-of-Sample

    print(f"Total Bars: {total_bars} (5m candles, ~12.1 days)")
    print(f"Warm-Up: 100 bars | In-Sample: Bars 100 to {split_idx} | Out-of-Sample: Bars {split_idx} to {total_bars}\n")

    # ------------------------------------------------------------------
    # RUN 1: BELIEF SYSTEM ON (In-Sample & Out-of-Sample)
    # ------------------------------------------------------------------
    print(">>> RUN 1: BELIEF SYSTEM ON (Hysteresis lambda=0.85, Persistence Gating, Dynamic Hurdles)")
    runner_on_is = BacktestRunner(bars, use_belief_system=True)
    m_on_is = runner_on_is.run(start_idx=100, end_idx=split_idx)

    runner_on_oos = BacktestRunner(bars, use_belief_system=True)
    m_on_oos = runner_on_oos.run(start_idx=split_idx, end_idx=total_bars)

    runner_on_full = BacktestRunner(bars, use_belief_system=True)
    m_on_full = runner_on_full.run(start_idx=100, end_idx=total_bars)

    # ------------------------------------------------------------------
    # RUN 2: BELIEF SYSTEM OFF (In-Sample & Out-of-Sample)
    # ------------------------------------------------------------------
    print(">>> RUN 2: BELIEF SYSTEM OFF (Raw Instant Edge, Zero Persistence, Fixed Baseline Hurdles)")
    runner_off_is = BacktestRunner(bars, use_belief_system=False)
    m_off_is = runner_off_is.run(start_idx=100, end_idx=split_idx)

    runner_off_oos = BacktestRunner(bars, use_belief_system=False)
    m_off_oos = runner_off_oos.run(start_idx=split_idx, end_idx=total_bars)

    runner_off_full = BacktestRunner(bars, use_belief_system=False)
    m_off_full = runner_off_full.run(start_idx=100, end_idx=total_bars)

    print("\n" + "=" * 70)
    print("COMPARATIVE EMPIRICAL AUDIT RESULTS")
    print("=" * 70)
    print(f"{'Metric':<25} | {'Belief ON (Full)':<18} | {'Belief OFF (Full)':<18} | {'Belief ON (OOS)':<15}")
    print("-" * 80)
    print(f"{'Total Trades':<25} | {m_on_full['total_trades']:<18} | {m_off_full['total_trades']:<18} | {m_on_oos['total_trades']:<15}")
    print(f"{'Win Rate (%)':<25} | {m_on_full['win_rate_pct']:<18} | {m_off_full['win_rate_pct']:<18} | {m_on_oos['win_rate_pct']:<15}")
    print(f"{'Net Profit (%)':<25} | {m_on_full['net_profit_pct']:<18} | {m_off_full['net_profit_pct']:<18} | {m_on_oos['net_profit_pct']:<15}")
    print(f"{'Expectancy (% / trade)':<25} | {m_on_full['expectancy_pct']:<18} | {m_off_full['expectancy_pct']:<18} | {m_on_oos['expectancy_pct']:<15}")
    print(f"{'Profit Factor':<25} | {m_on_full['profit_factor']:<18} | {m_off_full['profit_factor']:<18} | {m_on_oos['profit_factor']:<15}")
    print(f"{'Max Drawdown (%)':<25} | {m_on_full['max_drawdown_pct']:<18} | {m_off_full['max_drawdown_pct']:<18} | {m_on_oos['max_drawdown_pct']:<15}")
    print(f"{'Longest Loss Streak':<25} | {m_on_full['longest_losing_streak']:<18} | {m_off_full['longest_losing_streak']:<18} | {m_on_oos['longest_losing_streak']:<15}")
    print(f"{'Total Fees Paid (%)':<25} | {m_on_full['total_fees_pct']:<18} | {m_off_full['total_fees_pct']:<18} | {m_on_oos['total_fees_pct']:<15}")
    print("=" * 70)


if __name__ == "__main__":
    main()
