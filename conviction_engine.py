"""
conviction_engine.py — Institutional Whale & Liquidity Thesis Brain for Zebra Bot (btctool 2.0)
Architecture:
- The bot is here to make money, not trades (Patience over compulsive activity).
- Hard Chop Gate: Locked in 100% defensive cash during dead consolidation (<0.45% bandwidth).
- Liquidity Gravity & Fuel Model (LiqMap): Knows when overhead fuel is swept and gravity points down.
- Dip Absorption on Green Candle Turn: Buys dips at Middle Band in Bull Trend, Lower Band in Range.
- Asymmetric Runway Gate: Requires >= 0.45% room to target before risking a dollar.
- Thesis-Driven Trade Management: Prohibits sub-minute noise panics; holds until target or structural invalidation.
"""

import logging
from typing import Dict, Optional, Tuple
import numpy as np

logger = logging.getLogger("conviction_engine")

OKX_ROUNDTRIP_FEE_PCT = 0.0020  # 0.20% OKX Spot round-trip fee
MIN_RUNWAY_PCT = 0.45           # 0.45% minimum required room to structural target


class FreeConvictionEngine:
    """
    Whale & Liquidity Thesis-Driven Decision Engine.
    Operates without indicator lag or single-timeframe restrictions.
    """

    def __init__(self):
        pass

    def evaluate(self, matrix: dict, active_trade: Optional[dict] = None) -> dict:
        """
        Evaluates the multi-screen matrix, liquidity gravity, and thesis state.
        Outputs decisive autonomous actions.
        """
        price = float(matrix.get("latest_price", 0.0))
        if price <= 0:
            return {"action": "WAIT_IN_CASH", "reason": "Awaiting live price feed"}

        liq_gravity = matrix.get("liquidity_gravity", {})
        regime_data = matrix.get("regime_analysis", {})
        micro_data = matrix.get("micro_reversal", {})
        tanh_imb = float(matrix.get("tanh_imbalance", 0.0))
        absorption_idx = float(matrix.get("absorption_index", 0.0))
        trade_vel = float(matrix.get("trade_velocity", 0.0))

        regime = regime_data.get("regime", "RANGE")
        is_dead_chop = bool(regime_data.get("is_dead_chop", False))
        dynamic_support = float(regime_data.get("dynamic_support", price * 0.99))
        dynamic_target = float(regime_data.get("dynamic_target", price * 1.01))
        runway_pct = float(regime_data.get("runway_pct", 0.0))

        overhead_fuel_pct = float(liq_gravity.get("overhead_fuel_pct", 1.0))
        downside_fuel_pct = float(liq_gravity.get("downside_fuel_pct", 1.0))
        overhead_fuel_cleared = bool(liq_gravity.get("overhead_fuel_cleared", False))
        is_bottom_swept = bool(liq_gravity.get("is_bottom_swept", False))
        is_green_building = bool(micro_data.get("is_green_building", False))

        # ==================================================================
        # STATE 1: ALREADY IN A POSITION (THESIS-DRIVEN MANAGEMENT)
        # ==================================================================
        if active_trade:
            entry = float(active_trade.get("entry", price))
            gain_pct = (price - entry) / entry if entry > 0 else 0.0
            target_price = float(active_trade.get("target_price", dynamic_target))
            invalidation_floor = float(active_trade.get("invalidation_floor", dynamic_support * 0.998))
            tranche_2 = bool(active_trade.get("tranche_2_added", False))
            scenario = active_trade.get("scenario", "TRADE")

            # 1.1 PEAK EXHAUSTION / WHALE FLUSH IMMINENT
            # If in profit and the overhead short liquidations have been swept while downside liquidations are thick
            if gain_pct >= 0.0018 and overhead_fuel_cleared and downside_fuel_pct > 0.50:
                return {
                    "action": "BANK_PROFIT",
                    "gain_pct": gain_pct,
                    "exit_price": price,
                    "reason": f"PEAK EXHAUSTION: Overhead short stops cleared. Downside pool active ({downside_fuel_pct:.2f}%). Banking profit at peak (+{gain_pct*100:.2f}%).",
                    "telemetry": {"scenario": scenario, "gain_pct": gain_pct, "fuel_ratio": liq_gravity.get("fuel_ratio", 1.0)},
                }

            # 1.2 TARGET REACHED
            if price >= target_price:
                # Check if volatility balloon is actively expanding (trend riding mode)
                ind_15m = matrix.get("timeframes", {}).get("15m", {})
                bb_width = ind_15m.get("bb_width", 1.0)
                if bb_width > 1.2 and overhead_fuel_pct > 0.80 and tanh_imb > 0.20:
                    return {
                        "action": "RIDE_UNCAPPED",
                        "gain_pct": gain_pct,
                        "reason": f"Target reached (+{gain_pct*100:.2f}%), but Volatility Balloon expanding with untouched overhead fuel. Riding wave.",
                        "telemetry": {"scenario": scenario, "gain_pct": gain_pct},
                    }
                else:
                    return {
                        "action": "BANK_PROFIT",
                        "gain_pct": gain_pct,
                        "exit_price": price,
                        "reason": f"TARGET REACHED (+{gain_pct*100:.2f}%). Momentum capping at resistance. Profit secured in wallet.",
                        "telemetry": {"scenario": scenario, "gain_pct": gain_pct},
                    }

            # 1.3 SCALE-IN ON ABSORPTION DIP (DEPLOY LOT 2)
            # Price pulls back to discount (-0.40% to -0.10%), stays above invalidation floor, and bids absorb
            if not tranche_2 and -0.0050 <= gain_pct <= -0.0010 and price > invalidation_floor:
                if tanh_imb > 0.25 or absorption_idx > 15.0 or is_green_building:
                    return {
                        "action": "SCALE_IN_LOT_2",
                        "gain_pct": gain_pct,
                        "price": price,
                        "reason": f"BULLISH ABSORPTION DIP: Price tested support discount with heavy resting bids. Deploying Lot 2.",
                        "telemetry": {"scenario": scenario, "gain_pct": gain_pct},
                    }

            # 1.4 THESIS INVALIDATION (RECTIFYING A BAD CHOICE)
            # Support floor breached on volume -> cut immediately
            if price < invalidation_floor:
                return {
                    "action": "CUT_THESIS_INVALIDATED",
                    "gain_pct": gain_pct,
                    "exit_price": price,
                    "reason": f"THESIS INVALIDATED: Price broke support floor (${invalidation_floor:,.2f}) with volume. Cutting immediately to protect capital.",
                    "telemetry": {"scenario": scenario, "gain_pct": gain_pct},
                }

            # 1.5 NOISE IMMUNITY HOLD
            return {
                "action": "HOLD_POSITION",
                "gain_pct": gain_pct,
                "reason": f"THESIS INTACT: Holding {scenario} toward target ${target_price:,.2f}. Current PnL: {gain_pct*100:+.2f}%.",
                "telemetry": {"scenario": scenario, "gain_pct": gain_pct, "invalidation_floor": invalidation_floor},
            }

        # ==================================================================
        # STATE 2: IN CASH (SEEKING HIGH-EV OPPORTUNITY OR WAITING PATIENTLY)
        # ==================================================================

        # 2.1 CHOP GATE: Refuse to trade inside dead horizontal consolidation
        if is_dead_chop:
            return {
                "action": "WAIT_IN_CASH",
                "reason": f"CHOP GATE: Dead horizontal consolidation ({regime_data.get('bb_width_15m', 0):.2f}% bandwidth). Zero trades to preserve capital.",
                "telemetry": {"regime": regime, "runway_pct": runway_pct},
            }

        # 2.2 ASYMMETRIC RUNWAY GATE: Room to target must exceed fee hurdle
        if runway_pct < MIN_RUNWAY_PCT:
            return {
                "action": "WAIT_IN_CASH",
                "reason": f"INSUFFICIENT RUNWAY: Room to target is only +{runway_pct:.2f}% (requires >= {MIN_RUNWAY_PCT}%). Sitting in cash.",
                "telemetry": {"regime": regime, "runway_pct": runway_pct},
            }

        # 2.3 DO NOT BUY EXHAUSTED CEILINGS
        if overhead_fuel_cleared and runway_pct < 0.60:
            return {
                "action": "WAIT_IN_CASH",
                "reason": "CEILING GATE: Overhead short liquidity cleared. Risk of whale flush downward. Waiting in cash.",
                "telemetry": {"regime": regime, "overhead_fuel_pct": overhead_fuel_pct},
            }

        # 2.4 SCENARIO A: DIP ABSORPTION (CATCHING GREEN BODY OUT OF SUPPORT)
        # Price is near dynamic support (MB in Bull Trend, DN in Range)
        is_near_support = (price <= dynamic_support * 1.002) or is_bottom_swept
        if is_near_support and is_green_building:
            if tanh_imb > 0.15 or absorption_idx > 12.0 or is_bottom_swept:
                invalidation = dynamic_support * 0.9982  # 0.18% below support
                return {
                    "action": "ENTER_CORE_LOT_1",
                    "entry_price": price,
                    "scenario": f"DIP_ABSORPTION_{regime}",
                    "target_price": dynamic_target,
                    "invalidation_floor": invalidation,
                    "expected_runway_pct": runway_pct,
                    "reason": f"DIP ABSORPTION: Green candle building from {regime} support (${dynamic_support:,.2f}) with bid absorption. Target: ${dynamic_target:,.2f} (+{runway_pct:.2f}%).",
                    "telemetry": {"regime": regime, "runway_pct": runway_pct, "invalidation": invalidation},
                }

        # 2.5 SCENARIO B: VOLATILITY BREAKOUT WITH OPEN LIQUIDITY FUEL
        # Piercing upper band with wide open overhead runway and aggressive tape
        ind_15m = matrix.get("timeframes", {}).get("15m", {})
        up_15m = ind_15m.get("bb_upper", price * 1.01)
        if price >= up_15m and overhead_fuel_pct >= 0.75 and tanh_imb > 0.30 and trade_vel > 15.0:
            invalidation = up_15m * 0.998
            target = price * 1.012  # +1.20% breakout wave
            return {
                "action": "ENTER_CORE_LOT_1",
                "entry_price": price,
                "scenario": "FUELED_BREAKOUT",
                "target_price": target,
                "invalidation_floor": invalidation,
                "expected_runway_pct": 1.20,
                "reason": f"FUELED BREAKOUT: Upper band pierced with open short liquidation fuel ahead (+{overhead_fuel_pct:.2f}%). Takers lifting book.",
                "telemetry": {"regime": regime, "overhead_fuel_pct": overhead_fuel_pct},
            }

        # Default: Patiently wait in 100% cash
        return {
            "action": "WAIT_IN_CASH",
            "reason": f"PATIENT SCANNING: Market in {regime}. No high-probability whale setup active. Sitting in 100% cash.",
            "telemetry": {"regime": regime, "runway_pct": runway_pct, "tanh_imb": tanh_imb},
        }
