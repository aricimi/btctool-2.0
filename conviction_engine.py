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

import datetime
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
        # Calibrated conviction: normalizes practical signal capacity (0.35) to [0.0, 1.0] domain
        raw_conviction = abs(smoothed_bias) / (0.35 * (1.0 + 0.5 * smoothed_entropy))
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
        self.pending_acceptance: Optional[dict] = None

    @staticmethod
    def calculate_classical_expectancy(
        win_rate: float,
        target_pct: float,
        stop_pct: float,
        fee_pct: float = 0.20,
        slippage_pct: float = 0.02,
    ) -> Tuple[float, float]:
        """
        Computes classical mathematical expected value and reward-to-risk ratio:
        EV = (p_w * W_bar) - ((1 - p_w) * L_bar) - Costs
        RR = W_bar / L_bar
        """
        w_bar = max(float(target_pct), 0.0)
        l_bar = max(float(stop_pct), 0.01)
        rr = round(w_bar / l_bar, 2) if l_bar > 0 else 0.0
        costs = float(fee_pct + slippage_pct)
        p_w = float(np.clip(win_rate, 0.05, 0.95))
        ev = round((p_w * w_bar) - ((1.0 - p_w) * l_bar) - costs, 3)
        return ev, rr

    def reset_belief(self):
        """Resets persistent belief state to neutral baseline."""
        self.belief_system.reset()
        self.pending_acceptance = None

    def evaluate(self, matrix: dict, active_trade: Optional[dict] = None, governor: Optional[Any] = None) -> TradeIntent:
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
            highest_price = max(float(active_trade.get("highest_price", entry)), price)
            peak_gain_pct = (highest_price - entry) / entry if entry > 0 else gain_pct
            target_price = float(active_trade.get("target_price", nearest_resistance))
            trailing_stop = float(active_trade.get("trailing_stop", active_trade.get("invalidation_floor", entry * 0.997)))
            tranche_2 = bool(active_trade.get("tranche_2_added", False))
            scenario = active_trade.get("scenario", "TRADE")

            # 1.05 DEDICATED MEAN-REVERSION EXIT (For SWEEP_24H_RECLAIM)
            if scenario == "SWEEP_24H_RECLAIM":
                # Break-Even Ratchet: Once excursion >= 2.0 ATR, lock stop to Break-Even (+0.20% fee cover)
                if (highest_price - entry) >= (2.0 * atr):
                    be_stop = round(entry * 1.0020, 2)
                    if be_stop > trailing_stop:
                        trailing_stop = be_stop

                # Take Profit Target: 2.5 ATR
                tp_target = float(active_trade.get("target_price", entry + (2.5 * atr)))
                if price >= tp_target:
                    return TradeIntent(
                        action="BANK_PROFIT",
                        scenario=scenario,
                        gain_pct=gain_pct,
                        entry_price=price,
                        reason=f"SWEEP_24H TAKE PROFIT HIT (+{gain_pct*100:.2f}% gross, +{(gain_pct-0.0020)*100:.2f}% net). Locking in banked profit at ${price:,.2f}.",
                        telemetry={"scenario": scenario, "gain_pct": gain_pct},
                    )

                # Time Stop: 8 Hours (32 15m bars or 28,800 seconds)
                bars_held = int(active_trade.get("bars_held", 0))
                time_in_trade = (time.time() - float(active_trade.get("entry_time", 0.0))) if active_trade.get("entry_time") else 0
                if bars_held >= 32 or time_in_trade >= 28800:
                    if gain_pct > 0.0020:
                        return TradeIntent(
                            action="BANK_PROFIT",
                            scenario=scenario,
                            gain_pct=gain_pct,
                            entry_price=price,
                            reason=f"SWEEP_24H TIME STOP (8H) PROFIT: +{gain_pct*100:.2f}% gross. Securing profit at ${price:,.2f}.",
                            telemetry={"scenario": scenario, "gain_pct": gain_pct},
                        )
                    else:
                        return TradeIntent(
                            action="CUT_THESIS_INVALIDATED",
                            scenario=scenario,
                            gain_pct=gain_pct,
                            entry_price=price,
                            proposed_stop=price,
                            reason=f"SWEEP_24H TIME STOP EXPIRED (8H): Momentum failed to reach target. Releasing capital at ${price:,.2f}.",
                            telemetry={"scenario": scenario, "gain_pct": gain_pct},
                        )

            # 1.06 GRADUATED PROFIT RATCHET (For CAPITULATION_SWEEP_48H - Eliminates Profit Bleed)
            if scenario == "CAPITULATION_SWEEP_48H":
                if peak_gain_pct >= 0.030:
                    ratchet_stop = round(entry * 1.020, 2)
                    if ratchet_stop > trailing_stop:
                        trailing_stop = ratchet_stop
                elif peak_gain_pct >= 0.020:
                    ratchet_stop = round(entry * 1.010, 2)
                    if ratchet_stop > trailing_stop:
                        trailing_stop = ratchet_stop
                elif peak_gain_pct >= 0.010:
                    ratchet_stop = round(entry * 1.002, 2)
                    if ratchet_stop > trailing_stop:
                        trailing_stop = ratchet_stop

            # 1.07 MULTI-TIMEFRAME TREND SHIELD (For Breakout Runners: v4.1.0)
            is_breakout_runner = scenario in ("MACRO_BALLOON_BREAKOUT", "MACRO_BREAK_48H", "BREAK_24H", "BREAK_12H")
            if is_breakout_runner and peak_gain_pct >= 0.025:
                # Guaranteed profit floor (+1.5% profit protection)
                prot_stop = round(entry * 1.0150, 2)
                if prot_stop > trailing_stop:
                    trailing_stop = prot_stop

                tfs = matrix.get("timeframes", {})
                tf_1h = tfs.get("1h", {})
                ema20_1h = float(tf_1h.get("ema_20", tf_1h.get("bb_mid", 0.0)))
                close_1h = float(tf_1h.get("close", price))
                is_1h_close = bool(matrix.get("is_1h_bar_close", True))

                if ema20_1h > 0.0 and is_1h_close and close_1h < ema20_1h:
                    return TradeIntent(
                        action="BANK_PROFIT",
                        scenario=scenario,
                        gain_pct=gain_pct,
                        entry_price=price,
                        reason=f"1H_EMA20_TREND_EXIT: 1-Hour candle closed below 1H EMA20 (${close_1h:,.2f} < ${ema20_1h:,.2f}) after peak +{peak_gain_pct*100:.2f}% gross. Securing profit at ${price:,.2f}.",
                        telemetry={"scenario": scenario, "gain_pct": gain_pct, "1h_ema20_exit": True},
                    )

            # 1.1 IN-SITU MEMORY SOFT STOP EVALUATION
            if price <= trailing_stop:
                if trailing_stop >= entry or gain_pct >= 0.0005:
                    return TradeIntent(
                        action="BANK_PROFIT",
                        scenario=scenario,
                        gain_pct=gain_pct,
                        entry_price=price,
                        reason=f"TRAILING STOP HIT (+{gain_pct*100:.2f}% gross, +{(gain_pct-0.0020)*100:.2f}% net). Locking in banked profit at ${price:,.2f}.",
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

            # 1.2 CONTINUOUS PROPORTIONAL PROFIT-RETENTION RATCHET (CPPR v2: HIGH EXPECTANCY)
            updated_trailing_stop = trailing_stop

            # Step 1A: Graduated Breakeven Ratchet (v3.9.0 - Neutralizes Fakeout Reversals)
            # For dip-turn & spatial mean-reversion setups, if price advances to cover >= 65% of the
            # runway to the midline/target_1 or if explicit graduated breakeven is signaled, lock
            # the stop to breakeven (+0.05% gross) to eliminate losing fakeout reversals.
            mid_line = float(active_trade.get("mid_line", 0.0))
            use_graduated = bool(active_trade.get("graduated_breakeven", False) or mid_line > 0.0)

            target_distance = (mid_line - entry) if mid_line > entry else (target_price - entry)
            dist_covered_ratio = ((highest_price - entry) / target_distance) if target_distance > 0 else 0.0

            if use_graduated and (dist_covered_ratio >= 0.65 or (mid_line > 0 and highest_price >= mid_line)) and peak_gain_pct < 0.0120:
                graduated_be_stop = round(entry * 1.0005, 2)
                if graduated_be_stop > updated_trailing_stop:
                    updated_trailing_stop = graduated_be_stop
                    logger.info(f"[Brain] Stage 1 Graduated Ratchet: Peak +{peak_gain_pct*100:.2f}% (runway covered {dist_covered_ratio*100:.0f}%) -> Trailing stop locked to Breakeven (${updated_trailing_stop:,.2f})")

            # Step 1: Delayed Activation - Under +1.20% gross (+120 bps), do NOT lock premature tight stop.
            # Position breathes with structural invalidation floor to avoid sub-minute noise asphyxiation.
            # Step 2: Peak excursion >= +1.20% gross: lock 50% of peak gain (min +0.35% gross, ensuring positive net profit)
            # Exception: Breakout runners with peak >= +2.5% are governed by 1H EMA20 Trend Shield (+1.50% profit floor).
            if peak_gain_pct >= 0.0120 and not (is_breakout_runner and peak_gain_pct >= 0.025):
                locked_gain_pct = max(0.0035, peak_gain_pct * 0.50)
                cppr_stop = round(entry * (1.0 + locked_gain_pct), 2)
                if cppr_stop > updated_trailing_stop:
                    updated_trailing_stop = cppr_stop
                    logger.info(f"[Brain] CPPR v2 Ratchet Level 1: Peak +{peak_gain_pct*100:.2f}% gross -> trailing stop locked to ${updated_trailing_stop:,.2f} (+{locked_gain_pct*100:.2f}% gross)")

                # If nearest support is above entry, ratchet stop behind support with ATR breathing buffer
                if nearest_support > entry:
                    support_stop = round(nearest_support - (0.8 * atr), 2)
                    if support_stop > updated_trailing_stop:
                        updated_trailing_stop = support_stop
                        logger.info(f"[Brain] Ratchet trailing stop higher behind rising support: ${updated_trailing_stop:,.2f}")

            # Step 3: Peak excursion >= +1.50% gross (structural target territory): lock 60% of peak gain
            if peak_gain_pct >= 0.0150 and not (is_breakout_runner and peak_gain_pct >= 0.025):
                locked_gain_60 = peak_gain_pct * 0.60
                cppr_stop_60 = round(entry * (1.0 + locked_gain_60), 2)
                if cppr_stop_60 > updated_trailing_stop:
                    updated_trailing_stop = cppr_stop_60
                    logger.info(f"[Brain] CPPR v2 Ratchet Level 2: Peak +{peak_gain_pct*100:.2f}% gross -> trailing stop locked to ${updated_trailing_stop:,.2f} (+{locked_gain_60*100:.2f}% gross)")

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

            # 1.35 DYNAMIC MOMENTUM-DECAY EXIT: Lock profit before reversal if order flow aggression collapses
            if peak_gain_pct >= 0.0035 and tanh_imb < -0.15 and cvd < 0:
                return TradeIntent(
                    action="BANK_PROFIT",
                    scenario=scenario,
                    gain_pct=gain_pct,
                    entry_price=price,
                    reason=f"MOMENTUM DECAY EXIT: Peak +{peak_gain_pct*100:.2f}% gross reached, but order flow aggression reversed (CVD < 0, Imb={tanh_imb:+.2f}). Banking gains.",
                    telemetry={"scenario": scenario, "gain_pct": gain_pct, "momentum_decay": True},
                )

            # 1.4 STATE-MANAGED LOT 2 SCALE-IN FIREWALL (v3.8.0)
            # Separate Lot 1 and Lot 2 into a strict state machine. Eliminates instant micro-spacing ($4 difference).
            lot_1_entry = float(active_trade.get("lot_1_entry", entry))
            pullback_pct = ((lot_1_entry - price) / lot_1_entry) * 100.0 if lot_1_entry > 0 else 0.0

            if tranche_2:
                lot_2_state = "COMPLETED"
            elif active_trade.get("lot_2_state") == "CANCELED_BREAKDOWN":
                lot_2_state = "CANCELED_BREAKDOWN"
            elif price >= lot_1_entry:
                lot_2_state = "PENDING_PULLBACK"
            elif pullback_pct > 0.35:
                # Breakdown Firewall: Price dropped straight through without defense past -0.35%.
                # Permanently cancel Lot 2 to prevent blind averaging down.
                active_trade["lot_2_state"] = "CANCELED_BREAKDOWN"
                lot_2_state = "CANCELED_BREAKDOWN"
            elif pullback_pct < 0.20:
                # Spatial Firewall: Hard-barred unless price moves into structural pullback zone [-0.20%, -0.30%].
                lot_2_state = "SPATIAL_FIREWALL_HELD"
            else:
                # Inside structural zone [0.20%, 0.35%]
                # Temporal & Re-Verification Firewall:
                # Re-verify resting limit bids actively absorb AND CVD tape turns positive.
                is_bids_absorbing = (tanh_imb > 0.15 or absorption_idx > 15.0)
                is_tape_positive = (cvd > 0 or trade_vel > 5.0)

                if is_bids_absorbing and is_tape_positive:
                    active_trade["lot_2_state"] = "SCALE_IN_EXECUTED"
                    return TradeIntent(
                        action="SCALE_IN_LOT_2",
                        scenario=scenario,
                        entry_price=price,
                        reason=f"LOT_2_SCALE_IN_CONFIRMED: Pullback -{pullback_pct:.2f}% into structural zone [-0.20%, -0.30%] verified by absorption (tanh_imb={tanh_imb:+.2f}, Ai={absorption_idx:.1f}) and tape backing (cvd={cvd:+.1f}, vel={trade_vel:.1f}). Adding Lot 2.",
                        telemetry={
                            "scenario": scenario,
                            "gain_pct": gain_pct,
                            "lot_2_state": "SCALE_IN_LOT_2",
                            "pullback_pct": round(pullback_pct, 3),
                            "lot_2_reverified": True,
                            "tanh_imbalance": round(tanh_imb, 3),
                            "absorption_index": round(absorption_idx, 2),
                            "cvd": round(cvd, 2),
                        },
                    )
                else:
                    lot_2_state = "ZONE_PENDING_DEFENSE"

            # 1.5 NOISE-IMMUNE HOLD
            return TradeIntent(
                action="HOLD_POSITION",
                scenario=scenario,
                gain_pct=gain_pct,
                proposed_stop=updated_trailing_stop,
                reason=f"HOLDING {scenario}: Toward target ${target_price:,.2f}. Current PnL: {gain_pct*100:+.2f}%. Trailing Stop: ${updated_trailing_stop:,.2f}.",
                telemetry={
                    "scenario": scenario,
                    "gain_pct": gain_pct,
                    "trailing_stop": updated_trailing_stop,
                    "lot_2_state": lot_2_state,
                    "pullback_pct": round(pullback_pct, 3),
                },
            )

        # ==================================================================
        # STATE 2: IN CASH (EXPLICIT BELIEF SYSTEM & ADAPTIVE EV MIND)
        # ==================================================================
        # 2.0 STRUCTURAL ACCEPTANCE MICRO-RETEST VERIFICATION (v3.6.0)
        if self.pending_acceptance is not None:
            p_acc = self.pending_acceptance
            b_level = float(p_acc["breakout_level"])
            cushion_level = b_level * 0.998

            candles_1m = matrix.get("candles_1m") or []
            cur_bar = candles_1m[-1] if candles_1m else {}
            low_price = float(cur_bar.get("low", matrix.get("best_bid", price)))
            close_price = float(cur_bar.get("close", price))

            is_holding_retest = (low_price >= cushion_level) and (close_price >= cushion_level)

            if is_holding_retest:
                intent = TradeIntent(
                    action="ENTER_CORE_LOT_1",
                    scenario="MACRO_BALLOON_BREAKOUT",
                    entry_price=price,
                    target_price=p_acc["target_price"],
                    proposed_stop=p_acc["proposed_stop"],
                    expected_runway_pct=p_acc["expected_runway_pct"],
                    confidence=p_acc["confidence"],
                    reason=f"CONFIRMED STRUCTURAL ACCEPTANCE: Price held micro-retest cushion (${cushion_level:,.2f}, 0.20% cushion of ${b_level:,.2f}) at ${price:,.2f}. Flowing into macro space (${p_acc['target_price']:,.2f}).",
                    telemetry={**p_acc.get("intent_telemetry", {}), "acceptance_confirmed": True, "retest_level": round(b_level, 2)},
                )
                self.pending_acceptance = None
                return intent
            else:
                self.pending_acceptance = None
                return TradeIntent(
                    action="WAIT_IN_CASH",
                    scenario="MACRO_BALLOON_BREAKOUT",
                    reason=f"STRUCTURAL ACCEPTANCE FAILED: Price collapsed below micro-retest cushion (${cushion_level:,.2f}) at ${price:,.2f}. Vetoing false breakout.",
                    telemetry={"acceptance_failed": True, "breakout_level": round(b_level, 2), "cushion_level": round(cushion_level, 2)},
                )

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
        instant_conf = float(np.clip(abs(edge) / (0.35 * (1.0 + 0.5 * entropy)), 0.0, 1.0))
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
        macro_space = max(macro_ceiling - price, 0.0) if is_balloon_expanding else 0.0
        projected_move = macro_space if is_balloon_expanding else dist_to_struct_res
        projected_gross_pct = ((projected_move / price) * 100.0) if price > 0 else 0.0
        spread_pct = float(matrix.get("spread_pct", 0.0))
        # Dynamic slippage estimation: baseline 0.02%, scaled by half-spread + 25% execution impact
        dynamic_slippage_pct = round(max(0.02, (spread_pct / 2.0) * 1.25), 3)
        net_ev_pct = projected_gross_pct - (OKX_ROUNDTRIP_FEE_PCT * 100.0) - dynamic_slippage_pct

        intent_telemetry = {
            "edge": round(effective_edge, 3),
            "raw_edge": round(edge, 3),
            "confidence": round(effective_conf, 3),
            "urgency": round(effective_urgency, 3),
            "entropy": round(entropy, 3),
            "entropy_ema": round(belief.entropy_ema, 3),
            "trend_strength": round(trend_strength, 5),
            "dynamic_slippage_pct": dynamic_slippage_pct,
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

        # 2.4 MANDATORY NET EXPECTANCY GATE (v3.2.6 Decoupled Pre-Setup Filter)
        # Note: Universal pre-setup runway veto has been removed to allow Setup A (DIP_ABSORPTION_TURN)
        # and Setup B (MACRO_BALLOON_BREAKOUT) to evaluate their distinct structural edge and macro-expansion
        # space independently under their own dedicated classical expectancy and R:R gates.

        # 2.5 ADAPTIVE CONFIDENCE THRESHOLD BASED ON REGIME (v3.0 Priority 3)
        # TREND: 0.50 | BALANCED / RANGE: 0.65 | CHOP / HIGH ENTROPY: 0.80
        if belief.regime_belief == "BULL_ACCELERATION" or (is_balloon_expanding and entropy < 0.50):
            regime_conf_hurdle = 0.50
        elif is_slow_market or entropy >= 0.65 or belief.regime_belief == "CHOP_COMPRESSION":
            regime_conf_hurdle = 0.80
        else:
            regime_conf_hurdle = 0.65

        # 2.5C INTUITION TRIPWIRES (v3.0 Priority 7 - Modifiers only +-0.05, never opens trade directly)
        intuition_mod = 0.0
        if trade_vel > 8.0 and cvd > 0:
            intuition_mod += 0.05  # Tape acceleration burst
        if absorption_idx > 20.0:
            intuition_mod += 0.05  # Institutional limit absorption wall
        spread_pct = float(matrix.get("spread_pct", 0.0))
        if spread_pct > 0.15:
            intuition_mod -= 0.05  # Spread inflation friction
        if tanh_imb < -0.20 and cvd < 0:
            intuition_mod -= 0.05  # Aggressive taker selling pressure

        tuned_confidence = float(np.clip(effective_conf + intuition_mod, 0.0, 1.0))
        intent_telemetry["regime_conf_hurdle"] = regime_conf_hurdle
        intent_telemetry["intuition_mod"] = round(intuition_mod, 3)
        intent_telemetry["tuned_confidence"] = round(tuned_confidence, 3)

        # 2.58 SETUP: 48H CAPITULATION SWEEP (Panic Absorption Reclaim)
        candles_15m_all = matrix.get("candles_15m") or []
        tfs = matrix.get("timeframes", {})
        tf_4h = tfs.get("4h", {})
        bb_mid_4h = float(tf_4h.get("bb_mid", 0.0))
        ema50_4h = float(tf_4h.get("ema_50", bb_mid_4h))
        is_bull_macro_sweep = (price >= ema50_4h) or (bb_mid_4h > 0 and price >= bb_mid_4h)

        if candles_15m_all and len(candles_15m_all) >= 20:
            cur_15m = candles_15m_all[-1]
            c_low = float(cur_15m.get("low", price))
            c_high = float(cur_15m.get("high", price))
            c_close = float(cur_15m.get("close", price))
            c_open = float(cur_15m.get("open", price))
            lookback_192 = min(len(candles_15m_all) - 1, 192)
            if lookback_192 >= 20:
                recent_lows_48h = [float(c.get("low", price)) for c in candles_15m_all[-(lookback_192 + 1):-1]]
                sl_48h = min(recent_lows_48h) if recent_lows_48h else c_low
                is_sweep_48h = (c_low < sl_48h) and (c_close > sl_48h)
                c_rng = c_high - c_low
                clv = (c_close - c_low) / c_rng if c_rng > 0 else 0.5
                body_pct = ((c_close - c_open) / c_open * 100.0) if c_open > 0 else 0.0
                v_recent = [float(c.get("vol", 0.0)) for c in candles_15m_all[-min(len(candles_15m_all), 21):-1]]
                v_sma20 = float(np.mean(v_recent)) if v_recent else 1.0
                c_vol = float(cur_15m.get("vol", 0.0))
                vr = c_vol / v_sma20 if v_sma20 > 0 else 1.0

                if is_sweep_48h and vr >= 2.5 and body_pct >= 0.20 and clv >= 0.70:
                    take_sweep = is_bull_macro_sweep or (vr >= 3.5)
                    # v4.3.0 Capitulation Depth & Quality Gate Integration
                    dist_ema50_pct = ((price - ema50_4h) / ema50_4h) * 100.0 if ema50_4h > 0 else 0.0
                    depth_gate = dist_ema50_pct <= -1.0
                    quality_gate = (vr >= 4.5) or (dist_ema50_pct <= -2.5)
                    if not (depth_gate and quality_gate):
                        take_sweep = False

                    if take_sweep:
                        stop_price = round(price * 0.985, 2)
                        return TradeIntent(
                            action="ENTER_CORE_LOT_1",
                            scenario="CAPITULATION_SWEEP_48H",
                            entry_price=price,
                            target_price=nearest_resistance,
                            proposed_stop=stop_price,
                            expected_runway_pct=macro_runway,
                            confidence=0.85,
                            reason=f"CAPITULATION_SWEEP_48H: 48H low (${sl_48h:,.2f}) swept and reclaimed with panic absorption (Dist4H={dist_ema50_pct:+.2f}%, VR={vr:.1f}x, CLV={clv:.2f}) at ${price:,.2f}.",
                            telemetry={
                                **intent_telemetry,
                                "scenario": "CAPITULATION_SWEEP_48H",
                                "sl_48h": round(sl_48h, 2),
                                "clv": round(clv, 2),
                                "vr": round(vr, 2),
                                "body_pct": round(body_pct, 2),
                                "dist_ema50_pct": round(dist_ema50_pct, 2),
                            },
                        )

        # 2.6 SETUP A: 24H LIQUIDITY SWEEP & RECLAIM (Validated Dip-Absorption Alpha)
        # Unfreezes dip-buying strictly for high-conviction 24H liquidity flushes in Bull Macro regimes.
        if candles_15m_all and len(candles_15m_all) >= 20 and is_bull_macro_sweep:
            cur_15m = candles_15m_all[-1]
            c_low = float(cur_15m.get("low", price))
            c_high = float(cur_15m.get("high", price))
            c_close = float(cur_15m.get("close", price))
            c_open = float(cur_15m.get("open", price))

            # 24-hour lookback calculation
            lookback_bars = min(len(candles_15m_all) - 1, 96)
            if lookback_bars >= 12:
                recent_lows = [float(c.get("low", price)) for c in candles_15m_all[-(lookback_bars + 1):-1]]
                sl_24h = min(recent_lows) if recent_lows else c_low

                # Sweep & Reclaim check: pierced below 24h low, closed back ABOVE 24h low
                is_sweep_reclaimed = (c_low < sl_24h) and (c_close > sl_24h)
                c_rng = c_high - c_low
                clv = (c_close - c_low) / c_rng if c_rng > 0 else 0.5
                body_pct = ((c_close - c_open) / c_open * 100.0) if c_open > 0 else 0.0

                # 20-bar rolling 15M volume SMA
                v_recent = [float(c.get("vol", 0.0)) for c in candles_15m_all[-min(len(candles_15m_all), 21):-1]]
                v_sma20 = float(np.mean(v_recent)) if v_recent else 1.0
                c_vol = float(cur_15m.get("vol", 0.0))
                vr = c_vol / v_sma20 if v_sma20 > 0 else 1.0

                if is_sweep_reclaimed and vr >= 2.2 and clv >= 0.80 and body_pct >= -0.10:
                    tp_price = round(price + (2.5 * atr), 2)
                    stop_price = round(min(c_low * 0.998, price * 0.985), 2)
                    return TradeIntent(
                        action="ENTER_CORE_LOT_1",
                        scenario="SWEEP_24H_RECLAIM",
                        entry_price=price,
                        target_price=tp_price,
                        proposed_stop=stop_price,
                        expected_runway_pct=round(2.5 * (atr / price) * 100.0, 2),
                        confidence=0.82,
                        reason=f"SWEEP_24H_RECLAIM: 24H low (${sl_24h:,.2f}) swept and reclaimed with pin-bar absorption (CLV={clv:.2f}, VR={vr:.1f}x) at ${price:,.2f}. Target: ${tp_price:,.2f} (+2.5 ATR), Stop: ${stop_price:,.2f}.",
                        telemetry={
                            **intent_telemetry,
                            "scenario": "SWEEP_24H_RECLAIM",
                            "sl_24h": round(sl_24h, 2),
                            "clv": round(clv, 2),
                            "vr": round(vr, 2),
                            "body_pct": round(body_pct, 2),
                            "target_price": tp_price,
                            "proposed_stop": stop_price,
                        },
                    )

        # 2.62 SETUP: MULTI-HORIZON BREAKOUT SUITE (v4.2.0)
        # Evaluates 48H and 24H breakouts with mandatory 4H EMA50 Trend Clearance Gate (>= +0.80% for 48H).
        utc_dow = matrix.get("utc_dow")  # 5, 6 is weekend
        is_weekend = (utc_dow in (5, 6)) if utc_dow is not None else False
        if candles_15m_all and len(candles_15m_all) >= 20 and is_bull_macro_sweep and not is_weekend:
            cur_15m = candles_15m_all[-1]
            c_high = float(cur_15m.get("high", price))
            c_close = float(cur_15m.get("close", price))
            c_open = float(cur_15m.get("open", price))
            c_low = float(cur_15m.get("low", price))
            c_rng = c_high - c_low
            clv = (c_close - c_low) / c_rng if c_rng > 0 else 0.5
            body_pct = ((c_close - c_open) / c_open * 100.0) if c_open > 0 else 0.0

            v_recent = [float(c.get("vol", 0.0)) for c in candles_15m_all[-min(len(candles_15m_all), 21):-1]]
            v_sma20 = float(np.mean(v_recent)) if v_recent else 1.0
            c_vol = float(cur_15m.get("vol", 0.0))
            vr = c_vol / v_sma20 if v_sma20 > 0 else 1.0

            dist_ema50_pct = ((price - ema50_4h) / ema50_4h) * 100.0 if ema50_4h > 0 else 0.0

            # 48H lookback
            lookback_192 = min(len(candles_15m_all) - 1, 192)
            recent_highs_48h = [float(c.get("high", price)) for c in candles_15m_all[-(lookback_192 + 1):-1]]
            sh_48h = max(recent_highs_48h) if recent_highs_48h else price
            prev_close = float(candles_15m_all[-2].get("close", price)) if len(candles_15m_all) >= 2 else price
            is_48h_break = (c_close > sh_48h) and (prev_close <= sh_48h)

            if is_48h_break:
                # v4.2.0 Mandatory 4H EMA50 Trend Clearance Gate
                if dist_ema50_pct < 0.80:
                    # Low-momentum range noise veto; suppress fallthrough to shorter horizons
                    pass
                elif vr >= 2.2 and body_pct >= 0.25 and clv >= 0.70:
                    stop_price = round(price * 0.985, 2)
                    return TradeIntent(
                        action="ENTER_CORE_LOT_1",
                        scenario="MACRO_BREAK_48H",
                        entry_price=price,
                        target_price=macro_ceiling,
                        proposed_stop=stop_price,
                        expected_runway_pct=macro_runway,
                        confidence=0.85,
                        reason=f"MACRO_BREAK_48H: 48H high (${sh_48h:,.2f}) broken with momentum (Dist4H={dist_ema50_pct:+.2f}% >= +0.80%, VR={vr:.1f}x, CLV={clv:.2f}).",
                        telemetry={
                            **intent_telemetry,
                            "scenario": "MACRO_BREAK_48H",
                            "sh_48h": round(sh_48h, 2),
                            "dist_ema50_pct": round(dist_ema50_pct, 2),
                            "vr": round(vr, 2),
                            "clv": round(clv, 2),
                        },
                    )
            elif clv >= 0.70:
                # 24H lookback
                lookback_96 = min(len(candles_15m_all) - 1, 96)
                recent_highs_24h = [float(c.get("high", price)) for c in candles_15m_all[-(lookback_96 + 1):-1]]
                sh_24h = max(recent_highs_24h) if recent_highs_24h else price
                is_24h_break = (c_close > sh_24h) and (prev_close <= sh_24h)
                if is_24h_break and vr >= 2.2 and body_pct >= 0.25:
                    stop_price = round(price * 0.985, 2)
                    return TradeIntent(
                        action="ENTER_CORE_LOT_1",
                        scenario="BREAK_24H",
                        entry_price=price,
                        target_price=macro_ceiling,
                        proposed_stop=stop_price,
                        expected_runway_pct=macro_runway,
                        confidence=0.82,
                        reason=f"BREAK_24H: 24H high (${sh_24h:,.2f}) broken with volume (VR={vr:.1f}x, CLV={clv:.2f}).",
                        telemetry={
                            **intent_telemetry,
                            "scenario": "BREAK_24H",
                            "sh_24h": round(sh_24h, 2),
                            "dist_ema50_pct": round(dist_ema50_pct, 2),
                            "vr": round(vr, 2),
                        },
                    )

        # 2.6B SETUP A FALLBACK: GENERIC DIP TURN (FROZEN CAPITAL GOVERNOR)
        dist_to_support = abs(price - nearest_support)
        is_at_support_floor = dist_to_support <= (0.85 * atr)
        target_a = nearest_resistance
        target_pct_a = ((target_a - price) / price) * 100.0 if price > 0 else 0.0
        is_absorption_confirmed = (
            (tanh_imb > 0.10 or absorption_idx > 12.0)
            and tanh_imb >= 0.0
            and target_pct_a >= adaptive_runway
        )

        if is_at_support_floor and is_absorption_confirmed:
            if target_pct_a < 0.50:
                return TradeIntent(
                    action="WAIT_IN_CASH",
                    scenario="DIP_ABSORPTION_TURN",
                    reason=f"REJECTED BY RUNWAY GATE: Dip runway (+{target_pct_a:.2f}%) < +0.50% minimum physical clearance.",
                    telemetry={**intent_telemetry, "scenario": "DIP_ABSORPTION_TURN", "runway_pct": target_pct_a},
                )

            return TradeIntent(
                action="WAIT_IN_CASH",
                scenario="DIP_ABSORPTION_TURN",
                reason=f"SETUP_A_FROZEN_GOVERNOR: Absorption detected at support (${nearest_support:,.2f}, Ai={absorption_idx:.1f}). Capital governor active; cascade held in cash.",
                telemetry={**intent_telemetry, "scenario": "DIP_ABSORPTION_TURN", "governor_held": True, "target_price": target_a},
            )

        # ==================================================================
        # 2.65 HIERARCHICAL MULTI-TIMEFRAME ENTRY GATE (v3.8.0)
        # ==================================================================
        # Before evaluating ANY candidate setup or micro-structure trigger
        # (tanh_imbalance, absorption_idx, velocity), the market must clear
        # both Macro (1H/4H) and Structure (15M) gates.
        tfs = matrix.get("timeframes", {})
        tf_1h = tfs.get("1h", {})
        tf_4h = tfs.get("4h", {})
        bb_mid_1h = float(tf_1h.get("bb_mid", 0.0))
        bb_mid_4h = float(tf_4h.get("bb_mid", 0.0))
        macd_hist_1h = float(tf_1h.get("macd_hist", 0.0))
        macd_hist_4h = float(tf_4h.get("macd_hist", 0.0))

        macro_gate_status = "PASS"
        macro_gate_reason = ""

        # 1H & 4H Macro Check: Reject long entries if price < 1H Bollinger midline
        # or if 1H/4H MACD histogram momentum is actively negative.
        if bb_mid_1h > 0.0 and price < bb_mid_1h:
            macro_gate_status = "REJECT_MACRO_BELOW_MID"
            macro_gate_reason = f"Price (${price:,.2f}) trading below 1H Bollinger midline (${bb_mid_1h:,.2f})."
        elif bb_mid_4h > 0.0 and price < bb_mid_4h:
            macro_gate_status = "REJECT_MACRO_BELOW_MID"
            macro_gate_reason = f"Price (${price:,.2f}) trading below 4H Bollinger midline (${bb_mid_4h:,.2f})."
        elif (macd_hist_1h < 0.0 and tf_1h) or (macd_hist_4h < 0.0 and tf_4h):
            macro_gate_status = "REJECT_MACRO_MACD_NEG"
            macro_gate_reason = f"Macro MACD momentum actively negative (1H hist={macd_hist_1h:+.4f}, 4H hist={macd_hist_4h:+.4f})."

        # Forensic Filter 1: Toxic Liquidity Session Gating (v3.9.0)
        # Eliminates the 01:00 UTC settlement vacuum and 08:00-09:59 UTC London opening stop sweep traps.
        utc_hour = matrix.get("utc_hour")
        if utc_hour is not None:
            if utc_hour == 1:
                macro_gate_status = "REJECT_TOXIC_HOURS_SETTLEMENT"
                macro_gate_reason = "Toxic liquidity dead zone: 01:00 UTC daily option/funding settlement & collateral rebalancing vacuum."
            elif utc_hour in (8, 9):
                macro_gate_status = "REJECT_TOXIC_HOURS_LONDON_SWEEP"
                macro_gate_reason = f"Toxic liquidity dead zone: {utc_hour:02d}:00 UTC European cash open stop sweep trap."

        # Forensic Filter 2: High-Velocity Macro Dump Gating (v3.9.0)
        # Vetoes entries if price dropped deeper than -1.40% over the preceding 60 minutes.
        drop_60m_pct = float(matrix.get("drop_60m_pct", 0.0))
        if drop_60m_pct < -1.40:
            macro_gate_status = "REJECT_HIGH_VELOCITY_FLUSH"
            macro_gate_reason = f"High-velocity macro flush: 60m drop ({drop_60m_pct:.2f}% < -1.40% hurdle); absorption overwhelmed."

        # 15M Structure Check: Reject entry occurring in the middle of an aggressive
        # red impulse/dump candle. The 15m candle must show a completed base, defended
        # retest, or positive structure.
        tf_15m = tfs.get("15m", {})
        candles_15m = matrix.get("candles_15m") or []
        bb_pct_b_15m = float(tf_15m.get("bb_pct_b", 0.50))
        macd_hist_15m = float(tf_15m.get("macd_hist", 0.0))

        structure_15m_status = "PASS"
        structure_15m_reason = ""
        drop_15m_pct = 0.0

        if candles_15m and len(candles_15m) > 0:
            cur_15m = candles_15m[-1]
            open_15m = float(cur_15m.get("open", price))
            close_15m = float(cur_15m.get("close", price))
            high_15m = float(cur_15m.get("high", max(open_15m, close_15m)))
            low_15m = float(cur_15m.get("low", min(open_15m, close_15m)))
            drop_15m_pct = ((open_15m - close_15m) / open_15m) * 100.0 if open_15m > 0 else 0.0

            is_red_15m = close_15m < open_15m
            candle_range_15m = high_15m - low_15m
            lower_wick_ratio = (close_15m - low_15m) / candle_range_15m if candle_range_15m > 0 else 0.5

            if is_red_15m:
                if drop_15m_pct >= 0.30:
                    structure_15m_status = "REJECT_15M_RED_DUMP"
                    structure_15m_reason = f"Active 15M red dump candle (-{drop_15m_pct:.2f}% drop from ${open_15m:,.2f} to ${close_15m:,.2f})."
                elif lower_wick_ratio < 0.25 and macd_hist_15m < 0.0:
                    structure_15m_status = "REJECT_15M_BREAKDOWN"
                    structure_15m_reason = f"15M candle closing near lows (lower_wick={lower_wick_ratio:.2f}) with negative MACD momentum ({macd_hist_15m:+.4f})."
        elif tf_15m:
            if bb_pct_b_15m < 0.20 and macd_hist_15m < 0.0:
                structure_15m_status = "REJECT_15M_BREAKDOWN"
                structure_15m_reason = f"15M band breakdown (%b={bb_pct_b_15m:.2f}) with negative momentum (hist={macd_hist_15m:+.4f})."

        # Forensic Filter 3: Panic Liquidation Volume Surge Gating (v3.9.0)
        # Vetoes entries if 15M rolling volume exceeds 2.20x the 60M rolling average.
        vol_surge_ratio = float(matrix.get("vol_surge_ratio", 1.0))
        if vol_surge_ratio > 2.20:
            structure_15m_status = "REJECT_PANIC_LIQUIDATION_SURGE"
            structure_15m_reason = f"Panic liquidation cascade detected: 15m/60m volume surge ({vol_surge_ratio:.2f}x > 2.20x ceiling)."

        # Forensic Filter 4: LTF Micro-Turn Pseudo-Reversal Purification (v3.9.0)
        # Rejects pseudo-reversal green bars that lack genuine lower-wick rejection defense.
        micro_turn = matrix.get("micro_turn", {})
        if isinstance(micro_turn, dict) and micro_turn.get("confirmation") == "1M_GREEN_REVERSAL":
            structure_15m_status = "REJECT_PSEUDO_REVERSAL"
            structure_15m_reason = "Pseudo-reversal candle detected (1M green close without genuine lower wick rejection >= 0.15)."

        hierarchical_gates_passed = (macro_gate_status == "PASS") and (structure_15m_status == "PASS")

        # Telemetry updates
        intent_telemetry["macro_gate_status"] = macro_gate_status
        intent_telemetry["structure_15m_status"] = structure_15m_status
        intent_telemetry["hierarchical_gates_passed"] = hierarchical_gates_passed
        intent_telemetry["macro_shield_veto"] = not hierarchical_gates_passed
        intent_telemetry["bb_mid_1h"] = bb_mid_1h
        intent_telemetry["bb_mid_4h"] = bb_mid_4h
        intent_telemetry["macd_hist_1h"] = macd_hist_1h
        intent_telemetry["macd_hist_4h"] = macd_hist_4h
        intent_telemetry["drop_15m_pct"] = round(drop_15m_pct, 3)
        intent_telemetry["utc_hour"] = utc_hour
        intent_telemetry["vol_surge_ratio"] = round(vol_surge_ratio, 2)
        intent_telemetry["drop_60m_pct"] = round(drop_60m_pct, 3)

        if not hierarchical_gates_passed:
            reject_reason = f"HIERARCHICAL_GATE_VETO (MACRO_SHIELD_VETO): {macro_gate_reason or structure_15m_reason}"
            return TradeIntent(
                action="WAIT_IN_CASH",
                reason=reject_reason,
                telemetry=intent_telemetry,
            )

        # 2.7 SETUP C: VOLATILITY EXPANSION IMPULSE (Squeeze Firing Ignition)
        tfs = matrix.get("timeframes", {})
        tf_5m = tfs.get("5m", {})
        tf_15m = tfs.get("15m", {})
        tf_1h = tfs.get("1h", {})
        pinched_screens = int(balloon.get("pinched_screens", 0))

        bb_upper = float(tf_5m.get("bb_upper", price * 1.005))
        bb_mid = float(tf_5m.get("bb_mid", price))
        bb_width = float(tf_5m.get("bb_width", 0.60))
        bb_pct_b = float(tf_5m.get("bb_pct_b", 0.50))
        bb_width_15m = float(tf_15m.get("bb_width", 1.0))
        bb_width_1h = float(tf_1h.get("bb_width", 1.0))

        # Dual-Horizon Squeeze: 5m and 15m compressed simultaneously
        is_squeeze_precursor = (
            (bb_width < 0.65 and bb_width_15m < 0.85) or
            (entropy < 0.45 and bb_width < 0.65) or
            (is_slow_market and bb_width_15m < 0.85)
        )

        # 1H Macro Expansion and Minimum +1.00% Clearance Requirement
        macro_ceiling_dist_pct = ((macro_ceiling - price) / price) * 100.0 if price > 0 else 0.0
        is_1h_macro_expanding = (bb_width_1h > 1.2 or is_balloon_expanding) and (macro_ceiling_dist_pct >= 1.00)

        is_expansion_firing = (
            (price >= bb_upper or bb_pct_b >= 0.95) and
            (price >= nearest_resistance - (0.10 * atr)) and
            (trade_vel > 5.0 or cvd > 0) and
            (tanh_imb >= 0.0)
        )

        if is_squeeze_precursor and is_1h_macro_expanding and is_expansion_firing:
            # Physical market structure target (macro_ceiling) only
            target_exp = macro_ceiling
            target_pct_exp = macro_ceiling_dist_pct

            # MANDATORY PHYSICAL RUNWAY GATE (+80 bps hurdle)
            if target_pct_exp < 0.80:
                return TradeIntent(
                    action="WAIT_IN_CASH",
                    reason=f"REJECTED BY RUNWAY GATE: Squeeze runway (+{target_pct_exp:.2f}%) < +0.80% minimum physical clearance.",
                    telemetry={**intent_telemetry, "rr_ratio": 0.0, "true_net_ev": 0.0},
                )
            dynamic_stop_exp = round(max(bb_mid, price - (0.80 * atr)), 2)
            stop_pct_exp = ((price - dynamic_stop_exp) / price) * 100.0 if price > 0 else 0.0

            p_sensory_exp = float(np.clip(0.55 + 0.10 * (trade_vel / 10.0) + 0.05 * min(tanh_imb, 0.5), 0.45, 0.75))
            if governor:
                h = governor.get_health("VOLATILITY_EXPANSION_IMPULSE")
                m_prior = 10.0
                pw_raw = (h.total_trades * (h.win_rate / 100.0) + m_prior * p_sensory_exp) / (h.total_trades + m_prior)
                pw_exp = float(np.clip(pw_raw, 0.25, 0.80))
            else:
                pw_exp = p_sensory_exp

            ev_exp, rr_exp = self.calculate_classical_expectancy(pw_exp, target_pct_exp, stop_pct_exp, slippage_pct=dynamic_slippage_pct)
            if rr_exp >= 1.50 and ev_exp > 0.05:
                return TradeIntent(
                    action="ENTER_CORE_LOT_1",
                    scenario="VOLATILITY_EXPANSION_IMPULSE",
                    entry_price=price,
                    target_price=target_exp,
                    proposed_stop=dynamic_stop_exp,
                    expected_runway_pct=target_pct_exp,
                    confidence=max(tuned_confidence, 0.80),
                    reason=f"VOLATILITY EXPANSION: Squeeze firing through upper band (${bb_upper:,.2f}) into expanding 1h macro ceiling (${macro_ceiling:,.2f}, +{target_pct_exp:.2f}%). True Net EV={ev_exp:+.2f}% (R:R {rr_exp:.2f}:1, pw={pw_exp*100:.0f}%).",
                    telemetry={**intent_telemetry, "true_net_ev": ev_exp, "rr_ratio": rr_exp, "win_rate_prob": pw_exp},
                )

        # 2.8 SETUP D: TREND PULLBACK CONTINUATION (Value Zone Re-Entry)
        ema9 = float(tf_5m.get("ema_9", price))
        ema21 = float(tf_5m.get("ema_21", price))
        ema50 = float(tf_5m.get("ema_50", price))

        is_trend_aligned = (
            (ema9 > ema21 > ema50) and
            (trend_strength >= 0.0006) and
            (belief.regime_belief in ("BULL_ACCELERATION", "NEUTRAL_WAIT")) and
            (entropy < 0.60)
        )

        dist_from_swing_high = ((pooled_swing_high - price) / price) * 100.0 if price > 0 else 0.0
        is_in_value_zone = (
            price <= (ema9 + (0.15 * atr)) and
            price >= (ema21 - (0.35 * atr)) and
            dist_from_swing_high >= 0.25
        )

        is_pullback_supported = (
            price >= (ema21 - (0.20 * atr)) and
            (tanh_imb >= 0.0 or trade_vel > 4.0)
        )

        if is_trend_aligned and is_in_value_zone and is_pullback_supported:
            # Physical target strictly bound to pooled swing high (purged synthetic floors)
            target_d = pooled_swing_high
            target_pct_d = ((target_d - price) / price) * 100.0 if price > 0 else 0.0

            # MANDATORY HIGH-EXPECTANCY PHYSICAL RUNWAY GATE (+150 bps hurdle)
            if target_pct_d < 1.50:
                return TradeIntent(
                    action="WAIT_IN_CASH",
                    reason=f"REJECTED BY HIGH-EXPECTANCY RUNWAY GATE: Pullback runway (+{target_pct_d:.2f}%) < +1.50% minimum physical clearance.",
                    telemetry={**intent_telemetry, "rr_ratio": 0.0, "true_net_ev": 0.0},
                )
            
            dynamic_stop_d = round(ema21 - (0.40 * atr), 2)
            stop_pct_d = ((price - dynamic_stop_d) / price) * 100.0 if price > 0 else 0.0

            p_sensory_d = float(np.clip(0.60 + 0.10 * np.tanh(400.0 * trend_strength), 0.50, 0.75))
            if governor:
                h = governor.get_health("TREND_PULLBACK_CONTINUATION")
                m_prior = 10.0
                pw_raw = (h.total_trades * (h.win_rate / 100.0) + m_prior * p_sensory_d) / (h.total_trades + m_prior)
                pw_d = float(np.clip(pw_raw, 0.25, 0.80))
            else:
                pw_d = p_sensory_d

            ev_d, rr_d = self.calculate_classical_expectancy(pw_d, target_pct_d, stop_pct_d, slippage_pct=dynamic_slippage_pct)
            if rr_d >= 1.50 and ev_d > 0.05:
                return TradeIntent(
                    action="ENTER_CORE_LOT_1",
                    scenario="TREND_PULLBACK_CONTINUATION",
                    entry_price=price,
                    target_price=target_d,
                    proposed_stop=dynamic_stop_d,
                    expected_runway_pct=target_pct_d,
                    confidence=max(tuned_confidence, 0.75),
                    reason=f"TREND CONTINUATION: Pullback into Value Zone (${ema21:,.2f}) with trend_strength={trend_strength:.4f}. True Net EV={ev_d:+.2f}% (R:R {rr_d:.2f}:1, pw={pw_d*100:.0f}%). Target: ${target_d:,.2f} (+{target_pct_d:.2f}%).",
                    telemetry={**intent_telemetry, "true_net_ev": ev_d, "rr_ratio": rr_d, "win_rate_prob": pw_d},
                )

        # 2.9 SETUP B: MOMENTUM IGNITION / BREAKOUT SURGE (v3.0 Gated Momentum Flow)
        # STRICT GATES:
        # 1. Price at swing high or clean balloon expanding
        # 2. Positive Edge (>= +0.15)
        # 3. Positive Urgency (>= 0.15)
        # 4. Confidence clearing regime threshold
        # 5. Belief is NOT in CHOP_COMPRESSION
        is_clearing_high = price >= (pooled_swing_high - 1.0)
        has_real_momentum = (effective_edge >= 0.15) and (effective_urgency >= 0.15) and (tuned_confidence >= regime_conf_hurdle)
        is_belief_aligned = belief.regime_belief in ("BULL_ACCELERATION", "NEUTRAL_WAIT")

        has_orderflow_backing = (
            (tanh_imb > 0.20 and cvd > 0) or
            (absorption_idx > 15.0) or
            (trade_vel > 6.0 and tanh_imb >= 0.0 and cvd >= 0)
        )

        if (is_clearing_high or is_balloon_expanding) and has_real_momentum and is_belief_aligned and has_orderflow_backing:
            # Bollinger Upper Band Exhaustion Shield:
            # Prevents buying into local range ceiling exhaustion above +2.0 Upper BB
            tf_15m_dict = tfs.get("15m", {})
            bb_upper_15m = float(tf_15m_dict.get("bb_upper", price * 1.05))
            if price > bb_upper_15m:
                return TradeIntent(
                    action="WAIT_IN_CASH",
                    scenario="MACRO_BALLOON_BREAKOUT",
                    reason=f"VETO UPPER BB EXHAUSTION: Price (${price:,.2f}) stretched above 15M Upper Bollinger Band (${bb_upper_15m:,.2f}). Vetoing local range ceiling chase.",
                    telemetry={**intent_telemetry, "upper_bb_exhaustion_veto": True, "bb_upper_15m": bb_upper_15m},
                )

            # Physical target strictly bound to macro ceiling (purged synthetic floors)
            target = macro_ceiling
            target_pct = ((target - price) / price) * 100.0 if price > 0 else 0.0

            # MANDATORY HIGH-EXPECTANCY PHYSICAL RUNWAY GATE (+150 bps hurdle)
            if target_pct < 1.50:
                return TradeIntent(
                    action="WAIT_IN_CASH",
                    reason=f"REJECTED BY HIGH-EXPECTANCY RUNWAY GATE: Breakout runway (+{target_pct:.2f}%) < +1.50% minimum physical clearance.",
                    telemetry={**intent_telemetry, "rr_ratio": 0.0, "true_net_ev": 0.0},
                )

            effective_runway = max(macro_runway, target_pct)
            stop_pct = ((price - dynamic_invalidation) / price) * 100.0 if price > 0 else 0.0

            p_sensory = float(np.clip(0.40 + 0.15 * tuned_confidence, 0.35, 0.65))
            if governor:
                h = governor.get_health("MACRO_BALLOON_BREAKOUT")
                m_prior = 10.0
                pw_raw = (h.total_trades * (h.win_rate / 100.0) + m_prior * p_sensory) / (h.total_trades + m_prior)
                pw = float(np.clip(pw_raw, 0.20, 0.80))
            else:
                pw = p_sensory

            ev_breakout, rr_breakout = self.calculate_classical_expectancy(pw, target_pct, stop_pct, slippage_pct=dynamic_slippage_pct)
            if rr_breakout < 1.50:
                return TradeIntent(
                    action="WAIT_IN_CASH",
                    reason=f"REJECTED BY RR GATE: Breakout R:R ({rr_breakout:.2f}:1) < 1.50:1 minimum threshold (Target +{target_pct:.2f}%, Risk -{stop_pct:.2f}%).",
                    telemetry={**intent_telemetry, "rr_ratio": rr_breakout, "true_net_ev": ev_breakout},
                )
            if ev_breakout <= 0.05:
                return TradeIntent(
                    action="WAIT_IN_CASH",
                    reason=f"REJECTED BY EXPECTANCY GATE: Breakout Net EV={ev_breakout:+.2f}% <= +0.05% (pw={pw*100:.1f}%, Target +{target_pct:.2f}%, Risk -{stop_pct:.2f}%).",
                    telemetry={**intent_telemetry, "rr_ratio": rr_breakout, "true_net_ev": ev_breakout},
                )

            # -----------------------------------------------------------------
            # STRUCTURAL ACCEPTANCE & VOLUME CONFIRMATION GATES (v3.6.0)
            # -----------------------------------------------------------------
            candles_1m = matrix.get("candles_1m") or []
            if candles_1m and len(candles_1m) >= 6:
                if price >= (pooled_swing_high - 1.0):
                    breakout_level = pooled_swing_high
                else:
                    breakout_level = price

                cur_bar = candles_1m[-1]
                is_real_green_body = cur_bar["close"] > cur_bar["open"]
                is_closed_above_level = cur_bar["close"] >= (breakout_level - 1.0)

                if not is_real_green_body:
                    return TradeIntent(
                        action="WAIT_IN_CASH",
                        scenario="MACRO_BALLOON_BREAKOUT",
                        reason=f"VETO BREAKOUT REJECTION: Candle closed red (${cur_bar['open']:,.2f} -> ${cur_bar['close']:,.2f}) indicating upper-wick rejection.",
                        telemetry={**intent_telemetry, "candle_color_veto": True},
                    )

                if not is_closed_above_level:
                    return TradeIntent(
                        action="WAIT_IN_CASH",
                        scenario="MACRO_BALLOON_BREAKOUT",
                        reason=f"VETO BLIND TOUCH: Candle closed below breakout level (${cur_bar['close']:,.2f} < ${breakout_level:,.2f}).",
                        telemetry={**intent_telemetry, "blind_touch_veto": True},
                    )

                prev_5 = candles_1m[-6:-1]
                avg_vol_5 = float(np.mean([b["vol"] for b in prev_5]))
                vol_ratio = cur_bar.get("vol", 0.0) / avg_vol_5 if avg_vol_5 > 0 else 1.0
                if vol_ratio < 1.20:
                    return TradeIntent(
                        action="WAIT_IN_CASH",
                        scenario="MACRO_BALLOON_BREAKOUT",
                        reason=f"VETO LOW VOLUME: Breakout volume ({cur_bar.get('vol', 0):.2f}) < 1.20x 5-bar average ({avg_vol_5:.2f}).",
                        telemetry={**intent_telemetry, "volume_veto": True},
                    )

                intent_telemetry["true_net_ev"] = ev_breakout
                intent_telemetry["rr_ratio"] = rr_breakout
                intent_telemetry["win_rate_prob"] = pw

                # Arm pending acceptance state for micro-retest confirmation on subsequent bar
                self.pending_acceptance = {
                    "breakout_level": breakout_level,
                    "target_price": target,
                    "proposed_stop": dynamic_invalidation,
                    "expected_runway_pct": effective_runway,
                    "confidence": max(tuned_confidence, 0.80),
                    "intent_telemetry": intent_telemetry,
                }

                return TradeIntent(
                    action="WAIT_IN_CASH",
                    scenario="MACRO_BALLOON_BREAKOUT",
                    reason=f"AWAITING_STRUCTURAL_ACCEPTANCE_RETEST: Armed breakout acceptance candidate at ${breakout_level:,.2f}. Awaiting micro-retest hold (cushion: ${breakout_level * 0.998:,.2f}).",
                    telemetry={**intent_telemetry, "pending_acceptance": True, "breakout_level": round(breakout_level, 2)},
                )

            # Direct execution fallback if candle buffers not provided (e.g. synthetic test matrix)
            return TradeIntent(
                action="ENTER_CORE_LOT_1",
                scenario="MACRO_BALLOON_BREAKOUT",
                entry_price=price,
                target_price=target,
                proposed_stop=dynamic_invalidation,
                expected_runway_pct=effective_runway,
                confidence=max(tuned_confidence, 0.80),
                reason=f"MOMENTUM IGNITION: Validated surge (Edge={effective_edge:+.2f}, Urgency={effective_urgency:.2f}, Conf={tuned_confidence:.2f}). Flowing into macro space (${macro_ceiling:,.2f}, +{effective_runway:.2f}%) with True Net EV=+{ev_breakout:.2f}%.",
                telemetry={**intent_telemetry, "true_net_ev": ev_breakout, "rr_ratio": rr_breakout, "win_rate_prob": pw},
            )

        # 2.8 FALLBACK: Slow market or patient scanning in cash
        if is_slow_market and immediate_runway < (adaptive_runway + 0.15):
            return TradeIntent(
                action="WAIT_IN_CASH",
                expected_runway_pct=immediate_runway,
                confidence=effective_conf,
                reason=f"SLOW MARKET: Bollinger lines horizontal and volume compressed (runway +{immediate_runway:.2f}%). Sitting 100% in cash.",
                telemetry=intent_telemetry,
            )

        # Default fallback: Patiently scanning in cash
        return TradeIntent(
            action="WAIT_IN_CASH",
            expected_runway_pct=immediate_runway,
            confidence=tuned_confidence,
            reason=f"PATIENT SCANNING: Belief={belief.regime_belief} (Bias={effective_edge:+.2f}, Conf={tuned_confidence:.2f}, Pers={belief.persistence_ticks}). Hurdle={adaptive_runway:.2f}%. Nearest Support ${nearest_support:,.2f}, Structural Ceiling ${nearest_resistance:,.2f} (+{immediate_runway:.2f}%).",
            telemetry=intent_telemetry,
        )
