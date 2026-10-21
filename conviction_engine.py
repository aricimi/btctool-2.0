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
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Any
import numpy as np

from risk_engine import TradeIntent

logger = logging.getLogger("conviction_engine")

OKX_ROUNDTRIP_FEE_PCT = 0.0020     # 0.20% OKX Spot round-trip fee
MIN_PROJECTED_RUNWAY_PCT = 0.45    # 0.45% baseline minimum required room to target


@dataclass
class BeliefState:
    """
    Component 5: Explicit Belief State Representation.
    Represents persistent directional conviction, cross-timeframe entropy, and regime belief across ticks.
    """
    directional_bias: float = 0.0          # Continuous smoothed bias in [-1.0, 1.0] (hysteresis filtered)
    conviction: float = 0.0                # Conviction scaled by entropy and persistence in [0.0, 1.0]
    persistence_ticks: int = 0             # Ticks maintaining consistent directional polarity
    regime_belief: str = "NEUTRAL_WAIT"    # "BULL_ACCELERATION", "BEAR_PRESSURE", "CHOP_COMPRESSION", "NEUTRAL_WAIT"
    entropy_ema: float = 0.50              # Exponentially smoothed cross-timeframe entropy
    adaptive_runway_hurdle: float = 0.45   # Component 2: Bounded dynamic hurdle in [%]
    adaptive_conf_hurdle: float = 0.55     # Component 2: Bounded dynamic confidence hurdle in [0.0, 1.0]
    last_raw_edge: float = 0.0             # Raw un-smoothed edge snapshot
    last_urgency: float = 0.0              # Urgency snapshot
    last_update_ts: float = 0.0            # Timestamp of last update


class BeliefSystem:
    """
    Component 5: Explicit Belief System with Temporal Hysteresis & Decay.
    Maintains persistent continuous directional conviction across ticks,
    filtering 1-second noise flicker and ensuring stable conviction accumulation.
    """

    def __init__(self, decay_rate: float = 0.85):
        self.decay_rate = decay_rate  # 85% prior belief weight, 15% new tick evidence
        self.state = BeliefState()

    def reset(self):
        """Resets belief state to neutral baseline."""
        self.state = BeliefState()

    def update(
        self,
        raw_edge: float,
        instant_urgency: float,
        entropy: float,
        vol_regime: float,
        is_balloon_expanding: bool,
        is_slow_market: bool,
        absorption_idx: float,
        timestamp: float = 0.0,
    ) -> BeliefState:
        """
        Updates persistent belief state with temporal smoothing and computes adaptive hurdles.
        """
        # First tick initialization
        if self.state.last_update_ts == 0.0:
            smoothed_bias = raw_edge
            smoothed_entropy = entropy
            persistence = 1
        else:
            decay = self.decay_rate
            smoothed_bias = (decay * self.state.directional_bias) + ((1.0 - decay) * raw_edge)
            smoothed_entropy = (decay * self.state.entropy_ema) + ((1.0 - decay) * entropy)

            # Polarity persistence: checks whether directional sign has remained consistent
            same_polarity = (smoothed_bias * self.state.directional_bias) > 0.0
            if same_polarity and abs(smoothed_bias) >= 0.08:
                persistence = self.state.persistence_ticks + 1
            else:
                persistence = 1

        smoothed_bias = float(np.clip(smoothed_bias, -1.0, 1.0))
        smoothed_entropy = float(np.clip(smoothed_entropy, 0.0, 1.0))

        # Persistence multiplier: prevents isolated 1-tick flash spikes from triggering full conviction
        pers_mult = min(1.0, 0.70 + (0.15 * min(persistence, 2)))
        raw_conviction = abs(smoothed_bias) / (1.0 + smoothed_entropy)
        conviction = float(np.clip(raw_conviction * pers_mult, 0.0, 1.0))

        # Regime belief classification
        if smoothed_bias > 0.20 and (is_balloon_expanding or instant_urgency >= 0.20):
            regime = "BULL_ACCELERATION"
        elif smoothed_bias < -0.20:
            regime = "BEAR_PRESSURE"
        elif is_slow_market or smoothed_entropy >= 0.65:
            regime = "CHOP_COMPRESSION"
        else:
            regime = "NEUTRAL_WAIT"

        # ------------------------------------------------------------------
        # Component 2: Bounded Adaptive Confidence & Runway Thresholds
        # ------------------------------------------------------------------
        # Dynamic runway hurdle:
        # - Hard floor: 0.40% (guarantees clearing 0.20% fee + 0.02% slippage + positive net profit)
        # - In clean expansion: clamps down to 0.40% to ride early breakouts
        # - In chop/high entropy: scales up to 0.70% to defend capital against fee-drag
        if is_balloon_expanding and vol_regime >= 1.0:
            adaptive_runway = 0.40
        else:
            entropy_penalty = 0.20 * smoothed_entropy
            vol_penalty = 0.10 * max(0.0, 1.0 - vol_regime)
            adaptive_runway = float(np.clip(0.45 + entropy_penalty + vol_penalty, 0.40, 0.70))

        # Dynamic confidence hurdle: baseline 0.55
        # High absorption discounts hurdle; high entropy raises it
        conf_hurdle = float(np.clip(0.55 + (0.20 * smoothed_entropy) - (0.15 * min(absorption_idx / 20.0, 1.0)), 0.45, 0.75))

        self.state = BeliefState(
            directional_bias=round(smoothed_bias, 4),
            conviction=round(conviction, 4),
            persistence_ticks=persistence,
            regime_belief=regime,
            entropy_ema=round(smoothed_entropy, 4),
            adaptive_runway_hurdle=round(adaptive_runway, 3),
            adaptive_conf_hurdle=round(conf_hurdle, 3),
            last_raw_edge=round(raw_edge, 3),
            last_urgency=round(instant_urgency, 3),
            last_update_ts=timestamp or time.time(),
        )
        return self.state


