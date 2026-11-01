"""
test_futures.py — Dedicated Institutional Unit Test Suite for Futures 2.2.1 (Candidate 2 Pure Core + Upgrades 1 & 3)
Target: OKX BTC-USDT-SWAP (Perpetual Futures)
Verifies:
1. Isolated Margin & Liquidation Boundary Mathematics (2.5x Leverage)
2. Short Alpha Trigger (SHORT_4H_UPPER_BB_REJECT) in Bear Market
3. Macro 1D Gate Rejection of Counter-Trend Shorts when 4H is not in distribution
4. Tactical 4H Distribution Short Valve (Allows short during 4H distribution in Bull pullback)
5. Short Take-Profit & Hard Stop Execution
6. Short Breakeven Protection Ratchet (+1.20% drop -> stop to Entry * 0.9980)
7. Verification that Rebounds & RBR are pruned; Capitulation Sweep 48H triggers on flush
8. Bidirectional State Machine Mutex (No self-hedging)
9. Failed Breakout Cooldown Integrity (48-bar lockout)
10. Dynamic Short Hurdle (Upgrade 1): Adapts minimum distance to 4H midline based on ATR
11. ATH Sweep Gate (Upgrade 3): Prunes false-reclaims in stretched ATH distribution ranges
"""

import unittest
from conviction_engine_futures import ConvictionEngineFutures, FuturesPosition, FuturesSignal


