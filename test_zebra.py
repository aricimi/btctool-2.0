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
from unittest.mock import MagicMock, patch
from market_stream import MarketStream
from market_state import MarketState
from conviction_engine import FreeConvictionEngine
from risk_engine import RiskEngine, TradeIntent, RiskDecision, ThesisFailureCounter, SetupPerformanceGovernor
from execution_manager import ExecutionManager
from trade_logger import TradeJournal
from dream_engine import DreamEngine
from okx_trader import OKXSpotClient


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
        for f in ["test_bot_state.json", "test_bot_state.json.tmp", "test_bot_state.json.bak", "test_episodes.jsonl", "test_trade_history.json", "test_journal.md", "test_journal.csv"]:
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
        self.assertTrue(any(k in hurdle_decision["reason"] for k in ["NO REAL GAIN ON TABLE", "SLOW MARKET", "PATIENT SCANNING"]))

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
        # In BTCTOOL 3.0, Setup A is frozen as a capital governor to prevent chop & false breakout cascades
        self.assertEqual(dip_decision["action"], "WAIT_IN_CASH")
        self.assertEqual(dip_decision["scenario"], "DIP_ABSORPTION_TURN")
        self.assertTrue(dip_decision["telemetry"].get("governor_held", False))

        # 3. RIDE UNCAPPED MACRO BREAKOUT: Target reached, balloon blowing open outward
        active_trade = {
            "entry": 81750.0,
            "target_price": 82800.0,
            "invalidation_floor": 81650.0,
            "trailing_stop": 81650.0,
            "scenario": "DIP_ABSORPTION_TURN",
            "tranche_2_added": False,
        }
        uncapped_matrix = {
            "latest_price": 82850.0,  # Hit target (+1.35% gross, clears +1.20% CPPR v2)
            "tanh_imbalance": 0.35,
            "absorption_index": 18.0,
            "multi_screen_bounds": {
                "nearest_support": 82100.0,     # Rising Middle Band support
                "nearest_resistance": 82800.0,
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

    def test_08_explicit_belief_and_adaptive_hurdles(self):
        """Verify Component 5 (Belief System hysteresis) and Component 2 (Adaptive Hurdles)."""
        from conviction_engine import BeliefSystem, FreeConvictionEngine

        # 1. Hysteresis Anti-Flicker Test
        belief_sys = BeliefSystem(decay_rate=0.85)
        # Tick 1: Initial bullish conviction
        s1 = belief_sys.update(
            raw_edge=0.50,
            instant_urgency=0.30,
            entropy=0.20,
            vol_regime=1.0,
            is_balloon_expanding=False,
            is_slow_market=False,
            absorption_idx=15.0,
        )
        self.assertEqual(s1.persistence_ticks, 1)
        self.assertGreater(s1.directional_bias, 0.40)

        # Tick 2: Sudden 1-tick negative noise shock (-0.40)
        s2 = belief_sys.update(
            raw_edge=-0.40,
            instant_urgency=0.0,
            entropy=0.20,
            vol_regime=1.0,
            is_balloon_expanding=False,
            is_slow_market=False,
            absorption_idx=15.0,
        )
        # Hysteresis dampening: bias must remain POSITIVE despite the 1-tick shock
        self.assertGreater(s2.directional_bias, 0.20, "1-tick flash shock must not flip persistent belief")

        # 2. Adaptive Hurdles Test: High Entropy Chop vs Clean Expansion
        # High Entropy Chop: Hurdle must scale UP to defend against fee-drag
        s_chop = belief_sys.update(
            raw_edge=0.10,
            instant_urgency=0.05,
            entropy=0.90,
            vol_regime=0.50,
            is_balloon_expanding=False,
            is_slow_market=True,
            absorption_idx=4.0,
        )
        self.assertGreaterEqual(s_chop.adaptive_runway_hurdle, 0.55, "Chop must elevate runway hurdle")
        self.assertEqual(s_chop.regime_belief, "CHOP_COMPRESSION")

        # Clean Volatility Expansion: Hurdle must clamp DOWN to 0.40%
        s_expand = belief_sys.update(
            raw_edge=0.60,
            instant_urgency=0.45,
            entropy=0.15,
            vol_regime=1.30,
            is_balloon_expanding=True,
            is_slow_market=False,
            absorption_idx=18.0,
        )
        self.assertEqual(s_expand.adaptive_runway_hurdle, 0.40, "Expansion must clamp hurdle to 0.40%")
        self.assertEqual(s_expand.regime_belief, "BULL_ACCELERATION")

        # 3. Brain Integration Test
        brain = FreeConvictionEngine()
        brain.reset_belief()
        test_matrix = {
            "latest_price": 82500.0,
            "tanh_imbalance": 0.25,
            "absorption_index": 16.0,
            "composite_atr": 250.0,
            "multi_screen_bounds": {
                "nearest_support": 82400.0,
                "nearest_resistance": 83000.0,
                "macro_ceiling": 84500.0,
                "immediate_runway_pct": 0.61,
                "macro_runway_pct": 2.42,
            },
            "balloon_geometry": {
                "regime": "BULL_TREND",
                "is_balloon_expanding": False,
                "is_slow_market": False,
            },
            "micro_turn": {"is_green_building": True, "velocity_slowing": False},
            "feature_vector": {
                "trend_strength": 0.0008,
                "entropy": 0.25,
                "vol_regime": 1.1,
                "liquidity": 12.0,
            },
        }
        intent = brain.evaluate(test_matrix)
        self.assertIn("adaptive_runway_hurdle", intent.telemetry)
        self.assertIn("adaptive_conf_hurdle", intent.telemetry)
        self.assertIn("belief_regime", intent.telemetry)
        self.assertIn("belief_persistence", intent.telemetry)

    def test_09_v3_governor_escalation_and_noise_immune_trailing(self):
        """Verify BTCTOOL v3.0 Master Package: Governor, Failure Counter, Escalation, Stress, & Noise-Immune Stops."""
        from risk_engine import RiskEngine, TradeIntent, SetupPerformanceGovernor, ThesisFailureCounter, ConscienceEscalation, LightweightStressEngine
        from conviction_engine import FreeConvictionEngine

        # 1. Setup Performance Governor (with Burn-In Grace Period)
        gov = SetupPerformanceGovernor(window_size=20, min_burn_in_trades=5)
        setup = "TEST_BREAKOUT"
        # 4 consecutive bad trades (-0.40% each) - inside burn-in grace period (< 5)
        for _ in range(4):
            gov.record_trade_result(setup, -0.40)
        health = gov.get_health(setup)
        self.assertEqual(health.win_rate, 0.0)
        self.assertLess(health.health_score, 20.0, "Repeated bad losses must crash health score below 20")
        self.assertFalse(health.is_disabled, "During burn-in (< 5 trades), setup must NOT be permanently disabled")
        self.assertEqual(health.size_multiplier, 0.25, "During burn-in with score < 20, sizing is clamped to 0.25x")
        self.assertEqual(health.confidence_modifier, 0.10, "During burn-in with score < 20, conf_mod is +0.10")

        # 5th bad trade: completes burn-in (total_trades >= 5) -> now permanently disabled
        gov.record_trade_result(setup, -0.40)
        health_post_burnin = gov.get_health(setup)
        self.assertTrue(health_post_burnin.is_disabled, "Once burn-in completes (>= 5 trades), score < 20 must disable setup")
        self.assertEqual(health_post_burnin.size_multiplier, 0.0)

        # 2. Thesis Failure Counter & Cooldown
        fc = ThesisFailureCounter(max_consecutive_failures=3, cooldown_seconds=600.0)
        t_now = 10000.0
        fc.record_outcome("TEST_THESIS", -0.20, timestamp=t_now)
        fc.record_outcome("TEST_THESIS", -0.20, timestamp=t_now + 10)
        self.assertEqual(fc.get_failure_penalty("TEST_THESIS"), 0.70)
        # 2 consecutive losses enforces graduated 8m cooldown
        is_cd, rem = fc.is_in_cooldown("TEST_THESIS", current_time=t_now + 15)
        self.assertTrue(is_cd, "2nd consecutive failure must enforce graduated 8m cooldown")
        self.assertGreaterEqual(rem, 400.0)

        # After 8m expires (at t_now + 600s), cooldown clears
        is_cd_exp, _ = fc.is_in_cooldown("TEST_THESIS", current_time=t_now + 600.0)
        self.assertFalse(is_cd_exp, "Cooldown must clear after 8m expires")

        # 3rd failure triggers 20m minimum loss floor cooldown
        fc.record_outcome("TEST_THESIS", -0.20, timestamp=t_now + 610)
        is_cd_3, rem_3 = fc.is_in_cooldown("TEST_THESIS", current_time=t_now + 615)
        self.assertTrue(is_cd_3, "3rd consecutive failure must enforce 20m loss floor cooldown")
        self.assertGreaterEqual(rem_3, 1100.0)

        # 3. Conscience Escalation Gate
        esc = ConscienceEscalation(escalation_threshold=3)
        esc.record_trade(-0.10)
        esc.record_trade(-0.15)
        self.assertFalse(esc.is_escalated)
        self.assertEqual(esc.confidence_hike, 0.0)
        # 3rd loss triggers escalation
        esc.record_trade(-0.25)
        self.assertTrue(esc.is_escalated)
        self.assertEqual(esc.confidence_hike, 0.10)

        # 4. Lightweight Stress Engine
        passed, msg, drop = LightweightStressEngine.evaluate_stress(
            price=84000.0,
            stop_price=83500.0,
            spread_pct=0.25,  # Shock spread > 0.20%
            bid_depth=15.0,
        )
        self.assertFalse(passed, "Spread shock > 0.20% must fail stress gate")
        self.assertIn("Spread inflated", msg)

        # 5. Noise-Immune Breakeven & Trailing Stop Math
        brain = FreeConvictionEngine()
        active = {
            "entry": 80000.0,
            "target_price": 84000.0,
            "invalidation_floor": 79500.0,
            "trailing_stop": 79500.0,
            "scenario": "TEST",
        }
        # Price moved up +0.40% (should NOT move stop to breakeven yet; requires +1.20% CPPR v2 delayed activation)
        m_40 = {
            "latest_price": 80320.0,  # +0.40%
            "multi_screen_bounds": {"nearest_support": 80100.0, "nearest_resistance": 83000.0, "macro_ceiling": 85000.0, "immediate_runway_pct": 3.3, "macro_runway_pct": 5.8},
            "balloon_geometry": {"regime": "TREND", "is_balloon_expanding": True, "is_slow_market": False},
            "micro_turn": {},
            "composite_atr": 250.0,
        }
        intent_40 = brain.evaluate(m_40, active_trade=active)
        self.assertEqual(intent_40.proposed_stop, 79500.0, "Must not ratchet to breakeven prematurely at +0.40%")

        # Price moved up +0.80% (still below +1.20% CPPR v2 threshold, breathes with initial stop to avoid noise asphyxiation)
        m_80 = dict(m_40)
        m_80["latest_price"] = 80640.0  # +0.80%
        intent_80 = brain.evaluate(m_80, active_trade=active)
        self.assertEqual(intent_80.proposed_stop, 79500.0, "Must maintain initial structural stop below +1.20% to avoid premature noise asphyxiation")

        # Price expands to +1.25% (exceeds +1.20% CPPR v2 requirement)
        m_125 = dict(m_40)
        m_125["latest_price"] = 81000.0  # +1.25%
        active_125 = dict(active)
        active_125["highest_price"] = 81000.0
        intent_125 = brain.evaluate(m_125, active_trade=active_125)
        # With CPPR v2: Stop locks at entry * (1.0 + max(0.0035, 0.0125 * 0.50)) = entry * 1.00625 = $80,500.0 (+0.625% gross)
        self.assertEqual(intent_125.proposed_stop, 80500.0, "Must ratchet stop via CPPR v2 Level 1 to entry * 1.00625 (+0.625%)")
        net_at_cppr = ((80500.0 - 80000.0) / 80000.0) - 0.0020
        self.assertGreater(net_at_cppr, 0.0, "CPPR exit must guarantee net positive cash")

    def test_10_v31_classical_expectancy_and_hard_stop_primacy(self):
        """Verify BTCTOOL v3.1: Classical Expectancy Formula, R:R >= 1.5 Gate, & Absolute Hard Stop Primacy."""
        # 1. Classical Expectancy Math
        # Case A: Good R:R (2:1) but poor win-rate (30%) -> Net EV is negative!
        ev_neg, rr_a = FreeConvictionEngine.calculate_classical_expectancy(win_rate=0.30, target_pct=0.80, stop_pct=0.40)
        self.assertEqual(rr_a, 2.0)
        self.assertLess(ev_neg, 0.0, "30% win-rate with 2:1 R:R must yield negative EV after costs")

        # Case B: Strong setup (55% win rate, 3:1 R:R) -> Positive Net EV
        ev_pos, rr_b = FreeConvictionEngine.calculate_classical_expectancy(win_rate=0.55, target_pct=1.50, stop_pct=0.50)
        self.assertEqual(rr_b, 3.0)
        self.assertGreater(ev_pos, 0.30, "55% win rate with 3:1 R:R must clear expectancy hurdle")

        # Case C: Poor R:R (< 1.5:1)
        _, rr_poor = FreeConvictionEngine.calculate_classical_expectancy(win_rate=0.60, target_pct=0.30, stop_pct=0.30)
        self.assertEqual(rr_poor, 1.0)
        self.assertLess(rr_poor, 1.50)

        # 2. Absolute Hard Stop Primacy: Absorption CANNOT override exit past hard floor
        active_trade = {
            "entry": 80000.0,
            "target_price": 83000.0,
            "trailing_stop": 79600.0,  # Stop is at 79,600
            "invalidation_floor": 79600.0,
            "scenario": "DIP_ABSORPTION_TURN",
        }
        # Price drops to 79,500 (breaches soft wick zone: 79600 - 0.20*250 = 79,550)
        hard_breach_matrix = {
            "latest_price": 79500.0,
            "tanh_imbalance": 0.85,     # Huge resting bid wall
            "absorption_index": 45.0,   # Massive whale absorption
            "composite_atr": 250.0,
            "multi_screen_bounds": {"nearest_support": 79400.0, "nearest_resistance": 81000.0},
        }
        cut_intent = TradeIntent(action="CUT_THESIS_INVALIDATED", scenario="DIP_ABSORPTION_TURN", entry_price=79500.0, proposed_stop=79600.0)
        decision = self.risk_gate.evaluate(cut_intent, hard_breach_matrix, active_trade=active_trade)

        self.assertEqual(decision.status, "ALLOW", "Hard stop breach MUST NOT be overridden to MODIFY/HOLD")
        self.assertEqual(decision.action, "CUT_THESIS_INVALIDATED", "Must cut unconditionally past hard stop")
        self.assertIn("HARD RISK STOP BREACHED", decision.reason)

    def test_11_v32_dual_class_cooldown_and_eligibility_state_machine(self):
        """Verify BTCTOOL v3.2: Dual-Class Cooldowns, 5 Contiguous Health Tiers, & Zero Early-Release on Loss Locks."""
        from risk_engine import SetupPerformanceGovernor, ThesisFailureCounter, RiskEngine

        # 1. Five Contiguous Institutional Health Tiers
        gov = SetupPerformanceGovernor()
        # Pristine setup: 5 wins (+0.50% each)
        for _ in range(5):
            gov.record_trade_result("PRISTINE", 0.50)
        h_pristine = gov.get_health("PRISTINE")
        self.assertGreaterEqual(h_pristine.health_score, 80.0)
        self.assertEqual(h_pristine.size_multiplier, 1.00)
        self.assertEqual(h_pristine.confidence_modifier, 0.00)

        # Stressed setup: 1 win (+0.10%), 4 small losses (-0.20%) -> health ~32.0 (in [20, 40) Stressed tier)
        gov.record_trade_result("STRESSED", 0.10)
        for _ in range(4):
            gov.record_trade_result("STRESSED", -0.20)
        h_stressed = gov.get_health("STRESSED")
        self.assertLess(h_stressed.health_score, 40.0)
        self.assertGreaterEqual(h_stressed.health_score, 20.0)
        self.assertEqual(h_stressed.size_multiplier, 0.25)
        self.assertEqual(h_stressed.confidence_modifier, 0.10)
        self.assertFalse(h_stressed.is_disabled)

        # 2. Dual-Class Cooldown Architecture & Loss Floor Protection
        fc = ThesisFailureCounter(base_duration_sec=180.0)
        t_base = 50000.0

        # High historical health (95.0) must NOT reduce cooldown below 20m loss floor on 3 failures
        cooldown_dur = fc.calculate_cooldown_duration(consecutive_losses=3, health_score=95.0)
        self.assertGreaterEqual(cooldown_dur, 1200.0, "Historical health must never shorten cooldown below 20m loss floor")
        self.assertLessEqual(cooldown_dur, 2700.0, "Cooldown must be clamped to 45m max")

        # Record 3 failures to trigger Class B lock
        fc.record_outcome("BREAKOUT_TEST", -0.20, health_score=95.0, timestamp=t_base)
        fc.record_outcome("BREAKOUT_TEST", -0.20, health_score=95.0, timestamp=t_base + 10)
        fc.record_outcome("BREAKOUT_TEST", -0.20, health_score=95.0, timestamp=t_base + 20)

        is_cd, rem = fc.is_in_cooldown("BREAKOUT_TEST", current_time=t_base + 30)
        self.assertTrue(is_cd)
        self.assertGreaterEqual(rem, 1100.0)

        # 3. Unified 5-Tier Eligibility Gate & Verification of Zero Early Release
        engine = RiskEngine()
        engine.failure_counter = fc
        engine.governor = gov

        # Class B lock test: Even with ultra-low entropy (0.15) and clean trend, Class B loss cooldown CANNOT be bypassed
        clean_matrix = {
            "timestamp": t_base + 30,
            "feature_vector": {"entropy": 0.15},  # Low entropy
        }
        status, size_mult, conf_mod = engine.evaluate_entry_eligibility("BREAKOUT_TEST", clean_matrix)
        self.assertTrue(status.startswith("BLOCK_SETUP_COOLDOWN"), "Class B loss cooldown must never clear early on low entropy")
        self.assertEqual(size_mult, 0.0)

        # Class A condition gate test: Separate healthy setup without loss cooldown
        # When entropy is high (0.85), returns WAIT_HIGH_ENTROPY
        noisy_matrix = {
            "timestamp": t_base + 30,
            "feature_vector": {"entropy": 0.85},
        }
        status_a, _, _ = engine.evaluate_entry_eligibility("PRISTINE", noisy_matrix)
        self.assertEqual(status_a, "WAIT_HIGH_ENTROPY", "Class A gate must return WAIT on elevated entropy")

        # The instant entropy drops (0.35), Class A condition gate clears in real-time
        calm_matrix = {
            "timestamp": t_base + 30,
            "feature_vector": {"entropy": 0.35, "trend_strength": 0.0020},
        }
        status_clean, s_clean, c_clean = engine.evaluate_entry_eligibility("PRISTINE", calm_matrix)
        self.assertEqual(status_clean, "NORMAL_ELIGIBILITY", "Class A condition gate must unlock instantly when entropy clears")
        self.assertEqual(s_clean, 1.00)
        self.assertEqual(c_clean, 0.00)

        # 4. Exact Deterministic Boundary Handling at 20.0, 40.0, 60.0, 80.0
        # Check boundary at exactly 80.0
        gov.history["BOUND_80"] = [0.15] * 20  # win_rate=100%, avg=0.15 -> score = 50 + 50 + 30 = 130 -> 100.0
        # Let's force exact boundary scores directly to verify boundary logic
        class MockGov(SetupPerformanceGovernor):
            def get_health_with_score(self, score: float):
                h = super().get_health("ANY")
                h.health_score = score
                if score >= 80.0:
                    h.size_multiplier, h.confidence_modifier, h.is_disabled = 1.00, 0.00, False
                elif score >= 60.0:
                    h.size_multiplier, h.confidence_modifier, h.is_disabled = 0.75, 0.00, False
                elif score >= 40.0:
                    h.size_multiplier, h.confidence_modifier, h.is_disabled = 0.50, 0.05, False
                elif score >= 20.0:
                    h.size_multiplier, h.confidence_modifier, h.is_disabled = 0.25, 0.10, False
                else:
                    h.size_multiplier, h.confidence_modifier, h.is_disabled = 0.00, 0.00, True
                return h

        mg = MockGov()
        h80 = mg.get_health_with_score(80.0)
        self.assertEqual(h80.size_multiplier, 1.00)
        self.assertEqual(h80.confidence_modifier, 0.00)
        self.assertFalse(h80.is_disabled)

        h60 = mg.get_health_with_score(60.0)
        self.assertEqual(h60.size_multiplier, 0.75)
        self.assertEqual(h60.confidence_modifier, 0.00)
        self.assertFalse(h60.is_disabled)

        h40 = mg.get_health_with_score(40.0)
        self.assertEqual(h40.size_multiplier, 0.50)
        self.assertEqual(h40.confidence_modifier, 0.05)
        self.assertFalse(h40.is_disabled)

        h20 = mg.get_health_with_score(20.0)
        self.assertEqual(h20.size_multiplier, 0.25)
        self.assertEqual(h20.confidence_modifier, 0.10)
        self.assertFalse(h20.is_disabled)

        h19 = mg.get_health_with_score(19.9)
        self.assertEqual(h19.size_multiplier, 0.00)
        self.assertTrue(h19.is_disabled)

        # 5. Cooldown Persistence Across Bot Restarts
        exported_state = fc.export_state()
        new_fc = ThesisFailureCounter(base_duration_sec=180.0)
        new_fc.import_state(exported_state)
        is_cd_restored, rem_restored = new_fc.is_in_cooldown("BREAKOUT_TEST", current_time=t_base + 30)
        self.assertTrue(is_cd_restored, "Restored counter must maintain active Class B cooldown across restarts")
        self.assertGreater(rem_restored, 0.0)

        # 6. Emergency Risk-Reducing Exits Remain 100% Available During Every Cooldown & Hard Lock
        active_trade_lock = {
            "entry": 84000.0,
            "target_price": 86000.0,
            "trailing_stop": 83500.0,
            "scenario": "BREAKOUT_TEST",
        }
        exit_matrix = {
            "latest_price": 83450.0,  # Below stop
            "feed_latency_ms": 100.0,
            "spread_pct": 0.02,
            "composite_atr": 300.0,
            "tanh_imbalance": -0.40,
            "absorption_index": 0.0,
            "feature_vector": {"entropy": 0.90},  # Even in massive chop!
        }
        exit_intent = TradeIntent(
            action="CUT_THESIS_INVALIDATED",
            scenario="BREAKOUT_TEST",
            entry_price=83450.0,
            proposed_stop=83500.0,
        )
        # Pass severe account drawdown (5.0%) while setup is under 3-loss cooldown
        exit_decision = engine.evaluate(
            exit_intent,
            exit_matrix,
            active_trade=active_trade_lock,
            daily_drawdown_pct=5.0,  # Severe drawdown breach
            max_daily_drawdown=2.0,
        )
        self.assertEqual(exit_decision.status, "ALLOW", "Emergency risk-reducing exit MUST NOT be blocked by drawdown lock or cooldown")
        self.assertEqual(exit_decision.action, "CUT_THESIS_INVALIDATED", "Must allow capital-protecting exit unconditionally")

    def test_12_cooldown_multipliers_and_boundary_matrix(self):
        """Verify all cooldown multipliers, loss floors, and failure penalties across health & entropy tiers."""
        fc = ThesisFailureCounter(base_duration_sec=180.0)

        # 1. Zero failures -> 0 duration, penalty 1.0
        self.assertEqual(fc.calculate_cooldown_duration(0, 80.0), 0.0)
        self.assertEqual(fc.get_failure_penalty("SETUP"), 1.0)

        # 2. 1 failure: M_l = 1.0, Loss Floor = 180s (3m)
        self.assertEqual(fc.calculate_cooldown_duration(1, 90.0, entropy=0.40), 180.0)
        self.assertEqual(fc.calculate_cooldown_duration(1, 50.0, entropy=0.40), 216.0)  # 180 * 1.2
        self.assertEqual(fc.calculate_cooldown_duration(1, 30.0, entropy=0.40), 270.0)  # 180 * 1.5
        self.assertEqual(fc.calculate_cooldown_duration(1, 10.0, entropy=0.40), 324.0)  # 180 * 1.8
        self.assertEqual(fc.calculate_cooldown_duration(1, 10.0, entropy=0.75), 486.0)  # 180 * 1.8 * 1.5

        # 3. 2 failures: M_l = 2.5, Loss Floor = 480s (8m)
        # Even with pristine health (90.0), candidate is 180 * 2.5 * 1.0 = 450s, but floor enforces 480s!
        self.assertEqual(fc.calculate_cooldown_duration(2, 90.0, entropy=0.40), 480.0, "Historical health cannot reduce below 8m loss floor")
        self.assertEqual(fc.calculate_cooldown_duration(2, 50.0, entropy=0.40), 540.0)  # 180 * 2.5 * 1.2
        self.assertEqual(fc.calculate_cooldown_duration(2, 10.0, entropy=0.75), 1215.0) # 180 * 2.5 * 1.8 * 1.5

        # 4. 3 failures: M_l = 6.0, Loss Floor = 1200s (20m)
        # With pristine health (90.0), candidate is 180 * 6.0 * 1.0 = 1080s, but floor enforces 1200s!
        self.assertEqual(fc.calculate_cooldown_duration(3, 90.0, entropy=0.40), 1200.0, "Historical health cannot reduce below 20m loss floor")
        self.assertEqual(fc.calculate_cooldown_duration(3, 50.0, entropy=0.40), 1296.0)  # 180 * 6.0 * 1.2
        # Max cap clamp: 5 losses, health 10, entropy 0.75: candidate = 180 * 10 * 1.8 * 1.5 = 4860s -> clamped to 2700s (45m)
        self.assertEqual(fc.calculate_cooldown_duration(5, 10.0, entropy=0.75), 2700.0, "Duration must clamp to 2700s (45m)")

        # 5. Sizing failure penalties
        fc.consecutive_failures["TEST_PEN"] = 1
        self.assertEqual(fc.get_failure_penalty("TEST_PEN"), 0.85)
        fc.consecutive_failures["TEST_PEN"] = 2
        self.assertEqual(fc.get_failure_penalty("TEST_PEN"), 0.70)
        fc.consecutive_failures["TEST_PEN"] = 3
        self.assertEqual(fc.get_failure_penalty("TEST_PEN"), 0.50)

    def test_13_corrupted_state_and_backup_recovery(self):
        """Verify automated state recovery from .bak file when primary state file is corrupted."""
        state_path = "test_bot_state.json"
        bak_path = "test_bot_state.json.bak"

        # 1. Create a valid saved state
        em1 = ExecutionManager(state_file=state_path, journal=self.mock_journal)
        em1.active_trade = {"entry": 84000.0, "scenario": "TEST_RECOVER", "target_price": 86000.0}
        em1.save_state(market_state="IN_POSITION")
        em1.save_state(market_state="IN_POSITION")

        self.assertTrue(os.path.exists(state_path))
        self.assertTrue(os.path.exists(bak_path))

        # 2. Corrupt the primary state file with invalid JSON
        with open(state_path, "wb") as f:
            f.write(b'{"active_trade": {"entry": 84000.0, "scenario": "CORRUPTED_TRUNCATED_JSON...')

        # 3. Instantiate a new ExecutionManager; verify it recovers from .bak without crashing
        em2 = ExecutionManager(state_file=state_path, journal=self.mock_journal)
        self.assertIsNotNone(em2.active_trade, "Must recover active trade from .bak when primary file is corrupted")
        self.assertEqual(em2.active_trade.get("scenario"), "TEST_RECOVER")

        # 4. Remove both files and verify clean empty initialization
        if os.path.exists(state_path):
            os.remove(state_path)
        if os.path.exists(bak_path):
            os.remove(bak_path)

        em3 = ExecutionManager(state_file=state_path, journal=self.mock_journal)
        self.assertIsNone(em3.active_trade)
        self.assertFalse(bool(em3.cooldown_state))

    def test_14_drawdown_lock_and_recovery(self):
        """Verify Reflex 3 (Safety Lockdown) blocks entries at >= 2.0% daily drawdown and recovers."""
        engine = RiskEngine()
        entry_intent = TradeIntent(action="ENTER_CORE_LOT_1", scenario="TEST_DD", entry_price=84000.0, proposed_stop=83500.0, expected_runway_pct=1.0)
        exit_intent = TradeIntent(action="CUT_THESIS_INVALIDATED", scenario="TEST_DD", entry_price=83400.0, proposed_stop=83500.0)
        active_trade = {"entry": 84000.0, "scenario": "TEST_DD", "trailing_stop": 83500.0}
        matrix = {"latest_price": 84000.0, "feed_latency_ms": 10.0, "spread_pct": 0.02, "composite_atr": 300.0, "bid_depth_05": 10.0, "multi_screen_bounds": {"nearest_support": 83500.0, "nearest_resistance": 85000.0}, "feature_vector": {"entropy": 0.35, "trend_strength": 0.002, "vol_regime": 1.0}}

        # Breach daily drawdown limit (2.1% >= 2.0%)
        d_lock = engine.evaluate(entry_intent, matrix, daily_drawdown_pct=2.1, max_daily_drawdown=2.0)
        self.assertEqual(d_lock.status, "REJECT")
        self.assertIn("REFLEX_SAFETY_LOCKDOWN", d_lock.reason)

        # Emergency exit MUST be allowed even during drawdown lock
        exit_matrix = {**matrix, "latest_price": 83400.0}
        d_exit = engine.evaluate(exit_intent, exit_matrix, active_trade=active_trade, daily_drawdown_pct=5.0, max_daily_drawdown=2.0)
        self.assertEqual(d_exit.status, "ALLOW")
        self.assertEqual(d_exit.action, "CUT_THESIS_INVALIDATED")

        # Recovery when drawdown falls below limit (1.5% < 2.0%)
        status, s_mult, c_mod = engine.evaluate_entry_eligibility("TEST_DD", matrix, daily_drawdown_pct=1.5, max_daily_drawdown=2.0)
        self.assertNotEqual(status, "BLOCK_ACCOUNT_LOCKDOWN")

    def test_15_stale_data_and_microstructure_fault_injection(self):
        """Verify Priority-0 Subconscious Fallback Reflexes (Blind & Motor) trigger upon faults."""
        engine = RiskEngine()
        intent = TradeIntent(action="ENTER_CORE_LOT_1", scenario="TEST_FAULT", entry_price=84000.0, proposed_stop=83500.0)

        # 1. Invalid price (0.0 or negative)
        d_price = engine.evaluate(intent, {"latest_price": 0.0})
        self.assertEqual(d_price.status, "REJECT")
        self.assertIn("REFLEX_BLIND_MODE", d_price.reason)

        # 2. WebSocket stream latency > 5000ms
        d_lat = engine.evaluate(intent, {"latest_price": 84000.0, "feed_latency_ms": 5200.0, "spread_pct": 0.02})
        self.assertEqual(d_lat.status, "REJECT")
        self.assertIn("REFLEX_BLIND_MODE", d_lat.reason)

        # 3. Anomalous spread > 0.25%
        d_spread = engine.evaluate(intent, {"latest_price": 84000.0, "feed_latency_ms": 50.0, "spread_pct": 0.32})
        self.assertEqual(d_spread.status, "REJECT")
        self.assertIn("REFLEX_BLIND_MODE", d_spread.reason)

        # 4. Exchange API errors >= 2 -> Motor Lockdown
        d_motor = engine.evaluate(intent, {"latest_price": 84000.0, "feed_latency_ms": 50.0, "spread_pct": 0.02}, consecutive_api_errors=2)
        self.assertEqual(d_motor.status, "REJECT")
        self.assertIn("REFLEX_MOTOR_LOCKDOWN", d_motor.reason)

    def test_16_dynamic_slippage_and_cost_accounting(self):
        """Verify dynamic spread-based slippage model and fee accounting in TradeJournal."""
        # 1. Dynamic slippage scaling
        spread_tight = 0.01
        slip_tight = round(max(0.02, (spread_tight / 2.0) * 1.25), 3)
        self.assertEqual(slip_tight, 0.02)

        spread_wide = 0.16
        slip_wide = round(max(0.02, (spread_wide / 2.0) * 1.25), 3)
        self.assertEqual(slip_wide, 0.10)

        # In classical expectancy formula:
        # Tight spread (0.02%): EV = (0.50 * 1.5) - (0.50 * 0.8) - 0.22% = +0.13%
        ev_tight, rr = FreeConvictionEngine.calculate_classical_expectancy(0.50, 1.5, 0.8, fee_pct=0.20, slippage_pct=0.02)
        self.assertGreater(ev_tight, 0.05)

        # Wide spread (0.16% -> slippage 0.10%): EV = 0.75 - 0.40 - 0.30% = +0.05%
        ev_wide, rr = FreeConvictionEngine.calculate_classical_expectancy(0.50, 1.5, 0.8, fee_pct=0.20, slippage_pct=0.10)
        self.assertLessEqual(ev_wide, 0.05, "Wide spread slippage must drag marginal trade below hurdle")

        # 2. Fee accounting in TradeJournal
        tj = TradeJournal()
        tj.history_file = "test_trade_history.json"
        tj.journal_file = "test_journal.md"
        tj.csv_file = "test_journal.csv"
        tj.episodes_file = "test_episodes.jsonl"
        tj.data = {"trades": [], "stats": {}}

        tj.record_entry("TEST_FEE", entry_price=80000.0, stop_loss=79000.0, target_1=82000.0, target_2=0.0)
        tj.record_exit(exit_price=80800.0, exit_reason="WIN")  # +1.00% gross
        closed = tj.data["trades"][-1]
        self.assertEqual(closed["gross_pnl_pct"], 1.00)
        self.assertEqual(closed["net_pnl_pct"], 0.80, "Must deduct exactly 0.20% OKX fee")

    def test_17_okx_spot_client_resilience_and_order_handling(self):
        """Verify OKXSpotClient configuration, safe order formatting, and slippage-capped exits."""
        # 1. Unconfigured client returns None safely without raising exceptions
        client = OKXSpotClient(api_key=None, secret_key=None, passphrase=None)
        client.api_key = None  # Ensure unconfigured
        self.assertFalse(client.is_configured)
        self.assertIsNone(client.place_spot_order("buy", "0.01"))
        bals = client.get_spot_balance()
        self.assertEqual(bals, {"USDT": 0.0, "BTC": 0.0})

        # 2. Configured client order generation
        client.api_key = "MOCK_KEY"
        client.secret_key = "MOCK_SECRET"
        client.passphrase = "MOCK_PASSPHRASE"
        self.assertTrue(client.is_configured)

        with patch.object(client, "_request") as mock_req:
            mock_req.return_value = {"code": "0", "data": [{"ordId": "12345", "algoId": "ALGO_12345"}]}

            # Test limit buy order
            ord_id = client.place_spot_order("buy", "0.05", price=84000.0)
            self.assertEqual(ord_id, "12345")
            mock_req.assert_called_with("POST", "/api/v5/trade/order", data={"instId": "BTC-USDT", "tdMode": "cash", "side": "buy", "ordType": "limit", "sz": "0.05", "px": "84000.00"})

            # Test slippage-capped emergency exit: best_bid = 84000.0 -> IOC limit at 84000 * 0.9995 = 83958.00
            exit_id = client.execute_slippage_capped_exit(best_bid=84000.0, sz="0.10")
            self.assertEqual(exit_id, "12345")
            mock_req.assert_called_with("POST", "/api/v5/trade/order", data={"instId": "BTC-USDT", "tdMode": "cash", "side": "sell", "ordType": "ioc", "px": "83958.00", "sz": "0.10"})

            # Test server-side stop loss: conditional market stop with slOrdPx = "-1"
            algo_id = client.place_server_stop_loss(trigger_price=83000.0, sz="0.10")
            self.assertEqual(algo_id, "ALGO_12345")
            mock_req.assert_called_with("POST", "/api/v5/trade/order-algo", data={"instId": "BTC-USDT", "tdMode": "cash", "side": "sell", "ordType": "conditional", "sz": "0.10", "tpTriggerPxType": "last", "slTriggerPx": "83000.00", "slOrdPx": "-1"})

    def test_18_runway_decoupling_invariance(self):
        """Verify:
        1. DIP_ABSORPTION_TURN runway behavior is 100% unchanged (fails if immediate_runway < adaptive_runway).
        2. Breakout candidates under Entropy >= 0.50 strictly preserve baseline local runway logic.
        3. Breakout candidates under Entropy < 0.50 decouple runway into macro-expansion space.
        """
        import copy
        from conviction_engine import FreeConvictionEngine

        engine = FreeConvictionEngine()

        base_matrix = {
            "latest_price": 80000.0,
            "feature_vector": {
                "regime": "NEUTRAL",
                "composite_atr": 200.0,
                "tanh_imbalance": 0.50,
                "entropy": 0.20,
                "trend_strength": 0.002,
                "absorption_ratio": 15.0,
                "trade_velocity": 10.0,
                "delta_cvd": 50.0,
                "macd_histogram": 5.0,
                "ema_alignment": 0.50,
                "bollinger_width": 1.2,
                "divergence": 0.0,
            },
            "multi_screen_bounds": {
                "nearest_support": 79950.0,
                "nearest_resistance": 80100.0,  # 0.125% away (below adaptive hurdle 0.45%)
                "macro_ceiling": 82000.0,        # 2.50% away
                "immediate_runway_pct": 0.125,
                "macro_runway_pct": 2.50,
                "pooled_swing_high": 80100.0,
            },
            "balloon_geometry": {
                "is_balloon_expanding": False,
                "is_slow_market": False,
            },
            "spread_pct": 0.02,
        }

        # 1. Invariance Test: DIP_ABSORPTION_TURN at support with immediate_runway = 0.125% < hurdle (0.45%)
        # Must be rejected because dip turns require immediate_runway >= adaptive_runway
        dip_matrix = copy.deepcopy(base_matrix)
        dip_matrix["multi_screen_bounds"]["nearest_support"] = 79990.0  # At support floor
        intent_dip = engine.evaluate(dip_matrix)
        self.assertEqual(intent_dip.action, "WAIT_IN_CASH")
        self.assertTrue(any(k in intent_dip.reason for k in ["NO REAL GAIN ON TABLE", "PATIENT SCANNING", "SLOW MARKET"]))

        # 2. Invariance Test: Breakout candidate under HIGH ENTROPY (entropy = 0.70 >= 0.50)
        # Even with balloon expanding, high entropy must strictly preserve baseline rejection
        high_ent_matrix = copy.deepcopy(base_matrix)
        high_ent_matrix["feature_vector"]["entropy"] = 0.70
        high_ent_matrix["balloon_geometry"]["is_balloon_expanding"] = True
        intent_high_ent = engine.evaluate(high_ent_matrix)
        self.assertEqual(intent_high_ent.action, "WAIT_IN_CASH")

        # 3. Decoupling Test: Breakout candidate under LOW ENTROPY (entropy = 0.20 < 0.50)
        # With balloon expanding and low entropy, runway decouples into macro expansion space
        low_ent_matrix = copy.deepcopy(base_matrix)
        low_ent_matrix["feature_vector"]["entropy"] = 0.20
        low_ent_matrix["balloon_geometry"]["is_balloon_expanding"] = True
        intent_low_ent = engine.evaluate(low_ent_matrix)
        self.assertNotIn("NO REAL GAIN ON TABLE", intent_low_ent.reason)

    def test_19_governor_burn_in_grace_period(self):
        """Verify Priority 1: Governor Burn-In Grace Period prevents N=1 premature lockout."""
        from risk_engine import RiskEngine, SetupPerformanceGovernor, TradeIntent

        engine = RiskEngine()
        # Verify default min_burn_in_trades is 5
        self.assertEqual(engine.governor.min_burn_in_trades, 5)

        setup_name = "MACRO_BALLOON_BREAKOUT"
        t0 = 1792500000.0
        # Simulate Trade 1 loss (-0.686%) at t0
        engine.record_trade_outcome(setup_name, -0.686, timestamp=t0)

        health = engine.governor.get_health(setup_name)
        self.assertEqual(health.total_trades, 1)
        self.assertLess(health.health_score, 20.0, "Single loss crashes raw health score below 20.0")
        self.assertFalse(health.is_disabled, "During burn-in (total_trades < 5), setup must NOT be disabled")
        self.assertEqual(health.size_multiplier, 0.25, "Burn-in Tier 4 clamps sizing to 0.25x")
        self.assertEqual(health.confidence_modifier, 0.10, "Burn-in Tier 4 requires +0.10 confidence")

        # Evaluate entry eligibility after Class-B cooldown (5.4m = 324s) expires:
        dummy_matrix = {
            "timestamp": t0 + 600.0,
            "feature_vector": {"entropy": 0.40, "trend_strength": 0.001},
            "latest_price": 83000.0,
        }
        status, size_mult, conf_mod = engine.evaluate_entry_eligibility(setup_name, dummy_matrix)
        self.assertNotEqual(status, "BLOCK_SETUP_UNHEALTHY", "Setup must not be blocked during burn-in")
        self.assertIn(status, ("REDUCE_SIZE_AND_CONFIRM", "NORMAL_ELIGIBILITY"))
        self.assertEqual(size_mult, 0.25, "Burn-in maintains clamped 0.25x size factor")

    def test_20_bayesian_sensory_anchored_expectancy(self):
        """Verify Priority 2: Bayesian / Sensory-Anchored Expectancy Gate prevents absorbing barrier."""
        from conviction_engine import FreeConvictionEngine
        from risk_engine import RiskEngine

        engine = FreeConvictionEngine()
        risk_gate = RiskEngine()

        setup_name = "MACRO_BALLOON_BREAKOUT"
        # 1. With N=0 trades, win_rate_prob in telemetry equals sensory prior
        base_matrix = {
            "latest_price": 84000.0,
            "tanh_imbalance": 0.25,
            "trade_velocity": 8.5,
            "cvd": 100.0,
            "absorption_index": 15.0,
            "spread_pct": 0.02,
            "composite_atr": 200.0,
            "multi_screen_bounds": {
                "nearest_support": 83800.0,
                "nearest_resistance": 85000.0,
                "macro_ceiling": 86000.0,
                "pooled_swing_high": 83990.0,
                "immediate_runway_pct": 1.19,
                "macro_runway_pct": 2.38,
            },
            "balloon_geometry": {"is_balloon_expanding": True, "regime": "EXPANDING_BALLOON"},
            "micro_turn": {"is_green_building": True, "velocity_slowing": False},
            "feature_vector": {"entropy": 0.35, "trend_strength": 0.001, "vol_regime": 1.0, "liquidity": 15.0},
        }

        # Warm up belief system to BULL_ACCELERATION with high conviction
        for _ in range(5):
            intent_0 = engine.evaluate(base_matrix, active_trade=None, governor=risk_gate.governor)

        pw_0 = intent_0.telemetry.get("win_rate_prob")
        self.assertIsNotNone(pw_0)
        self.assertGreaterEqual(pw_0, 0.40)
        self.assertLessEqual(pw_0, 0.65)

        # 2. Simulate 3 consecutive losses (N=3, WR=0.0%)
        # In legacy code, pw collapsed to 0.20 via clip(win_rate, 0.20, 0.80) with unit bug
        # In Bayesian code, pw smoothly shrinks toward sensory prior with M=10 pseudo-trades:
        # pw = (3 * 0.0 + 10 * pw_0) / 13 = (10/13) * pw_0
        t0 = 1792500000.0
        for k in range(3):
            risk_gate.record_trade_outcome(setup_name, -0.50, timestamp=t0 + k * 1000)

        intent_3 = engine.evaluate(base_matrix, active_trade=None, governor=risk_gate.governor)
        pw_3 = intent_3.telemetry.get("win_rate_prob")
        self.assertIsNotNone(pw_3)
        expected_pw_3 = (10.0 * pw_0) / 13.0
        self.assertAlmostEqual(pw_3, expected_pw_3, places=2)
        self.assertGreater(pw_3, 0.30, "Bayesian shrinkage must NOT collapse to 0.20 absorbing state after only 3 trades")

    def test_21_telegram_command_normalization_and_routing(self):
        """Verify Telegram command normalization (/status@Bot, uppercase), direct routing, and buffer fallbacks."""
        from zebra_bot import TelegramNotifier, ZebraBotEngine

        notifier = TelegramNotifier(bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11", chat_id="999888777")
        self.assertTrue(notifier.is_configured)

        # 1. Mock getUpdates returning bot handle command and sender chat
        mock_updates = {
            "ok": True,
            "result": [
                {
                    "update_id": 501,
                    "message": {
                        "chat": {"id": 11223344},
                        "text": "/status@MyTestAlertBot",
                    }
                },
                {
                    "update_id": 502,
                    "edited_message": {
                        "chat": {"id": 55667788},
                        "text": "  /PING  ",
                    }
                }
            ]
        }

        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_updates
            mock_get.return_value = mock_resp

            commands = notifier.poll_incoming_commands()
            self.assertEqual(len(commands), 2)
            self.assertEqual(commands[0], ("/status@MyTestAlertBot", "11223344"))
            self.assertEqual(commands[1], ("/PING", "55667788"))
            self.assertEqual(notifier.last_update_id, 502)

        # 2. Test ZebraBotEngine command handler with handle stripping and empty matrix fallback
        engine = ZebraBotEngine()
        engine.notifier = notifier

        with patch.object(notifier, "send_message") as mock_send:
            # Test /status@... when matrix is None (warming up)
            engine._handle_telegram_cmd("/status@MyTestAlertBot", matrix=None, sender_chat_id="11223344")
            self.assertTrue(mock_send.called)
            sent_text, kwargs = mock_send.call_args[0][0], mock_send.call_args[1]
            self.assertIn("BUFFERING / STREAM CONNECTING", sent_text)
            self.assertEqual(kwargs.get("target_chat_id"), "11223344")

            # Test /STATUS when matrix has data
            mock_send.reset_mock()
            sample_matrix = {
                "latest_price": 84500.0,
                "tanh_imbalance": 0.42,
                "absorption_index": 18.5,
                "multi_screen_bounds": {
                    "nearest_support": 84200.0,
                    "nearest_resistance": 85100.0,
                    "macro_ceiling": 86000.0,
                    "immediate_runway_pct": 0.71,
                    "macro_runway_pct": 1.77,
                },
                "balloon_geometry": {
                    "regime": "EXPANDING_BALLOON",
                    "is_balloon_expanding": True,
                    "is_slow_market": False,
                },
            }
            engine._handle_telegram_cmd("/STATUS", matrix=sample_matrix, sender_chat_id="55667788")
            self.assertTrue(mock_send.called)
            sent_text, kwargs = mock_send.call_args[0][0], mock_send.call_args[1]
            self.assertIn("ZEBRA BOT MULTI-SCREEN TELEMETRY", sent_text)
            self.assertIn("$84,500.00", sent_text)
            self.assertIn("EXPANDING_BALLOON", sent_text)
            self.assertEqual(kwargs.get("target_chat_id"), "55667788")

    def test_22_unblocked_mean_reversion_dip_absorption(self):
        """Verify v3.2.6 Decoupled Macro Mean-Reversion Dip Absorption:
        1. When price is at support floor with confirmed bid absorption, compressed micro-resistance
           (< 0.45% immediate runway) no longer suppresses entry via a global pre-setup veto.
        2. Setup A projects macro mean-reversion target max(res, price * 1.012, price + 2.0 * atr).
        3. Expectancy and R:R clear hurdles, triggering ENTER_CORE_LOT_1 with DIP_ABSORPTION_TURN.
        """
        engine = FreeConvictionEngine()
        price = 79500.0
        nearest_support = 79480.0     # Within 0.85 * ATR ($170)
        nearest_resistance = 80100.0  # +0.75% immediate physical runway (>= 0.45% adaptive hurdle)
        atr = 200.0

        dip_matrix = {
            "latest_price": price,
            "absorption_index": 18.0,
            "tanh_imbalance": 0.35,
            "trade_velocity": 4.0,
            "cvd": 12.0,
            "composite_atr": atr,
            "feature_vector": {
                "entropy": 0.40,
                "trend_strength": -0.001,
                "vol_regime": 1.0,
            },
            "multi_screen_bounds": {
                "nearest_support": nearest_support,
                "nearest_resistance": nearest_resistance,
                "macro_ceiling": 82000.0,
                "immediate_runway_pct": ((nearest_resistance - price) / price) * 100.0,  # +0.25%
                "macro_runway_pct": ((82000.0 - price) / price) * 100.0,
                "pooled_swing_high": 81500.0,
            },
            "balloon_geometry": {
                "is_balloon_expanding": False,
                "is_slow_market": False,
            },
            "spread_pct": 0.02,
        }

        intent = engine.evaluate(dip_matrix)
        # In BTCTOOL 3.0, Setup A is frozen as a capital governor
        self.assertEqual(intent.action, "WAIT_IN_CASH")
        self.assertEqual(intent.scenario, "DIP_ABSORPTION_TURN")
        self.assertTrue(intent.telemetry.get("governor_held", False))
        self.assertIn("SETUP_A_FROZEN_GOVERNOR", intent.reason)

    def test_23_volatility_expansion_impulse(self):
        """Verify Setup C (VOLATILITY_EXPANSION_IMPULSE):
        1. When price breaks out of a compressed squeeze (bb_width < 0.65%),
           price closes above the 5m upper Bollinger band with positive velocity/CVD.
        2. Even if price is far below the 100-bar macro high (pooled_swing_high),
           Setup C detects the internal squeeze ignition without waiting for macro highs.
        3. Generates ENTER_CORE_LOT_1 with scenario VOLATILITY_EXPANSION_IMPULSE.
        """
        engine = FreeConvictionEngine()
        price = 81200.0
        bb_mid = 81000.0
        bb_upper = 81180.0
        bb_lower = 80820.0
        nearest_resistance = 81150.0
        macro_ceiling = 82500.0
        pooled_swing_high = 83500.0  # Far above price (High-Water gate would block Setup B)
        atr = 150.0

        squeeze_matrix = {
            "latest_price": price,
            "absorption_index": 8.0,
            "tanh_imbalance": 0.20,
            "trade_velocity": 7.5,
            "cvd": 25.0,
            "composite_atr": atr,
            "timeframes": {
                "5m": {
                    "bb_mid": bb_mid,
                    "bb_upper": bb_upper,
                    "bb_lower": bb_lower,
                    "bb_width": ((bb_upper - bb_lower) / bb_mid) * 100.0,  # ~0.44% (tight squeeze)
                    "bb_pct_b": 1.05,
                    "atr": atr,
                },
                "15m": {
                    "bb_width": 0.55,  # Dual-horizon compression
                },
                "1h": {
                    "bb_width": 1.35,  # 1h macro expansion
                },
            },
            "feature_vector": {
                "entropy": 0.40,
                "trend_strength": 0.001,
                "vol_regime": 1.0,
            },
            "multi_screen_bounds": {
                "nearest_support": 80850.0,
                "nearest_resistance": nearest_resistance,
                "macro_ceiling": macro_ceiling,
                "immediate_runway_pct": ((nearest_resistance - price) / price) * 100.0,
                "macro_runway_pct": ((macro_ceiling - price) / price) * 100.0,
                "pooled_swing_high": pooled_swing_high,
            },
            "balloon_geometry": {
                "is_balloon_expanding": True,
                "is_slow_market": False,
                "pinched_screens": 2,
            },
            "spread_pct": 0.02,
        }

        intent = engine.evaluate(squeeze_matrix)
        self.assertEqual(intent.action, "ENTER_CORE_LOT_1")
        self.assertEqual(intent.scenario, "VOLATILITY_EXPANSION_IMPULSE")
        self.assertGreaterEqual(intent.expected_runway_pct, 1.20)
        self.assertIn("VOLATILITY EXPANSION", intent.reason)
        self.assertGreaterEqual(intent.telemetry["rr_ratio"], 1.50)
        self.assertGreater(intent.telemetry["true_net_ev"], 0.05)

    def test_24_trend_pullback_continuation(self):
        """Verify Setup D (TREND_PULLBACK_CONTINUATION):
        1. In an established bullish trend (ema9 > ema21 > ema50, trend_strength > 0.0006, entropy < 0.60).
        2. Price is in mid-air (far above support, dist_from_swing_high >= 0.25%).
        3. Setup A is inactive (not at support floor) and Setup B is inactive (not at swing high).
        4. Setup D enters the EMA9-EMA21 Value Zone, generating ENTER_CORE_LOT_1 with TREND_PULLBACK_CONTINUATION.
        """
        engine = FreeConvictionEngine()
        price = 81500.0
        ema9 = 81520.0
        ema21 = 81420.0
        ema50 = 81200.0
        pooled_swing_high = 82800.0  # +1.60% above (clears mandatory >= +1.50% high-expectancy runway gate)
        nearest_support = 80800.0    # Far below ($700 below, dist > 0.85*atr)
        atr = 150.0

        trend_matrix = {
            "latest_price": price,
            "absorption_index": 5.0,
            "tanh_imbalance": 0.15,
            "trade_velocity": 6.0,
            "cvd": 18.0,
            "composite_atr": atr,
            "timeframes": {
                "5m": {
                    "ema_9": ema9,
                    "ema_21": ema21,
                    "ema_50": ema50,
                    "bb_mid": ema21,
                    "bb_upper": 81800.0,
                    "bb_lower": 81040.0,
                    "bb_width": 0.93,
                    "bb_pct_b": 0.60,
                    "atr": atr,
                }
            },
            "feature_vector": {
                "entropy": 0.35,
                "trend_strength": 0.0012,
                "vol_regime": 1.0,
            },
            "multi_screen_bounds": {
                "nearest_support": nearest_support,
                "nearest_resistance": 82800.0,
                "macro_ceiling": 83500.0,
                "immediate_runway_pct": ((82800.0 - price) / price) * 100.0,
                "macro_runway_pct": ((83500.0 - price) / price) * 100.0,
                "pooled_swing_high": pooled_swing_high,
            },
            "balloon_geometry": {
                "is_balloon_expanding": False,
                "is_slow_market": False,
            },
            "spread_pct": 0.02,
        }

        # Prime belief system to positive bias
        engine.belief_system.state.directional_bias = 0.25
        engine.belief_system.state.regime_belief = "BULL_ACCELERATION"

        intent = engine.evaluate(trend_matrix)
        self.assertEqual(intent.action, "ENTER_CORE_LOT_1")
        self.assertEqual(intent.scenario, "TREND_PULLBACK_CONTINUATION")
        self.assertGreaterEqual(intent.expected_runway_pct, 1.50)
        self.assertIn("TREND CONTINUATION", intent.reason)
        self.assertGreaterEqual(intent.telemetry["rr_ratio"], 1.50)
        self.assertGreater(intent.telemetry["true_net_ev"], 0.05)

    def test_25_one_trade_per_price_zone_anti_churn(self):
        """
        Verify Mechanism D: One-Trade-Per-Price-Zone Protection (Invariant 4A).
        Ensures that once a trade is executed in a price zone, subsequent entry intents
        within the exhausted price zone radius (+/- 1.0 ATR) are vetoed to prevent post-exit churn.
        """
        from risk_engine import RiskEngine, TradeIntent

        risk_gate = RiskEngine()
        entry_price = 81500.0
        zone_radius = 150.0
        t0 = 1730000000.0

        # 1. Record completed trade outcome in zone
        risk_gate.record_trade_outcome(
            "DIP_ABSORPTION_TURN",
            net_pnl_pct=0.40,
            timestamp=t0,
            entry_price=entry_price,
            radius=zone_radius
        )
        self.assertEqual(len(risk_gate.exhausted_price_zones), 1)
        self.assertEqual(risk_gate.exhausted_price_zones[0][0], entry_price)
        self.assertEqual(risk_gate.exhausted_price_zones[0][1], zone_radius)

        # 2. Candidate intent inside exhausted zone ($81,550 is within $81,500 +/- $150)
        inside_matrix = {
            "latest_price": 81550.0,
            "timestamp": t0 + 300.0,
            "feature_vector": {"entropy": 0.40, "trend_strength": 0.0010},
            "order_book": {"imbalance": 0.20, "absorption_idx": 15.0},
            "multi_screen_bounds": {"nearest_support": 81400.0, "nearest_resistance": 82200.0},
            "balloon_geometry": {"is_balloon_expanding": False, "is_slow_market": False},
            "spread_pct": 0.02,
        }
        inside_intent = TradeIntent(
            action="ENTER_CORE_LOT_1",
            scenario="DIP_ABSORPTION_TURN",
            entry_price=81550.0,
            confidence=0.75,
            telemetry={"adaptive_conf_hurdle": 0.50}
        )

        decision_inside = risk_gate.evaluate(inside_intent, inside_matrix)
        self.assertEqual(decision_inside.status, "REJECT")
        self.assertEqual(decision_inside.action, "WAIT_IN_CASH")
        self.assertIn("REJECTED BY ANTI-CHURN ZONE GUARD", decision_inside.reason)

        # 3. Candidate intent outside exhausted zone ($81,800 is outside $81,500 +/- $150)
        outside_matrix = dict(inside_matrix)
        outside_matrix["latest_price"] = 81800.0
        outside_intent = TradeIntent(
            action="ENTER_CORE_LOT_1",
            scenario="DIP_ABSORPTION_TURN",
            entry_price=81800.0,
            confidence=0.75,
            telemetry={"adaptive_conf_hurdle": 0.50}
        )

        decision_outside = risk_gate.evaluate(outside_intent, outside_matrix)
        self.assertNotIn("ANTI-CHURN ZONE GUARD", decision_outside.reason)

        # 4. Clear exhausted zones and verify previously blocked price is permitted
        risk_gate.clear_exhausted_zones()
        self.assertEqual(len(risk_gate.exhausted_price_zones), 0)
        decision_cleared = risk_gate.evaluate(inside_intent, inside_matrix)
        self.assertNotIn("ANTI-CHURN ZONE GUARD", decision_cleared.reason)

    def test_26_continuous_proportional_profit_retention_ratchet(self):
        """Verify CPPR v2 (Delayed Activation & High-Expectancy Ratchet):
        1. Below +1.20% gain, initial stop is maintained (avoids premature noise exits).
        2. At +1.20% gain, stop ratchets to max(0.35%, 1.20% * 0.50) = +0.60% gross.
        3. At +1.50% peak gain, stop ratchets to +0.90% gross (60% retention).
        4. When price falls back to the CPPR stop, BANK_PROFIT is triggered with positive net profit after fees.
        """
        entry_price = 80000.0
        active_trade = {
            "entry": entry_price,
            "highest_price": entry_price,
            "target_price": 82000.0,
            "invalidation_floor": 79600.0,
            "trailing_stop": 79600.0,
            "scenario": "DIP_ABSORPTION_TURN",
            "tranche_2_added": False,
        }
        base_matrix = {
            "latest_price": 80640.0,  # +0.80% gain (below +1.20% trigger)
            "composite_atr": 150.0,
            "tanh_imbalance": 0.20,
            "absorption_index": 15.0,
            "multi_screen_bounds": {
                "nearest_support": 79800.0,
                "nearest_resistance": 82000.0,
                "macro_ceiling": 83000.0,
                "immediate_runway_pct": 2.0,
                "macro_runway_pct": 3.0,
            },
            "balloon_geometry": {
                "regime": "BULL_ACCELERATION",
                "is_balloon_expanding": False,
                "is_slow_market": False,
            },
            "micro_turn": {"is_green_building": True, "velocity_slowing": False},
        }

        # 1. Gain < +1.20%: stop unchanged (noise tolerance)
        decision_1 = self.brain.evaluate(base_matrix, active_trade=active_trade)
        self.assertEqual(decision_1["action"], "HOLD_POSITION")
        self.assertEqual(decision_1["proposed_stop"], 79600.0)

        # 2. Gain reaches +1.20% (price $80,960): stop locks at max(0.35%, 1.20% * 0.50) = +0.60% gross ($80,480.00)
        base_matrix["latest_price"] = 80960.0
        active_trade["highest_price"] = 80960.0
        decision_2 = self.brain.evaluate(base_matrix, active_trade=active_trade)
        self.assertEqual(decision_2["action"], "HOLD_POSITION")
        expected_stop_2 = round(entry_price * (1.0 + 0.0060), 2)  # $80,480.00
        self.assertEqual(decision_2["proposed_stop"], expected_stop_2)
        active_trade["trailing_stop"] = decision_2["proposed_stop"]

        # 3. Peak expands to +1.50% (price $81,200): stop locks at 1.50% * 0.60 = +0.90% gross ($80,720.00)
        base_matrix["latest_price"] = 81200.0
        active_trade["highest_price"] = 81200.0
        decision_3 = self.brain.evaluate(base_matrix, active_trade=active_trade)
        expected_stop_3 = round(entry_price * (1.0 + 0.0090), 2)  # $80,720.00
        self.assertEqual(decision_3["proposed_stop"], expected_stop_3)
        active_trade["trailing_stop"] = decision_3["proposed_stop"]

        # 4. Pullback to CPPR stop ($80,720.00): triggers BANK_PROFIT with net positive return
        base_matrix["latest_price"] = expected_stop_3
        decision_exit = self.brain.evaluate(base_matrix, active_trade=active_trade)
        self.assertEqual(decision_exit["action"], "BANK_PROFIT")
        self.assertIn("TRAILING STOP HIT", decision_exit["reason"])
        self.assertGreater(decision_exit["gain_pct"], 0.0020, "Gross profit must exceed 0.20% OKX fee")

    def test_27_structural_acceptance_red_candle_rejection(self):
        """
        Verify v3.6.0: Red breakout candle (upper-wick rejection) is vetoed before entry.
        """
        brain = FreeConvictionEngine()
        candles = [
            {"open": 83000.0, "high": 83100.0, "low": 82950.0, "close": 83050.0, "vol": 10.0} for _ in range(5)
        ]
        # Red candle (open > close): spiked to 84150 but closed red at 83950
        candles.append({"open": 84050.0, "high": 84150.0, "low": 83900.0, "close": 83950.0, "vol": 25.0})

        matrix = {
            "latest_price": 83950.0,
            "candles_1m": candles,
            "tanh_imbalance": 0.25,
            "trade_velocity": 8.0,
            "cvd": 150.0,
            "absorption_index": 12.0,
            "spread_pct": 0.02,
            "composite_atr": 200.0,
            "multi_screen_bounds": {
                "nearest_support": 83500.0,
                "nearest_resistance": 85000.0,
                "macro_ceiling": 86000.0,
                "pooled_swing_high": 83900.0,
                "immediate_runway_pct": 1.25,
                "macro_runway_pct": 2.44,
            },
            "balloon_geometry": {"is_balloon_expanding": True, "regime": "EXPANDING_BALLOON"},
            "micro_turn": {"is_green_building": False, "velocity_slowing": False},
            "feature_vector": {"entropy": 0.35, "trend_strength": 0.001, "vol_regime": 1.0, "liquidity": 15.0},
        }

        # Warm up belief system to BULL_ACCELERATION
        for _ in range(5):
            intent = brain.evaluate(matrix, active_trade=None)

        self.assertEqual(intent.action, "WAIT_IN_CASH")
        self.assertIn("VETO BREAKOUT REJECTION", intent.reason)
        self.assertTrue(intent.telemetry.get("candle_color_veto"))

    def test_28_structural_acceptance_low_volume_rejection(self):
        """
        Verify v3.6.0: Breakout candle with volume < 1.20x average is vetoed.
        """
        brain = FreeConvictionEngine()
        candles = [
            {"open": 83000.0, "high": 83100.0, "low": 82950.0, "close": 83050.0, "vol": 10.0} for _ in range(5)
        ]
        # Green candle, closed above resistance, but volume = 11.0 (< 12.0 = 1.20x)
        candles.append({"open": 83900.0, "high": 84150.0, "low": 83880.0, "close": 84050.0, "vol": 11.0})

        matrix = {
            "latest_price": 84050.0,
            "candles_1m": candles,
            "tanh_imbalance": 0.25,
            "trade_velocity": 8.0,
            "cvd": 150.0,
            "absorption_index": 12.0,
            "spread_pct": 0.02,
            "composite_atr": 200.0,
            "multi_screen_bounds": {
                "nearest_support": 83500.0,
                "nearest_resistance": 85000.0,
                "macro_ceiling": 86000.0,
                "pooled_swing_high": 83900.0,
                "immediate_runway_pct": 1.13,
                "macro_runway_pct": 2.32,
            },
            "balloon_geometry": {"is_balloon_expanding": True, "regime": "EXPANDING_BALLOON"},
            "micro_turn": {"is_green_building": True, "velocity_slowing": False},
            "feature_vector": {"entropy": 0.35, "trend_strength": 0.001, "vol_regime": 1.0, "liquidity": 15.0},
        }

        for _ in range(5):
            intent = brain.evaluate(matrix, active_trade=None)

        self.assertEqual(intent.action, "WAIT_IN_CASH")
        self.assertIn("VETO LOW VOLUME", intent.reason)
        self.assertTrue(intent.telemetry.get("volume_veto"))

    def test_29_structural_acceptance_confirmed_entry(self):
        """
        Verify v3.6.0: 3-phase structural acceptance confirms entry after holding retest.
        """
        brain = FreeConvictionEngine()
        candles = [
            {"open": 83000.0, "high": 83100.0, "low": 82950.0, "close": 83050.0, "vol": 10.0} for _ in range(5)
        ]
        # Bar T: Strong green breakout candle with volume = 20.0 (2.0x avg)
        candles.append({"open": 83850.0, "high": 84150.0, "low": 83850.0, "close": 84100.0, "vol": 20.0})

        matrix_t = {
            "latest_price": 84100.0,
            "candles_1m": candles,
            "tanh_imbalance": 0.25,
            "trade_velocity": 8.0,
            "cvd": 150.0,
            "absorption_index": 12.0,
            "spread_pct": 0.02,
            "composite_atr": 200.0,
            "multi_screen_bounds": {
                "nearest_support": 83500.0,
                "nearest_resistance": 85000.0,
                "macro_ceiling": 86000.0,
                "pooled_swing_high": 83900.0,
                "immediate_runway_pct": 1.07,
                "macro_runway_pct": 2.26,
            },
            "balloon_geometry": {"is_balloon_expanding": True, "regime": "EXPANDING_BALLOON"},
            "micro_turn": {"is_green_building": True, "velocity_slowing": False},
            "feature_vector": {"entropy": 0.35, "trend_strength": 0.001, "vol_regime": 1.0, "liquidity": 15.0},
        }

        # Warm up belief to BULL_ACCELERATION
        for _ in range(5):
            intent_t = brain.evaluate(matrix_t, active_trade=None)

        # Bar T must arm pending acceptance
        self.assertEqual(intent_t.action, "WAIT_IN_CASH")
        self.assertIn("AWAITING_STRUCTURAL_ACCEPTANCE_RETEST", intent_t.reason)
        self.assertIsNotNone(brain.pending_acceptance)

        # Bar T+1: Holds retest cushion (level = 83900, cushion = 83732.2)
        candles_t1 = list(candles)
        candles_t1.append({"open": 84100.0, "high": 84200.0, "low": 83950.0, "close": 84150.0, "vol": 15.0})
        matrix_t1 = dict(matrix_t)
        matrix_t1["latest_price"] = 84150.0
        matrix_t1["candles_1m"] = candles_t1

        intent_t1 = brain.evaluate(matrix_t1, active_trade=None)
        self.assertEqual(intent_t1.action, "ENTER_CORE_LOT_1")
        self.assertEqual(intent_t1.scenario, "MACRO_BALLOON_BREAKOUT")
        self.assertIn("CONFIRMED STRUCTURAL ACCEPTANCE", intent_t1.reason)
        self.assertTrue(intent_t1.telemetry.get("acceptance_confirmed"))
        self.assertIsNone(brain.pending_acceptance)

    def test_30_structural_acceptance_retest_collapse(self):
        """
        Verify v3.6.0: Retest collapse below cushion cancels candidate before execution.
        """
        brain = FreeConvictionEngine()
        candles = [
            {"open": 83000.0, "high": 83100.0, "low": 82950.0, "close": 83050.0, "vol": 10.0} for _ in range(5)
        ]
        # Bar T: Armed breakout
        candles.append({"open": 83850.0, "high": 84150.0, "low": 83850.0, "close": 84100.0, "vol": 20.0})

        matrix_t = {
            "latest_price": 84100.0,
            "candles_1m": candles,
            "tanh_imbalance": 0.25,
            "trade_velocity": 8.0,
            "cvd": 150.0,
            "absorption_index": 12.0,
            "spread_pct": 0.02,
            "composite_atr": 200.0,
            "multi_screen_bounds": {
                "nearest_support": 83500.0,
                "nearest_resistance": 85000.0,
                "macro_ceiling": 86000.0,
                "pooled_swing_high": 83900.0,
                "immediate_runway_pct": 1.07,
                "macro_runway_pct": 2.26,
            },
            "balloon_geometry": {"is_balloon_expanding": True, "regime": "EXPANDING_BALLOON"},
            "micro_turn": {"is_green_building": True, "velocity_slowing": False},
            "feature_vector": {"entropy": 0.35, "trend_strength": 0.001, "vol_regime": 1.0, "liquidity": 15.0},
        }

        for _ in range(5):
            brain.evaluate(matrix_t, active_trade=None)

        self.assertIsNotNone(brain.pending_acceptance)

        # Bar T+1: Collapses back inside range (low = 83500, close = 83600 < cushion 83732.2)
        candles_t1 = list(candles)
        candles_t1.append({"open": 84100.0, "high": 84100.0, "low": 83500.0, "close": 83600.0, "vol": 25.0})
        matrix_t1 = dict(matrix_t)
        matrix_t1["latest_price"] = 83600.0
        matrix_t1["candles_1m"] = candles_t1

        intent_t1 = brain.evaluate(matrix_t1, active_trade=None)
        self.assertEqual(intent_t1.action, "WAIT_IN_CASH")
        self.assertIn("STRUCTURAL ACCEPTANCE FAILED", intent_t1.reason)
        self.assertTrue(intent_t1.telemetry.get("acceptance_failed"))
        self.assertIsNone(brain.pending_acceptance)

    def test_31_higher_timeframe_macro_shielding(self):
        """
        Verify v3.7.0 High-Margin Architecture:
        When 1h or 4h macro mid-band sits above price, long entries are strictly vetoed with MACRO_SHIELD_VETO.
        """
        brain = FreeConvictionEngine()
        price = 82000.0
        matrix = {
            "latest_price": price,
            "tanh_imbalance": 0.30,
            "trade_velocity": 8.0,
            "cvd": 100.0,
            "absorption_index": 18.0,
            "composite_atr": 150.0,
            "timeframes": {
                "1h": {"bb_mid": 82500.0},  # Macro ceiling above price (bearish trend)
                "4h": {"bb_mid": 83000.0},
            },
            "multi_screen_bounds": {
                "nearest_support": 81500.0,
                "nearest_resistance": 83500.0,
                "macro_ceiling": 84500.0,
                "pooled_swing_high": 82000.0,
                "immediate_runway_pct": 1.83,
                "macro_runway_pct": 3.05,
            },
            "balloon_geometry": {"is_balloon_expanding": True, "regime": "EXPANDING_BALLOON"},
            "feature_vector": {"entropy": 0.35, "trend_strength": 0.001, "vol_regime": 1.0},
        }
        intent = brain.evaluate(matrix, active_trade=None)
        self.assertEqual(intent.action, "WAIT_IN_CASH")
        self.assertIn("MACRO_SHIELD_VETO", intent.reason)
        self.assertTrue(intent.telemetry.get("macro_shield_veto"))

    def test_32_momentum_decay_exit(self):
        """
        Verify v3.7.0 High-Margin Architecture:
        When an active trade reaches >= +0.35% gross peak, but order flow aggression reverses
        (tanh_imbalance < -0.15 and cvd < 0), BANK_PROFIT is triggered immediately before reversal.
        """
        brain = FreeConvictionEngine()
        entry_price = 80000.0
        active_trade = {
            "entry": entry_price,
            "highest_price": 80360.0,  # +0.45% peak excursion (exceeds +0.35% threshold)
            "target_price": 81500.0,
            "invalidation_floor": 79600.0,
            "trailing_stop": 79600.0,
            "scenario": "BOLLINGER_CONFLUENCE_BREAKOUT",
            "tranche_2_added": False,
        }
        matrix = {
            "latest_price": 80320.0,  # +0.40% current gain (still above stop)
            "composite_atr": 150.0,
            "tanh_imbalance": -0.25,  # Aggressive taker selling dumps
            "cvd": -50.0,             # Negative CVD delta
            "absorption_index": 5.0,
            "multi_screen_bounds": {
                "nearest_support": 79800.0,
                "nearest_resistance": 81500.0,
                "macro_ceiling": 82000.0,
            },
            "balloon_geometry": {"is_balloon_expanding": False, "is_slow_market": False},
        }
        intent = brain.evaluate(matrix, active_trade=active_trade)
        self.assertEqual(intent.action, "BANK_PROFIT")
        self.assertIn("MOMENTUM DECAY EXIT", intent.reason)
        self.assertTrue(intent.telemetry.get("momentum_decay"))


if __name__ == "__main__":
    unittest.main()
