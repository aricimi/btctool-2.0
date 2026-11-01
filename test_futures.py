"""
test_futures.py — Dedicated Institutional Unit Test Suite for Futures 2.1 (BTC-USDT-SWAP)
Verifies:
1. Isolated Margin & Liquidation Boundary Mathematics (2.5x Leverage)
2. Short Alpha Trigger (SHORT_4H_UPPER_BB_REJECT)
3. Macro 1D Gate Rejection of Counter-Trend Shorts
4. Short Take-Profit & Hard Stop Execution
5. Short Breakeven Protection Ratchet (+1.20% drop -> stop to Entry * 0.9980)
6. Long Unified 4-Layer Rebound Execution in Futures Mode
7. Bidirectional State Machine Mutex (No self-hedging)
8. Failed Breakout Cooldown Integrity
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
                   'bb_mid': 80000.0, 'bb_upper': 82500.0, 'bb_lower': 77500.0}, # High touches Upper BB (82500), dist to mid: (81400-80000)/81400 = 1.72% >= 1.2%
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
        # Same technical setup, but 1D is Bullish (ema50_slope > 0, close > ema50)
        cur_bar = {'open': 82000.0, 'high': 82500.0, 'low': 81200.0, 'close': 81400.0, 'vol': 500.0, 'ts': 1762000000}
        prev_bars = [{'high': 82000.0, 'low': 80000.0, 'close': 81000.0} for _ in range(200)]
        mtf_data = {
            '1d': {'close': 81400.0, 'ema50': 78000.0, 'ema50_slope': +0.005}, # 1D BULL REGIME
            '4h': {'close': 81400.0, 'high': 82500.0, 'low': 79000.0, 'ema50': 80000.0, 'ema50_slope': +0.001,
                   'bb_mid': 80000.0, 'bb_upper': 82500.0, 'bb_lower': 77500.0},
            '1h': {'close': 81400.0, 'ema20': 81500.0, 'ema20_slope': +0.001, 'bb_mid': 81500.0, 'bb_upper': 82800.0, 'bb_lower': 80200.0},
            '15m': {'atr': 600.0, 'vol_sma20': 200.0, 'rsi': 58.0, 'bb_mid': 81600.0, 'bb_upper': 82400.0, 'bb_lower': 80800.0}
        }
        sig = self.engine.evaluate_bar(200, cur_bar, prev_bars, mtf_data)
        # Should NOT short into a 1D bull trend
        self.assertNotEqual(sig.action, "ENTER_SHORT")
        self.assertIsNone(self.engine.active_position)

    def test_04_short_take_profit_execution(self):
        # Put engine in active short position at 80,000, TP at 78,500
        self.engine.active_position = FuturesPosition(
            side="SHORT", type="SHORT_4H_UPPER_BB_REJECT", silo="FUTURES_SHORT",
            entry_idx=100, entry_t="2026-02-01 12:00", entry_p=80000.0,
            hard_stop=81200.0, take_profit=78500.0, trough_p=80000.0, leverage=2.5
        )
        # Bar drops to low of 78,400 (hitting TP)
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
        self.assertEqual(sig.price, 78500.0) # Closed at target
        self.assertEqual(sig.reason, "TAKE_PROFIT_2PCT")
        self.assertIsNone(self.engine.active_position)

    def test_05_short_breakeven_protection_ratchet(self):
        # Put engine in active short at 80,000, initial SL at 81,200 (+1.5%)
        self.engine.active_position = FuturesPosition(
            side="SHORT", type="SHORT_4H_UPPER_BB_REJECT", silo="FUTURES_SHORT",
            entry_idx=100, entry_t="2026-02-01 12:00", entry_p=80000.0,
            hard_stop=81200.0, take_profit=77500.0, trough_p=80000.0, leverage=2.5
        )
        # Bar drops cleanly from 79,800 to 79,000 (drop is (80000 - 79000)/80000 = 1.25% >= 1.20% BE hurdle)
        # High stays at 79,820 (below the 79,840 ratchet level)
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
        # Hard stop should have ratcheted down to entry * 0.9980 = 79,840.0
        self.assertAlmostEqual(self.engine.active_position.hard_stop, 79840.0, places=1)

    def test_06_long_unified_4l_rebound_futures(self):
        # 15M candle pierces lower band (low < 70,000) and reclaims (close = 70,400 > 70,000)
        # 1H %B <= 0.05, 4H %B <= 0.35, Headroom >= 2.0%, VR >= 2.5, CLV >= 0.75
        cur_bar = {'open': 69800.0, 'high': 70500.0, 'low': 69500.0, 'close': 70400.0, 'vol': 600.0, 'ts': 1762002000}
        prev_bars = [{'high': 72000.0, 'low': 70000.0, 'close': 71000.0} for _ in range(200)]
        mtf_data = {
            '1d': {'close': 70400.0, 'ema50': 75000.0, 'ema50_slope': -0.002},
            '4h': {'close': 70400.0, 'high': 74000.0, 'low': 69000.0, 'ema50': 73000.0, 'ema50_slope': -0.001,
                   'bb_mid': 72000.0, 'bb_upper': 75000.0, 'bb_lower': 69000.0}, # %B = (70400-69000)/6000 = 0.233 <= 0.35
            '1h': {'close': 70400.0, 'ema20': 72200.0, 'ema20_slope': -0.001,
                   'bb_mid': 72200.0, 'bb_upper': 73500.0, 'bb_lower': 70300.0}, # %B = (70400-70300)/3200 = 0.031 <= 0.05, Headroom = (72200-70400)/70400 = 2.55% >= 2.0%
            '15m': {'atr': 500.0, 'vol_sma20': 200.0, 'rsi': 28.0, 'bb_mid': 71200.0, 'bb_upper': 72400.0, 'bb_lower': 70000.0}
        }
        sig = self.engine.evaluate_bar(200, cur_bar, prev_bars, mtf_data)
        self.assertEqual(sig.action, "ENTER_LONG")
        self.assertEqual(sig.setup_type, "UNIFIED_4L_REBOUND")
        self.assertEqual(sig.side, "LONG")
        self.assertEqual(sig.price, 70400.0)
        self.assertEqual(sig.take_profit, 72200.0) # 1H midline target
        self.assertEqual(sig.leverage, 2.5)
        self.assertIsNotNone(self.engine.active_position)
        self.assertEqual(self.engine.active_position.side, "LONG")

    def test_07_bidirectional_state_machine_mutex(self):
        # Set engine in active LONG position (target at 73,000)
        self.engine.active_position = FuturesPosition(
            side="LONG", type="UNIFIED_4L_REBOUND", silo="TIER_1_REBOUND",
            entry_idx=100, entry_t="2026-02-01 12:00", entry_p=70400.0,
            hard_stop=69300.0, take_profit=73000.0, peak_p=70400.0, leverage=2.5
        )
        # Bar arrives that would otherwise qualify as a short trigger (4H upper band touch)
        cur_bar = {'open': 71000.0, 'high': 71500.0, 'low': 70800.0, 'close': 70900.0, 'vol': 500.0, 'ts': 1762003000}
        prev_bars = [{'high': 72000.0, 'low': 70000.0, 'close': 71000.0} for _ in range(50)]
        mtf_data = {
            '1d': {'close': 70900.0, 'ema50': 75000.0, 'ema50_slope': -0.002},
            '4h': {'close': 70900.0, 'high': 71500.0, 'low': 69000.0, 'ema50': 73000.0, 'ema50_slope': -0.001, 'bb_mid': 70000.0, 'bb_upper': 71500.0, 'bb_lower': 68500.0},
            '1h': {'close': 70900.0, 'ema20': 71200.0, 'ema20_slope': -0.001, 'bb_mid': 73000.0, 'bb_upper': 74000.0, 'bb_lower': 70400.0},
            '15m': {'atr': 400.0, 'vol_sma20': 150.0, 'rsi': 45.0, 'bb_mid': 71000.0, 'bb_upper': 71600.0, 'bb_lower': 70400.0}
        }
        sig = self.engine.evaluate_bar(102, cur_bar, prev_bars, mtf_data)
        # Engine MUST hold the long position, NOT open a short (mutex protection)
        self.assertEqual(sig.action, "HOLD")
        self.assertEqual(sig.side, "LONG")
        self.assertEqual(self.engine.active_position.side, "LONG")

    def test_08_failed_breakout_cooldown_futures(self):
        # Position entered as MACRO_BREAK_48H at 80,000
        self.engine.active_position = FuturesPosition(
            side="LONG", type="MACRO_BREAK_48H", silo="CORE_v450",
            entry_idx=100, entry_t="2026-02-01 12:00", entry_p=80000.0,
            hard_stop=78800.0, breakout_level=79500.0, leverage=2.5
        )
        # Bar drops below hard stop (stopped out at a loss)
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
        self.assertEqual(self.engine.last_failed_breakout_bar, 105) # Cooldown registered at bar 105


if __name__ == "__main__":
    unittest.main()
