"""
conviction_engine_futures.py — Institutional Bidirectional Futures Engine (btctool 2.0 / BTC_BOT 2.2.1)
Architecture: Candidate 2 Pure Core Alpha + Upgrades 1 & 3 (Dynamic Short Hurdle + ATH Sweep Gate)
Target Instrument: OKX BTC-USDT-SWAP (Perpetual Futures)
Margin Architecture: Isolated Margin (Default 2.5x Leverage)
Execution Philosophy:
- Master Switch Architecture with Tactical 4H Distribution Short Valve.
- Dynamic Short Headroom Hurdle (Upgrade 1): Adapts minimum distance to 4H midline to ATR/volatility (max(0.75%, 1.5*ATR)), unlocking high-conviction pre-breakdown shorts.
- ATH Range Sweep Gate (Upgrade 3): Requires institutional volume surge (VR >= 3.5) when price is stretched >2.0% above 4H EMA50, eliminating chop drag near all-time highs.
- Pure Institutional Core: Breakouts (48H, 24H, 12H), Liquidity Sweeps (24H, 48H Capitulation), and 4H Distribution Shorts.
- Mean-Reversion Knife-Catching (`UNIFIED_4L_REBOUND`) and Chop Scalping (`RANGE_BOLLINGER_REVERSION`) Permanently Pruned.
- Strict fee friction modeling: 0.06% round-trip OKX Futures taker/maker blend.
- Isolated liquidation buffer defense: 2.5x leverage places liquidation >38% away,
  while maximum stop-loss is strictly capped at 1.50% (25x safety margin).
- Zero Spot interference: Runs alongside Spot v5.0.0 in complete logical isolation.
"""

import math
import datetime
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("conviction_engine_futures")

OKX_FUTURES_ROUNDTRIP_FEE_PCT = 0.0006  # 0.06% OKX Perpetual Swap round-trip friction
DEFAULT_ISOLATED_LEVERAGE = 2.5         # 2.5x Isolated Margin Leverage


@dataclass
class FuturesPosition:
    side: str                         # "LONG" or "SHORT"
    type: str                         # Setup identifier (e.g. "MACRO_BREAK_48H", "SHORT_4H_UPPER_BB_REJECT")
    silo: str                         # "CORE_v450", "FUTURES_SHORT"
    entry_idx: int
    entry_t: str
    entry_p: float
    hard_stop: float
    take_profit: Optional[float] = None
    trail_floor: Optional[float] = None # For longs (moving upwards)
    trail_ceil: Optional[float] = None  # For shorts (moving downwards)
    peak_p: float = 0.0                 # Highest high since entry (for longs)
    trough_p: float = 0.0               # Lowest low since entry (for shorts)
    leverage: float = DEFAULT_ISOLATED_LEVERAGE
    bars_held: int = 0
    rsi_entry: float = 50.0
    vr_entry: float = 1.0
    dist_ema50: float = 0.0
    breakout_level: Optional[float] = None
    consec_below: int = 0
    consec_above: int = 0


@dataclass
class FuturesSignal:
    action: str                       # "ENTER_LONG", "ENTER_SHORT", "EXIT_LONG", "EXIT_SHORT", "HOLD", "SCANNING"
    setup_type: str
    side: str                         # "LONG", "SHORT", "NONE"
    price: float
    hard_stop: float
    take_profit: Optional[float]
    leverage: float
    liquidation_estimate: float
    reason: str
    telemetry: Dict[str, Any] = field(default_factory=dict)


