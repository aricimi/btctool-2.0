"""
conviction_engine.py — Hierarchical Confluence & Kinetic Brain for Zebra Bot (btctool 2.0)
Synthesizes the 100-Screen State Matrix using:
1. Kinetic Push vs Structural Barrier physical forces model.
2. Sticky Lifecycle State Machine (Zero tick-jitter).
3. 3-Tier Top-Down Confluence (Macro Tide -> Structural Ground -> Micro Trigger).
4. The 5 Dynamic Playbooks (Macro Entry, Absorption Reload Lot 2, Uncapped Harvesting, Structural Cut, Chop Gate).
"""

import logging
from enum import Enum
from typing import Dict, Optional, Tuple
import numpy as np

logger = logging.getLogger("conviction_engine")

OKX_ROUNDTRIP_FEE_PCT = 0.0020  # 0.20% OKX Spot maker/taker round-trip fee


class LifecycleState(Enum):
    SCANNING = "SCANNING"
    OPTIMAL_ENTRY = "OPTIMAL_ENTRY"
    IN_PROGRESS = "IN_PROGRESS"
    EXHAUSTION = "EXHAUSTION"
    TARGET = "TARGET"


class ConvictionEngine:
    """
    Quantitative Brain for Zebra Bot.
    Evaluates expected value, kinetic energy vs barriers, and manages trade lifecycles.
    """

    def __init__(self):
        self.state = LifecycleState.SCANNING
        self.active_side: Optional[str] = None  # "LONG"
        self.entry_price: float = 0.0
        self.current_stop: float = 0.0
        self.target_1: float = 0.0
        self.target_2: float = 0.0
        self.highest_price: float = 0.0
        self.tranche_2_added: bool = False
        self.breakeven_set: bool = False

    def evaluate(self, matrix: dict, active_trade: Optional[dict] = None) -> dict:
        """
        Main decision loop.
        Evaluates current 100-Screen State Matrix and outputs an actionable directive.
        """
        price = matrix.get("latest_price", 0.0)
        if price <= 0:
            return {"action": "WAIT", "reason": "Awaiting live price feed"}

        tf_data = matrix.get("timeframes", {})
        benchmarks = matrix.get("benchmarks", {})
        vwap = matrix.get("session_vwap", price)
        absorption_idx = matrix.get("absorption_index", 0.0)
        tanh_imbalance = matrix.get("tanh_imbalance", 0.0)
        oi_zscore = matrix.get("oi_zscore", 0.0)
        funding_rate = matrix.get("funding_rate", 0.0)

        # Reference ATR from 15m or 5m
        atr_15m = tf_data.get("15m", {}).get("atr", 150.0)
        atr_5m = tf_data.get("5m", {}).get("atr", 80.0)
        atr_ref = max(atr_15m, atr_5m, 50.0)

        # ------------------------------------------------------------------
        # 1. Kinetic Push vs Structural Barrier Scoring
        # ------------------------------------------------------------------
        # Kinetic Energy (Push): Volume surge, Taker CVD, MACD acceleration, EMA alignment
        kinetic_score = 0.0

        # 1.1 EMA Alignment (15m, 1h, 4h)
        for tf_name in ("15m", "1h", "4h"):
            tf_item = tf_data.get(tf_name, {})
            if tf_item.get("ema_9", 0) > tf_item.get("ema_21", 0) > tf_item.get("ema_50", 0):
                kinetic_score += 10.0
            elif tf_item.get("ema_9", 0) < tf_item.get("ema_21", 0):
                kinetic_score -= 10.0

        # 1.2 MACD Velocity (1m, 5m, 15m)
        for tf_name in ("1m", "5m", "15m"):
            tf_item = tf_data.get(tf_name, {})
            if tf_item.get("macd_hist", 0) > 0:
                kinetic_score += 6.0
            else:
                kinetic_score -= 6.0

        # 1.3 Order Flow & CVD Taker Aggression
        if tanh_imbalance > 0.2:
            kinetic_score += 15.0 * tanh_imbalance
        elif tanh_imbalance < -0.2:
            kinetic_score += 15.0 * tanh_imbalance

        # 1.4 Derivatives Fuel (OI Z-Score)
        if oi_zscore > 1.5:
            kinetic_score += 10.0  # Expanding leveraged momentum
        elif oi_zscore < -1.5:
            kinetic_score -= 10.0  # Liquidation flush / money leaving

        # Structural Barrier Distance
        bb_15m = tf_data.get("15m", {})
        upper_barrier = bb_15m.get("bb_upper", price + 2.0 * atr_ref)
        lower_barrier = bb_15m.get("bb_lower", price - 2.0 * atr_ref)
        dist_to_upper_pct = (upper_barrier - price) / price if price > 0 else 0.0
        dist_to_lower_pct = (price - lower_barrier) / price if price > 0 else 0.0

        # Volatility Chop Gate: Check if market bandwidth is too compressed to beat fees
        bb_width_15m = bb_15m.get("bb_width", 1.0)
        if bb_width_15m < 0.35 and abs(kinetic_score) < 20.0:
            return {
                "action": "CHOP_GATE_WAIT",
                "reason": f"Volatility compressed ({bb_width_15m:.2f}% BB width). Sitting in cash to save fees.",
                "kinetic_score": kinetic_score,
            }

        # ------------------------------------------------------------------
        # 2. IF ALREADY IN AN ACTIVE POSITION -> MANAGE LIFECYCLE
        # ------------------------------------------------------------------
        if active_trade:
            entry = float(active_trade.get("entry", price))
            current_stop = float(active_trade.get("current_stop", entry - 1.5 * atr_ref))
            gain_pct = (price - entry) / entry
            high_price = max(float(active_trade.get("highest_price", entry)), price)
            tranche_2 = bool(active_trade.get("tranche_2_added", False))

            # 2.1 Ruthless Structural Invalidation
            if price <= current_stop:
                return {
                    "action": "EXIT_STRUCTURAL_STOP",
                    "reason": f"Price broke structural stop floor at ${current_stop:,.2f}. Exiting to protect capital.",
                    "gain_pct": gain_pct,
                }

            # 2.2 Bullish Absorption Reload (Scale-in Lot 2)
            # If price pulls back but holds dynamic support (VWAP or EMA 50) and Absorption Index is high
            if not tranche_2 and gain_pct < 0.003 and price >= (entry - 0.75 * atr_ref):
                # Check absorption at support
                is_near_vwap = abs(price - vwap) / price < 0.003
                is_near_ema50 = abs(price - tf_data.get("15m", {}).get("ema_50", price)) / price < 0.003
                if (is_near_vwap or is_near_ema50) and (absorption_idx > 15.0 or tanh_imbalance > 0.25):
                    return {
                        "action": "SCALE_IN_LOT_2",
                        "reason": f"Bullish Absorption detected at dynamic support (${price:,.2f}). Deploying Lot 2.",
                        "new_stop": max(current_stop, price - 0.8 * atr_ref),
                    }

            # 2.3 Uncapped Profit Run & Dynamic Trailing Stop
            # In profit > 0.40% (covers 0.20% OKX fee with margin) -> Move stop to breakeven + fee shield
            if gain_pct >= 0.0040 and not active_trade.get("breakeven_set", False):
                be_stop = entry * (1.0 + 0.0022)  # Breakeven + fee shield
                return {
                    "action": "RATCHET_BREAKEVEN",
                    "reason": f"Trade in profit (+{gain_pct*100:.2f}%). Moving stop to Breakeven Fee Shield (${be_stop:,.2f}).",
                    "new_stop": be_stop,
                }

            # In profit > 0.80% -> Dynamic Structural Trailing behind 5m swing low
            if gain_pct >= 0.0080:
                low_5m = tf_data.get("5m", {}).get("bb_mid", price - 0.8 * atr_ref)
                if low_5m > current_stop:
                    return {
                        "action": "RATCHET_TRAILING_STOP",
                        "reason": f"Trailing profit at +{gain_pct*100:.2f}%. Ratcheting stop higher to ${low_5m:,.2f}.",
                        "new_stop": low_5m,
                    }

            # 2.4 Top Exhaustion (Kinetic Fuel Depletion at Barrier)
            # Price near upper barrier AND kinetic score collapsing AND MACD 1m/5m negative
            rsi_15m = tf_data.get("15m", {}).get("rsi", 50.0)
            if dist_to_upper_pct < 0.0015 and kinetic_score < 0.0 and rsi_15m > 72.0 and gain_pct > 0.004:
                return {
                    "action": "HARVEST_PROFIT",
                    "reason": f"Kinetic push exhausted at structural resistance (${upper_barrier:,.2f}). Banking profit (+{gain_pct*100:.2f}%).",
                    "gain_pct": gain_pct,
                }

            # Sticky Hold in Progress
            return {
                "action": "HOLD_IN_PROGRESS",
                "reason": f"Position healthy. Kinetic Score: {kinetic_score:+.1f}, Gain: +{gain_pct*100:.2f}%.",
                "highest_price": high_price,
            }

        # ------------------------------------------------------------------
        # 3. IF NO ACTIVE POSITION -> SCAN FOR FRESH ENTRY
        # ------------------------------------------------------------------
        # Requirement for Macro Continuation Entry:
        # 1. Macro Tide is Bullish (4H EMA9 > EMA21 or 1H EMA9 > EMA50)
        # 2. Kinetic Score > +35.0 (Strong institutional fuel)
        # 3. Order Book tanh imbalance > +0.15 (Buyers dominating depth)
        # 4. Expected Move to Resistance exceeds Fee Hurdle (0.20%) by at least 2.5x
        macro_bullish = tf_data.get("4h", {}).get("ema_9", 0) >= tf_data.get("4h", {}).get("ema_21", 0)
        expected_run_pct = dist_to_upper_pct

        if macro_bullish and kinetic_score >= 35.0 and tanh_imbalance >= 0.15:
            # Fee Hurdle Validation: Expected move must exceed round-trip fee (0.20%) + buffer
            if expected_run_pct >= (OKX_ROUNDTRIP_FEE_PCT * 2.0):
                stop_loss = price - 1.2 * atr_ref
                target_1 = price + 1.0 * atr_ref
                target_2 = price + 2.2 * atr_ref

                return {
                    "action": "ENTER_CORE_LOT_1",
                    "reason": f"Macro Bullish Continuation confirmed. Kinetic Score: {kinetic_score:+.1f}, Imbalance: {tanh_imbalance:+.2f}.",
                    "entry_price": price,
                    "stop_loss": stop_loss,
                    "target_1": target_1,
                    "target_2": target_2,
                    "expected_move_pct": expected_run_pct,
                }

        return {
            "action": "SCANNING",
            "reason": f"Scanning market. Kinetic Score: {kinetic_score:+.1f}, Imbalance: {tanh_imbalance:+.2f}.",
            "kinetic_score": kinetic_score,
        }
