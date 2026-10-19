"""
execution_manager.py — Asymmetric Position & Ledger Manager for Zebra Bot (btctool 2.0)
Manages multi-lot capital allocation (Lot 1 Core + Lot 2 Scale-in),
uncapped structural trailing stops, bot_state.json persistence, and Excel lock-proof trade auditing.
"""

import json
import logging
import os
import time
from typing import Dict, Optional, Tuple
from trade_logger import TradeJournal

logger = logging.getLogger("execution_manager")

BOT_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state.json")


class ExecutionManager:
    """
    Manages position lifecycle, stop ratchets, multi-lot scaling, and state persistence for Zebra Bot.
    """

    def __init__(self, state_file: str = BOT_STATE_FILE):
        self.state_file = state_file
        self.journal = TradeJournal()
        self.active_trade: Optional[dict] = None
        self.load_state()

    def load_state(self) -> Optional[dict]:
        """Loads persistent bot state from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.active_trade = data.get("active_trade")
                    if self.active_trade:
                        # Check staleness (> 4 hours without update)
                        saved_at = data.get("saved_at", 0)
                        if time.time() - saved_at > 14400:
                            logger.warning("[Execution] Active trade in state file is >4h stale. Discarding.")
                            self.active_trade = None
                            self.save_state()
                        else:
                            logger.info(f"[Execution] Recovered active trade: Entry=${self.active_trade.get('entry')} Stop=${self.active_trade.get('current_stop')}")
                return self.active_trade
            except Exception as e:
                logger.error(f"[Execution] Error loading state: {e}")
        return None

    def save_state(self, market_state: str = "EXPANDING", last_alert_time: float = 0.0):
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

    def open_core_lot_1(self, entry_price: float, stop_loss: float, target_1: float, target_2: float, reason: str) -> dict:
        """Opens Core Position (Lot 1)."""
        trade_id = self.journal.record_entry(
            setup_name=f"ZEBRA CORE: {reason}",
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            rationale=reason,
        )

        self.active_trade = {
            "trade_id": trade_id,
            "entry": round(entry_price, 2),
            "current_stop": round(stop_loss, 2),
            "target_1": round(target_1, 2),
            "target_2": round(target_2, 2),
            "highest_price": round(entry_price, 2),
            "target_1_hit": False,
            "breakeven_set": False,
            "tranche_2_added": False,
            "ratchet_level": 0,
            "timestamp": time.time(),
            "reason": reason,
        }
        self.save_state()
        logger.info(f"[Execution] Core Lot 1 opened: ${entry_price:,.2f} | Stop: ${stop_loss:,.2f}")
        return self.active_trade

    def scale_in_lot_2(self, price: float, new_stop: float, reason: str):
        """Scales in Lot 2 on verified Bullish Absorption Dip."""
        if not self.active_trade:
            return

        old_entry = self.active_trade["entry"]
        # Blended entry price (assuming 50% Lot 1 + 50% Lot 2)
        blended_entry = round((old_entry + price) / 2.0, 2)
        self.active_trade["entry"] = blended_entry
        self.active_trade["current_stop"] = round(new_stop, 2)
        self.active_trade["tranche_2_added"] = True

        self.save_state()
        logger.info(f"[Execution] Lot 2 scaled in at ${price:,.2f}. Blended Entry=${blended_entry:,.2f}, New Stop=${new_stop:,.2f}")

    def ratchet_stop(self, new_stop: float, reason: str, is_breakeven: bool = False):
        """Ratchets trailing stop higher to lock in gains."""
        if not self.active_trade:
            return

        current_stop = self.active_trade["current_stop"]
        if new_stop > current_stop:
            self.active_trade["current_stop"] = round(new_stop, 2)
            if is_breakeven:
                self.active_trade["breakeven_set"] = True
            self.active_trade["ratchet_level"] = self.active_trade.get("ratchet_level", 0) + 1
            self.save_state()
            logger.info(f"[Execution] Ratcheted stop: ${current_stop:,.2f} -> ${new_stop:,.2f} ({reason})")

    def close_position(self, exit_price: float, exit_reason: str):
        """Closes the active trade and updates all ledgers."""
        if not self.active_trade:
            return

        self.journal.record_exit(exit_price=exit_price, exit_reason=f"ZEBRA: {exit_reason}")
        self.active_trade = None
        self.save_state()
        self.journal.flush_pending_csv()
        logger.info(f"[Execution] Position closed at ${exit_price:,.2f}: {exit_reason}")

    def update_highest_price(self, price: float):
        """Updates the highest price reached during the trade."""
        if self.active_trade and price > self.active_trade.get("highest_price", 0.0):
            self.active_trade["highest_price"] = round(price, 2)
            self.save_state()