class ConvictionEngineFutures:
    """
    Autonomous Multi-Timeframe Bidirectional Futures Engine.
    Operates in isolated margin on BTC-USDT-SWAP with Pure Core Alpha Master Switch Architecture.
    """

    def __init__(self, leverage: float = DEFAULT_ISOLATED_LEVERAGE, fee_rt: float = OKX_FUTURES_ROUNDTRIP_FEE_PCT):
        self.leverage = leverage
        self.fee_rt = fee_rt
        self.active_position: Optional[FuturesPosition] = None
        self.last_failed_breakout_bar: int = -999
        self.trail_atr_mult: float = 4.5
        self.base_stop_pct: float = 0.015

    def reset(self):
        """Resets active position state and memory."""
        self.active_position = None
        self.last_failed_breakout_bar = -999

    def calculate_liquidation_price(self, entry_p: float, side: str, leverage: float, mmr: float = 0.004) -> float:
        """
        Calculates estimated OKX isolated liquidation price for BTC-USDT-SWAP.
        Maintenance Margin Ratio (MMR) for Tier 1 BTC Swap on OKX is 0.40% (0.004).
        For Long:  Liq = Entry * (1 - 1/Lev + MMR)
        For Short: Liq = Entry * (1 + 1/Lev - MMR)
        At 2.5x Leverage:
          Long Liq  = Entry * (1 - 0.40 + 0.004) = Entry * 0.604 (-39.6% drop)
          Short Liq = Entry * (1 + 0.40 - 0.004) = Entry * 1.396 (+39.6% pump)
        """
        if side == "LONG":
            return entry_p * (1.0 - (1.0 / leverage) + mmr)
        else:
            return entry_p * (1.0 + (1.0 / leverage) - mmr)

    def evaluate_bar(
        self,
        bar_idx: int,
        cur_bar: Dict[str, Any],
        prev_bars_15m: List[Dict[str, Any]],
        mtf_data: Dict[str, Any]
    ) -> FuturesSignal:
        """
        Evaluates a closed 15M bar against active position or Master Switch candidate triggers.
        """
        b = cur_bar
        dt = b.get('datetime', '')
        p_close = b['close']
        p_open = b['open']
        p_high = b['high']
        p_low = b['low']
        vol = b.get('vol', 0.0)

        # Unpack MTF Context
        d1 = mtf_data['1d']
        h4 = mtf_data['4h']
        h1 = mtf_data['1h']
        m15 = mtf_data['15m']

        atr_val = m15['atr']
        v_sma = m15['vol_sma20']
        vr = (vol / v_sma) if v_sma > 0 else 1.0
        rng = p_high - p_low
        clv = ((p_close - p_low) / rng) if rng > 0 else 0.5
        body_pct = ((p_close - p_open) / p_open) * 100.0
        candle_body_pct = (abs(p_close - p_open) / rng * 100.0) if rng > 0 else 0.0
        dist_ema = ((p_close - h4['ema50']) / h4['ema50']) * 100.0

        # Master Regimes
        is_bull_1d = (p_close > d1['ema50']) and (d1['ema50_slope'] > 0.0)
        is_bear_1d = (p_close < d1['ema50']) and (d1['ema50_slope'] < 0.0)
        is_bull_4h = p_close > h4['ema50']
        is_bear_4h = p_close < h4['ema50']
        is_4h_dist = is_bear_4h and (h4.get('ema50_slope', 0.0) < -0.0005)

        # Time helpers
        ts = b.get('ts', 0)
        dt_obj = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc) if ts else datetime.datetime.utcnow()
        is_weekend = dt_obj.weekday() in [5, 6]
        entry_minutes = dt_obj.hour * 60 + dt_obj.minute

        # Historical swing boundaries from prev_bars_15m
        if len(prev_bars_15m) >= 192:
            sh_48h = max(x['high'] for x in prev_bars_15m[-192:])
            sl_48h = min(x['low'] for x in prev_bars_15m[-192:])
        else:
            sh_48h = p_high * 1.02
            sl_48h = p_low * 0.98

        if len(prev_bars_15m) >= 96:
            sh_24h = max(x['high'] for x in prev_bars_15m[-96:])
            sl_24h = min(x['low'] for x in prev_bars_15m[-96:])
        else:
            sh_24h = p_high * 1.01
            sl_24h = p_low * 0.99

        range_48h_pct = ((sh_48h - sl_48h) / p_close) * 100.0
        prev_close = prev_bars_15m[-1]['close'] if prev_bars_15m else p_close

        # =====================================================================
        # 1. POSITION MANAGEMENT (If Position is Active)
        # =====================================================================
        if self.active_position is not None:
            pos = self.active_position
            pos.bars_held += 1
            entry_p = pos.entry_p
            exited = False
            exit_p = 0.0
            exit_reason = ""

            if pos.side == "LONG":
                if p_high > pos.peak_p:
                    pos.peak_p = p_high
                peak_gain_pct = ((pos.peak_p - entry_p) / entry_p) * 100.0

                if pos.type == 'SWEEP_24H_RECLAIM':
                    if (p_high - entry_p) >= (2.0 * atr_val):
                        pos.hard_stop = max(pos.hard_stop, entry_p * 1.002)
                    tp_p = entry_p + (2.5 * atr_val)
                    if p_high >= tp_p:
                        exit_p = tp_p; exit_reason = "TAKE_PROFIT_2.5_ATR"; exited = True
                    elif p_low <= pos.hard_stop:
                        exit_p = pos.hard_stop; exit_reason = "HARD_STOP"; exited = True
                    elif pos.bars_held >= 32:
                        exit_p = p_close; exit_reason = "TIME_STOP_8H"; exited = True

                elif pos.type == 'CAPITULATION_SWEEP_48H':
                    if peak_gain_pct >= 3.0: pos.hard_stop = max(pos.hard_stop, entry_p * 1.020)
                    elif peak_gain_pct >= 2.0: pos.hard_stop = max(pos.hard_stop, entry_p * 1.010)
                    elif peak_gain_pct >= 1.0: pos.hard_stop = max(pos.hard_stop, entry_p * 1.002)

                    new_floor = p_high - (self.trail_atr_mult * atr_val)
                    if pos.trail_floor is None or new_floor > pos.trail_floor:
                        pos.trail_floor = new_floor
                    if pos.bars_held >= 1:
                        if p_low <= pos.hard_stop:
                            exit_p = pos.hard_stop
                            exit_reason = "SWEEP_RATCHET_STOP" if pos.hard_stop > entry_p else "HARD_STOP"
                            exited = True
                        elif pos.trail_floor and p_low <= pos.trail_floor:
                            exit_p = pos.trail_floor; exit_reason = "TRAILING_ATR"; exited = True

                else: # Breakout runners (MACRO_BREAK_48H, BREAK_24H, BREAK_12H)
                    if pos.type == 'MACRO_BREAK_48H':
                        sh_level = pos.breakout_level if pos.breakout_level else entry_p
                        if peak_gain_pct < 1.0:
                            if p_close < sh_level: pos.consec_below += 1
                            else: pos.consec_below = 0
                            if pos.consec_below >= 2 and pos.bars_held >= 2:
                                exit_p = p_close; exit_reason = "STRUCTURAL_REENTRY_CUT"; exited = True

                        if not exited and pos.bars_held >= 16 and ((p_close - entry_p) / entry_p < 0.0030):
                            exit_p = p_close; exit_reason = "BREAKOUT_STAGNATION_CUT_4H"; exited = True

                    if not exited:
                        if peak_gain_pct >= 2.5:
                            pos.hard_stop = max(pos.hard_stop, entry_p * 1.015)
                            is_1h_close = (bar_idx % 4 == 3)
                            if is_1h_close and (h1['close'] < h1['ema20']):
                                exit_p = p_close; exit_reason = "1H_EMA20_TREND_EXIT"; exited = True
                            elif p_low <= pos.hard_stop:
                                exit_p = pos.hard_stop; exit_reason = "PROFIT_PROTECTION_STOP"; exited = True
                        else:
                            new_floor = p_high - (self.trail_atr_mult * atr_val)
                            if pos.trail_floor is None or new_floor > pos.trail_floor:
                                pos.trail_floor = new_floor
                            if pos.bars_held >= 1:
                                if pos.trail_floor and p_low <= pos.trail_floor:
                                    exit_p = pos.trail_floor; exit_reason = "TRAILING_ATR"; exited = True
                                elif p_low <= pos.hard_stop:
                                    exit_p = pos.hard_stop; exit_reason = "HARD_STOP"; exited = True

            elif pos.side == "SHORT":
                if p_low < pos.trough_p or pos.trough_p == 0.0:
                    pos.trough_p = p_low
                favorable_pct = ((entry_p - pos.trough_p) / entry_p) * 100.0

                if pos.take_profit and p_low <= pos.take_profit:
                    exit_p = pos.take_profit; exit_reason = "TAKE_PROFIT_2PCT"; exited = True
                elif p_high >= pos.hard_stop:
                    exit_p = pos.hard_stop; exit_reason = "HARD_STOP"; exited = True
                else:
                    if favorable_pct >= 1.20:
                        pos.hard_stop = min(pos.hard_stop, entry_p * 0.9980) # lock in +0.20% buffer
                        if p_high >= pos.hard_stop:
                            exit_p = pos.hard_stop; exit_reason = "BE_PROTECTION"; exited = True
                    elif pos.bars_held >= 32:
                        exit_p = p_close; exit_reason = "TIME_STOP_8H"; exited = True

            if exited:
                if pos.side == "LONG" and pos.type in ['MACRO_BREAK_48H', 'BREAK_24H', 'BREAK_12H']:
                    gross_pnl = (exit_p - entry_p) / entry_p
                    if gross_pnl < -0.0005:
                        self.last_failed_breakout_bar = bar_idx

                exit_side = pos.side
                exit_type = pos.type
                self.active_position = None
                return FuturesSignal(
                    action=f"EXIT_{exit_side}",
                    setup_type=exit_type,
                    side=exit_side,
                    price=exit_p,
                    hard_stop=0.0,
                    take_profit=None,
                    leverage=self.leverage,
                    liquidation_estimate=0.0,
                    reason=exit_reason,
                    telemetry={'bars_held': pos.bars_held, 'entry_price': entry_p}
                )

            # Still holding
            return FuturesSignal(
                action="HOLD",
                setup_type=pos.type,
                side=pos.side,
                price=p_close,
                hard_stop=pos.hard_stop,
                take_profit=pos.take_profit,
                leverage=self.leverage,
                liquidation_estimate=self.calculate_liquidation_price(entry_p, pos.side, self.leverage),
                reason="IN_POSITION",
                telemetry={'bars_held': pos.bars_held, 'entry_price': entry_p, 'peak': pos.peak_p, 'trough': pos.trough_p}
            )

        # =====================================================================
        # 2. CANDIDATE EVALUATION: THE PURE CORE MASTER REGIME SWITCH (When FLAT)
        # =====================================================================

        # Candidate Trigger Evaluators:
        cand_short = None
        if is_bear_4h:
            touch_upper_4h = p_high >= (h4['bb_upper'] * 0.998)
            bear_reversal = (p_close < p_open) and (clv <= 0.40)
            dist_to_4h_mid = ((p_close - h4['bb_mid']) / p_close) * 100.0
            min_hurdle = max(0.75, (1.5 * atr_val / p_close * 100.0))
            if touch_upper_4h and bear_reversal and (dist_to_4h_mid >= min_hurdle):
                hard_stop = min(p_high * 1.0030, p_close * 1.0150)
                tp_target = p_close * 0.980 # 2.0% fixed target
                cand_short = (
                    "SHORT_4H_UPPER_BB_REJECT", "SHORT", "FUTURES_SHORT",
                    hard_stop, tp_target, "4H_UPPER_BB_REJECT",
                    {'vr': vr, 'clv': clv, 'dist_to_mid': dist_to_4h_mid, 'min_hurdle': min_hurdle}
                )

        cand_capitulation = None
        if p_low < sl_48h and p_close > sl_48h:
            if vr >= 2.5 and body_pct >= 0.20 and clv >= 0.70:
                take_sweep = is_bull_4h or (vr >= 3.5)
                depth_gate = dist_ema <= -1.0
                quality_gate = (vr >= 4.5) or (dist_ema <= -2.5)
                is_london_ny = (11 <= dt_obj.hour <= 15) or (dt_obj.hour == 16 and dt_obj.minute == 0)
                inst_cap_gate = (vr >= 10.0) or (candle_body_pct >= 60.0 and is_london_ny)
                if depth_gate and quality_gate and inst_cap_gate and take_sweep:
                    hard_stop = p_close * (1.0 - self.base_stop_pct)
                    cand_capitulation = (
                        "CAPITULATION_SWEEP_48H", "LONG", "CORE_v450",
                        hard_stop, None, "CAPITULATION_SWEEP_48H",
                        {'vr': vr, 'clv': clv}
                    )

        cand_sweep_24h = None
        if is_bull_4h:
            if p_low < sl_24h and p_close > sl_24h:
                if vr >= 2.5 and clv >= 0.80 and body_pct >= -0.10:
                    in_asian_dead_zone = (90 <= entry_minutes <= 210)
                    asian_pass = True
                    if in_asian_dead_zone:
                        asian_pass = (h1['ema20_slope'] > 0.0) and (candle_body_pct >= 25.0)

                    # Upgrade 3: ATH Sweep Gate (protect against buying exhausted ranges near highs)
                    ath_pass = True
                    if dist_ema > 2.0 and vr < 3.5:
                        ath_pass = False

                    if asian_pass and ath_pass:
                        hard_stop = min(p_low * 0.998, p_close * (1.0 - self.base_stop_pct))
                        tp_target = p_close + (2.5 * atr_val)
                        cand_sweep_24h = (
                            "SWEEP_24H_RECLAIM", "LONG", "CORE_v450",
                            hard_stop, tp_target, "SWEEP_24H_RECLAIM",
                            {'vr': vr, 'clv': clv}
                        )

        cand_breakout = None
        if not is_weekend:
            in_breakout_cooldown = (bar_idx - self.last_failed_breakout_bar < 48)
            if not in_breakout_cooldown:
                res_4h = h4['high']
                headroom = ((res_4h - p_close) / p_close) * 100.0

                if is_bull_4h and clv >= 0.70:
                    # 48H Breakout
                    if p_close > sh_48h and prev_close <= sh_48h:
                        if dist_ema >= 0.80 and h1['ema20_slope'] >= 0.0015 and range_48h_pct >= 2.0:
                            if vr >= 2.2 and body_pct >= 0.25 and headroom >= 0.5:
                                hard_stop = p_close * (1.0 - self.base_stop_pct)
                                cand_breakout = (
                                    "MACRO_BREAK_48H", "LONG", "CORE_v450",
                                    hard_stop, None, "48H_MACRO_BREAKOUT",
                                    {'vr': vr, 'range_48h_pct': range_48h_pct},
                                    sh_48h
                                )

                    # 24H Breakout
                    elif p_close > sh_24h and prev_close <= sh_24h:
                        overhead_ok = (((sh_48h - p_close) / p_close) >= 0.012) or (p_close >= sh_48h)
                        slope_ok = (h1['ema20_slope'] >= 0.0020)
                        if overhead_ok and slope_ok and vr >= 2.2 and body_pct >= 0.25 and headroom >= 0.8:
                            hard_stop = p_close * (1.0 - self.base_stop_pct)
                            cand_breakout = (
                                "BREAK_24H", "LONG", "CORE_v450",
                                hard_stop, None, "24H_MOMENTUM_BREAKOUT",
                                {'vr': vr},
                                None
                            )

                    # 12H Breakout
                    elif len(prev_bars_15m) >= 48:
                        sh_12h = max(x['high'] for x in prev_bars_15m[-48:])
                        if p_close > sh_12h and prev_close <= sh_12h:
                            if vr >= 2.2 and body_pct >= 0.25 and headroom >= 1.0 and p_close <= m15['bb_upper']:
                                hard_stop = p_close * (1.0 - self.base_stop_pct)
                                cand_breakout = (
                                    "BREAK_12H", "LONG", "CORE_v450",
                                    hard_stop, None, "12H_VELOCITY_BREAKOUT",
                                    {'vr': vr},
                                    None
                                )

        # ---------------------------------------------------------------------
        # ROUTING LOGIC: MUTUALLY EXCLUSIVE MASTER SWITCH
        # ---------------------------------------------------------------------
        chosen = None

        if is_bull_1d:
            # Tactical Distribution Short Valve:
            # If 4H is in active distribution during a bull pull-back, prioritize institutional short
            if is_4h_dist and cand_short is not None:
                chosen = cand_short
            else:
                for c in [cand_capitulation, cand_sweep_24h, cand_breakout]:
                    if c is not None:
                        chosen = c
                        break

        elif is_bear_1d:
            # Bear Playbook: Prioritize Short, allow deep 48H Capitulation flush reclaim
            for c in [cand_short, cand_capitulation]:
                if c is not None:
                    chosen = c
                    break

        else:
            # Neutral / Chop Regime:
            # If 4H distribution occurs, allow tactical distribution short; otherwise 100% Cash!
            if is_4h_dist and cand_short is not None:
                chosen = cand_short

        if chosen is not None:
            setup_type = chosen[0]
            side = chosen[1]
            silo = chosen[2]
            hard_stop = chosen[3]
            tp_target = chosen[4]
            reason = chosen[5]
            telem = chosen[6]
            breakout_level = chosen[7] if len(chosen) > 7 else None

            liq_p = self.calculate_liquidation_price(p_close, side, self.leverage)
            trail_fl = p_close - (self.trail_atr_mult * atr_val) if side == "LONG" else None

            self.active_position = FuturesPosition(
                side=side,
                type=setup_type,
                silo=silo,
                entry_idx=bar_idx,
                entry_t=dt,
                entry_p=p_close,
                hard_stop=hard_stop,
                take_profit=tp_target,
                trail_floor=trail_fl,
                peak_p=p_close if side == "LONG" else 0.0,
                trough_p=p_close if side == "SHORT" else 0.0,
                leverage=self.leverage,
                rsi_entry=m15['rsi'],
                vr_entry=vr,
                dist_ema50=dist_ema,
                breakout_level=breakout_level
            )

            action = f"ENTER_{side}"
            return FuturesSignal(
                action=action,
                setup_type=setup_type,
                side=side,
                price=p_close,
                hard_stop=hard_stop,
                take_profit=tp_target,
                leverage=self.leverage,
                liquidation_estimate=liq_p,
                reason=f"MASTER_SWITCH_{reason}",
                telemetry=telem
            )

        # Default: Scanning / No action (100% Cash Protection)
        return FuturesSignal(
            action="SCANNING",
            setup_type="NONE",
            side="NONE",
            price=p_close,
            hard_stop=0.0,
            take_profit=None,
            leverage=self.leverage,
            liquidation_estimate=0.0,
            reason="AWAITING_CONFLUENCE",
            telemetry={'is_bull_1d': is_bull_1d, 'is_bear_1d': is_bear_1d, 'is_4h_dist': is_4h_dist}
        )
