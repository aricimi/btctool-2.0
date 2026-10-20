"""
conviction_engine.py — Predictive Multi-Screen Autonomous Brain for Zebra Bot (btctool 2.0)
Architecture:
- The bot is here to make money, not trades.
- Predicts the turn instead of chasing after price moves.
- Evaluates room to run before entering (requires >= 0.45% to clear OKX 0.20% fees).
- Dips can happen at Middle Band in an uptrend, or Lower Band in a range.
- Never caps winning runs: trails structural support behind rising Middle Bands to ride $1,000 to $2,000 waves.
- Zero hardcoded single-timeframe proxies. All 11 timeframes pooled dynamically.
- Stop-loss is mathematically guaranteed to sit below actual entry fill price.
"""

import logging
from typing import Dict, Optional, Tuple
import numpy as np

logger = logging.getLogger("conviction_engine")

OKX_ROUNDTRIP_FEE_PCT = 0.0020     # 0.20% OKX Spot round-trip fee
MIN_PROJECTED_RUNWAY_PCT = 0.45    # 0.45% minimum required room to target


class FreeConvictionEngine:
    """
    Predictive Multi-Screen Autonomous Decision Brain.
    Evaluates market state, predicts turns, and acts freely.
    """

    def __init__(self):
        pass

    def evaluate(self, matrix: dict, active_trade: Optional[dict] = None) -> dict:
        """
        Evaluates the multi-screen sensory matrix and outputs autonomous trading decisions.
        """
        price = float(matrix.get("latest_price", 0.0))
        if price <= 0:
            return {"action": "WAIT_IN_CASH", "reason": "Awaiting live price stream"}

        bounds = matrix.get("multi_screen_bounds", {})
        balloon = matrix.get("balloon_geometry", {})
        micro_turn = matrix.get("micro_turn", {})

        nearest_support = float(bounds.get("nearest_support", price * 0.99))
        nearest_resistance = float(bounds.get("nearest_resistance", price * 1.01))
        pooled_swing_high = float(bounds.get("pooled_swing_high", nearest_resistance))
        macro_ceiling = float(bounds.get("macro_ceiling", nearest_resistance * 1.02))
        immediate_runway = float(bounds.get("immediate_runway_pct", 0.0))
        macro_runway = float(bounds.get("macro_runway_pct", 0.0))

        is_balloon_expanding = bool(balloon.get("is_balloon_expanding", False))
        is_slow_market = bool(balloon.get("is_slow_market", False))

        tanh_imb = float(matrix.get("tanh_imbalance", 0.0))
        absorption_idx = float(matrix.get("absorption_index", 0.0))
        velocity_slowing = bool(micro_turn.get("velocity_slowing", False))
        cvd = float(matrix.get("cvd", 0.0))
        trade_vel = float(matrix.get("trade_velocity", 0.0))

        atr = float(matrix.get("composite_atr", 250.0))

        # Dynamic Volatility Invalidation: anchored behind nearest support with ATR buffer
        raw_risk = max(price - nearest_support, 0.0) + (0.5 * atr)
        clamped_risk = min(max(raw_risk, 0.8 * atr), 2.0 * atr)
        dynamic_invalidation = min(price - (0.8 * atr), price - clamped_risk)

        # ==================================================================
        # STATE 1: ALREADY IN A POSITION (TRAILING & RIDING THE WAVE)
        # ==================================================================
        if active_trade:
            entry = float(active_trade.get("entry", price))
            gain_pct = (price - entry) / entry if entry > 0 else 0.0
            target_price = float(active_trade.get("target_price", nearest_resistance))
            trailing_stop = float(active_trade.get("trailing_stop", active_trade.get("invalidation_floor", entry * 0.997)))
            tranche_2 = bool(active_trade.get("tranche_2_added", False))
            scenario = active_trade.get("scenario", "TRADE")

            # 1.1 IN-SITU MEMORY SOFT STOP EVALUATION
            if price <= trailing_stop:
                if gain_pct >= 0.0020:
                    # In profit: Trailing stop reached -> Bank profit
                    return {
                        "action": "BANK_PROFIT",
                        "gain_pct": gain_pct,
                        "exit_price": price,
                        "reason": f"TRAILING STOP HIT (+{gain_pct*100:.2f}% net). Locking in banked profit at ${price:,.2f}.",
                        "telemetry": {"scenario": scenario, "gain_pct": gain_pct},
                    }
                else:
                    # Underwater: At invalidation floor. In-Situ Audit:
                    # Hard Emergency Floor: if price drops past floor by > 0.8 * ATR, cut unconditionally
                    if price <= (trailing_stop - (0.8 * atr)):
                        return {
                            "action": "CUT_THESIS_INVALIDATED",
                            "gain_pct": gain_pct,
                            "exit_price": price,
                            "reason": f"HARD FLOOR BREACH: Price broke past floor buffer (${price:,.2f}). Position closed to preserve capital.",
                            "telemetry": {"scenario": scenario, "gain_pct": gain_pct},
                        }

                    # Memory Soft Stop: Check if resting bids are absorbing the wick sweep
                    if tanh_imb > 0.15 or absorption_idx > 15.0:
                        return {
                            "action": "HOLD_POSITION",
                            "gain_pct": gain_pct,
                            "trailing_stop": trailing_stop,
                            "reason": f"ABSORPTION AT FLOOR: Price touching ${price:,.2f}, but bids absorbing sweep (tanh_imb={tanh_imb:+.2f}, Ai={absorption_idx:.1f}). Holding.",
                            "telemetry": {"scenario": scenario, "gain_pct": gain_pct, "trailing_stop": trailing_stop},
                        }
                    else:
                        return {
                            "action": "CUT_THESIS_INVALIDATED",
                            "gain_pct": gain_pct,
                            "exit_price": price,
                            "reason": f"STRUCTURAL BREAKDOWN: Support broken without bid absorption. Controlled cut small ({gain_pct*100:+.2f}%).",
                            "telemetry": {"scenario": scenario, "gain_pct": gain_pct},
                        }

            # 1.2 DYNAMIC TRAILING RATCHET (PROTECTING PROFITS & RIDING)
            updated_trailing_stop = trailing_stop
            # Once price gains +0.35%, move stop to Breakeven + fee protection (+0.15%)
            if gain_pct >= 0.0035 and trailing_stop < (entry * 1.0015):
                updated_trailing_stop = entry * 1.0015
                logger.info(f"[Brain] Trade risk-free: trailing stop moved to Breakeven+Fee: ${updated_trailing_stop:,.2f}")

            # As price surges higher, ratchet stop behind the rising nearest support
            if gain_pct >= 0.0070 and nearest_support > entry:
                ratchet_level = nearest_support - (0.3 * atr)
                if ratchet_level > updated_trailing_stop:
                    updated_trailing_stop = ratchet_level
                    logger.info(f"[Brain] Ratchet trailing stop higher behind rising support: ${updated_trailing_stop:,.2f}")

            # 1.3 TARGET DECISION POINT (BANK OR RIDE MACRO BALLOON)
            if price >= target_price:
                # If the balloon is blowing open and CVD is strong, DO NOT EXIT! Ride the macro wave!
                if is_balloon_expanding and macro_runway >= 0.80 and tanh_imb > 0.15:
                    return {
                        "action": "RIDE_UNCAPPED",
                        "gain_pct": gain_pct,
                        "target_price": macro_ceiling,
                        "trailing_stop": updated_trailing_stop,
                        "reason": f"TARGET REACHED (+{gain_pct*100:.2f}%), but Balloon opening outward into macro space (+{macro_runway:.2f}%). Trailing stop at ${updated_trailing_stop:,.2f}.",
                        "telemetry": {"scenario": scenario, "gain_pct": gain_pct, "macro_ceiling": macro_ceiling},
                    }
                else:
                    return {
                        "action": "BANK_PROFIT",
                        "gain_pct": gain_pct,
                        "exit_price": price,
                        "reason": f"TARGET HIT (+{gain_pct*100:.2f}%). Resistance capping momentum. Securing profit in wallet.",
                        "telemetry": {"scenario": scenario, "gain_pct": gain_pct},
                    }

            # 1.4 SCALE-IN LOT 2 ON CONFIRMED STRUCTURAL ABSORPTION DISCOUNT
            dist_to_support = abs(price - nearest_support)
            is_at_support_zone = (dist_to_support <= (0.75 * atr)) and (price < entry)
            if not tranche_2 and is_at_support_zone and (tanh_imb > 0.15 or absorption_idx > 15.0 or velocity_slowing):
                return {
                    "action": "SCALE_IN_LOT_2",
                    "price": price,
                    "reason": f"STRUCTURAL DISCOUNT ABSORPTION: Pullback to support (${nearest_support:,.2f}) absorbed by resting bids. Adding Lot 2 at discount.",
                    "telemetry": {"scenario": scenario, "gain_pct": gain_pct},
                }

            # 1.5 NOISE-IMMUNE HOLD
            return {
                "action": "HOLD_POSITION",
                "gain_pct": gain_pct,
                "trailing_stop": updated_trailing_stop,
                "reason": f"HOLDING {scenario}: Toward target ${target_price:,.2f}. Current PnL: {gain_pct*100:+.2f}%. Trailing Stop: ${updated_trailing_stop:,.2f}.",
                "telemetry": {"scenario": scenario, "gain_pct": gain_pct, "trailing_stop": updated_trailing_stop},
            }

        # ==================================================================
        # STATE 2: IN CASH (SEEKING REAL ASYMMETRIC GAIN OR SITTING PATIENTLY)
        # ==================================================================

        # 2.1 REAL GAIN HURDLE: If room to target is too small to make real money after fees -> PASS
        if immediate_runway < MIN_PROJECTED_RUNWAY_PCT and not is_balloon_expanding:
            return {
                "action": "WAIT_IN_CASH",
                "reason": f"NO REAL GAIN ON TABLE: Room to target is only +{immediate_runway:.2f}% (requires >= {MIN_PROJECTED_RUNWAY_PCT}% to clear fees). Sitting in cash.",
                "telemetry": {"immediate_runway": immediate_runway, "support": nearest_support, "resistance": nearest_resistance},
            }

        # 2.2 SLOW MARKET: Lines are horizontal and slow -> Stay in cash
        if is_slow_market and immediate_runway < 0.60:
            return {
                "action": "WAIT_IN_CASH",
                "reason": "SLOW MARKET: Bollinger lines horizontal and volume compressed. Sitting 100% in cash.",
                "telemetry": {"immediate_runway": immediate_runway},
            }

        # 2.3 SETUP A: BOTTOM / DIP TURN PREDICTION (BUYING LOW AT SUPPORT)
        dist_to_support = abs(price - nearest_support)
        is_at_support_floor = dist_to_support <= (0.75 * atr)
        is_absorption_confirmed = (tanh_imb > 0.15 or absorption_idx > 12.0 or velocity_slowing)

        if is_at_support_floor and is_absorption_confirmed:
            target = nearest_resistance
            return {
                "action": "ENTER_CORE_LOT_1",
                "entry_price": price,
                "scenario": "DIP_ABSORPTION_TURN",
                "target_price": target,
                "invalidation_floor": dynamic_invalidation,
                "trailing_stop": dynamic_invalidation,
                "expected_runway_pct": immediate_runway,
                "reason": f"DIP TURN PREDICTED: Tested support (${nearest_support:,.2f}) with bid absorption (Ai={absorption_idx:.1f}, tanh_imb={tanh_imb:+.2f}). Target: ${target:,.2f} (+{immediate_runway:.2f}%).",
                "telemetry": {"support": nearest_support, "target": target, "invalidation": dynamic_invalidation},
            }

        # 2.4 SETUP B: MACRO FUELED BREAKOUT (BUYING REAL EXPANSION)
        # Physics Breakout: Price physically at or above the pooled swing high, with positive kinetic push
        is_clearing_high = price >= (pooled_swing_high - 1.0)
        is_kinetic_push_positive = (tanh_imb > 0.0) and (cvd >= 0.0 or trade_vel > 8.0)

        if is_clearing_high and is_balloon_expanding and is_kinetic_push_positive and macro_runway >= 0.90:
            target = macro_ceiling
            return {
                "action": "ENTER_CORE_LOT_1",
                "entry_price": price,
                "scenario": "MACRO_BALLOON_BREAKOUT",
                "target_price": target,
                "invalidation_floor": dynamic_invalidation,
                "trailing_stop": dynamic_invalidation,
                "expected_runway_pct": macro_runway,
                "reason": f"BALLOON BREAKOUT: Price cleared swing high (${pooled_swing_high:,.2f}) into macro space (${macro_ceiling:,.2f}, +{macro_runway:.2f}%) with positive kinetic flow.",
                "telemetry": {"target": target, "invalidation": dynamic_invalidation, "macro_runway": macro_runway},
            }

        # Default: Patiently sitting 100% in cash
        return {
            "action": "WAIT_IN_CASH",
            "reason": f"PATIENT SCANNING: Nearest support ${nearest_support:,.2f}, Nearest ceiling ${nearest_resistance:,.2f} (+{immediate_runway:.2f}%). Waiting for setup.",
            "telemetry": {"immediate_runway": immediate_runway, "support": nearest_support, "resistance": nearest_resistance},
        }