class FreeConvictionEngine:
    """
    Predictive Multi-Screen Autonomous Decision Brain.
    Integrates Component 5 (Explicit Belief System) and Component 2 (Adaptive Confidence & Runway Thresholds).
    """

    def __init__(self, decay_rate: float = 0.85):
        self.belief_system = BeliefSystem(decay_rate=decay_rate)

    def reset_belief(self):
        """Resets persistent belief state to neutral baseline."""
        self.belief_system.reset()

    def evaluate(self, matrix: dict, active_trade: Optional[dict] = None) -> TradeIntent:
        """
        Evaluates the multi-screen sensory matrix and outputs autonomous trading decisions.
        """
        price = float(matrix.get("latest_price", 0.0))
        if price <= 0:
            return TradeIntent(action="WAIT_IN_CASH", reason="Awaiting live price stream")

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
                    return TradeIntent(
                        action="BANK_PROFIT",
                        scenario=scenario,
                        gain_pct=gain_pct,
                        entry_price=price,
                        reason=f"TRAILING STOP HIT (+{gain_pct*100:.2f}% net). Locking in banked profit at ${price:,.2f}.",
                        telemetry={"scenario": scenario, "gain_pct": gain_pct},
                    )
                else:
                    return TradeIntent(
                        action="CUT_THESIS_INVALIDATED",
                        scenario=scenario,
                        gain_pct=gain_pct,
                        entry_price=price,
                        proposed_stop=trailing_stop,
                        reason=f"STOP TOUCHED: Price at ${price:,.2f} crossed floor ${trailing_stop:,.2f}. Requesting Risk Gate evaluation.",
                        telemetry={"scenario": scenario, "gain_pct": gain_pct},
                    )

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
                    return TradeIntent(
                        action="RIDE_UNCAPPED",
                        scenario=scenario,
                        gain_pct=gain_pct,
                        target_price=macro_ceiling,
                        proposed_stop=updated_trailing_stop,
                        reason=f"TARGET REACHED (+{gain_pct*100:.2f}%), but Balloon opening outward into macro space (+{macro_runway:.2f}%). Trailing stop at ${updated_trailing_stop:,.2f}.",
                        telemetry={"scenario": scenario, "gain_pct": gain_pct, "macro_ceiling": macro_ceiling, "trailing_stop": updated_trailing_stop},
                    )
                else:
                    return TradeIntent(
                        action="BANK_PROFIT",
                        scenario=scenario,
                        gain_pct=gain_pct,
                        entry_price=price,
                        reason=f"TARGET HIT (+{gain_pct*100:.2f}%). Resistance capping momentum. Securing profit in wallet.",
                        telemetry={"scenario": scenario, "gain_pct": gain_pct},
                    )

            # 1.4 SCALE-IN LOT 2 ON CONFIRMED STRUCTURAL ABSORPTION DISCOUNT
            dist_to_support = abs(price - nearest_support)
            is_at_support_zone = (dist_to_support <= (0.75 * atr)) and (price < entry)
            if not tranche_2 and is_at_support_zone and (tanh_imb > 0.15 or absorption_idx > 15.0 or velocity_slowing):
                return TradeIntent(
                    action="SCALE_IN_LOT_2",
                    scenario=scenario,
                    entry_price=price,
                    reason=f"STRUCTURAL DISCOUNT ABSORPTION: Pullback to support (${nearest_support:,.2f}) absorbed by resting bids. Proposing Lot 2 add.",
                    telemetry={"scenario": scenario, "gain_pct": gain_pct},
                )

            # 1.5 NOISE-IMMUNE HOLD
            return TradeIntent(
                action="HOLD_POSITION",
                scenario=scenario,
                gain_pct=gain_pct,
                proposed_stop=updated_trailing_stop,
                reason=f"HOLDING {scenario}: Toward target ${target_price:,.2f}. Current PnL: {gain_pct*100:+.2f}%. Trailing Stop: ${updated_trailing_stop:,.2f}.",
                telemetry={"scenario": scenario, "gain_pct": gain_pct, "trailing_stop": updated_trailing_stop},
            )

        # ==================================================================
        # STATE 2: IN CASH (EXPLICIT BELIEF SYSTEM & ADAPTIVE EV MIND)
        # ==================================================================
        f_vec = matrix.get("feature_vector", {})
        trend_strength = float(f_vec.get("trend_strength", 0.0))
        entropy = float(f_vec.get("entropy", 0.5))
        vol_regime = float(f_vec.get("vol_regime", 1.0))
        liquidity = float(f_vec.get("liquidity", 10.0))

        # 2.1 CONTINUOUS MATHEMATICAL EDGE & URGENCY (Spec Section 2.3)
        trend_term = float(np.tanh(400.0 * trend_strength))
        imb_term = float(tanh_imb)
        abs_term = float(min(absorption_idx / 20.0, 1.0))
        flow_term = 0.5 if (cvd > 0 and trade_vel > 5.0) else (-0.3 if cvd < 0 else 0.0)

        raw_edge = (0.35 * trend_term) + (0.25 * imb_term) + (0.20 * abs_term) + (0.20 * flow_term) - (0.15 * entropy)
        edge = float(np.clip(raw_edge, -1.0, 1.0))
        instant_conf = float(max(0.0, abs(edge) / (1.0 + entropy)))
        urgency = float(instant_conf * max(trend_term, 0.0))

        # 2.2 UPDATE EXPLICIT BELIEF SYSTEM (Component 5) & ADAPTIVE HURDLES (Component 2)
        belief = self.belief_system.update(
            raw_edge=edge,
            instant_urgency=urgency,
            entropy=entropy,
            vol_regime=vol_regime,
            is_balloon_expanding=is_balloon_expanding,
            is_slow_market=is_slow_market,
            absorption_idx=absorption_idx,
        )

        effective_edge = belief.directional_bias
        effective_conf = max(belief.conviction, instant_conf * 0.70)
        effective_urgency = float(effective_conf * max(trend_term, 0.0))
        adaptive_runway = belief.adaptive_runway_hurdle
        adaptive_conf = belief.adaptive_conf_hurdle

        # 2.3 NET EXPECTED VALUE FORMULATION (Spec Section 11.2)
        dist_to_struct_res = max(nearest_resistance - price, 0.0)
        projected_move = max(dist_to_struct_res, 1.2 * atr)
        projected_gross_pct = max((projected_move / price) * 100.0, immediate_runway) if price > 0 else 0.0
        slippage_est_pct = 0.02
        net_ev_pct = projected_gross_pct - (OKX_ROUNDTRIP_FEE_PCT * 100.0) - slippage_est_pct

        intent_telemetry = {
            "edge": round(effective_edge, 3),
            "raw_edge": round(edge, 3),
            "confidence": round(effective_conf, 3),
            "urgency": round(effective_urgency, 3),
            "entropy": round(entropy, 3),
            "entropy_ema": round(belief.entropy_ema, 3),
            "trend_strength": round(trend_strength, 5),
            "net_ev_pct": round(net_ev_pct, 3),
            "immediate_runway": immediate_runway,
            "macro_runway": macro_runway,
            "adaptive_runway_hurdle": adaptive_runway,
            "adaptive_conf_hurdle": adaptive_conf,
            "belief_regime": belief.regime_belief,
            "belief_persistence": belief.persistence_ticks,
            "support": nearest_support,
            "resistance": nearest_resistance,
            "macro_ceiling": macro_ceiling,
        }

        # 2.4 FEE & ADAPTIVE HURDLE DEFENSE: Reject entries when room cannot clear dynamic hurdle
        if immediate_runway < adaptive_runway and not (is_balloon_expanding and macro_runway >= 0.80):
            return TradeIntent(
                action="WAIT_IN_CASH",
                expected_runway_pct=immediate_runway,
                confidence=effective_conf,
                reason=f"NO REAL GAIN ON TABLE: Immediate runway is only +{immediate_runway:.2f}% (requires >= {adaptive_runway:.2f}% adaptive hurdle under entropy {belief.entropy_ema:.2f}). Net EV={net_ev_pct:+.2f}%. Sitting in cash.",
                telemetry=intent_telemetry,
            )

        # 2.5 SLOW MARKET: Lines are horizontal and volume compressed -> Stay in cash
        if is_slow_market and immediate_runway < (adaptive_runway + 0.15):
            return TradeIntent(
                action="WAIT_IN_CASH",
                expected_runway_pct=immediate_runway,
                confidence=effective_conf,
                reason=f"SLOW MARKET: Bollinger lines horizontal and volume compressed (runway +{immediate_runway:.2f}%). Sitting 100% in cash.",
                telemetry=intent_telemetry,
            )

        # 2.6 SETUP A: BOTTOM / DIP TURN PREDICTION (BUYING LOW AT SUPPORT)
        dist_to_support = abs(price - nearest_support)
        is_at_support_floor = dist_to_support <= (0.85 * atr)
        is_absorption_confirmed = (
            (tanh_imb > 0.10 or absorption_idx > 12.0)
            and tanh_imb >= 0.0
            and immediate_runway >= adaptive_runway
        )

        if is_at_support_floor and is_absorption_confirmed:
            target = nearest_resistance
            return TradeIntent(
                action="ENTER_CORE_LOT_1",
                scenario="DIP_ABSORPTION_TURN",
                entry_price=price,
                target_price=target,
                proposed_stop=dynamic_invalidation,
                expected_runway_pct=immediate_runway,
                confidence=max(effective_conf, 0.75),
                reason=f"DIP TURN PREDICTED: Tested support (${nearest_support:,.2f}) with bid absorption (Ai={absorption_idx:.1f}, tanh_imb={tanh_imb:+.2f}). Belief={belief.regime_belief} (pers={belief.persistence_ticks}). Net EV={net_ev_pct:+.2f}%. Target: ${target:,.2f} (+{immediate_runway:.2f}%).",
                telemetry=intent_telemetry,
            )

        # 2.7 SETUP B: MOMENTUM IGNITION / BREAKOUT SURGE (THE MARKET FIRES UP)
        is_clearing_high = price >= (pooled_swing_high - 1.0)
        breakout_urgency_hurdle = 0.20 if is_balloon_expanding else 0.25
        is_breakout_surge = (
            (is_balloon_expanding and macro_runway >= 0.80)
            or (effective_urgency >= breakout_urgency_hurdle and (edge > 0.18 or effective_edge > 0.18) and macro_runway >= 0.85)
        )

        if (is_clearing_high or is_breakout_surge) and (tanh_imb >= 0.0 or trade_vel > 6.0):
            target = macro_ceiling
            effective_runway = max(macro_runway, projected_gross_pct)
            return TradeIntent(
                action="ENTER_CORE_LOT_1",
                scenario="MACRO_BALLOON_BREAKOUT",
                entry_price=price,
                target_price=target,
                proposed_stop=dynamic_invalidation,
                expected_runway_pct=effective_runway,
                confidence=max(effective_conf, 0.80),
                reason=f"MOMENTUM IGNITION: Market surge detected (Edge={effective_edge:+.2f}, Urgency={effective_urgency:.2f}). Belief={belief.regime_belief} (pers={belief.persistence_ticks}). Flowing into macro space (${macro_ceiling:,.2f}, +{effective_runway:.2f}%) with Net EV=+{net_ev_pct:.2f}%.",
                telemetry=intent_telemetry,
            )

        # Default fallback: Patiently scanning in cash
        return TradeIntent(
            action="WAIT_IN_CASH",
            expected_runway_pct=immediate_runway,
            confidence=effective_conf,
            reason=f"PATIENT SCANNING: Belief={belief.regime_belief} (Bias={effective_edge:+.2f}, Conf={effective_conf:.2f}, Pers={belief.persistence_ticks}). Hurdle={adaptive_runway:.2f}%. Nearest Support ${nearest_support:,.2f}, Structural Ceiling ${nearest_resistance:,.2f} (+{immediate_runway:.2f}%).",
            telemetry=intent_telemetry,
        )
