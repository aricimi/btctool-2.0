"""
risk_engine.py — The Independent Risk Gate (Conscience) for Zebra Bot (btctool 2.0 / v3.0)
Architecture:
- "Models Propose, Risk Disposes" (PROJECT_BLUEPRINT.md Section 10).
- Pure, cold, deterministic safety layer sitting between the Mind (Conviction Engine)
  and the Hands (Execution Manager).
- Components Integrated (v3.0 Master Package):
  1. Priority-0 Subconscious Fallback Reflexes (Blind, Motor, Safety).
  2. Setup Performance Governor (SetupHealth rolling win rate, net PnL, health score & auto-disable).
  3. Thesis Failure Counter & Setup Cooldown (tracks consecutive setup failures; imposes 30m cooldown).
  4. Conscience Escalation (+10% entry hurdle escalation after 3 consecutive portfolio losses).
  5. Lightweight Analytical Stress Engine (spread shock, liquidity vacuum, and adverse drop).
  6. In-Situ Memory Soft Stop (wick-sweep absorption defense overrides panic cuts).
  7. Noise-Immune Floor Calculation (ATR-anchored stop guaranteed below fill).
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List
import numpy as np

logger = logging.getLogger("risk_engine")

OKX_ROUNDTRIP_FEE_PCT = 0.0020     # 0.20% OKX Spot round-trip fee
MIN_PROJECTED_RUNWAY_PCT = 0.45    # 0.45% minimum required room to target


@dataclass
class SetupHealth:
    """Component 1 Data Contract: Setup Performance Health."""
    setup_name: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_net_pnl: float = 0.0
    health_score: float = 100.0   # 0.0 to 100.0
    size_multiplier: float = 1.0  # 0.0 to 1.0
    confidence_modifier: float = 0.0  # +0.00, +0.05, +0.10
    is_disabled: bool = False
    trades_last_20: int = 0


class SetupPerformanceGovernor:
    """
    Component 1: Setup Performance Governor.
    Monitors rolling 20 trades for each setup name.
    Dynamically scales position sizing and enforces confidence hurdle modifiers across
    5 contiguous institutional health tiers.
    """

    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.history: Dict[str, List[float]] = {}

    def record_trade_result(self, setup_name: str, net_pnl_pct: float):
        clean_name = setup_name.replace("ZEBRA WHALE: ", "")
        if clean_name not in self.history:
            self.history[clean_name] = []
        self.history[clean_name].append(float(net_pnl_pct))
        if len(self.history[clean_name]) > self.window_size:
            self.history[clean_name] = self.history[clean_name][-self.window_size:]

    def get_health(self, setup_name: str) -> SetupHealth:
        clean_name = setup_name.replace("ZEBRA WHALE: ", "")
        trades = self.history.get(clean_name, [])
        if not trades:
            return SetupHealth(setup_name=clean_name, health_score=100.0, size_multiplier=1.0, confidence_modifier=0.0, is_disabled=False)

        wins = sum(1 for p in trades if p > 0.0)
        losses = sum(1 for p in trades if p <= 0.0)
        win_rate = (wins / len(trades)) * 100.0
        avg_net_pnl = float(np.mean(trades))

        # Health score: 50.0 base + 0.5 * win_rate + 200 * avg_net_pnl
        raw_score = 50.0 + (0.5 * win_rate) + (200.0 * avg_net_pnl)
        health_score = float(np.clip(raw_score, 0.0, 100.0))

        # Contiguous Institutional Health Tiers:
        # [80, 100]: Pristine -> size 1.00, conf_mod +0.00
        # [60, 80):  Healthy  -> size 0.75, conf_mod +0.00
        # [40, 60):  Degraded -> size 0.50, conf_mod +0.05
        # [20, 40):  Stressed -> size 0.25, conf_mod +0.10
        # [0, 20):   Disabled -> size 0.00, disabled = True
        if health_score >= 80.0:
            size_mult = 1.00
            conf_mod = 0.00
            disabled = False
        elif health_score >= 60.0:
            size_mult = 0.75
            conf_mod = 0.00
            disabled = False
        elif health_score >= 40.0:
            size_mult = 0.50
            conf_mod = 0.05
            disabled = False
        elif health_score >= 20.0:
            size_mult = 0.25
            conf_mod = 0.10
            disabled = False
        else:
            size_mult = 0.00
            conf_mod = 0.00
            disabled = True

        return SetupHealth(
            setup_name=clean_name,
            total_trades=len(trades),
            wins=wins,
            losses=losses,
            win_rate=round(win_rate, 1),
            avg_net_pnl=round(avg_net_pnl, 3),
            health_score=round(health_score, 1),
            size_multiplier=size_mult,
            confidence_modifier=conf_mod,
            is_disabled=disabled,
            trades_last_20=len(trades),
        )


class ThesisFailureCounter:
    """
    Component 5: Dual-Class Thesis Failure Counter & Cooldown Manager (Spec Section 5.2).
    - Class A: Market-condition gate (Entropy/Chop) is evaluated real-time without timers.
    - Class B: Failure/Loss-based cooldown is an immutable timer calculated from consecutive losses,
      setup health, and entropy with hard minimum loss floors:
      1 loss -> >= 3m, 2 losses -> >= 8m, 3+ losses -> >= 20m (clamped 3m to 45m).
      Zero early release permitted on Class B loss locks.
    """

    def __init__(self, base_duration_sec: float = 180.0, max_consecutive_failures: int = 3, cooldown_seconds: float = 1800.0):
        self.base_duration_sec = base_duration_sec  # Base 3 minutes
        self.max_failures = max_consecutive_failures
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_failures: Dict[str, int] = {}
        self.disabled_until: Dict[str, float] = {}

    def calculate_cooldown_duration(self, consecutive_losses: int, health_score: float, entropy: float = 0.50) -> float:
        """
        Calculates cooldown duration with hard loss-based minimum floors (Section 5.2):
        Candidate = clamp(Base * M_losses * M_health * M_entropy, 3m, 45m)
        Duration = max(Candidate, LossFloor)
        """
        if consecutive_losses <= 0:
            return 0.0

        # M_losses multipliers & Loss Floors
        if consecutive_losses == 1:
            m_l = 1.0
            loss_floor_sec = 3.0 * 60.0    # 3m minimum
        elif consecutive_losses == 2:
            m_l = 2.5
            loss_floor_sec = 8.0 * 60.0    # 8m minimum
        else:
            m_l = 6.0 + (consecutive_losses - 3) * 2.0
            loss_floor_sec = 20.0 * 60.0   # 20m minimum

        # M_health modifier (Never reduces cooldown below 1.0x to prevent historical health from masking recent losses)
        if health_score < 20.0:
            m_h = 1.8
        elif health_score < 40.0:
            m_h = 1.5
        elif health_score < 60.0:
            m_h = 1.2
        else:
            m_h = 1.0  # Historical health cannot shorten loss cooldown below floor

        # M_entropy modifier (Section 5.2B: entropy >= 0.70 extends candidate duration by 1.5x)
        m_e = 1.5 if entropy >= 0.70 else 1.0

        candidate_sec = float(np.clip(self.base_duration_sec * m_l * m_h * m_e, 180.0, 2700.0))  # 3m to 45m
        final_sec = float(np.clip(max(candidate_sec, loss_floor_sec), 180.0, 2700.0))
        return final_sec

    def record_outcome(self, setup_name: str, net_pnl_pct: float, health_score: float = 50.0, entropy: float = 0.50, timestamp: float = 0.0):
        clean_name = setup_name.replace("ZEBRA WHALE: ", "")
        ts = timestamp or time.time()
        if net_pnl_pct <= 0.0:
            cnt = self.consecutive_failures.get(clean_name, 0) + 1
            self.consecutive_failures[clean_name] = cnt
            logger.info(f"[ThesisTracker] Setup '{clean_name}' consecutive failure count: {cnt}")

            # Enforce Class B cooldown duration with loss floor
            cooldown_sec = self.calculate_cooldown_duration(cnt, health_score, entropy)
            self.disabled_until[clean_name] = ts + cooldown_sec
            logger.warning(
                f"[ThesisTracker] Setup '{clean_name}' enforced Class-B cooldown for {cooldown_sec/60:.1f}m (Failures: {cnt}, Health: {health_score:.1f}, Entropy: {entropy:.2f})."
            )
        else:
            self.consecutive_failures[clean_name] = 0
            if clean_name in self.disabled_until:
                del self.disabled_until[clean_name]

    def is_in_cooldown(self, setup_name: str, current_time: float = 0.0) -> Tuple[bool, float]:
        clean_name = setup_name.replace("ZEBRA WHALE: ", "")
        ts = current_time or time.time()
        until = self.disabled_until.get(clean_name, 0.0)
        if ts < until:
            return True, round(until - ts, 0)
        return False, 0.0

    def get_failure_penalty(self, setup_name: str) -> float:
        clean_name = setup_name.replace("ZEBRA WHALE: ", "")
        cnt = self.consecutive_failures.get(clean_name, 0)
        if cnt == 1:
            return 0.85
        elif cnt == 2:
            return 0.70
        elif cnt >= 3:
            return 0.50
        return 1.0

    def export_state(self) -> dict:
        """Exports cooldown state for atomic disk persistence."""
        return {
            "consecutive_failures": dict(self.consecutive_failures),
            "disabled_until": dict(self.disabled_until),
        }

    def import_state(self, state: dict):
        """Restores persisted cooldown state across bot restarts."""
        if not state or not isinstance(state, dict):
            return
        self.consecutive_failures.update(state.get("consecutive_failures", {}))
        self.disabled_until.update(state.get("disabled_until", {}))


class ConscienceEscalation:
    """
    Component 8: Conscience Escalation Gate.
    Tracks portfolio-wide consecutive losses.
    When 3 or more losses occur, temporarily raises the minimum required confidence hurdle by +10% to +15%.
    """

    def __init__(self, escalation_threshold: int = 3):
        self.escalation_threshold = escalation_threshold
        self.consecutive_losses: int = 0

    def record_trade(self, net_pnl_pct: float):
        if net_pnl_pct <= 0.0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    @property
    def is_escalated(self) -> bool:
        return self.consecutive_losses >= self.escalation_threshold

    @property
    def confidence_hike(self) -> float:
        if self.consecutive_losses >= 4:
            return 0.15
        elif self.consecutive_losses >= 3:
            return 0.10
        return 0.0


class LightweightStressEngine:
    """
    Component 6: Lightweight Analytical Stress Engine.
    Evaluates instantaneous market shock tolerance without Monte Carlo overhead:
    - Adverse price drop (to stop loss)
    - Spread shock (spread > 0.20%)
    - Liquidity vacuum (bid depth < 30% of normal baseline)
    """

    @staticmethod
    def evaluate_stress(
        price: float,
        stop_price: float,
        spread_pct: float,
        bid_depth: float,
        avg_bid_depth: float = 10.0,
    ) -> Tuple[bool, str, float]:
        if price <= 0:
            return False, "Invalid price data", 0.0

        # 1. Adverse drop to stop loss
        drop_pct = round(((price - stop_price) / price) * 100.0, 3) if stop_price > 0 else 0.0

        # 2. Spread inflation shock
        if spread_pct > 0.20:
            return False, f"STRESS_FAIL: Spread inflated ({spread_pct:.3f}% > 0.20% shock threshold)", drop_pct

        # 3. Liquidity vacuum check (depth collapsed below 30% baseline)
        if avg_bid_depth > 0 and bid_depth > 0 and bid_depth < (0.30 * avg_bid_depth):
            return False, f"STRESS_FAIL: Liquidity vacuum (bid depth {bid_depth:.1f} < 30% of normal baseline)", drop_pct

        return True, "PASSED", drop_pct


@dataclass
class TradeIntent:
    """The cognitive proposal generated by the Mind (Conviction Engine)."""
    action: str                     # "ENTER_CORE_LOT_1", "SCALE_IN_LOT_2", "BANK_PROFIT", "CUT_THESIS_INVALIDATED", "RIDE_UNCAPPED", "HOLD_POSITION", "WAIT_IN_CASH"
    scenario: str = "SCANNING"
    entry_price: float = 0.0
    target_price: float = 0.0
    proposed_stop: float = 0.0
    invalidation_floor: float = 0.0
    trailing_stop: float = 0.0
    confidence: float = 0.50
    reason: str = ""
    expected_runway_pct: float = 0.0
    gain_pct: float = 0.0
    telemetry: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.invalidation_floor and self.proposed_stop:
            self.invalidation_floor = self.proposed_stop
        if not self.trailing_stop and self.proposed_stop:
            self.trailing_stop = self.proposed_stop

    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, item, default=None):
        return getattr(self, item, default)


@dataclass
class RiskDecision:
    """The deterministic ruling issued by the Conscience (Risk Gate)."""
    status: str                     # "ALLOW", "MODIFY", "REJECT"
    action: str                     # Final approved action to dispatch
    scenario: str = "SCANNING"
    entry_price: float = 0.0
    target_price: float = 0.0
    trailing_stop: float = 0.0
    invalidation_floor: float = 0.0
    reason: str = ""
    expected_runway_pct: float = 0.0
    gain_pct: float = 0.0
    approved_size_factor: float = 1.0  # Volatility / Stress adjusted position sizing multiplier (0.1 to 1.0)
    stress_loss_pct: float = 0.0       # Shadow Self simulated worst-case drop to stop
    telemetry: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.invalidation_floor and self.trailing_stop:
            self.invalidation_floor = self.trailing_stop

    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, item, default=None):
        return getattr(self, item, default)


class RiskEngine:
    """
    Independent Deterministic Risk Gate (Conscience).
    Enforces capital preservation, mathematical expectancy, and v3.0 Governor rules.
    """

    def __init__(self, history_file: Optional[str] = None):
        self.last_invalidation_exit_price: float = 0.0
        self.last_invalidation_timestamp: float = 0.0
        self.governor = SetupPerformanceGovernor()
        self.failure_counter = ThesisFailureCounter()
        self.escalation = ConscienceEscalation()
        self.stress_engine = LightweightStressEngine()

        # Seed initial state from historical ledger if requested
        if history_file:
            self._seed_from_history(history_file)

    def _seed_from_history(self, history_file: str):
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                trades = data.get("trades", [])
                for t in trades:
                    if t.get("status") in ("CLOSED_PROFIT", "CLOSED_LOSS"):
                        sc = t.get("setup", "WHALE_TRADE")
                        net = float(t.get("net_pnl_pct", 0.0) or 0.0)
                        self.governor.record_trade_result(sc, net)
                        h = self.governor.get_health(sc)
                        self.failure_counter.record_outcome(sc, net, health_score=h.health_score)
                        self.escalation.record_trade(net)
                logger.info(f"[RiskGate] Seeded Governor with {len(trades)} trades from {history_file}")
            except Exception as e:
                logger.warning(f"[RiskGate] Could not seed governor from {history_file}: {e}")

    def record_invalidation_exit(self, exit_price: float, timestamp: float = 0.0):
        """Records price level where a thesis broke down to prevent re-entering a false breakout at the same level."""
        self.last_invalidation_exit_price = float(exit_price)
        self.last_invalidation_timestamp = float(timestamp)
        logger.info(f"[RiskGate] Recorded invalidation level: ${self.last_invalidation_exit_price:,.2f}")

    def record_trade_outcome(self, setup_name: str, net_pnl_pct: float, timestamp: float = 0.0):
        """Records finalized trade outcome into Governor, Failure Counter, and Escalation organs."""
        self.governor.record_trade_result(setup_name, net_pnl_pct)
        health = self.governor.get_health(setup_name)
        self.failure_counter.record_outcome(setup_name, net_pnl_pct, health_score=health.health_score, timestamp=timestamp)
        self.escalation.record_trade(net_pnl_pct)

    def evaluate_entry_eligibility(
        self,
        setup_name: str,
        matrix: dict,
        daily_drawdown_pct: float = 0.0,
        max_daily_drawdown: float = 2.0,
    ) -> Tuple[str, float, float]:
        """
        Unified 5-tier entry eligibility gate:
        1. Hard account safety reflexes (Absolute Priority)
        2. Setup-specific Class B loss cooldowns & Governor health
        3. Class A Market Condition Gate (Real-time Entropy / Chop - Zero Timers)
        4. Portfolio loss escalation (Conscience Escalation)
        5. Moderate entropy / degraded health caution scaling

        Returns: (eligibility_status, approved_size_multiplier, confidence_hurdle_modifier)
        """
        ts_now = float(matrix.get("timestamp", 0.0) or time.time())
        f_vec = matrix.get("feature_vector", {})
        entropy = float(f_vec.get("entropy", 0.50))
        trend_strength = float(f_vec.get("trend_strength", 0.0))
        trend_term = float(np.tanh(400.0 * trend_strength))

        setup_health = self.governor.get_health(setup_name)
        is_cd, rem_sec = self.failure_counter.is_in_cooldown(setup_name, ts_now)

        # 1. HARD SAFETY GATES (Absolute Priority)
        if daily_drawdown_pct >= max_daily_drawdown:
            return "BLOCK_ACCOUNT_LOCKDOWN", 0.0, 0.0

        if setup_health.is_disabled or setup_health.health_score < 20.0:
            return "BLOCK_SETUP_UNHEALTHY", 0.0, 0.0

        # Class B Loss Cooldown: Immutable, zero early release permitted
        if is_cd:
            return f"BLOCK_SETUP_COOLDOWN_{rem_sec:.0f}S", 0.0, 0.0

        # 2. CLASS A: MARKET-STATE CONDITION GATE (Spec Section 5.2B)
        # Elevated entropy (>= 0.70): Wait for structure to organize
        # Early release permitted ONLY when entropy < 0.40 AND trend_term >= 0.15 (Comment 3 correction)
        if entropy >= 0.70:
            return "WAIT_HIGH_ENTROPY", 0.0, 0.0

        # 3. CONSCIENCE ESCALATION & CAUTION GATES
        size_mult = setup_health.size_multiplier
        conf_mod = setup_health.confidence_modifier

        # Portfolio-wide loss escalation
        if self.escalation.is_escalated:
            conf_mod += self.escalation.confidence_hike

        # Moderate entropy (0.65 - 0.70) or degraded health (< 60):
        # If trend is igniting (entropy < 0.40 and trend_term >= 0.15), allow normal size; otherwise caution
        if (entropy >= 0.65 or setup_health.health_score < 60.0):
            size_mult = min(size_mult, 0.50)
            conf_mod += 0.05
            return "REDUCE_SIZE_AND_CONFIRM", size_mult, conf_mod

        if self.escalation.is_escalated:
            return "REQUIRE_STRONGER_CONFIRMATION", size_mult, conf_mod

        return "NORMAL_ELIGIBILITY", size_mult, conf_mod

    def evaluate(
        self,
        intent: TradeIntent,
        matrix: dict,
        active_trade: Optional[dict] = None,
        consecutive_api_errors: int = 0,
        daily_drawdown_pct: float = 0.0,
        max_daily_drawdown: float = 2.0,
        max_stress_risk_pct: float = 0.75,
    ) -> RiskDecision:
        """
        Evaluates the Mind's TradeIntent against Priority-0 Subconscious Reflexes,
        In-Situ Memory Soft Stop, and deterministic Risk Invariants.
        Returns a concrete RiskDecision: ALLOW, MODIFY, or REJECT.
        """
        price = float(matrix.get("latest_price", 0.0))
        feed_latency_ms = float(matrix.get("feed_latency_ms", 0.0))
        spread_pct = float(matrix.get("spread_pct", 0.0))

        # ==================================================================
        # PRIORITY 0: SUBCONSCIOUS FALLBACK REFLEXES (bot.txt Nervous System)
        # ==================================================================
        # Reflex 1: Blind Reflex (Sensory Feed Failure)
        if price <= 0:
            return RiskDecision(status="REJECT", action="WAIT_IN_CASH", reason="REFLEX_BLIND_MODE: Invalid price data")
        if feed_latency_ms > 5000.0:
            return RiskDecision(
                status="REJECT",
                action="WAIT_IN_CASH",
                reason=f"REFLEX_BLIND_MODE: WebSocket stream latency ({feed_latency_ms:.0f}ms) > 5,000ms. Trading frozen until sight returns.",
                telemetry={"feed_latency_ms": feed_latency_ms},
            )
        if spread_pct > 0.25:
            return RiskDecision(
                status="REJECT",
                action="WAIT_IN_CASH",
                reason=f"REFLEX_BLIND_MODE: Anomalous bid/ask spread ({spread_pct:.2f}%). Execution paused to prevent slippage shock.",
                telemetry={"spread_pct": spread_pct},
            )

        # Reflex 2: Motor Reflex (Exchange / API Execution Failure)
        if consecutive_api_errors >= 2:
            return RiskDecision(
                status="REJECT",
                action="WAIT_IN_CASH",
                reason=f"REFLEX_MOTOR_LOCKDOWN: {consecutive_api_errors} consecutive exchange API failures. Hands frozen until connectivity clears.",
                telemetry={"consecutive_api_errors": consecutive_api_errors},
            )

        # Reflex 3: Safety Reflex (Drawdown Breach / Capital Preservation)
        if daily_drawdown_pct >= max_daily_drawdown:
            # Conscience paralysis: exits are allowed, but ALL new entries are unconditionally rejected
            if intent.action in ("ENTER_CORE_LOT_1", "SCALE_IN_LOT_2"):
                return RiskDecision(
                    status="REJECT",
                    action="WAIT_IN_CASH",
                    reason=f"REFLEX_SAFETY_LOCKDOWN: Daily drawdown ({daily_drawdown_pct:.2f}%) >= {max_daily_drawdown:.2f}% limit. Account locked against further entries.",
                    telemetry={"daily_drawdown_pct": daily_drawdown_pct},
                )

        atr = float(matrix.get("composite_atr", 250.0))
        tanh_imb = float(matrix.get("tanh_imbalance", 0.0))
        absorption_idx = float(matrix.get("absorption_index", 0.0))
        bounds = matrix.get("multi_screen_bounds", {})
        nearest_support = float(bounds.get("nearest_support", price * 0.99))
        nearest_resistance = float(bounds.get("nearest_resistance", price * 1.01))

        # ==================================================================
        # STATE 1: ACTIVE POSITION MANAGEMENT
        # ==================================================================
        if active_trade:
            entry = float(active_trade.get("entry", price))
            gain_pct = (price - entry) / entry if entry > 0 else 0.0
            trailing_stop = float(active_trade.get("trailing_stop", active_trade.get("invalidation_floor", entry * 0.995)))
            target_price = float(active_trade.get("target_price", nearest_resistance))

            # --------------------------------------------------------------
            # INVARIANT 1: ABSOLUTE HARD STOP PRIMACY & SOFT WICK DEFENSE
            # --------------------------------------------------------------
            if intent.action == "CUT_THESIS_INVALIDATED":
                # Hard Risk Limit: absolute non-overridable boundary
                max_risk_price = round(entry * (1.0 - (max_stress_risk_pct / 100.0)), 2)
                hard_risk_floor = min(trailing_stop, max_risk_price)

                # Soft Wick Zone: absorption is ONLY evaluated if price is within a micro-wick buffer
                # (<= 0.20 * ATR below trailing_stop) AND strictly above max account risk price
                is_within_soft_wick = (price >= (trailing_stop - (0.20 * atr))) and (price > max_risk_price)

                if not is_within_soft_wick or (price <= max_risk_price):
                    # Hard Stop Breached: Absorption override is strictly disabled. Emergency cut unconditionally.
                    self.record_invalidation_exit(price, matrix.get("timestamp", 0.0))
                    return RiskDecision(
                        status="ALLOW",
                        action="CUT_THESIS_INVALIDATED",
                        scenario=active_trade.get("scenario", "TRADE"),
                        entry_price=entry,
                        target_price=target_price,
                        trailing_stop=trailing_stop,
                        gain_pct=gain_pct,
                        reason=f"HARD RISK STOP BREACHED: Price (${price:,.2f}) breached hard floor (${hard_risk_floor:,.2f}). Absorption override disabled to protect capital.",
                        telemetry=intent.telemetry,
                    )

                # Inside soft wick test zone: Are resting bids absorbing the sweep?
                if tanh_imb > 0.15 or absorption_idx > 15.0:
                    logger.info(f"[RiskGate] VETO CUT: Price touching soft stop (${price:,.2f}), but bids absorbing sweep (Ai={absorption_idx:.1f}). Overriding to HOLD within buffer.")
                    return RiskDecision(
                        status="MODIFY",
                        action="HOLD_POSITION",
                        scenario=active_trade.get("scenario", "TRADE"),
                        entry_price=entry,
                        target_price=target_price,
                        trailing_stop=trailing_stop,
                        gain_pct=gain_pct,
                        reason=f"RISK GATE OVERRIDE: Soft stop touched but bids absorbing sweep (tanh_imb={tanh_imb:+.2f}, Ai={absorption_idx:.1f}). Holding strictly above hard floor (${hard_risk_floor:,.2f}).",
                        telemetry=intent.telemetry,
                    )
                else:
                    # Bids collapsed: real breakdown confirmed
                    self.record_invalidation_exit(price, matrix.get("timestamp", 0.0))
                    return RiskDecision(
                        status="ALLOW",
                        action="CUT_THESIS_INVALIDATED",
                        scenario=active_trade.get("scenario", "TRADE"),
                        entry_price=entry,
                        target_price=target_price,
                        trailing_stop=trailing_stop,
                        gain_pct=gain_pct,
                        reason=f"STRUCTURAL BREAKDOWN: Support broken without bid absorption. Controlled cut ({gain_pct*100:+.2f}%).",
                        telemetry=intent.telemetry,
                    )

            # --------------------------------------------------------------
            # INVARIANT 2: SCALE-IN HARMONIZATION GATE
            # --------------------------------------------------------------
            if intent.action == "SCALE_IN_LOT_2":
                # Verify price is above trailing stop and below entry
                if price <= trailing_stop or price >= entry:
                    return RiskDecision(
                        status="REJECT",
                        action="HOLD_POSITION",
                        scenario=active_trade.get("scenario", "TRADE"),
                        entry_price=entry,
                        target_price=target_price,
                        trailing_stop=trailing_stop,
                        gain_pct=gain_pct,
                        reason="REJECTED BY RISK GATE: Scale-in only allowed at structural discount above stop.",
                        telemetry=intent.telemetry,
                    )
                return RiskDecision(
                    status="ALLOW",
                    action="SCALE_IN_LOT_2",
                    scenario=active_trade.get("scenario", "TRADE"),
                    entry_price=price,
                    target_price=target_price,
                    trailing_stop=trailing_stop,
                    gain_pct=gain_pct,
                    reason=intent.reason,
                    telemetry=intent.telemetry,
                )

            # --------------------------------------------------------------
            # INVARIANT 3: PROFIT BANKING & UNCAPPED RATCHETING
            # --------------------------------------------------------------
            if intent.action in ("BANK_PROFIT", "RIDE_UNCAPPED", "HOLD_POSITION"):
                # Ensure trailing stop ratchets only upward, never downward
                proposed_stop = float(intent.telemetry.get("trailing_stop", trailing_stop))
                approved_stop = max(trailing_stop, proposed_stop)

                return RiskDecision(
                    status="ALLOW",
                    action=intent.action,
                    scenario=active_trade.get("scenario", "TRADE"),
                    entry_price=entry,
                    target_price=intent.target_price or target_price,
                    trailing_stop=approved_stop,
                    gain_pct=gain_pct,
                    reason=intent.reason,
                    telemetry=intent.telemetry,
                )

        # ==================================================================
        # STATE 2: IN CASH (EVALUATING NEW ENTRY PROPOSALS)
        # ==================================================================
        if intent.action == "ENTER_CORE_LOT_1":
            # --------------------------------------------------------------
            # INVARIANT 4A: ANTI-CHURN / POST-STOP RE-ENTRY GUARD
            # --------------------------------------------------------------
            # A Breakout intent cannot be approved at or below the price level of a recent stop cut
            if intent.scenario == "MACRO_BALLOON_BREAKOUT":
                if self.last_invalidation_exit_price > 0.0 and price <= self.last_invalidation_exit_price:
                    logger.info(f"[RiskGate] VETO BREAKOUT: Proposed entry ${price:,.2f} is at/below failed level ${self.last_invalidation_exit_price:,.2f}.")
                    return RiskDecision(
                        status="REJECT",
                        action="WAIT_IN_CASH",
                        reason=f"REJECTED BY RISK GATE: Breakout intent at ${price:,.2f} is below prior failed invalidation level (${self.last_invalidation_exit_price:,.2f}).",
                        telemetry={"last_invalidation_exit_price": self.last_invalidation_exit_price},
                    )

            # --------------------------------------------------------------
            # INVARIANT 4B: UNIFIED 5-TIER ENTRY ELIGIBILITY GATE
            # --------------------------------------------------------------
            eligibility, approved_size_mult, req_conf_mod = self.evaluate_entry_eligibility(
                intent.scenario, matrix, daily_drawdown_pct, max_daily_drawdown
            )
            if eligibility.startswith("BLOCK"):
                logger.info(f"[RiskGate] VETO: Setup '{intent.scenario}' blocked ({eligibility}).")
                return RiskDecision(
                    status="REJECT",
                    action="WAIT_IN_CASH",
                    reason=f"REJECTED BY RISK GATE: {eligibility}",
                    telemetry={"eligibility": eligibility},
                )
            if eligibility == "WAIT_HIGH_ENTROPY":
                logger.info(f"[RiskGate] VETO: Market entropy elevated (>= 0.70).")
                return RiskDecision(
                    status="REJECT",
                    action="WAIT_IN_CASH",
                    reason="REJECTED BY CONDITION GATE: Market entropy elevated (>= 0.70). Waiting for structure to organize.",
                    telemetry={"eligibility": eligibility},
                )

            # Dynamic confidence check with Contiguous Health & Escalation Modifiers
            if req_conf_mod > 0.0:
                base_req_conf = float(intent.telemetry.get("adaptive_conf_hurdle", 0.50))
                effective_req_conf = base_req_conf + req_conf_mod
                if float(intent.confidence or 0.0) < effective_req_conf:
                    logger.info(f"[RiskGate] VETO: Confidence ({intent.confidence:.2f}) < Required hurdle ({effective_req_conf:.2f}).")
                    return RiskDecision(
                        status="REJECT",
                        action="WAIT_IN_CASH",
                        reason=f"REJECTED BY CONFIDENCE GATE: Current {intent.confidence:.2f} < Required {effective_req_conf:.2f} (Base {base_req_conf:.2f} + Mod {req_conf_mod:+.2f}).",
                        telemetry={"required_conf": effective_req_conf, "eligibility": eligibility},
                    )

            # --------------------------------------------------------------
            # INVARIANT 4D: EXPECTANCY & ADAPTIVE HURDLE GATE (Component 2 & 4)
            # --------------------------------------------------------------
            adaptive_hurdle = float(intent.telemetry.get("adaptive_runway_hurdle", MIN_PROJECTED_RUNWAY_PCT))
            required_runway = max(0.40, adaptive_hurdle)
            if intent.expected_runway_pct < required_runway:
                return RiskDecision(
                    status="REJECT",
                    action="WAIT_IN_CASH",
                    reason=f"REJECTED BY RISK GATE: Projected runway (+{intent.expected_runway_pct:.2f}%) < {required_runway:.2f}% adaptive hurdle.",
                    telemetry={"expected_runway_pct": intent.expected_runway_pct, "adaptive_hurdle": required_runway},
                )

            # --------------------------------------------------------------
            # INVARIANT 6: NOISE-IMMUNE STOP-LOSS CALCULATION
            # --------------------------------------------------------------
            # Stop must sit outside normal noise (min 0.8 * ATR) behind nearest support
            raw_risk = max(price - nearest_support, 0.0) + (0.5 * atr)
            clamped_risk = min(max(raw_risk, 0.8 * atr), 2.0 * atr)
            approved_stop = round(price - clamped_risk, 2)

            # --------------------------------------------------------------
            # INVARIANT 6B: LIGHTWEIGHT ANALYTICAL STRESS ENGINE (Component 6)
            # --------------------------------------------------------------
            bid_depth = float(matrix.get("bid_depth_05", 10.0))
            passed_stress, stress_msg, adverse_drop = self.stress_engine.evaluate_stress(
                price=price,
                stop_price=approved_stop,
                spread_pct=spread_pct,
                bid_depth=bid_depth,
            )
            if not passed_stress:
                logger.info(f"[RiskGate] VETO STRESS: {stress_msg}")
                return RiskDecision(
                    status="REJECT",
                    action="WAIT_IN_CASH",
                    reason=f"REJECTED BY STRESS GATE: {stress_msg}",
                    telemetry={"stress_msg": stress_msg},
                )

            # Reward-to-Risk check: target distance must exceed 1.5x risk distance
            reward_dist = max(intent.target_price - price, 0.0)
            if reward_dist < (clamped_risk * 1.5):
                # Adjust target higher to macro ceiling if open space exists, otherwise reject
                macro_ceiling = float(bounds.get("macro_ceiling", intent.target_price))
                if (macro_ceiling - price) >= (clamped_risk * 1.5):
                    approved_target = macro_ceiling
                else:
                    return RiskDecision(
                        status="REJECT",
                        action="WAIT_IN_CASH",
                        reason=f"REJECTED BY RISK GATE: Insufficient asymmetry. Reward (${reward_dist:,.1f}) < 1.5x Risk (${clamped_risk:,.1f}).",
                        telemetry={"reward_dist": reward_dist, "risk_dist": clamped_risk},
                    )
            else:
                approved_target = round(intent.target_price, 2)

            # --------------------------------------------------------------
            # INVARIANT 7: CONTINUOUS VOLATILITY-LIQUIDITY SIZING & SHADOW SELF (Spec Section 2.3 & 3)
            # --------------------------------------------------------------
            # Continuous target sizing: target_position = k * confidence * (liquidity / vol_regime)
            conf = float(intent.confidence or 0.75)
            f_vec = matrix.get("feature_vector", {})
            vol_regime = float(f_vec.get("vol_regime", 1.0))
            base_size_factor = round(float(np.clip(conf / max(vol_regime, 0.5), 0.25, 1.0)), 2)

            # Simulated adverse drop to approved noise-immune stop:
            stress_loss_pct = round(((price - approved_stop) / price) * 100.0, 3)
            size_factor = base_size_factor
            if stress_loss_pct > max_stress_risk_pct and stress_loss_pct > 0:
                # Dynamically clamp sizing so that dollar risk never breaches risk budget
                stress_clamp = round(max(0.1, max_stress_risk_pct / stress_loss_pct), 2)
                size_factor = min(size_factor, stress_clamp)
                logger.info(
                    f"[ShadowSelf] Stress drop ({stress_loss_pct:.2f}%) exceeds budget ({max_stress_risk_pct:.2f}%). Clamping Lot 1 size factor to {size_factor:.2f}"
                )

            # Apply Governor and Failure Counter multipliers
            setup_health = self.governor.get_health(intent.scenario)
            gov_mult = approved_size_mult
            fail_pen = self.failure_counter.get_failure_penalty(intent.scenario)
            composite_size_factor = round(float(np.clip(size_factor * gov_mult * fail_pen, 0.10, 1.0)), 2)

            final_status = "ALLOW" if (approved_stop == round(intent.proposed_stop, 2) and composite_size_factor == 1.0) else "MODIFY"

            combined_telemetry = dict(intent.telemetry)
            combined_telemetry.update({
                "shadow_stress_loss_pct": stress_loss_pct,
                "approved_size_factor": composite_size_factor,
                "governor_health_score": setup_health.health_score,
                "governor_size_mult": gov_mult,
                "failure_penalty": fail_pen,
                "consecutive_portfolio_losses": self.escalation.consecutive_losses,
                "eligibility": eligibility,
            })

            return RiskDecision(
                status=final_status,
                action="ENTER_CORE_LOT_1",
                scenario=intent.scenario,
                entry_price=price,
                target_price=approved_target,
                trailing_stop=approved_stop,
                expected_runway_pct=intent.expected_runway_pct,
                approved_size_factor=composite_size_factor,
                stress_loss_pct=stress_loss_pct,
                reason=intent.reason,
                telemetry=combined_telemetry,
            )

        # Default fallback: Wait in cash
        return RiskDecision(
            status="ALLOW",
            action="WAIT_IN_CASH",
            reason=intent.reason or "Risk gate standing by in cash",
            telemetry=intent.telemetry,
        )
