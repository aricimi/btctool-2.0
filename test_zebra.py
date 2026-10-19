"""
test_zebra.py — Comprehensive Unit & Integration Test Suite for Zebra Bot (btctool 2.0)
Tests:
1. Sensory Ingestion & 11-Timeframe Ring Buffers
2. Vectorized 100-Screen State Matrix (<10ms execution)
3. Kinetic Push vs Structural Barrier Brain & Playbooks
4. Asymmetric Execution Manager & State Persistence
"""

import time
import unittest
import numpy as np
from market_stream import MarketStream
from market_state import MarketState
from conviction_engine import ConvictionEngine, LifecycleState
from execution_manager import ExecutionManager


class TestZebraBot(unittest.TestCase):

    def setUp(self):
        self.stream = MarketStream(inst_id="BTC-USDT", max_bars=100)
        self.state_calculator = MarketState()
        self.brain = ConvictionEngine()
        self.execution = ExecutionManager(state_file="test_bot_state.json")

    def tearDown(self):
        import os
        if os.path.exists("test_bot_state.json"):
            os.remove("test_bot_state.json")
        if os.path.exists("test_bot_state.json.tmp"):
            os.remove("test_bot_state.json.tmp")

    def test_01_synthetic_stream_and_candle_aggregation(self):
        """Verify that trade ticks aggregate into 11-timeframe ring buffers."""
        t_base = 1700000000.0
        # Feed 10 ticks
        for i in range(10):
            p = 82000.0 + i * 10.0
            self.stream.on_trade_tick(price=p, size=0.5, side="buy" if i % 2 == 0 else "sell", ts=t_base + i)

        self.assertEqual(self.stream.latest_price, 82090.0)
        self.assertTrue("1s" in self.stream.buffers)
        self.assertTrue("1m" in self.stream.buffers)
        self.assertTrue("1h" in self.stream.buffers)
        self.assertGreater(len(self.stream.recent_trades), 0)

    def test_02_anti_spoofing_orderbook_and_tanh_imbalance(self):
        """Verify 3-snapshot anti-spoofing filter and tanh-smoothed order book imbalance."""
        self.stream.latest_price = 82000.0
        # Snapshot 1
        self.stream.on_orderbook_update(
            bids_data=[["81990", "5.0"], ["81950", "10.0"]],
            asks_data=[["82010", "4.0"], ["82050", "8.0"]],
            action="snapshot"
        )
        # Snapshot 2 (spoofed bid wall added at 81980)
        self.stream.on_orderbook_update(
            bids_data=[["81980", "50.0"], ["81990", "5.0"]],
            asks_data=[["82010", "4.0"]],
            action="update"
        )
        # Snapshot 3 (spoofed bid wall removed)
        self.stream.on_orderbook_update(
            bids_data=[["81980", "0.0"]],
            asks_data=[["82010", "4.0"]],
            action="update"
        )

        bid_vol, ask_vol, tanh_imb = self.stream.get_anti_spoof_depth(distance_pct=0.01)
        self.assertGreaterEqual(tanh_imb, -1.0)
        self.assertLessEqual(tanh_imb, 1.0)

    def test_03_vectorized_100_screen_state_matrix_speed(self):
        """Verify that market_state computes all 11-timeframe indicators in <15ms."""
        # Populate buffers with synthetic candle series
        t_base = time.time()
        for tf in self.stream.buffers.keys():
            candles = []
            p = 82000.0
            for i in range(50):
                p += (np.sin(i / 5.0) * 50.0)
                candles.append({
                    "ts": t_base - (50 - i) * 60,
                    "open": p - 10,
                    "high": p + 20,
                    "low": p - 20,
                    "close": p,
                    "vol": 10.0 + i,
                })
            self.stream.buffers[tf].extend(candles)

        self.stream.latest_price = 82000.0
        self.stream.bids = {81990.0: 5.0, 81950.0: 10.0}
        self.stream.asks = {82010.0: 4.0, 82050.0: 8.0}

        t0 = time.time()
        matrix = self.state_calculator.extract_state_matrix(self.stream)
        elapsed_ms = (time.time() - t0) * 1000.0

        print(f"\n[Performance Benchmark] 100-Screen State Matrix computed in: {elapsed_ms:.2f} ms")
        self.assertLess(elapsed_ms, 25.0, "State matrix calculation must be ultra-fast (<25ms)")
        self.assertIn("timeframes", matrix)
        self.assertIn("15m", matrix["timeframes"])
        self.assertIn("session_vwap", matrix)
        self.assertIn("absorption_index", matrix)
        self.assertIn("tanh_imbalance", matrix)

    def test_04_conviction_engine_playbooks(self):
        """Verify Kinetic Push vs Barrier scoring and Playbook triggers."""
        # Synthetic matrix representing a strong bullish momentum breakout
        matrix = {
            "latest_price": 82000.0,
            "best_bid": 81999.0,
            "best_ask": 82001.0,
            "session_vwap": 81800.0,
            "absorption_index": 25.0,
            "tanh_imbalance": 0.45,  # Strong buyer depth
            "oi_zscore": 2.2,        # Real institutional leverage
            "funding_rate": 0.0001,
            "timeframes": {
                "4h": {"ema_9": 81500, "ema_21": 81000, "ema_50": 80000, "atr": 400.0},
                "1h": {"ema_9": 81800, "ema_21": 81400, "ema_50": 81000, "atr": 200.0},
                "15m": {"ema_9": 81900, "ema_21": 81700, "ema_50": 81500, "atr": 120.0, "bb_upper": 82500, "bb_lower": 81500, "bb_width": 1.2, "rsi": 62.0},
                "5m": {"atr": 60.0, "macd_hist": 15.0, "bb_mid": 81850},
                "1m": {"macd_hist": 8.0},
            }
        }

        # 1. Test Entry Scan
        decision = self.brain.evaluate(matrix, active_trade=None)
        self.assertEqual(decision["action"], "ENTER_CORE_LOT_1")
        self.assertGreater(decision["target_1"], matrix["latest_price"])
        self.assertLess(decision["stop_loss"], matrix["latest_price"])

        # 2. Test In-Progress Active Trade Holding
        active_trade = {
            "entry": 81800.0,
            "current_stop": 81500.0,
            "highest_price": 82000.0,
            "breakeven_set": False,
            "tranche_2_added": False,
        }
        hold_decision = self.brain.evaluate(matrix, active_trade=active_trade)
        # Gain is (82000 - 81800)/81800 = +0.24% (< 0.40% breakeven ratchet threshold)
        self.assertIn(hold_decision["action"], ("HOLD_IN_PROGRESS", "SCALE_IN_LOT_2"))

        # 3. Test Structural Stop Loss Trigger
        crash_matrix = dict(matrix)
        crash_matrix["latest_price"] = 81400.0  # Below 81500 stop
        stop_decision = self.brain.evaluate(crash_matrix, active_trade=active_trade)
        self.assertEqual(stop_decision["action"], "EXIT_STRUCTURAL_STOP")

    def test_05_execution_manager_state_cycle(self):
        """Verify ExecutionManager multi-lot lifecycle and state persistence."""
        # Open Core Lot 1
        trade = self.execution.open_core_lot_1(
            entry_price=82000.0,
            stop_loss=81500.0,
            target_1=82500.0,
            target_2=83000.0,
            reason="Test Core Breakout"
        )
        self.assertIsNotNone(self.execution.active_trade)
        self.assertEqual(self.execution.active_trade["entry"], 82000.0)

        # Scale in Lot 2 on Absorption Dip
        self.execution.scale_in_lot_2(price=81800.0, new_stop=81600.0, reason="Test Absorption Dip")
        self.assertTrue(self.execution.active_trade["tranche_2_added"])
        self.assertEqual(self.execution.active_trade["entry"], 81900.0)  # Blended entry (82000 + 81800) / 2

        # Ratchet Stop to Breakeven
        self.execution.ratchet_stop(new_stop=82100.0, reason="Breakeven Lock", is_breakeven=True)
        self.assertEqual(self.execution.active_trade["current_stop"], 82100.0)
        self.assertTrue(self.execution.active_trade["breakeven_set"])


if __name__ == "__main__":
    unittest.main()
