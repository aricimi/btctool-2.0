"""
conviction_engine.py — Truly Free Autonomous Expected Value Agent for Zebra Bot (btctool 2.0)
Operates on the AlphaGo paradigm:
- Ingests all 11 screens (1s to 1D), L2 order book depth, CVD tape, and derivatives into continuous directional probability P_up.
- Calculates Expected Value (E[Edge]) net of OKX fees.
- Zero leashes, zero static stop lines, zero artificial profit ceilings.
- Rides winning waves uncapped, scales into verified absorption dips, and cuts immediately when P_up flips negative.
"""

import logging
from typing import Dict, Optional, Tuple
import numpy as np

logger = logging.getLogger("conviction_engine")

OKX_ROUNDTRIP_FEE_PCT = 0.0020  # 0.20% OKX Spot round-trip fee

# Multi-Horizon Weights across all 11 screens (Total = 1.0)
HORIZON_WEIGHTS = {
    # Macro Tier (35%)
    "1D": 0.10,
    "6h": 0.08,
    "4h": 0.09,
    "2h": 0.08,
    # Structural Tier (30%)
    "1h": 0.10,
    "30m": 0.10,
    "15m": 0.10,
    # Tactical Trigger Tier (35%)
    "5m": 0.10,
    "3m": 0.08,
    "1m": 0.10,
    "1s": 0.07,
}


