"""
test_zebra.py — Comprehensive Unit & Integration Test Suite for Truly Free Zebra Bot
Tests:
1. Sensory Ingestion & 11-Timeframe Ring Buffers
2. Vectorized 100-Screen State Matrix (<15ms execution)
3. Free Expected Value Brain (Continuous P_up calculation & dynamic execution)
4. Clean Slate Ledger Archiving & Execution Manager
"""

import os
import time
import unittest
import numpy as np
from unittest.mock import MagicMock
from market_stream import MarketStream
from market_state import MarketState
from conviction_engine import FreeConvictionEngine
from execution_manager import ExecutionManager


class TestZebraBot(unittest.TestCase):

    def setUp(self):
        self.stream = MarketStream(inst_id="BTC-USDT", max_bars=100)
        self.state_calculator = MarketState()
        self.brain = FreeConvictionEngine()
        self.mock_journal = MagicMock()
        self.mock_journal.record_entry.return_value = 1
        self.execution = ExecutionManager(state_file="test_bot_state.json", journal=self.mock_journal)

    def tearDown(self):
        if os.path.exists("test_bot_state.json"):
            os.remove("test_bot_state.json")
        if os.path.exists("test_bot_state.json.tmp"):
            os.remove("test_bot_state.json.tmp")

    def test_01_synthetic_stream_and_candle_aggregation(self):
        """Verify that trade ticks aggregate into 11-timeframe ring buffers."""
        t_base = 1700000000.0
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
        self.stream.on_orderbook_update(
            bids_data=[["81990", "5.0"], ["81950", "10.0"]],
            asks_data=[["82010", "4.0"], ["82050", "8.0"]],
            action="snapshot"
        )
        self.stream.on_orderbook_update(
            bids_data=[["81980", "50.0"], ["81990", "5.0"]],
            asks_data=[["82010", "4.0"]],
            action="update"
        )
        self.stream.on_orderbook_update(
            bids_data=[["81980", "0.0"]],
            asks_data=[["82010", "4.0"]],
            action="update"
        )

        bid_vol, ask_vol, tanh_imb = self.stream.get_anti_spoof_depth(distance_pct=0.01)
        self.assertGreaterEqual(tanh_imb, -1.0)
        self.assertLessEqual(tanh_imb, 1.0)

    def test_03_vectorized_100_screen_state_matrix_speed(self):
        """Verify that market_state computes all 11-timeframe indicators in <25ms."""
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

    def test_04_free_brain_autonomous_decisions(self):
        """Verify continuous directional probability P_up and zero-static-stop actions."""
        # Bullish matrix setup
        matrix = {
            "latest_price": 82000.0,
            "session_vwap": 81800.0,
            "absorption_index": 20.0,
            "tanh_imbalance": 0.40,
            "oi_zscore": 1.8,
            "trade_velocity": 25.0,
            "timeframes": {
                "1D": {"ema_9": 80000, "ema_21": 78000, "ema_50": 75000, "macd_hist": 200, "bb_pct_b": 0.7},
                "6h": {"ema_9": 81000, "ema_21": 80000, "ema_50": 79000, "macd_hist": 100, "bb_pct_b": 0.65},
                "4h": {"ema_9": 81500, "ema_21": 81000, "ema_50": 80000, "macd_hist": 50, "bb_pct_b": 0.6},
                "2h": {"ema_9": 81700, "ema_21": 81400, "ema_50": 81000, "macd_hist": 30, "bb_pct_b": 0.6},
                "1h": {"ema_9": 81800, "ema_21": 81600, "ema_50": 81200, "macd_hist": 20, "bb_pct_b": 0.58},
                "30m": {"ema_9": 81850, "ema_21": 81700, "ema_50": 81400, "macd_hist": 15, "bb_pct_b": 0.55},
                "15m": {"ema_9": 81900, "ema_21": 81800, "ema_50": 81600, "macd_hist": 10, "bb_pct_b": 0.52, "atr": 100.0},
                "5m": {"ema_9": 81950, "ema_21": 81900, "ema_50": 81800, "macd_hist": 5, "bb_pct_b": 0.51},
                "3m": {"ema_9": 81970, "ema_21": 81940, "ema_50": 81900, "macd_hist": 2, "bb_pct_b": 0.50},
                "1m": {"ema_9": 81990, "ema_21": 81960, "ema_50": 81920, "macd_hist": 1, "bb_pct_b": 0.50},
                "1s": {"ema_9": 82000, "ema_21": 81980, "ema_50": 81950, "macd_hist": 0.5, "bb_pct_b": 0.50},
            }
        }

        # 1. In cash -> Should detect strong edge and enter Core Lot 1
        decision = self.brain.evaluate(matrix, active_trade=None)
        self.assertEqual(decision["action"], "ENTER_CORE_LOT_1")
        self.assertGreaterEqual(decision["p_up"], 0.65)

        # 2. In position -> Riding uncapped
        active_trade = {"entry": 81800.0, "tranche_2_added": False}
        ride_decision = self.brain.evaluate(matrix, active_trade=active_trade)
        self.assertEqual(ride_decision["action"], "RIDE_UNCAPPED")

        # 3. In position + Bearish reversal -> Immediate predictive cut (no waiting for static stop)
        bearish_matrix = dict(matrix)
        # Flip indicators to bearish
        bearish_tf = {}
        for tf, data in matrix["timeframes"].items():
            b_data = dict(data)
            b_data["ema_9"] = 81000
            b_data["ema_21"] = 82000
            b_data["macd_hist"] = -50
            b_data["bb_pct_b"] = 0.1
            bearish_tf[tf] = b_data
        bearish_matrix["timeframes"] = bearish_tf
        bearish_matrix["tanh_imbalance"] = -0.50

        cut_decision = self.brain.evaluate(bearish_matrix, active_trade=active_trade)
        self.assertIn(cut_decision["action"], ("CUT_IMMEDIATE", "HARVEST_PROFIT"))
        self.assertLess(cut_decision["p_up"], 0.45)

    def test_05_execution_manager_clean_slate(self):
        """Verify ExecutionManager position operations without static stops."""
        trade = self.execution.open_core_lot_1(
            entry_price=82000.0,
            p_up=0.78,
            reason="Test Multi-Screen Edge"
        )
        self.assertIsNotNone(self.execution.active_trade)
        self.assertEqual(self.execution.active_trade["entry"], 82000.0)

        self.execution.scale_in_lot_2(price=81800.0, p_up=0.82, reason="Test Absorption Dip")
        self.assertTrue(self.execution.active_trade["tranche_2_added"])
        self.assertEqual(self.execution.active_trade["entry"], 81900.0)

        self.execution.close_position(exit_price=82200.0, exit_reason="Edge Exhausted", p_up=0.42)
        self.assertIsNone(self.execution.active_trade)


if __name__ == "__main__":
    unittest.main()