class TestConvictionEngineFutures(unittest.TestCase):

    def setUp(self):
        self.engine = ConvictionEngineFutures(leverage=2.5, fee_rt=0.0006)

    def test_01_isolated_leverage_and_liquidation_math(self):
        entry_p = 100000.0
        # Long Liquidation: entry * (1 - 1/2.5 + 0.004) = 100000 * (1 - 0.40 + 0.004) = 60,400.0
        long_liq = self.engine.calculate_liquidation_price(entry_p, "LONG", 2.5)
        self.assertAlmostEqual(long_liq, 60400.0, places=1)
        self.assertTrue((entry_p - long_liq) / entry_p >= 0.38) # >38% safety buffer

        # Short Liquidation: entry * (1 + 1/2.5 - 0.004) = 100000 * (1 + 0.40 - 0.004) = 139,600.0
        short_liq = self.engine.calculate_liquidation_price(entry_p, "SHORT", 2.5)
        self.assertAlmostEqual(short_liq, 139600.0, places=1)
        self.assertTrue((short_liq - entry_p) / entry_p >= 0.38) # >38% safety buffer

    def test_02_short_alpha_trigger_bear_upper_bb(self):
        # Setup: 1D Bear, 4H Bear, 15M candle tests 4H Upper BB and prints red reversal
        cur_bar = {'open': 82000.0, 'high': 82500.0, 'low': 81200.0, 'close': 81400.0, 'vol': 500.0, 'ts': 1762000000}
        prev_bars = [{'high': 82000.0, 'low': 80000.0, 'close': 81000.0} for _ in range(200)]
        mtf_data = {
            '1d': {'close': 81400.0, 'ema50': 90000.0, 'ema50_slope': -0.005}, # 1D Bear
            '4h': {'close': 81400.0, 'high': 82500.0, 'low': 79000.0, 'ema50': 85000.0, 'ema50_slope': -0.003,
                   'bb_mid': 80000.0, 'bb_upper': 82500.0, 'bb_lower': 77500.0}, # High touches Upper BB (82500), dist to mid >= 1.2%
            '1h': {'close': 81400.0, 'ema20': 81500.0, 'ema20_slope': -0.001, 'bb_mid': 81500.0, 'bb_upper': 82800.0, 'bb_lower': 80200.0},
            '15m': {'atr': 600.0, 'vol_sma20': 200.0, 'rsi': 58.0, 'bb_mid': 81600.0, 'bb_upper': 82400.0, 'bb_lower': 80800.0}
        }
        sig = self.engine.evaluate_bar(200, cur_bar, prev_bars, mtf_data)
        self.assertEqual(sig.action, "ENTER_SHORT")
        self.assertEqual(sig.setup_type, "SHORT_4H_UPPER_BB_REJECT")
        self.assertEqual(sig.side, "SHORT")
        self.assertEqual(sig.price, 81400.0)
        self.assertEqual(sig.take_profit, 81400.0 * 0.980) # 2.0% fixed target (79772.0)
        self.assertIsNotNone(self.engine.active_position)
        self.assertEqual(self.engine.active_position.side, "SHORT")

    def test_03_short_alpha_gated_by_1d_macro(self):
        # 1D Bullish and 4H has positive slope (not distribution) -> Should NOT short
        cur_bar = {'open': 82000.0, 'high': 82500.0, 'low': 81200.0, 'close': 81400.0, 'vol': 500.0, 'ts': 1762000000}
        prev_bars = [{'high': 82000.0, 'low': 80000.0, 'close': 81000.0} for _ in range(200)]
        mtf_data = {
            '1d': {'close': 81400.0, 'ema50': 78000.0, 'ema50_slope': +0.005}, # 1D BULL REGIME
            '4h': {'close': 81400.0, 'high': 82500.0, 'low': 79000.0, 'ema50': 80000.0, 'ema50_slope': +0.001, # POSITIVE SLOPE
                   'bb_mid': 80000.0, 'bb_upper': 82500.0, 'bb_lower': 77500.0},
            '1h': {'close': 81400.0, 'ema20': 81500.0, 'ema20_slope': +0.001, 'bb_mid': 81500.0, 'bb_upper': 82800.0, 'bb_lower': 80200.0},
            '15m': {'atr': 600.0, 'vol_sma20': 200.0, 'rsi': 58.0, 'bb_mid': 81600.0, 'bb_upper': 82400.0, 'bb_lower': 80800.0}
        }
        sig = self.engine.evaluate_bar(200, cur_bar, prev_bars, mtf_data)
        self.assertNotEqual(sig.action, "ENTER_SHORT")
        self.assertIsNone(self.engine.active_position)

    def test_04_tactical_distribution_short_in_bull_pullback(self):
        # 1D is Bullish (macro trend), but 4H is in active distribution (close < 4h ema50, slope < -0.0005)
        # Tactical Distribution Short Valve should fire!
        cur_bar = {'open': 82000.0, 'high': 82500.0, 'low': 81200.0, 'close': 81400.0, 'vol': 500.0, 'ts': 1762000000}
        prev_bars = [{'high': 82000.0, 'low': 80000.0, 'close': 81000.0} for _ in range(200)]
        mtf_data = {
            '1d': {'close': 81400.0, 'ema50': 78000.0, 'ema50_slope': +0.005}, # 1D BULL
            '4h': {'close': 81400.0, 'high': 82500.0, 'low': 79000.0, 'ema50': 83000.0, 'ema50_slope': -0.002, # 4H DISTRIBUTION
                   'bb_mid': 80000.0, 'bb_upper': 82500.0, 'bb_lower': 77500.0},
            '1h': {'close': 81400.0, 'ema20': 81500.0, 'ema20_slope': -0.001, 'bb_mid': 81500.0, 'bb_upper': 82800.0, 'bb_lower': 80200.0},
            '15m': {'atr': 600.0, 'vol_sma20': 200.0, 'rsi': 58.0, 'bb_mid': 81600.0, 'bb_upper': 82400.0, 'bb_lower': 80800.0}
        }
        sig = self.engine.evaluate_bar(200, cur_bar, prev_bars, mtf_data)
        self.assertEqual(sig.action, "ENTER_SHORT")
        self.assertEqual(sig.setup_type, "SHORT_4H_UPPER_BB_REJECT")
        self.assertEqual(sig.side, "SHORT")
        self.assertEqual(sig.price, 81400.0)

    def test_05_generic_short_take_profit_execution(self):
        # Put engine in active generic short position at 80,000, TP at 78,500
        self.engine.active_position = FuturesPosition(
            side="SHORT", type="GENERIC_SHORT", silo="FUTURES_SHORT",
            entry_idx=100, entry_t="2026-02-01 12:00", entry_p=80000.0,
            hard_stop=81200.0, take_profit=78500.0, trough_p=80000.0, leverage=2.5
        )
        cur_bar = {'open': 79000.0, 'high': 79200.0, 'low': 78400.0, 'close': 78600.0, 'vol': 100.0, 'ts': 1762001000}
        prev_bars = [{'high': 80000.0, 'low': 78500.0, 'close': 79000.0} for _ in range(50)]
        mtf_data = {
            '1d': {'close': 78600.0, 'ema50': 85000.0, 'ema50_slope': -0.002},
            '4h': {'close': 78600.0, 'high': 80000.0, 'low': 78400.0, 'ema50': 83000.0, 'ema50_slope': -0.002, 'bb_mid': 78500.0, 'bb_upper': 81000.0, 'bb_lower': 76000.0},
            '1h': {'close': 78600.0, 'ema20': 79000.0, 'ema20_slope': -0.001, 'bb_mid': 79000.0, 'bb_upper': 80000.0, 'bb_lower': 78000.0},
            '15m': {'atr': 400.0, 'vol_sma20': 150.0, 'rsi': 40.0, 'bb_mid': 78900.0, 'bb_upper': 79500.0, 'bb_lower': 78300.0}
        }
        sig = self.engine.evaluate_bar(105, cur_bar, prev_bars, mtf_data)
        self.assertEqual(sig.action, "EXIT_SHORT")
        self.assertEqual(sig.price, 78500.0)
        self.assertEqual(sig.reason, "TAKE_PROFIT_2PCT")
        self.assertIsNone(self.engine.active_position)

    def test_06_short_breakeven_protection_ratchet(self):
        # Put engine in active short at 80,000, initial SL at 81,200 (+1.5%)
        self.engine.active_position = FuturesPosition(
            side="SHORT", type="SHORT_4H_UPPER_BB_REJECT", silo="FUTURES_SHORT",
            entry_idx=100, entry_t="2026-02-01 12:00", entry_p=80000.0,
            hard_stop=81200.0, take_profit=77500.0, trough_p=80000.0, leverage=2.5
        )
        cur_bar = {'open': 79800.0, 'high': 79820.0, 'low': 79000.0, 'close': 79100.0, 'vol': 100.0, 'ts': 1762001000}
        prev_bars = [{'high': 80000.0, 'low': 79500.0, 'close': 79800.0} for _ in range(50)]
        mtf_data = {
            '1d': {'close': 79100.0, 'ema50': 85000.0, 'ema50_slope': -0.002},
            '4h': {'close': 79100.0, 'high': 80000.0, 'low': 78400.0, 'ema50': 83000.0, 'ema50_slope': -0.002, 'bb_mid': 77500.0, 'bb_upper': 81000.0, 'bb_lower': 75000.0},
            '1h': {'close': 79100.0, 'ema20': 79500.0, 'ema20_slope': -0.001, 'bb_mid': 77500.0, 'bb_upper': 80500.0, 'bb_lower': 78500.0},
            '15m': {'atr': 400.0, 'vol_sma20': 150.0, 'rsi': 45.0, 'bb_mid': 79400.0, 'bb_upper': 80000.0, 'bb_lower': 78800.0}
        }
        sig = self.engine.evaluate_bar(101, cur_bar, prev_bars, mtf_data)
        self.assertEqual(sig.action, "HOLD")
        self.assertAlmostEqual(self.engine.active_position.hard_stop, 79840.0, places=1)

    def test_07_pruned_knife_catch_rejection_and_capitulation_sweep(self):
        # 1. Verify UNIFIED_4L_REBOUND conditions are PRUNED (Zero entries)
        cur_bar = {'open': 69800.0, 'high': 70500.0, 'low': 69500.0, 'close': 70400.0, 'vol': 600.0, 'ts': 1762002000}
        prev_bars = [{'high': 72000.0, 'low': 70000.0, 'close': 71000.0} for _ in range(200)]
        mtf_data = {
            '1d': {'close': 70400.0, 'ema50': 75000.0, 'ema50_slope': -0.002},
            '4h': {'close': 70400.0, 'high': 74000.0, 'low': 69000.0, 'ema50': 73000.0, 'ema50_slope': -0.001,
                   'bb_mid': 72000.0, 'bb_upper': 75000.0, 'bb_lower': 69000.0},
            '1h': {'close': 70400.0, 'ema20': 72200.0, 'ema20_slope': -0.001,
                   'bb_mid': 72200.0, 'bb_upper': 73500.0, 'bb_lower': 70300.0},
            '15m': {'atr': 500.0, 'vol_sma20': 200.0, 'rsi': 28.0, 'bb_mid': 71200.0, 'bb_upper': 72400.0, 'bb_lower': 70000.0}
        }
        # In Candidate 2, UNIFIED_4L_REBOUND is completely pruned
        sig = self.engine.evaluate_bar(200, cur_bar, prev_bars, mtf_data)
        self.assertNotEqual(sig.setup_type, "UNIFIED_4L_REBOUND")

        # 2. Verify CAPITULATION_SWEEP_48H triggers on institutional flush reclaim
        # Price dips below 48H low (69,000) to 68,500 and reclaims to 69,500 with extreme volume (VR=12.0) during London/NY (hour 12)
        cur_bar_cap = {'open': 68800.0, 'high': 69600.0, 'low': 68500.0, 'close': 69500.0, 'vol': 2400.0, 'ts': 1762002000} # ts hour 12:00
        prev_bars_cap = [{'high': 72000.0, 'low': 69000.0, 'close': 71000.0} for _ in range(200)] # 48h low is 69000
        sig_cap = self.engine.evaluate_bar(200, cur_bar_cap, prev_bars_cap, mtf_data)
        self.assertEqual(sig_cap.action, "ENTER_LONG")
        self.assertEqual(sig_cap.setup_type, "CAPITULATION_SWEEP_48H")
        self.assertEqual(sig_cap.side, "LONG")

    def test_08_bidirectional_state_machine_mutex(self):
        # Set engine in active LONG position (SWEEP_24H_RECLAIM)
        self.engine.active_position = FuturesPosition(
            side="LONG", type="SWEEP_24H_RECLAIM", silo="CORE_v450",
            entry_idx=100, entry_t="2026-02-01 12:00", entry_p=70400.0,
            hard_stop=69300.0, take_profit=73000.0, peak_p=70400.0, leverage=2.5
        )
        cur_bar = {'open': 70800.0, 'high': 71100.0, 'low': 70600.0, 'close': 70900.0, 'vol': 500.0, 'ts': 1762003000}
        prev_bars = [{'high': 72000.0, 'low': 70000.0, 'close': 71000.0} for _ in range(50)]
        mtf_data = {
            '1d': {'close': 70900.0, 'ema50': 75000.0, 'ema50_slope': -0.002},
            '4h': {'close': 70900.0, 'high': 71100.0, 'low': 69000.0, 'ema50': 73000.0, 'ema50_slope': -0.001, 'bb_mid': 70000.0, 'bb_upper': 71100.0, 'bb_lower': 68500.0},
            '1h': {'close': 70900.0, 'ema20': 71200.0, 'ema20_slope': -0.001, 'bb_mid': 73000.0, 'bb_upper': 74000.0, 'bb_lower': 70400.0},
            '15m': {'atr': 400.0, 'vol_sma20': 150.0, 'rsi': 45.0, 'bb_mid': 71000.0, 'bb_upper': 71600.0, 'bb_lower': 70400.0}
        }
        sig = self.engine.evaluate_bar(102, cur_bar, prev_bars, mtf_data)
        self.assertEqual(sig.action, "HOLD")
        self.assertEqual(sig.side, "LONG")
        self.assertEqual(self.engine.active_position.side, "LONG")

    def test_09_failed_breakout_cooldown_futures(self):
        # Position entered as MACRO_BREAK_48H at 80,000
        self.engine.active_position = FuturesPosition(
            side="LONG", type="MACRO_BREAK_48H", silo="CORE_v450",
            entry_idx=100, entry_t="2026-02-01 12:00", entry_p=80000.0,
            hard_stop=78800.0, breakout_level=79500.0, leverage=2.5
        )
        cur_bar = {'open': 78900.0, 'high': 79000.0, 'low': 78500.0, 'close': 78600.0, 'vol': 100.0, 'ts': 1762004000}
        prev_bars = [{'high': 80000.0, 'low': 79000.0, 'close': 79500.0} for _ in range(50)]
        mtf_data = {
            '1d': {'close': 78600.0, 'ema50': 75000.0, 'ema50_slope': +0.001},
            '4h': {'close': 78600.0, 'high': 80000.0, 'low': 78000.0, 'ema50': 77000.0, 'ema50_slope': +0.001, 'bb_mid': 78000.0, 'bb_upper': 81000.0, 'bb_lower': 75000.0},
            '1h': {'close': 78600.0, 'ema20': 78500.0, 'ema20_slope': +0.001, 'bb_mid': 78500.0, 'bb_upper': 79500.0, 'bb_lower': 77500.0},
            '15m': {'atr': 400.0, 'vol_sma20': 150.0, 'rsi': 45.0, 'bb_mid': 78700.0, 'bb_upper': 79300.0, 'bb_lower': 78100.0}
        }
        sig = self.engine.evaluate_bar(105, cur_bar, prev_bars, mtf_data)
        self.assertEqual(sig.action, "EXIT_LONG")
        self.assertEqual(sig.reason, "HARD_STOP")
        self.assertEqual(self.engine.last_failed_breakout_bar, 105)

    def test_10_dynamic_short_hurdle_upgrade_1(self):
        # Upgrade 1: Dynamic Short Hurdle adapts minimum distance to 4H midline based on ATR
        # When ATR is low (e.g. 400 at price 80,000 -> 1.5 * 400 / 80000 * 100 = 0.75%), min_hurdle is 0.75%.
        # A setup with dist_to_4h_mid = 0.90% (e.g. close=80,000, 4h mid=79,280 -> dist=0.90%)
        # would FAIL the legacy rigid 1.20% hurdle, but PASSES Upgrade 1's dynamic 0.75% hurdle.
        cur_bar = {'open': 80500.0, 'high': 80800.0, 'low': 79800.0, 'close': 80000.0, 'vol': 500.0, 'ts': 1762000000}
        prev_bars = [{'high': 80800.0, 'low': 79000.0, 'close': 80000.0} for _ in range(200)]
        mtf_data = {
            '1d': {'close': 80000.0, 'ema50': 85000.0, 'ema50_slope': -0.005}, # 1D Bear
            '4h': {'close': 80000.0, 'high': 80900.0, 'low': 78000.0, 'ema50': 83000.0, 'ema50_slope': -0.003,
                   'bb_mid': 79280.0, 'bb_upper': 80850.0, 'bb_lower': 77710.0}, # dist_to_mid = 0.90%, high touches upper BB
            '1h': {'close': 80000.0, 'ema20': 80200.0, 'ema20_slope': -0.001, 'bb_mid': 80200.0, 'bb_upper': 81200.0, 'bb_lower': 79200.0},
            '15m': {'atr': 400.0, 'vol_sma20': 200.0, 'rsi': 55.0, 'bb_mid': 80100.0, 'bb_upper': 80800.0, 'bb_lower': 79400.0}
        }
        sig = self.engine.evaluate_bar(200, cur_bar, prev_bars, mtf_data)
        self.assertEqual(sig.action, "ENTER_SHORT")
        self.assertEqual(sig.setup_type, "SHORT_4H_UPPER_BB_REJECT")
        self.assertAlmostEqual(sig.telemetry['min_hurdle'], 0.75, places=2)
        self.assertTrue(sig.telemetry['dist_to_mid'] >= sig.telemetry['min_hurdle'])

        # Now test rejection when dist_to_mid < min_hurdle (e.g. 4H mid is 79,600 -> dist = 0.50% < 0.75%)
        mtf_data_reject = dict(mtf_data)
        mtf_data_reject['4h'] = dict(mtf_data['4h'])
        mtf_data_reject['4h']['bb_mid'] = 79600.0 # dist_to_mid = 0.50%
        engine2 = ConvictionEngineFutures(leverage=2.5, fee_rt=0.0006)
        sig2 = engine2.evaluate_bar(200, cur_bar, prev_bars, mtf_data_reject)
        self.assertNotEqual(sig2.action, "ENTER_SHORT")

    def test_11_ath_sweep_gate_upgrade_3(self):
        # Upgrade 3: ATH Sweep Gate prunes false-reclaims in stretched ATH distribution ranges.
        # When price is > 2.0% above 4H EMA50 (dist_ema > 2.0%), require institutional volume VR >= 3.5.
        # Case A: dist_ema > 2.0% and VR = 2.6 (< 3.5) -> Must be BLOCKED.
        # 4H EMA50 = 85,000, Close = 87,000 -> dist_ema = (87000 - 85000)/85000 * 100 = +2.35%
        # 24H low = 86,500, cur_bar low = 86,200, close = 87,000 (reclaims 24H low)
        cur_bar_blocked = {'open': 86400.0, 'high': 87100.0, 'low': 86200.0, 'close': 87000.0, 'vol': 520.0, 'ts': 1762020000} # vol/vol_sma20 = 520/200 = 2.6
        prev_bars = [{'high': 88000.0, 'low': 86500.0, 'close': 87200.0} for _ in range(200)] # 24H low is 86,500
        mtf_data = {
            '1d': {'close': 87000.0, 'ema50': 80000.0, 'ema50_slope': +0.005},
            '4h': {'close': 87000.0, 'high': 88500.0, 'low': 84500.0, 'ema50': 85000.0, 'ema50_slope': +0.003, # dist_ema = +2.35%
                   'bb_mid': 86500.0, 'bb_upper': 88500.0, 'bb_lower': 84500.0},
            '1h': {'close': 87000.0, 'ema20': 86800.0, 'ema20_slope': +0.002, 'bb_mid': 86800.0, 'bb_upper': 87500.0, 'bb_lower': 86100.0},
            '15m': {'atr': 500.0, 'vol_sma20': 200.0, 'rsi': 55.0, 'bb_mid': 86600.0, 'bb_upper': 87300.0, 'bb_lower': 85900.0}
        }
        engine_a = ConvictionEngineFutures(leverage=2.5, fee_rt=0.0006)
        sig_a = engine_a.evaluate_bar(200, cur_bar_blocked, prev_bars, mtf_data)
        self.assertNotEqual(sig_a.action, "ENTER_LONG", "ATH Sweep Gate should have blocked VR=2.6 when dist_ema > 2.0%")

        # Case B: dist_ema > 2.0% but institutional surge VR >= 3.5 (e.g. vol = 760 -> VR = 3.8) -> PASSES!
        cur_bar_pass = {'open': 86400.0, 'high': 87100.0, 'low': 86200.0, 'close': 87000.0, 'vol': 760.0, 'ts': 1762020000}
        engine_b = ConvictionEngineFutures(leverage=2.5, fee_rt=0.0006)
        sig_b = engine_b.evaluate_bar(200, cur_bar_pass, prev_bars, mtf_data)
        self.assertEqual(sig_b.action, "ENTER_LONG")
        self.assertEqual(sig_b.setup_type, "SWEEP_24H_RECLAIM")

    def test_12_short_runner_valve_rec_1(self):
        # Recommendation 1: Asymmetric Short Runner Valve
        # When in SHORT_4H_UPPER_BB_REJECT entered at 80,000:
        # Phase 1: Price reaches +2.0% profit target (80,000 * 0.98 = 78,400)
        # -> Banks Tranche 1 (50%), ratchets stop to BE (+0.20% buffer: 79,840), and stays in position (HOLD, RUNNER_ACTIVE)
        self.engine.active_position = FuturesPosition(
            side="SHORT", type="SHORT_4H_UPPER_BB_REJECT", silo="FUTURES_SHORT",
            entry_idx=100, entry_t="2026-02-01 12:00", entry_p=80000.0,
            hard_stop=81200.0, take_profit=78400.0, trough_p=80000.0, leverage=2.5
        )
        cur_bar_t1 = {'open': 79000.0, 'high': 79200.0, 'low': 78400.0, 'close': 78600.0, 'vol': 100.0, 'ts': 1762001000}
        prev_bars = [{'high': 80000.0, 'low': 78500.0, 'close': 79000.0} for _ in range(50)]
        mtf_data_hold = {
            '1d': {'close': 78600.0, 'ema50': 85000.0, 'ema50_slope': -0.002},
            '4h': {'close': 78600.0, 'high': 80000.0, 'low': 78400.0, 'ema50': 83000.0, 'ema50_slope': -0.002, 'bb_mid': 78500.0, 'bb_upper': 81000.0, 'bb_lower': 76000.0},
            '1h': {'close': 78600.0, 'ema20': 79000.0, 'ema20_slope': -0.001, 'bb_mid': 79000.0, 'bb_upper': 80000.0, 'bb_lower': 78000.0},
            '15m': {'atr': 400.0, 'vol_sma20': 150.0, 'rsi': 40.0, 'bb_mid': 78900.0, 'bb_upper': 79500.0, 'bb_lower': 78300.0}
        }
        sig_t1 = self.engine.evaluate_bar(105, cur_bar_t1, prev_bars, mtf_data_hold)
        self.assertEqual(sig_t1.action, "HOLD")
        self.assertEqual(sig_t1.reason, "RUNNER_ACTIVE")
        self.assertTrue(self.engine.active_position.t1_banked)
        self.assertEqual(self.engine.active_position.t1_ret, 0.020)
        self.assertAlmostEqual(self.engine.active_position.hard_stop, 79840.0, places=1)

        # Phase 2: Tranche 2 trails until 1H EMA20 crossover
        # Bar 107 is 1H close (107 % 4 == 3). 1H close (79,200) > 1H EMA20 (79,000)
        cur_bar_exit = {'open': 78800.0, 'high': 79300.0, 'low': 78700.0, 'close': 79200.0, 'vol': 120.0, 'ts': 1762004000}
        mtf_data_exit = {
            '1d': {'close': 79200.0, 'ema50': 85000.0, 'ema50_slope': -0.002},
            '4h': {'close': 79200.0, 'high': 80000.0, 'low': 78400.0, 'ema50': 83000.0, 'ema50_slope': -0.002, 'bb_mid': 78500.0, 'bb_upper': 81000.0, 'bb_lower': 76000.0},
            '1h': {'close': 79200.0, 'ema20': 79000.0, 'ema20_slope': -0.001, 'bb_mid': 79000.0, 'bb_upper': 80000.0, 'bb_lower': 78000.0},
            '15m': {'atr': 400.0, 'vol_sma20': 150.0, 'rsi': 48.0, 'bb_mid': 78900.0, 'bb_upper': 79500.0, 'bb_lower': 78300.0}
        }
        sig_exit = self.engine.evaluate_bar(107, cur_bar_exit, prev_bars, mtf_data_exit)
        self.assertEqual(sig_exit.action, "EXIT_SHORT")
        self.assertEqual(sig_exit.reason, "RUNNER_1H_EMA20_EXIT")
        self.assertTrue(sig_exit.telemetry['t1_banked'])
        self.assertEqual(sig_exit.telemetry['t1_ret'], 0.020)
        self.assertIsNone(self.engine.active_position)

    def test_13_volatility_sizing_and_dynamic_risk_budget_rec_3(self):
        # Recommendation 3: Volatility-Adjusted Sizing & Dynamic Risk Budget
        # Case A: Low Volatility (Tight Coil, ATR% = 0.40% <= 0.48%) -> Leverage scales to 3.125x max,
        # and Dynamic Risk Budget clamps stop loss to 1.20% (0.0375 / 3.125 = 0.0120), capping equity risk to 3.75%.
        # ts = 1762172800 is Monday (weekday, not blocked by weekend filter)
        cur_bar_coil = {'open': 79950.0, 'high': 80250.0, 'low': 79900.0, 'close': 80220.0, 'vol': 800.0, 'ts': 1762172800}
        prev_bars = [{'high': 80000.0, 'low': 78000.0, 'close': 79900.0} for _ in range(200)] # 48H high is 80000, low is 78000 (range = 2.56% >= 2.0%)
        # atr = 320.88 at price 80,220 -> atr_pct = 320.88 / 80220 * 100 = 0.40%
        # size_scale = min(1.25, 0.60 / 0.40 = 1.50) = 1.25 -> eff_leverage = 2.5 * 1.25 = 3.125x
        # active_stop_pct = min(0.015, 0.0375 / 3.125) = 0.0120 (1.20%)
        mtf_data_coil = {
            '1d': {'close': 80220.0, 'ema50': 75000.0, 'ema50_slope': +0.005},
            '4h': {'close': 80220.0, 'high': 82000.0, 'low': 78000.0, 'ema50': 78000.0, 'ema50_slope': +0.003,
                   'bb_mid': 79000.0, 'bb_upper': 82500.0, 'bb_lower': 77000.0},
            '1h': {'close': 80220.0, 'ema20': 79500.0, 'ema20_slope': +0.002, 'bb_mid': 79500.0, 'bb_upper': 80500.0, 'bb_lower': 78500.0},
            '15m': {'atr': 320.88, 'vol_sma20': 200.0, 'rsi': 60.0, 'bb_mid': 79800.0, 'bb_upper': 80400.0, 'bb_lower': 79200.0}
        }
        engine_coil = ConvictionEngineFutures(leverage=2.5, fee_rt=0.0006)
        sig_coil = engine_coil.evaluate_bar(200, cur_bar_coil, prev_bars, mtf_data_coil)
        self.assertEqual(sig_coil.action, "ENTER_LONG")
        self.assertEqual(sig_coil.setup_type, "MACRO_BREAK_48H")
        self.assertAlmostEqual(sig_coil.leverage, 3.125, places=3)
        self.assertAlmostEqual(sig_coil.telemetry['active_stop_pct'], 0.0120, places=4)
        # Verify hard_stop price is exactly 1.20% below close: 80220 * (1 - 0.0120)
        self.assertAlmostEqual(sig_coil.hard_stop, 80220.0 * 0.9880, places=1)
        # Verify max single trade equity risk is strictly capped at 3.75%:
        equity_risk = sig_coil.leverage * sig_coil.telemetry['active_stop_pct']
        self.assertAlmostEqual(equity_risk, 0.0375, places=4)

        # Case B: High Volatility (Chaotic wicks, ATR% = 1.0%) -> Leverage scales to 1.75x min,
        # and Dynamic Risk Budget maintains stop loss at base 1.50%.
        # atr = 802.2 at price 80,220 -> atr_pct = 1.0%
        # size_scale = max(0.70, 0.60 / 1.00 = 0.60) = 0.70 -> eff_leverage = 2.5 * 0.70 = 1.75x
        # active_stop_pct = min(0.015, 0.0375 / 1.75 = 0.0214) = 0.0150 (1.50%)
        mtf_data_high_vol = dict(mtf_data_coil)
        mtf_data_high_vol['15m'] = dict(mtf_data_coil['15m'])
        mtf_data_high_vol['15m']['atr'] = 802.2
        engine_high_vol = ConvictionEngineFutures(leverage=2.5, fee_rt=0.0006)
        sig_high_vol = engine_high_vol.evaluate_bar(200, cur_bar_coil, prev_bars, mtf_data_high_vol)
        self.assertEqual(sig_high_vol.action, "ENTER_LONG")
        self.assertAlmostEqual(sig_high_vol.leverage, 1.75, places=3)
        self.assertAlmostEqual(sig_high_vol.telemetry['active_stop_pct'], 0.0150, places=4)
        equity_risk_high_vol = sig_high_vol.leverage * sig_high_vol.telemetry['active_stop_pct']
        self.assertTrue(equity_risk_high_vol <= 0.0375)


if __name__ == "__main__":
    unittest.main()