class FreeConvictionEngine:
    """
    Autonomous Expected Value Agent.
    Evaluates the continuous probability P_up across all 11 screens and decides actions dynamically.
    """

    def __init__(self):
        pass

    def compute_directional_probability(self, matrix: dict) -> Tuple[float, dict]:
        """
        Calculates the continuous directional probability P_up in [0.0, 1.0] across all 11 screens.
        Returns: (P_up, screen_telemetry_dict)
        """
        tf_data = matrix.get("timeframes", {})
        price = matrix.get("latest_price", 0.0)
        tanh_imbalance = matrix.get("tanh_imbalance", 0.0)
        absorption_idx = matrix.get("absorption_index", 0.0)
        oi_zscore = matrix.get("oi_zscore", 0.0)
        trade_vel = matrix.get("trade_velocity", 0.0)
        vwap = matrix.get("session_vwap", price)

        raw_score = 0.0
        screen_votes = {}

        # 1. Evaluate all 11 Timeframes (Trend alignment + Momentum acceleration)
        for tf, weight in HORIZON_WEIGHTS.items():
            item = tf_data.get(tf, {})
            if not item:
                continue

            tf_score = 0.0

            # 1.1 Trend Alignment (EMA 9 vs EMA 21 vs EMA 50)
            ema9 = item.get("ema_9", price)
            ema21 = item.get("ema_21", price)
            ema50 = item.get("ema_50", price)
            if ema9 > ema21 > ema50:
                tf_score += 1.0
            elif ema9 > ema21:
                tf_score += 0.5
            elif ema9 < ema21 < ema50:
                tf_score -= 1.0
            elif ema9 < ema21:
                tf_score -= 0.5

            # 1.2 MACD Momentum Acceleration
            macd_hist = item.get("macd_hist", 0.0)
            if macd_hist > 0:
                tf_score += 0.5
            elif macd_hist < 0:
                tf_score -= 0.5

            # 1.3 Bollinger Band Position
            pct_b = item.get("bb_pct_b", 0.5)
            # Normalizing pct_b into [-1.0, +1.0]
            bb_score = (pct_b - 0.5) * 2.0
            tf_score += 0.3 * bb_score

            # Weight and accumulate
            raw_score += tf_score * weight
            screen_votes[tf] = round(tf_score, 2)

        # 2. Order Book Depth & Wall Mass
        raw_score += 0.40 * tanh_imbalance

        # 3. Derivatives Leverage Expansion
        if oi_zscore != 0:
            norm_oi = float(np.tanh(oi_zscore / 2.0))
            raw_score += 0.25 * norm_oi

        # 4. Real-Time Absorption (Taker sells swallowed by resting bids)
        if absorption_idx > 15.0:
            raw_score += 0.30

        # Convert raw_score into continuous probability P_up using Sigmoid
        # Sigmoid: P_up = 1 / (1 + exp(-2.2 * raw_score))
        p_up = float(1.0 / (1.0 + np.exp(-2.2 * raw_score)))

        telemetry = {
            "p_up": round(p_up, 4),
            "raw_score": round(raw_score, 3),
            "screen_votes": screen_votes,
            "order_book_tanh": round(tanh_imbalance, 3),
            "oi_zscore": round(oi_zscore, 2),
            "absorption_index": round(absorption_idx, 2),
        }
        return p_up, telemetry

    def evaluate(self, matrix: dict, active_trade: Optional[dict] = None) -> dict:
        """
        Evaluates the 11-screen board state and outputs action without leashes or static stop lines.
        """
        price = matrix.get("latest_price", 0.0)
        if price <= 0:
            return {"action": "WAIT", "reason": "Awaiting live price feed"}

        p_up, telemetry = self.compute_directional_probability(matrix)
        tf_data = matrix.get("timeframes", {})
        atr_15m = tf_data.get("15m", {}).get("atr", 150.0)
        # Dynamic expansion range: at least 0.50% or based on 15m ATR
        expected_expansion_pct = max((atr_15m * 1.5) / price if price > 0 else 0.005, 0.005)

        # Expected Value: Probability * Magnitude - Downside - Fee
        expected_edge = (p_up * expected_expansion_pct) - ((1.0 - p_up) * expected_expansion_pct * 0.8) - OKX_ROUNDTRIP_FEE_PCT

        # ==================================================================
        # STATE 1: ALREADY IN POSITION -> UNRESTRICTED AUTONOMOUS MANAGEMENT
        # ==================================================================
        if active_trade:
            entry = float(active_trade.get("entry", price))
            gain_pct = (price - entry) / entry
            tranche_2 = bool(active_trade.get("tranche_2_added", False))

            # 1. IMMEDIATE INVALIDATION CUT (No static stop lines, no waiting)
            # The edge has flipped to sellers. Cut immediately at market.
            if p_up < 0.44:
                action_name = "HARVEST_PROFIT" if gain_pct >= 0.0020 else "CUT_IMMEDIATE"
                return {
                    "action": action_name,
                    "p_up": p_up,
                    "gain_pct": gain_pct,
                    "reason": f"Directional edge flipped negative (P_up={p_up*100:.1f}%). Exiting immediately at market.",
                    "telemetry": telemetry,
                }

            # 2. SCALE-IN ON ABSORPTION DIP (Deploy Lot 2)
            # Price pulls back, but higher timeframes remain strongly bullish (P_up >= 0.70)
            # and order book confirms absorption
            if not tranche_2 and -0.0060 <= gain_pct <= 0.0020 and p_up >= 0.70:
                if matrix.get("absorption_index", 0.0) > 15.0 or matrix.get("tanh_imbalance", 0.0) > 0.25:
                    return {
                        "action": "SCALE_IN_LOT_2",
                        "p_up": p_up,
                        "gain_pct": gain_pct,
                        "reason": f"Bullish Absorption Dip at discount. P_up={p_up*100:.1f}%. Deploying Lot 2.",
                        "telemetry": telemetry,
                    }

            # 3. RIDE UNCAPPED (Market is paying us)
            return {
                "action": "RIDE_UNCAPPED",
                "p_up": p_up,
                "gain_pct": gain_pct,
                "reason": f"Riding winning move uncapped. P_up={p_up*100:.1f}%, Net Gain: {gain_pct*100:+.2f}%.",
                "telemetry": telemetry,
            }

        # ==================================================================
        # STATE 2: IN CASH -> SEEKING HIGH-PROBABILITY OPPORTUNITY
        # ==================================================================
        # Enters only when probability is bullish and net expected edge > 0 after fees
        if p_up >= 0.60 and expected_edge > 0.0:
            return {
                "action": "ENTER_CORE_LOT_1",
                "p_up": p_up,
                "expected_edge_pct": expected_edge,
                "entry_price": price,
                "reason": f"High-probability edge detected (P_up={p_up*100:.1f}%, E[Edge]={expected_edge*100:+.2f}%). Entering Core Lot 1.",
                "telemetry": telemetry,
            }

        return {
            "action": "SCANNING_IN_CASH",
            "p_up": p_up,
            "expected_edge_pct": expected_edge,
            "reason": f"Scanning 11 screens. P_up={p_up*100:.1f}%. Sitting in cash to preserve capital.",
            "telemetry": telemetry,
        }
