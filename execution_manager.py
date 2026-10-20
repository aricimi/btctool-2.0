"""
execution_manager.py — Autonomous Execution & Clean Ledger Manager for Zebra Bot (btctool 2.0)
Manages multi-lot allocations, clean-slate trade journal archiving,
zero-leash immediate exits, and rich Telegram push alerts on every move.
"""

import json
import logging
import os
import shutil
import time
from typing import Dict, Optional, Tuple
from trade_logger import TradeJournal

logger = logging.getLogger("execution_manager")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_STATE_FILE = os.path.join(BASE_DIR, "bot_state.json")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive_legacy_trades")


class ExecutionManager:
    """
    Manages autonomous trade execution, position tracking, and clean-slate auditing.
    """

    def __init__(self, state_file: str = BOT_STATE_FILE, journal: Optional[TradeJournal] = None):
        self.state_file = state_file
        self.journal = journal or TradeJournal()
        self.active_trade: Optional[dict] = None
        self.load_state()

    def reset_clean_slate(self):
        """Archives legacy logs and resets the ledger to start fresh from Trade #1."""
        logger.info("[Execution] Archiving legacy trade history and starting clean slate for Zebra Bot...")
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")

        files_to_archive = ["trade_history.json", "trade_journal.csv", "trade_journal.md", "bot_state.json"]
        for fname in files_to_archive:
            src = os.path.join(BASE_DIR, fname)
            if os.path.exists(src):
                dst = os.path.join(ARCHIVE_DIR, f"{timestamp_str}_{fname}")
                shutil.copy2(src, dst)

        # Reset trade_history.json to clean slate
        fresh_history = {
            "trades": [],
            "stats": {
                "total_closed_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_pct": 0.0,
                "gross_cumulative_pct": 0.0,
                "total_fees_pct": 0.0,
                "net_cumulative_pct": 0.0,
            }
        }
        with open(os.path.join(BASE_DIR, "trade_history.json"), "w", encoding="utf-8") as f:
            json.dump(fresh_history, f, indent=2)

        # Reset bot_state.json
        self.active_trade = None
        self.save_state(market_state="SCANNING")

        # Reload clean journal
        self.journal = TradeJournal()
        self.journal._recalculate_and_save()
        logger.info("[Execution] Clean slate initialized. Trade counter reset to #1.")

    def load_state(self) -> Optional[dict]:
        """Loads active trade from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.active_trade = data.get("active_trade")
                return self.active_trade
            except Exception as e:
                logger.error(f"[Execution] Error loading state: {e}")
        return None

    def save_state(self, market_state: str = "SCANNING", last_alert_time: float = 0.0):
        """Atomically saves bot state to disk."""
        try:
            payload = {
                "market_state": market_state,
                "active_trade": self.active_trade,
                "last_alert_time": last_alert_time or time.time(),
                "saved_at": time.time(),
            }
            tmp_file = f"{self.state_file}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_file, self.state_file)
        except Exception as e:
            logger.error(f"[Execution] Error saving state: {e}")

    def open_core_lot_1(
        self,
        entry_price: float,
        scenario: str,
        target_price: float,
        invalidation_floor: float,
        reason: str,
        p_up: float = 0.70,
        feature_vector: Optional[dict] = None,
        trade_intent: Optional[dict] = None,
        risk_decision: Optional[dict] = None,
    ) -> dict:
        """Opens Core Position (Lot 1) with specific Whale Thesis parameters and episodic state."""
        trade_id = self.journal.record_entry(
            setup_name=f"ZEBRA WHALE: {scenario}",
            entry_price=entry_price,
            stop_loss=invalidation_floor,
            target_1=target_price,
            target_2=0.0,
            rationale=reason,
            feature_vector=feature_vector,
            trade_intent=trade_intent,
            risk_decision=risk_decision,
        )

        self.active_trade = {
            "trade_id": trade_id,
            "entry": round(entry_price, 2),
            "highest_price": round(entry_price, 2),
            "scenario": scenario,
            "target_price": round(target_price, 2),
            "invalidation_floor": round(invalidation_floor, 2),
            "trailing_stop": round(invalidation_floor, 2),
            "tranche_2_added": False,
            "timestamp": time.time(),
            "reason": reason,
            "pre_state": {
                "feature_vector": feature_vector or {},
                "trade_intent": trade_intent or {},
                "risk_decision": risk_decision or {},
            },
        }
        self.save_state(market_state="IN_POSITION")
        logger.info(f"[Execution] Core Lot 1 opened: ${entry_price:,.2f} | Scenario: {scenario} | Target: ${target_price:,.2f}")
        return self.active_trade

    def update_trailing_stop(self, new_stop: float):
        """Ratchets trailing stop higher to lock in profits without capping the run."""
        if self.active_trade:
            current_stop = self.active_trade.get("trailing_stop", self.active_trade.get("invalidation_floor", 0.0))
            if new_stop > current_stop:
                self.active_trade["trailing_stop"] = round(new_stop, 2)
                self.save_state(market_state="IN_POSITION")
                logger.info(f"[Execution] Trailing stop ratcheted to: ${new_stop:,.2f}")

    def update_target_price(self, new_target: float):
        """Updates target price when riding uncapped macro breakout."""
        if self.active_trade:
            current_target = self.active_trade.get("target_price", 0.0)
            if new_target > current_target:
                self.active_trade["target_price"] = round(new_target, 2)
                self.save_state(market_state="IN_POSITION")
                logger.info(f"[Execution] Target price updated to macro level: ${new_target:,.2f}")

    def scale_in_lot_2(self, price: float, reason: str, p_up: float = 0.75):
        """Scales in Lot 2 on verified Bullish Absorption Dip."""
        if not self.active_trade:
            return

        old_entry = self.active_trade["entry"]
        blended_entry = round((old_entry + price) / 2.0, 2)
        self.active_trade["entry"] = blended_entry
        self.active_trade["tranche_2_added"] = True

        self.save_state(market_state="SCALED_LOT_2")
        logger.info(f"[Execution] Lot 2 scaled in at ${price:,.2f}. Blended Entry=${blended_entry:,.2f}")

    def close_position(
        self,
        exit_price: float,
        exit_reason: str,
        p_up: float = 0.50,
        feature_vector: Optional[dict] = None,
        trade_intent: Optional[dict] = None,
        risk_decision: Optional[dict] = None,
    ):
        """Closes position immediately at market and updates ledger + episodic memory."""
        if not self.active_trade:
            return

        saved_pre = self.active_trade.get("pre_state", {})
        f_vec = feature_vector or saved_pre.get("feature_vector")
        t_intent = trade_intent or saved_pre.get("trade_intent")
        r_decision = risk_decision or saved_pre.get("risk_decision")

        full_reason = f"ZEBRA EXIT: {exit_reason}"
        self.journal.record_exit(
            exit_price=exit_price,
            exit_reason=full_reason,
            feature_vector=f_vec,
            trade_intent=t_intent,
            risk_decision=r_decision,
        )
        self.active_trade = None
        self.save_state(market_state="SCANNING")
        self.journal.flush_pending_csv()
        logger.info(f"[Execution] Position closed at ${exit_price:,.2f}: {full_reason}")

    def update_highest_price(self, price: float):
        """Updates highest price reached during active trade."""
        if self.active_trade and price > self.active_trade.get("highest_price", 0.0):
            self.active_trade["highest_price"] = round(price, 2)
            self.save_state(market_state="IN_POSITION")
