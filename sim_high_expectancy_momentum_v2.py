"""
sim_high_expectancy_momentum_v2.py — CPPR Widening & High-Expectancy Momentum Replay (v2)
Dataset: Full 34.7-day continuous 1-minute historical dataset (49,996 bars)
Location: historical_btc_30d_1m.json

OBJECTIVE:
Test the fix for the Premature CPPR Ratchet Trap:
1. Delayed Activation: Do not arm CPPR trailing ratchet until price achieves >= +1.20% gross expansion.
2. Widened Buffer: Allow 1-minute market noise breathing room (50% retention above +1.20%, 60% above +1.50%, support ratchets).
3. Post-only limit/maker entry modeling (0.02% maker fee) + standard taker comparison.
4. Focus strictly on Setup B & clean Setup D with >= +1.50% gross target clearance.

ZERO PRODUCTION CODE MODIFIED. Strictly isolated simulation.
"""

import os
import sys
import json
import time
import datetime
import numpy as np

from market_state import MarketState
from conviction_engine import FreeConvictionEngine, TradeIntent
from risk_engine import RiskEngine


# =============================================================================
# 1. 1-MINUTE MULTI-TIMEFRAME STREAMING BUFFER & ADAPTER
# =============================================================================

class Buffer1m:
    """Maintains multi-timeframe rolling buffers updated at 1-minute resolution."""
    def __init__(self, max_bars: int = 150):
        self.max_bars = max_bars
        self.buffers = {
            "1m": [],
            "3m": [],
            "5m": [],
            "15m": [],
            "1h": [],
            "4h": [],
            "1D": [],
        }
        self.active_candles = {}

    def update(self, bar: dict):
        self.buffers["1m"].append(bar)
        if len(self.buffers["1m"]) > self.max_bars:
            self.buffers["1m"] = self.buffers["1m"][-self.max_bars:]

        ts = bar["ts"]

        # Aggregate into higher timeframes matching live market_stream.py
        tf_secs = {"3m": 180, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1D": 86400}
        for tf, sec in tf_secs.items():
            start_ts = int(ts // sec) * sec
            curr = self.active_candles.get(tf)
            if curr is None or curr["start_ts"] != start_ts:
                if curr is not None:
                    self.buffers[tf].append({
                        "ts": curr["start_ts"],
                        "open": curr["open"],
                        "high": curr["high"],
                        "low": curr["low"],
                        "close": curr["close"],
                        "vol": curr["vol"],
                    })
                    if len(self.buffers[tf]) > self.max_bars:
                        self.buffers[tf] = self.buffers[tf][-self.max_bars:]

                self.active_candles[tf] = {
                    "start_ts": start_ts,
                    "open": bar["open"],
                    "high": bar["high"],
                    "low": bar["low"],
                    "close": bar["close"],
                    "vol": bar["vol"],
                }
            else:
                curr["high"] = max(curr["high"], bar["high"])
                curr["low"] = min(curr["low"], bar["low"])
                curr["close"] = bar["close"]
                curr["vol"] += bar["vol"]


class MockStreamAdapter1m:
    """Adapts 1-minute streaming buffers for MarketState calculation."""
    def __init__(self, buf: Buffer1m, current_bar: dict):
        self.buf = buf
        self.latest_price = float(current_bar["close"])
        self.spread_pct = 0.02
        spread_usd = self.latest_price * (self.spread_pct / 100.0)
        self.best_bid = self.latest_price - (spread_usd / 2.0)
        self.best_ask = self.latest_price + (spread_usd / 2.0)
        self.last_update_ts = 0.0
        self.trade_velocity = 8.0
        self.cvd = (current_bar["close"] - current_bar["open"]) * current_bar["vol"]
        self.funding_rate = 0.0001
        self.buffers = buf.buffers
        self.recent_trades = []

    def get_candles(self, tf: str):
        candles = self.buffers.get(tf)
        if not candles and tf in ("5m", "15m", "1h", "4h"):
            return self.buffers.get("1m", [])
        return candles or []

    def get_oi_zscore(self) -> float:
        return 0.5

    def get_anti_spoof_depth(self, distance_pct: float = 0.005):
        bar = self.buffers["1m"][-1] if self.buffers["1m"] else {"open": 1, "close": 1, "high": 1, "low": 1, "vol": 1}
        rng = max(bar["high"] - bar["low"], 0.1)
        lower_wick = max(min(bar["open"], bar["close"]) - bar["low"], 0.0)
        upper_wick = max(bar["high"] - max(bar["open"], bar["close"]), 0.0)
        imbalance = float(np.clip((lower_wick - upper_wick) / rng, -1.0, 1.0))
        bid_vol = float(bar["vol"] * 5.0 * (1.0 + imbalance))
        ask_vol = float(bar["vol"] * 5.0 * (1.0 - imbalance))
        return bid_vol, ask_vol, float(np.tanh(imbalance * 2.0))


# =============================================================================
# 2. v2 REPLAY HARNESS: CPPR DELAYED ACTIVATION (+1.20%) & WIDENED BUFFER
# =============================================================================

def run_high_expectancy_simulation_v2(bars: list, min_runway_pct: float = 1.50) -> dict:
    engine = FreeConvictionEngine()
    risk_gate = RiskEngine()
    state_calc = MarketState()

    buf = Buffer1m(max_bars=150)
    warmup = 500  # 500 minutes

    for b in bars[:warmup]:
        buf.update(b)

    trades = []
    equity_taker = [100.0]
    equity_maker = [100.0]
    active_trade = None

    t0 = time.time()
    n_bars = len(bars)

    for i in range(warmup, n_bars):
        cur_bar = bars[i]
        nxt_bar = bars[i + 1] if i + 1 < n_bars else None
        ts = cur_bar["ts"]
        dt_str = cur_bar.get("datetime", str(i))
        buf.update(cur_bar)

        mock = MockStreamAdapter1m(buf, cur_bar)
        mat = state_calc.extract_state_matrix(mock)
        mat["timestamp"] = ts

        # ---------------------------------------------------------------------
        # ACTIVE TRADE LIFECYCLE (CPPR v2: DELAYED ACTIVATION & WIDENED BUFFER)
        # ---------------------------------------------------------------------
        if active_trade:
            e_p = active_trade["entry"]
            s_p = active_trade["trailing_stop"]
            t_p = active_trade["target_price"]
            b_high = cur_bar["high"]
            b_low = cur_bar["low"]

            if b_high > active_trade["highest_price"]:
                active_trade["highest_price"] = b_high

            gross_peak = ((active_trade["highest_price"] - e_p) / e_p) * 100.0
            if gross_peak > active_trade["mfe_gross"]:
                active_trade["mfe_gross"] = gross_peak

            gross_trough = ((b_low - e_p) / e_p) * 100.0
            if gross_trough < active_trade["mae_gross"]:
                active_trade["mae_gross"] = gross_trough

            active_trade["duration_bars"] = active_trade.get("duration_bars", 0) + 1

            # -----------------------------------------------------------------
            # CPPR v2 MODIFIED RATCHET LOGIC:
            # 1. Delayed Activation: Under +1.20% peak gain, do NOT arm CPPR!
            #    Position breathes with original structural stop (avoiding 0.32% noise traps).
            # 2. Level 1 Ratchet (Peak >= +1.20%):
            #    Lock 50% of peak gain (or min +0.35% gross, ensuring positive net profit).
            #    Also ratchet behind rising support if available.
            # 3. Level 2 Ratchet (Peak >= +1.50%):
            #    Lock 60% of peak gain, allowing runner to seek target or macro space.
            # -----------------------------------------------------------------
            peak_gain_pct = (active_trade["highest_price"] - e_p) / e_p if e_p > 0 else 0.0

            if peak_gain_pct >= 0.0120:
                locked_gain = max(0.0035, peak_gain_pct * 0.50)
                ratchet_stop = round(e_p * (1.0 + locked_gain), 2)
                if ratchet_stop > active_trade["trailing_stop"]:
                    active_trade["trailing_stop"] = ratchet_stop

                sup = mat["multi_screen_bounds"]["nearest_support"]
                atr = mat["composite_atr"]
                if sup > e_p and (sup - 0.8 * atr) > active_trade["trailing_stop"]:
                    active_trade["trailing_stop"] = round(sup - 0.8 * atr, 2)

            if peak_gain_pct >= 0.0150:
                locked_gain_60 = peak_gain_pct * 0.60
                ratchet_stop_60 = round(e_p * (1.0 + locked_gain_60), 2)
                if ratchet_stop_60 > active_trade["trailing_stop"]:
                    active_trade["trailing_stop"] = ratchet_stop_60

            s_p = active_trade["trailing_stop"]

            # Exit Check 1: Stop / Trailing Stop Breached
            if b_low <= s_p:
                ex_p = min(cur_bar["open"], s_p)
                gross = ((ex_p - e_p) / e_p) * 100.0
                slip = max(0.02, (mat["spread_pct"] / 2.0) * 1.25)

                taker_fee_drag = 0.20 + slip
                net_taker = gross - taker_fee_drag

                maker_fee_drag = 0.07 + (slip / 2.0)
                net_maker = gross - maker_fee_drag

                exit_reason = "CPPR_PROFIT_LOCKED" if ex_p > e_p else "STOP_INVALIDATION"

                active_trade.update({
                    "exit_bar": i,
                    "exit_time": dt_str,
                    "exit_price": ex_p,
                    "exit_reason": exit_reason,
                    "gross_pnl": gross,
                    "taker_fee_drag": taker_fee_drag,
                    "net_pnl_taker": net_taker,
                    "maker_fee_drag": maker_fee_drag,
                    "net_pnl_maker": net_maker,
                })
                trades.append(active_trade)
                risk_gate.record_trade_outcome(
                    active_trade["scenario"], net_taker, timestamp=ts,
                    entry_price=e_p, radius=mat.get("composite_atr", 150.0) * 1.0
                )
                equity_taker.append(equity_taker[-1] * (1.0 + (net_taker / 100.0)))
                equity_maker.append(equity_maker[-1] * (1.0 + (net_maker / 100.0)))
                active_trade = None
                continue

            # Exit Check 2: Structural Target Reached
            elif b_high >= t_p:
                ex_p = t_p
                gross = ((ex_p - e_p) / e_p) * 100.0
                slip = max(0.02, (mat["spread_pct"] / 2.0) * 1.25)

                taker_fee_drag = 0.20 + slip
                net_taker = gross - taker_fee_drag

                maker_fee_drag = 0.07 + (slip / 2.0)
                net_maker = gross - maker_fee_drag

                active_trade.update({
                    "exit_bar": i,
                    "exit_time": dt_str,
                    "exit_price": ex_p,
                    "exit_reason": "TARGET_PROFIT",
                    "gross_pnl": gross,
                    "taker_fee_drag": taker_fee_drag,
                    "net_pnl_taker": net_taker,
                    "maker_fee_drag": maker_fee_drag,
                    "net_pnl_maker": net_maker,
                })
                trades.append(active_trade)
                risk_gate.record_trade_outcome(
                    active_trade["scenario"], net_taker, timestamp=ts,
                    entry_price=e_p, radius=mat.get("composite_atr", 150.0) * 1.0
                )
                equity_taker.append(equity_taker[-1] * (1.0 + (net_taker / 100.0)))
                equity_maker.append(equity_maker[-1] * (1.0 + (net_maker / 100.0)))
                active_trade = None
                continue

            continue

        # ---------------------------------------------------------------------
        # IN CASH: HIGH-EXPECTANCY CANDIDATE EVALUATION
        # ---------------------------------------------------------------------
        intent = engine.evaluate(mat, active_trade=None, governor=risk_gate.governor)

        if intent.action == "ENTER_CORE_LOT_1":
            if intent.scenario in ("MACRO_BALLOON_BREAKOUT", "TREND_PULLBACK_CONTINUATION"):
                if intent.expected_runway_pct >= min_runway_pct:
                    decision = risk_gate.evaluate(intent, mat, active_trade=None)
                    if decision.action == "ENTER_CORE_LOT_1" and nxt_bar:
                        slip = max(0.02, (mat["spread_pct"] / 2.0) * 1.25)
                        entry_price = nxt_bar["open"] * (1.0 + (slip / 100.0))
                        active_trade = {
                            "entry": entry_price,
                            "entry_bar": i + 1,
                            "entry_time": nxt_bar.get("datetime", str(i + 1)),
                            "scenario": decision.scenario,
                            "target_price": decision.target_price,
                            "trailing_stop": decision.trailing_stop,
                            "expected_runway_pct": intent.expected_runway_pct,
                            "size_factor": decision.approved_size_factor,
                            "highest_price": entry_price,
                            "lowest_price": entry_price,
                            "mfe_gross": 0.0,
                            "mae_gross": 0.0,
                            "duration_bars": 0,
                        }

    elapsed = time.time() - t0

    # Compute Statistics
    def compute_stats(trades_list, fee_mode="taker"):
        n = len(trades_list)
        if n == 0:
            return {
                "total_trades": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
                "gross_pnl_pct": 0.0, "fee_drag_pct": 0.0, "net_pnl_pct": 0.0,
                "profit_factor": 0.0, "max_drawdown_pct": 0.0, "expectancy_pct": 0.0,
            }

        pnl_key = "net_pnl_taker" if fee_mode == "taker" else "net_pnl_maker"
        fee_key = "taker_fee_drag" if fee_mode == "taker" else "maker_fee_drag"
        eq_curve = equity_taker if fee_mode == "taker" else equity_maker

        wins = [t for t in trades_list if t[pnl_key] > 0]
        losses = [t for t in trades_list if t[pnl_key] <= 0]
        wr = (len(wins) / n * 100.0)

        tot_gross = sum(t["gross_pnl"] for t in trades_list)
        tot_fees = sum(t[fee_key] for t in trades_list)
        tot_net = sum(t[pnl_key] for t in trades_list)
        exp = tot_net / n

        gw = sum(t[pnl_key] for t in wins) if wins else 0.0
        gl = abs(sum(t[pnl_key] for t in losses)) if losses else 0.0
        pf = (gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)

        # Max Drawdown
        pk = 100.0
        mdd = 0.0
        for eq in eq_curve:
            if eq > pk: pk = eq
            dd = ((pk - eq) / pk) * 100.0
            if dd > mdd: mdd = dd

        return {
            "total_trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(wr, 2),
            "gross_pnl_pct": round(tot_gross, 2),
            "fee_drag_pct": round(tot_fees, 2),
            "net_pnl_pct": round(tot_net, 2),
            "profit_factor": round(pf, 2),
            "max_drawdown_pct": round(mdd, 2),
            "expectancy_pct": round(exp, 3),
        }

    stats_taker = compute_stats(trades, "taker")
    stats_maker = compute_stats(trades, "maker")

    breakdown = {}
    for sc in ["MACRO_BALLOON_BREAKOUT", "TREND_PULLBACK_CONTINUATION"]:
        sc_trades = [t for t in trades if t["scenario"] == sc]
        breakdown[sc] = {
            "taker": compute_stats(sc_trades, "taker"),
            "maker": compute_stats(sc_trades, "maker"),
        }

    return {
        "elapsed_seconds": round(elapsed, 1),
        "total_bars": n_bars,
        "standard_taker_model": stats_taker,
        "fee_optimized_maker_model": stats_maker,
        "setup_breakdown": breakdown,
        "trades": trades,
    }


if __name__ == "__main__":
    data_path = "historical_btc_30d_1m.json"
    if not os.path.exists(data_path):
        print(f"Error: {data_path} not found.")
        sys.exit(1)

    print(f"Loading continuous 34.7-day dataset ({data_path})...")
    with open(data_path, "r") as f:
        bars = json.load(f)

    print(f"Loaded {len(bars)} 1-minute bars. Running CPPR Widening Simulation v2 (Activation >= +1.20%)...")
    results = run_high_expectancy_simulation_v2(bars, min_runway_pct=1.50)

    print("\n" + "=" * 80)
    print("CPPR WIDENING v2 REPLAY RESULTS (49,996 BARS / 34.7 DAYS)")
    print("=" * 80)
    print(f"Elapsed Time:               {results['elapsed_seconds']}s")
    print(f"Total Bars Replayed:        {results['total_bars']:,}")
    print("-" * 80)
    print("MODEL A: STANDARD TAKER EXECUTION (0.05% + slippage roundtrip)")
    st = results["standard_taker_model"]
    print(f"  Total Trades:             {st['total_trades']}")
    print(f"  Win / Loss Record:        {st['wins']} Wins / {st['losses']} Losses")
    print(f"  Win Rate:                 {st['win_rate_pct']}%")
    print(f"  Gross PnL:                {st['gross_pnl_pct']:+.2f}%")
    print(f"  Fee Drag:                 -{st['fee_drag_pct']:.2f}%")
    print(f"  Net Realized PnL:         {st['net_pnl_pct']:+.2f}%")
    print(f"  Profit Factor:            {st['profit_factor']}")
    print(f"  Maximum Drawdown:         {st['max_drawdown_pct']:.2f}%")
    print(f"  Trade Expectancy:         {st['expectancy_pct']:+.3f}%")
    print("-" * 80)
    print("MODEL B: FEE-OPTIMIZED LIMIT/MAKER ENTRY (0.02% maker + taker exit)")
    sm = results["fee_optimized_maker_model"]
    print(f"  Total Trades:             {sm['total_trades']}")
    print(f"  Win / Loss Record:        {sm['wins']} Wins / {sm['losses']} Losses")
    print(f"  Win Rate:                 {sm['win_rate_pct']}%")
    print(f"  Gross PnL:                {sm['gross_pnl_pct']:+.2f}%")
    print(f"  Fee Drag:                 -{sm['fee_drag_pct']:.2f}%")
    print(f"  Net Realized PnL:         {sm['net_pnl_pct']:+.2f}%")
    print(f"  Profit Factor:            {sm['profit_factor']}")
    print(f"  Maximum Drawdown:         {sm['max_drawdown_pct']:.2f}%")
    print(f"  Trade Expectancy:         {sm['expectancy_pct']:+.3f}%")
    print("=" * 80)

    print("\nSETUP BREAKDOWN (Fee-Optimized Maker Model):")
    for sc, data in results["setup_breakdown"].items():
        m = data["maker"]
        print(f"  {sc:30s} | Trades: {m['total_trades']:2d} | WR: {m['win_rate_pct']:5.1f}% | Gross: {m['gross_pnl_pct']:+6.2f}% | Net: {m['net_pnl_pct']:+6.2f}% | PF: {m['profit_factor']:4.2f}")

    print("\nINDIVIDUAL TRADES EXECUTED:")
    for idx, t in enumerate(results["trades"], 1):
        print(f"  Trade #{idx:2d}: {t['scenario']:28s} | In: {t['entry_time']} (${t['entry']:,.1f}) -> Out: {t['exit_time']} (${t['exit_price']:,.1f}) | MFE: {t['mfe_gross']:+5.2f}% | Gross: {t['gross_pnl']:+5.2f}% | Net(Maker): {t['net_pnl_maker']:+5.2f}% | Net(Taker): {t['net_pnl_taker']:+5.2f}% | Reason: {t['exit_reason']}")

    output_file = "high_expectancy_momentum_v2_results.json"
    save_data = {
        "elapsed_seconds": results["elapsed_seconds"],
        "total_bars": results["total_bars"],
        "standard_taker_model": results["standard_taker_model"],
        "fee_optimized_maker_model": results["fee_optimized_maker_model"],
        "setup_breakdown": results["setup_breakdown"],
        "trades": results["trades"],
    }
    with open(output_file, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\nDetailed trade results saved to {output_file}.")
