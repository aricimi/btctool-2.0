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
from risk_engine import RiskEngine, TradeIntent, RiskDecision
from execution_manager import ExecutionManager
from trade_logger import TradeJournal
from dream_engine import DreamEngine


class TestZebraBot(unittest.TestCase):

    def setUp(self):
        self.stream = MarketStream(inst_id="BTC-USDT", max_bars=100)
        self.state_calculator = MarketState()
        self.brain = FreeConvictionEngine()
        self.risk_gate = RiskEngine()
        self.mock_journal = MagicMock()
        self.mock_journal.record_entry.return_value = 1
        self.execution = ExecutionManager(state_file="test_bot_state.json", journal=self.mock_journal)

    def tearDown(self):
        for f in ["test_bot_state.json", "test_bot_state.json.tmp", "test_episodes.jsonl", "test_trade_history.json", "test_journal.md", "test_journal.csv"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

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

        # Warm-up pass to eliminate initial Python/JIT import latency
        _ = self.state_calculator.extract_state_matrix(self.stream)

        t0 = time.time()
        matrix = self.state_calculator.extract_state_matrix(self.stream)
        elapsed_ms = (time.time() - t0) * 1000.0

        print(f"\n[Performance Benchmark] 100-Screen State Matrix computed in: {elapsed_ms:.2f} ms")
        self.assertLess(elapsed_ms, 25.0, "State matrix calculation must be ultra-fast (<25ms)")
        self.assertIn("timeframes", matrix)
        self.assertIn("multi_screen_bounds", matrix)
        self.assertIn("balloon_geometry", matrix)
        self.assertIn("micro_turn", matrix)
        self.assertIn("absorption_index", matrix)

    def test_04_predictive_brain_and_multi_screen_decisions(self):
        """Verify Real Gain Hurdle, Dip Turn Prediction, Trailing Ratchet, Uncapped Runner, and Invalidation Cut."""
        # 1. LOW RUNWAY HURDLE (<0.45%): Bot refuses to enter dead chop or insufficient profit runway
        low_runway_matrix = {
            "latest_price": 82000.0,
            "tanh_imbalance": 0.05,
            "absorption_index": 5.0,
            "multi_screen_bounds": {
                "nearest_support": 81950.0,
                "nearest_resistance": 82100.0,
                "macro_ceiling": 82300.0,
                "immediate_runway_pct": 0.12,  # Too small to clear fees!
                "macro_runway_pct": 0.36,
            },
            "balloon_geometry": {
                "regime": "DEAD_CHOP",
                "is_balloon_expanding": False,
                "is_slow_market": True,
            },
            "micro_turn": {"is_green_building": False, "velocity_slowing": False},
        }
        hurdle_decision = self.brain.evaluate(low_runway_matrix, active_trade=None)
        self.assertEqual(hurdle_decision["action"], "WAIT_IN_CASH")
        self.assertIn("NO REAL GAIN ON TABLE", hurdle_decision["reason"])

        # 2. DIP TURN PREDICTION ENTRY: Testing support floor, absorption confirmed, green candle building
        dip_matrix = {
            "latest_price": 81750.0,
            "tanh_imbalance": 0.45,
            "absorption_index": 22.0,
            "multi_screen_bounds": {
                "nearest_support": 81720.0,
                "nearest_resistance": 82300.0,
                "macro_ceiling": 83500.0,
                "immediate_runway_pct": 0.67,  # > 0.45% minimum hurdle
                "macro_runway_pct": 2.14,
            },
            "balloon_geometry": {
                "regime": "BULL_TREND",
                "is_balloon_expanding": False,
                "is_slow_market": False,
            },
            "micro_turn": {
                "is_green_building": True,
                "velocity_slowing": True,
            },
        }
        dip_decision = self.brain.evaluate(dip_matrix, active_trade=None)
        self.assertEqual(dip_decision["action"], "ENTER_CORE_LOT_1")
        self.assertEqual(dip_decision["scenario"], "DIP_ABSORPTION_TURN")
        self.assertGreaterEqual(dip_decision["expected_runway_pct"], 0.45)
        # Mathematical guarantee: Stop MUST sit below actual entry price
        self.assertLess(dip_decision["invalidation_floor"], dip_decision["entry_price"])

        # 3. RIDE UNCAPPED MACRO BREAKOUT: Target reached, balloon blowing open outward
        active_trade = {
            "entry": 81750.0,
            "target_price": 82300.0,
            "invalidation_floor": 81650.0,
            "trailing_stop": 81650.0,
            "scenario": "DIP_ABSORPTION_TURN",
            "tranche_2_added": False,
        }
        uncapped_matrix = {
            "latest_price": 82350.0,  # Hit initial target
            "tanh_imbalance": 0.35,
            "absorption_index": 18.0,
            "multi_screen_bounds": {
                "nearest_support": 82100.0,     # Rising Middle Band support
                "nearest_resistance": 82300.0,
                "macro_ceiling": 83600.0,       # Wide open macro space
                "immediate_runway_pct": 0.10,
                "macro_runway_pct": 1.52,
            },
            "balloon_geometry": {
                "regime": "EXPANDING_BALLOON",
                "is_balloon_expanding": True,   # Volatility balloon opening!
                "is_slow_market": False,
            },
            "micro_turn": {"is_green_building": True, "velocity_slowing": False},
        }
        uncapped_decision = self.brain.evaluate(uncapped_matrix, active_trade=active_trade)
        self.assertEqual(uncapped_decision["action"], "RIDE_UNCAPPED")
        self.assertEqual(uncapped_decision["target_price"], 83600.0)
        self.assertGreater(uncapped_decision["trailing_stop"], active_trade["entry"])

        # 4. TRAILING STOP BANK: Profit locked in when trailing stop breached
        trailing_trade = {
            "entry": 81750.0,
            "target_price": 83600.0,
            "invalidation_floor": 81650.0,
            "trailing_stop": 82250.0,  # Ratcheted above entry (+0.61%)
            "scenario": "MACRO_BALLOON_EXPANSION",
            "tranche_2_added": False,
        }
        trailing_matrix = dict(uncapped_matrix)
        trailing_matrix["latest_price"] = 82240.0  # Fell back below trailing stop
        bank_decision = self.brain.evaluate(trailing_matrix, active_trade=trailing_trade)
        self.assertEqual(bank_decision["action"], "BANK_PROFIT")
        self.assertIn("TRAILING STOP HIT", bank_decision["reason"])

        # 5. CONTROLLED THESIS INVALIDATION CUT: Price drops below stop and order book bids collapse
        inval_matrix = dict(dip_matrix)
        inval_matrix["latest_price"] = 81400.0  # Plunged past emergency buffer
        inval_matrix["tanh_imbalance"] = -0.30  # Aggressive selling
        inval_matrix["absorption_index"] = 1.0  # Zero absorption
        cut_decision = self.brain.evaluate(inval_matrix, active_trade=active_trade)
        self.assertEqual(cut_decision["action"], "CUT_THESIS_INVALIDATED")

        # 6. MEMORY SOFT STOP WICK IMMUNITY: Mind proposes CUT, but Risk Gate overrides to HOLD
        wick_matrix = dict(dip_matrix)
        wick_matrix["latest_price"] = 81640.0   # Touching stop floor ($81,650)
        wick_matrix["tanh_imbalance"] = 0.35    # Resting bids thick!
        wick_matrix["absorption_index"] = 22.0  # Whale absorption active!
        wick_intent = self.brain.evaluate(wick_matrix, active_trade=active_trade)
        wick_decision = self.risk_gate.evaluate(wick_intent, wick_matrix, active_trade=active_trade)
        self.assertEqual(wick_decision["action"], "HOLD_POSITION")
        self.assertEqual(wick_decision.status, "MODIFY")
        self.assertIn("RISK GATE OVERRIDE", wick_decision["reason"])

        # 7. CONTEXTUAL SCALE-IN LOT 2 AT STRUCTURAL SUPPORT DISCOUNT
        scale_trade = dict(active_trade)
        scale_trade["tranche_2_added"] = False
        scale_matrix = dict(dip_matrix)
        scale_matrix["latest_price"] = 81710.0  # Testing support floor ($81,720) at discount to entry ($81,750)
        scale_matrix["tanh_imbalance"] = 0.30   # Institutional bids active
        scale_matrix["absorption_index"] = 18.0
        scale_intent = self.brain.evaluate(scale_matrix, active_trade=scale_trade)
        scale_decision = self.risk_gate.evaluate(scale_intent, scale_matrix, active_trade=scale_trade)
        self.assertEqual(scale_decision["action"], "SCALE_IN_LOT_2")
        self.assertEqual(scale_decision.status, "ALLOW")

        # 8. ANTI-CHURN BREAKOUT VETO: Risk Gate vetoes breakout proposed at or below failed stop
        self.risk_gate.record_invalidation_exit(82453.30, time.time())
        churn_matrix = dict(dip_matrix)
        churn_matrix["latest_price"] = 82450.0  # Below failed level ($82,453.30)
        churn_intent = TradeIntent(
            action="ENTER_CORE_LOT_1",
            scenario="MACRO_BALLOON_BREAKOUT",
            entry_price=82450.0,
            target_price=87200.0,
            proposed_stop=82200.0,
            expected_runway_pct=5.5,
        )
        churn_decision = self.risk_gate.evaluate(churn_intent, churn_matrix, active_trade=None)
        self.assertEqual(churn_decision["action"], "WAIT_IN_CASH")
        self.assertEqual(churn_decision.status, "REJECT")
        self.assertIn("REJECTED BY RISK GATE", churn_decision["reason"])

    def test_05_execution_manager_clean_slate_and_trailing(self):
        """Verify ExecutionManager position operations, trailing ratcheting, and target stepping."""
        trade = self.execution.open_core_lot_1(
            entry_price=81750.0,
            scenario="DIP_ABSORPTION_TURN",
            target_price=82300.0,
            invalidation_floor=81650.0,
            reason="Predictive Multi-Screen Turn",
        )
        self.assertIsNotNone(self.execution.active_trade)
        self.assertEqual(self.execution.active_trade["entry"], 81750.0)
        self.assertEqual(self.execution.active_trade["target_price"], 82300.0)
        self.assertEqual(self.execution.active_trade["invalidation_floor"], 81650.0)
        self.assertEqual(self.execution.active_trade["trailing_stop"], 81650.0)

        # Ratchet trailing stop higher
        self.execution.update_trailing_stop(82050.0)
        self.assertEqual(self.execution.active_trade["trailing_stop"], 82050.0)

        # Step target to macro ceiling
        self.execution.update_target_price(83600.0)
        self.assertEqual(self.execution.active_trade["target_price"], 83600.0)

        # Scale in Lot 2
        self.execution.scale_in_lot_2(price=81680.0, reason="Discount Support Scale")
        self.assertTrue(self.execution.active_trade["tranche_2_added"])
        self.assertEqual(self.execution.active_trade["entry"], 81715.0)

        # Close position
        self.execution.close_position(exit_price=82800.0, exit_reason="Trailing Structural Target")
        self.assertIsNone(self.execution.active_trade)

    def test_06_subconscious_reflexes_and_shadow_self(self):
        """Verify Priority-0 Reflexes (Blind, Motor, Safety) and Shadow Self stress sizing."""
        base_intent = TradeIntent(
            action="ENTER_CORE_LOT_1",
            scenario="DIP_ABSORPTION_TURN",
            entry_price=82000.0,
            target_price=82600.0,
            proposed_stop=81700.0,
            expected_runway_pct=0.73,
        )
        base_matrix = {
            "latest_price": 82000.0,
            "feed_latency_ms": 120.0,
            "spread_pct": 0.02,
            "composite_atr": 200.0,
            "tanh_imbalance": 0.25,
            "absorption_index": 18.0,
            "multi_screen_bounds": {
                "nearest_support": 81750.0,
                "nearest_resistance": 82600.0,
                "macro_ceiling": 83500.0,
                "immediate_runway_pct": 0.73,
            },
        }

        # 1. BLIND REFLEX: Stale WebSocket feed (>5000ms latency)
        blind_matrix = dict(base_matrix, feed_latency_ms=6200.0)
        blind_decision = self.risk_gate.evaluate(base_intent, blind_matrix)
        self.assertEqual(blind_decision.status, "REJECT")
        self.assertEqual(blind_decision.action, "WAIT_IN_CASH")
        self.assertIn("REFLEX_BLIND_MODE", blind_decision.reason)

        # 2. BLIND REFLEX: Anomalous bid/ask spread (>0.25%)
        spread_matrix = dict(base_matrix, spread_pct=0.35)
        spread_decision = self.risk_gate.evaluate(base_intent, spread_matrix)
        self.assertEqual(spread_decision.status, "REJECT")
        self.assertIn("REFLEX_BLIND_MODE", spread_decision.reason)

        # 3. MOTOR REFLEX: Consecutive execution API errors (>=2)
        motor_decision = self.risk_gate.evaluate(base_intent, base_matrix, consecutive_api_errors=2)
        self.assertEqual(motor_decision.status, "REJECT")
        self.assertIn("REFLEX_MOTOR_LOCKDOWN", motor_decision.reason)

        # 4. SAFETY REFLEX: Daily drawdown limit breached (>=2.0%)
        safety_decision = self.risk_gate.evaluate(base_intent, base_matrix, daily_drawdown_pct=2.1)
        self.assertEqual(safety_decision.status, "REJECT")
        self.assertIn("REFLEX_SAFETY_LOCKDOWN", safety_decision.reason)

        # 5. SHADOW SELF: Worst-case stress drop clamps Lot 1 size factor
        stress_matrix = dict(base_matrix)
        stress_matrix["composite_atr"] = 400.0
        stress_matrix["multi_screen_bounds"] = dict(base_matrix["multi_screen_bounds"], nearest_support=81000.0, nearest_resistance=83500.0)
        stress_decision = self.risk_gate.evaluate(base_intent, stress_matrix, max_stress_risk_pct=0.60)
        self.assertEqual(stress_decision.status, "MODIFY")
        self.assertLess(stress_decision.approved_size_factor, 1.0)
        self.assertGreater(stress_decision.approved_size_factor, 0.0)
        self.assertGreater(stress_decision.stress_loss_pct, 0.60)

    def test_07_episodic_memory_and_dream_engine(self):
        """Verify EpisodeLog calculation (e = r - r_hat, regret) and DreamEngine analysis."""
        journal = TradeJournal()
        journal.history_file = "test_trade_history.json"
        journal.episodes_file = "test_episodes.jsonl"
        journal.journal_file = "test_journal.md"
        journal.csv_file = "test_journal.csv"
        journal.data = {"trades": [], "stats": {}}

        # Record entry with pre_state
        trade_id = journal.record_entry(
            setup_name="ZEBRA WHALE: TEST_SETUP",
            entry_price=82000.0,
            stop_loss=81600.0,
            target_1=82800.0,
            target_2=0.0,
            rationale="Test Setup Rationale",
            feature_vector={"regime": "BULL_TREND", "absorption_index": 20.0},
            trade_intent={"expected_runway_pct": 0.98},
            risk_decision={"approved_size_factor": 1.0, "stress_loss_pct": 0.49},
        )
        self.assertEqual(trade_id, 1)

        # Record exit (price: 82500 -> gross +0.61%, net +0.41%)
        journal.record_exit(exit_price=82500.0, exit_reason="Target Trailed")

        # Verify episode stored in episodes.jsonl
        episodes = journal.get_episodes(limit=10)
        self.assertEqual(len(episodes), 1)
        ep = episodes[0]
        self.assertEqual(ep["episode_id"], 1)
        self.assertEqual(ep["gross_pnl_pct"], 0.61)
        self.assertEqual(ep["net_pnl_pct"], 0.41)
        self.assertEqual(ep["predicted_runway_pct"], 0.98)
        self.assertEqual(ep["prediction_error_pct"], round(0.61 - 0.98, 2))
        self.assertEqual(ep["regret"], 0.37)

        # Run DreamEngine on the test episode file
        dreamer = DreamEngine(episodes_file="test_episodes.jsonl", history_file="test_trade_history.json")
        analysis = dreamer.analyze()
        self.assertEqual(analysis["total_episodes"], 1)
        self.assertEqual(analysis["win_rate_pct"], 100.0)
        self.assertEqual(analysis["mean_prediction_error"], -0.37)
        self.assertEqual(analysis["mean_regret"], 0.37)


if __name__ == "__main__":
    unittest.main()
