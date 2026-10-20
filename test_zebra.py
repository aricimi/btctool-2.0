"""
test_zebra.py — Comprehensive Unit & Integration Test Suite for Institutional Whale Zebra Bot
Tests:
1. Sensory Ingestion & 11-Timeframe Ring Buffers
2. Vectorized 100-Screen State Matrix (<15ms execution)
3. Whale & Liquidity Thesis Brain (Chop Gate, Asymmetric Runway, Dip Absorption, Peak Exhaustion)
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
        self.assertIn("liquidity_gravity", matrix)
        self.assertIn("regime_analysis", matrix)
        self.assertIn("micro_reversal", matrix)

    def test_04_whale_scenarios_and_chop_gate(self):
        """Verify Chop Gate lock, Dip Absorption entry, Peak Exhaustion banking, and Invalidation Cut."""
        # 1. DEAD CHOP TEST: Small range, narrow bandwidth -> Must lock to cash!
        chop_matrix = {
            "latest_price": 82000.0,
            "tanh_imbalance": 0.05,
            "absorption_index": 5.0,
            "trade_velocity": 3.0,
            "regime_analysis": {
                "regime": "DEAD_CHOP",
                "is_dead_chop": True,
                "bb_width_15m": 0.30,
                "runway_pct": 0.20,
            },
            "liquidity_gravity": {"overhead_fuel_cleared": False},
            "micro_reversal": {"is_green_building": False},
        }
        chop_decision = self.brain.evaluate(chop_matrix, active_trade=None)
        self.assertEqual(chop_decision["action"], "WAIT_IN_CASH")
        self.assertIn("CHOP GATE", chop_decision["reason"])

        # 2. DIP ABSORPTION ENTRY TEST: Bull trend dip to support with bids and green candle building
        dip_matrix = {
            "latest_price": 81750.0,
            "tanh_imbalance": 0.45,
            "absorption_index": 22.0,
            "trade_velocity": 12.0,
            "regime_analysis": {
                "regime": "BULL_TREND",
                "is_dead_chop": False,
                "dynamic_support": 81750.0,
                "dynamic_target": 82250.0,
                "runway_pct": 0.61,  # > 0.45% minimum hurdle
            },
            "liquidity_gravity": {
                "overhead_fuel_pct": 1.20,
                "downside_fuel_pct": 0.30,
                "overhead_fuel_cleared": False,
                "is_bottom_swept": True,
            },
            "micro_reversal": {
                "is_green_building": True,
                "candle_pct": 0.15,
            },
        }
        dip_decision = self.brain.evaluate(dip_matrix, active_trade=None)
        self.assertEqual(dip_decision["action"], "ENTER_CORE_LOT_1")
        self.assertIn("DIP ABSORPTION", dip_decision["reason"])
        self.assertGreaterEqual(dip_decision["expected_runway_pct"], 0.45)

        # 3. PEAK EXHAUSTION EXIT TEST: In profit + overhead fuel cleared + downside liquidations thick
        active_trade = {
            "entry": 81750.0,
            "target_price": 82250.0,
            "invalidation_floor": 81600.0,
            "scenario": "DIP_ABSORPTION_BULL_TREND",
            "tranche_2_added": False,
        }
        peak_matrix = {
            "latest_price": 82200.0,  # +0.55% gain
            "tanh_imbalance": -0.20,
            "absorption_index": 2.0,
            "trade_velocity": 8.0,
            "regime_analysis": {"is_dead_chop": False, "dynamic_target": 82250.0},
            "liquidity_gravity": {
                "overhead_fuel_cleared": True,  # Upper stops cleared!
                "downside_fuel_pct": 0.85,      # Massive pool waiting below
                "fuel_ratio": 0.15,
            },
            "micro_reversal": {"is_green_building": False},
        }
        exit_decision = self.brain.evaluate(peak_matrix, active_trade=active_trade)
        self.assertEqual(exit_decision["action"], "BANK_PROFIT")
        self.assertIn("PEAK EXHAUSTION", exit_decision["reason"])

        # 4. THESIS INVALIDATION CUT: Price drops below invalidation floor -> Rectify mistake immediately
        inval_matrix = dict(dip_matrix)
        inval_matrix["latest_price"] = 81550.0  # Dropped below 81,600 floor
        cut_decision = self.brain.evaluate(inval_matrix, active_trade=active_trade)
        self.assertEqual(cut_decision["action"], "CUT_THESIS_INVALIDATED")

    def test_05_execution_manager_clean_slate(self):
        """Verify ExecutionManager position operations with thesis parameters."""
        trade = self.execution.open_core_lot_1(
            entry_price=81750.0,
            scenario="DIP_ABSORPTION",
            target_price=82200.0,
            invalidation_floor=81650.0,
            reason="Whale Floor Support",
        )
        self.assertIsNotNone(self.execution.active_trade)
        self.assertEqual(self.execution.active_trade["entry"], 81750.0)
        self.assertEqual(self.execution.active_trade["target_price"], 82200.0)
        self.assertEqual(self.execution.active_trade["invalidation_floor"], 81650.0)

        self.execution.scale_in_lot_2(price=81680.0, reason="Discount Support Scale")
        self.assertTrue(self.execution.active_trade["tranche_2_added"])
        self.assertEqual(self.execution.active_trade["entry"], 81715.0)

        self.execution.close_position(exit_price=82250.0, exit_reason="Target Reached")
        self.assertIsNone(self.execution.active_trade)


if __name__ == "__main__":
    unittest.main()
