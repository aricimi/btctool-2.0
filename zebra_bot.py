"""
zebra_bot.py — Truly Free Autonomous 100-Screen Real-Time Quant Engine for btctool 2.0
Continuous sub-second event loop, AlphaGo-style Expected Value decision brain,
clean-slate ledger auditing, and instantaneous rich Telegram push alerts on every move.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, Tuple, List
import asyncio
import datetime
import gc
import json
import logging
import os
import re
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

import requests

from market_stream import MarketStream
from market_state import MarketState
from conviction_engine import FreeConvictionEngine
from risk_engine import RiskEngine, TradeIntent, RiskDecision
from execution_manager import ExecutionManager
from trade_logger import TradeJournal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("zebra_bot")

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_config.json")
DEFAULT_BOT_TOKEN = ""
DEFAULT_CHAT_ID = "8922701269"


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Responds to Render and UptimeRobot HTTP pings to keep service alive 24/7."""
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        payload = {
            "status": "online",
            "service": "btctool 2.0 Truly Free Zebra Bot Engine",
            "utc_time": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format, *args):
        return


def start_health_server(port: int = 10000) -> Optional[HTTPServer]:
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"[HealthServer] Running on port {port}")
        return server
    except Exception as e:
        logger.warning(f"[HealthServer] Could not start HTTP server on port {port}: {e}")
        return None


class TelegramNotifier:
    """Handles delivery of instant push alerts and on-demand commands."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

        if (not self.bot_token or not self.chat_id) and os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                    self.bot_token = self.bot_token or cfg.get("bot_token")
                    self.chat_id = self.chat_id or cfg.get("chat_id")
            except Exception:
                pass

        self.bot_token = self.bot_token or DEFAULT_BOT_TOKEN
        self.chat_id = self.chat_id or DEFAULT_CHAT_ID
        self.last_update_id = 0

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and self.bot_token != "YOUR_BOT_TOKEN_HERE")

    def send_message(self, text: str, target_chat_id: Optional[str] = None) -> bool:
        """Sends an HTML formatted push message directly to Telegram."""
        if not self.is_configured:
            return False

        dest_chat = str(target_chat_id) if target_chat_id else str(self.chat_id)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": dest_chat,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                clean_title = text.split("\n")[0]
                clean_title = re.sub(r'<[^>]+>', '', clean_title)
                logger.info(f"[Telegram] Sent to {dest_chat}: {clean_title}")
                return True
            else:
                logger.error(f"[Telegram Error] HTTP {r.status_code}: {r.text}")
                return False
        except Exception as e:
            logger.error(f"[Telegram Network Error] {e}")
            return False

    def poll_incoming_commands(self) -> List[Tuple[str, str]]:
        """
        Polls Telegram getUpdates for all on-demand user commands.
        Returns a list of (raw_command_text, sender_chat_id).
        """
        if not self.is_configured:
            return []
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 0, "limit": 10}
        commands: List[Tuple[str, str]] = []
        try:
            r = requests.get(url, params=params, timeout=4)
            if r.status_code == 200:
                updates = r.json().get("result", [])
                for u in updates:
                    self.last_update_id = max(self.last_update_id, u.get("update_id", 0))
                    msg = u.get("message") or u.get("edited_message") or {}
                    text = msg.get("text", "").strip()
                    sender_id = str(msg.get("chat", {}).get("id") or self.chat_id)
                    if text.startswith("/"):
                        commands.append((text, sender_id))
        except Exception as e:
            logger.debug(f"[Telegram Poll Network] {e}")
        return commands

    def poll_incoming_command(self) -> Optional[str]:
        """Backward-compatible single command polling."""
        cmds = self.poll_incoming_commands()
        return cmds[0][0] if cmds else None

    def send_test_ping(self) -> bool:
        msg = (
            "⚡ <b>btctool 2.0 · Telegram Alert System Online</b>\n\n"
            "Your mobile alert bot is successfully connected!\n"
            "Operating in pure <b>Event-Driven Autonomous Mode</b> (Zero Clock Spam).\n"
            "Send <code>/status</code> at any time to receive instant live telemetry."
        )
        return self.send_message(msg)


class ZebraBotEngine:
    """
    Main Zebra Bot orchestrator:
    Continuous sub-second perception, Expected Value brain, and rich Telegram alerts.
    """

    def __init__(self, clean_start: bool = False):
        self.stream = MarketStream(inst_id="BTC-USDT", swap_id="BTC-USDT-SWAP")
        self.state_calculator = MarketState()
        self.brain = FreeConvictionEngine()
        self.risk_gate = RiskEngine(history_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json"))
        self.execution = ExecutionManager()
        if hasattr(self.execution, "cooldown_state") and self.execution.cooldown_state:
            self.risk_gate.failure_counter.import_state(self.execution.cooldown_state)
            logger.info("[Zebra] Successfully restored active cooldown timers from persistent state.")
        self.notifier = TelegramNotifier()
        self.consecutive_api_errors = 0
        self.latest_matrix: Optional[Dict[str, Any]] = None
        self._listener_task: Optional[asyncio.Task] = None

        if clean_start:
            self.execution.reset_clean_slate()

    async def _telegram_listener_loop(self):
        """Dedicated background task polling and responding to Telegram commands."""
        logger.info("[Zebra] Dedicated Telegram Command Listener task active.")
        while True:
            try:
                # Run polling in threadpool executor to guarantee non-blocking event loop execution
                cmds = await asyncio.to_thread(self.notifier.poll_incoming_commands)
                for raw_cmd, sender_id in cmds:
                    self._handle_telegram_cmd(raw_cmd, self.latest_matrix, p_up=0.0, sender_chat_id=sender_id)
            except Exception as e:
                logger.error(f"[Telegram Listener Loop Error] {e}")
            await asyncio.sleep(1.0)

    async def run(self):
        """Starts continuous sensory loop and autonomous evaluation."""
        logger.info("=" * 60)
        logger.info("🦓 ZEBRA BOT: TRULY FREE EXPECTED VALUE ENGINE RUNNING")
        logger.info("Zero Static Stops • Zero Artificial Ceilings • 100-Screen Autonomous Agent")
        logger.info("=" * 60)

        # 1. Start WebSocket Stream
        self.stream.start()

        # Start decoupled Telegram Command Listener Task immediately
        self._listener_task = asyncio.create_task(self._telegram_listener_loop())

        # 2. Wait for initial data buffer
        await asyncio.sleep(2.0)
        logger.info(f"[Zebra] Stream active. Current Price: ${self.stream.latest_price:,.2f}")

        # Send Telegram Online Notification
        self.notifier.send_message(
            "⚡ <b>ZEBRA BOT: TRULY FREE ENGINE ONLINE</b>\n\n"
            "Autonomous Expected Value Agent active 24/7!\n"
            "• Zero Static Stop Leashes\n"
            "• Zero Artificial Ceilings (Rides Winners)\n"
            "• Immediate Predictive Cut on Edge Reversal\n"
            "• Continuous 11-Screen Sub-Second Streaming\n\n"
            "Send <code>/status</code> for live 11-screen telemetry."
        )

        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                t0 = time.time()

                # 1. PERCEPTION: Extract 100-Screen State Matrix (<2ms)
                matrix = self.state_calculator.extract_state_matrix(self.stream)
                self.latest_matrix = matrix

                # 2. COGNITION (Mind): Models Propose TradeIntent
                active_trade = self.execution.active_trade
                intent = self.brain.evaluate(matrix, active_trade=active_trade, governor=self.risk_gate.governor)

                # 3. RISK GATE (Conscience): Risk Disposes (Priority-0 Reflexes & Invariant Rules)
                decision = self.risk_gate.evaluate(
                    intent,
                    matrix,
                    active_trade=active_trade,
                    consecutive_api_errors=self.consecutive_api_errors,
                )

                action = decision.get("action")
                p_up = decision.get("p_up", 0.5)

                # ----------------------------------------------------------
                # ACTION DISPATCH & TELEGRAM ALERTS
                # ----------------------------------------------------------
                if action == "ENTER_CORE_LOT_1":
                    entry_p = float(decision["entry_price"])
                    scenario = decision.get("scenario", "WHALE_EDGE")
                    target_p = float(decision.get("target_price", entry_p * 1.01))
                    inval_p = float(decision.get("trailing_stop", decision.get("invalidation_floor", entry_p * 0.995)))
                    reason = decision["reason"]
                    runway_pct = float(decision.get("expected_runway_pct", 0.0))
                    size_factor = float(decision.get("approved_size_factor", 1.0))
                    stress_loss_pct = float(decision.get("stress_loss_pct", 0.0))

                    # Snapshot compact pre-trade feature vector for episodic memory
                    f_vec = {
                        "regime": matrix.get("balloon_geometry", {}).get("regime", "UNKNOWN"),
                        "composite_atr": float(matrix.get("composite_atr", 0.0)),
                        "tanh_imbalance": float(matrix.get("tanh_imbalance", 0.0)),
                        "absorption_index": float(matrix.get("absorption_index", 0.0)),
                        "immediate_runway_pct": float(matrix.get("multi_screen_bounds", {}).get("immediate_runway_pct", 0.0)),
                        "macro_runway_pct": float(matrix.get("multi_screen_bounds", {}).get("macro_runway_pct", 0.0)),
                        "trade_velocity": float(matrix.get("trade_velocity", 0.0)),
                        "oi_zscore": float(matrix.get("oi_zscore", 0.0)),
                        "funding_rate": float(matrix.get("funding_rate", 0.0)),
                        "feed_latency_ms": float(matrix.get("feed_latency_ms", 0.0)),
                    }

                    self.execution.open_core_lot_1(
                        entry_price=entry_p,
                        scenario=scenario,
                        target_price=target_p,
                        invalidation_floor=inval_p,
                        reason=reason,
                        feature_vector=f_vec,
                        trade_intent=intent.__dict__ if hasattr(intent, "__dict__") else dict(intent),
                        risk_decision=decision.__dict__ if hasattr(decision, "__dict__") else dict(decision),
                    )

                    stress_clamp_note = (
                        f"<b>Shadow Self Stress Clamp:</b> Lot 1 scaled to {size_factor * 100:.0f}% (Worst-Case Risk: {stress_loss_pct:.2f}%)\n"
                        if size_factor < 1.0 else ""
                    )

                    self.notifier.send_message(
                        f"🟢 <b>ZEBRA BOT: ENTER CORE LOT 1</b>\n\n"
                        f"<b>Pair:</b> BTC/USDT (Spot)\n"
                        f"<b>Scenario:</b> <code>{scenario}</code>\n"
                        f"<b>Entry Price:</b> ${entry_p:,.2f}\n"
                        f"<b>Target:</b> ${target_p:,.2f} (+{runway_pct:.2f}%)\n"
                        f"<b>Invalidation Floor:</b> ${inval_p:,.2f}\n"
                        f"{stress_clamp_note}\n"
                        f"<b>Whale Thesis:</b> {reason}\n"
                        f"Patience active: Holding through sub-minute noise toward target."
                    )

                elif action == "SCALE_IN_LOT_2":
                    price = float(matrix["latest_price"])
                    reason = decision["reason"]

                    self.execution.scale_in_lot_2(price=price, reason=reason)
                    self.notifier.send_message(
                        f"➕ <b>ZEBRA BOT: SCALE-IN LOT 2 (DIP ABSORPTION)</b>\n\n"
                        f"<b>Action:</b> Adding Capital at Support Discount\n"
                        f"<b>Scale Price:</b> ${price:,.2f}\n"
                        f"<b>New Blended Entry:</b> ${self.execution.active_trade['entry']:,.2f}\n\n"
                        f"<b>Reason:</b> Pullback absorbed by resting institutional bids. Multiplying profit on rebound."
                    )

                elif action == "RIDE_UNCAPPED":
                    macro_target = float(decision.get("target_price", 0.0))
                    new_stop = float(decision.get("trailing_stop", 0.0))
                    gain_pct = float(decision.get("gain_pct", 0.0))
                    current_target = active_trade.get("target_price", 0.0) if active_trade else 0.0

                    if new_stop > 0:
                        self.execution.update_trailing_stop(new_stop)
                    if macro_target > 0:
                        self.execution.update_target_price(macro_target)

                    # Notify once when uncapped expansion begins
                    if macro_target > current_target and macro_target > 0:
                        self.notifier.send_message(
                            f"🚀 <b>ZEBRA BOT: RIDING MACRO BALLOON (+{gain_pct*100:.2f}%)</b>\n\n"
                            f"<b>BTC Price:</b> ${matrix['latest_price']:,.2f}\n"
                            f"<b>Macro Target Stepped To:</b> ${macro_target:,.2f}\n"
                            f"<b>Trailing Stop Ratcheted To:</b> ${new_stop:,.2f}\n\n"
                            f"<b>Engine Logic:</b> Balloon expanding outward with open overhead space. Uncapped wave runner active."
                        )

                elif action == "HOLD_POSITION":
                    new_stop = float(decision.get("trailing_stop", 0.0))
                    if new_stop > 0:
                        self.execution.update_trailing_stop(new_stop)

                elif action == "BANK_PROFIT":
                    exit_p = float(matrix["latest_price"])
                    reason = decision["reason"]
                    gain_pct = float(decision.get("gain_pct", 0.0))
                    net_gain_pct = gain_pct - 0.0020
                    scenario = active_trade.get("scenario", "TRADE") if active_trade else "TRADE"

                    entry_p = float(active_trade.get("entry_price", 0.0)) if active_trade else 0.0
                    atr_val = float(matrix.get("composite_atr", 150.0))
                    self.risk_gate.record_trade_outcome(
                        scenario, net_gain_pct, timestamp=matrix.get("timestamp", 0.0),
                        entry_price=entry_p, radius=atr_val * 1.0
                    )
                    self.execution.close_position(exit_price=exit_p, exit_reason=reason, cooldown_state=self.risk_gate.failure_counter.export_state())
                    self.notifier.send_message(
                        f"🏁 <b>ZEBRA BOT: PROFIT BANKED (+{net_gain_pct*100:.2f}% NET)</b>\n\n"
                        f"<b>Exit Price:</b> ${exit_p:,.2f}\n"
                        f"<b>Gross Market Move:</b> {gain_pct*100:+.2f}%\n"
                        f"<b>OKX Fees Deducted:</b> -0.20%\n"
                        f"<b>Clean Realized Profit:</b> +{net_gain_pct*100:.2f}%\n\n"
                        f"<b>Whale Action:</b> {reason}"
                    )

                elif action == "CUT_THESIS_INVALIDATED":
                    exit_p = float(matrix["latest_price"])
                    reason = decision["reason"]
                    gain_pct = float(decision.get("gain_pct", 0.0))
                    net_pnl_pct = gain_pct - 0.0020
                    scenario = active_trade.get("scenario", "TRADE") if active_trade else "TRADE"

                    entry_p = float(active_trade.get("entry_price", 0.0)) if active_trade else 0.0
                    atr_val = float(matrix.get("composite_atr", 150.0))
                    self.risk_gate.record_invalidation_exit(exit_p, matrix.get("timestamp", 0.0), radius=atr_val * 1.0)
                    self.risk_gate.record_trade_outcome(
                        scenario, net_pnl_pct, timestamp=matrix.get("timestamp", 0.0),
                        entry_price=entry_p, radius=atr_val * 1.0
                    )
                    self.execution.close_position(exit_price=exit_p, exit_reason=reason, cooldown_state=self.risk_gate.failure_counter.export_state())
                    self.notifier.send_message(
                        f"🛑 <b>ZEBRA BOT: THESIS CUT (PRESERVE CAPITAL)</b>\n\n"
                        f"<b>Exit Price:</b> ${exit_p:,.2f}\n"
                        f"<b>Net PnL Impact:</b> {net_pnl_pct*100:+.2f}%\n\n"
                        f"<b>Rectification:</b> {reason}"
                    )

                # Update highest price if active trade exists
                if active_trade:
                    self.execution.update_highest_price(matrix["latest_price"])

                # Periodic garbage collection and CSV auto-flush
                if cycle_count % 30 == 0:
                    self.execution.journal.flush_pending_csv()
                    gc.collect()

            except Exception as e:
                logger.error(f"[Zebra Loop Error] {e}")

            await asyncio.sleep(1.0)

    def _handle_telegram_cmd(self, cmd: str, matrix: Optional[dict] = None, p_up: float = 0.0, sender_chat_id: Optional[str] = None):
        """Responds to on-demand Telegram commands with Whale & Multi-Screen telemetry."""
        clean_cmd = cmd.strip().split()[0].split("@")[0].lower()
        if clean_cmd in ("/status", "/ping", "/info", "/start", "/help"):
            if not matrix:
                connecting_msg = (
                    "⚡ <b>ZEBRA BOT: SYSTEM ONLINE</b>\n\n"
                    "• Status: <code>BUFFERING / STREAM CONNECTING</code>\n"
                    "• Mode: 24/7 Autonomous Expected Value Engine\n"
                    "• Feed: OKX Public WebSocket Ingress\n\n"
                    "Initial 100-screen state matrix is warming up. Please retry in a few seconds."
                )
                self.notifier.send_message(connecting_msg, target_chat_id=sender_chat_id)
                return

            price = matrix.get("latest_price", 0.0)
            tanh_imb = matrix.get("tanh_imbalance", 0.0)
            absorption = matrix.get("absorption_index", 0.0)

            bounds = matrix.get("multi_screen_bounds", {})
            balloon = matrix.get("balloon_geometry", {})
            micro_turn = matrix.get("micro_turn", {})

            nearest_sup = bounds.get("nearest_support", 0.0)
            nearest_res = bounds.get("nearest_resistance", 0.0)
            macro_ceil = bounds.get("macro_ceiling", 0.0)
            imm_runway = bounds.get("immediate_runway_pct", 0.0)
            macro_runway = bounds.get("macro_runway_pct", 0.0)

            regime = balloon.get("regime", "UNKNOWN")
            is_expanding = balloon.get("is_balloon_expanding", False)
            is_slow = balloon.get("is_slow_market", False)

            active = self.execution.active_trade

            status_msg = (
                f"🦓 <b>ZEBRA BOT MULTI-SCREEN TELEMETRY</b>\n\n"
                f"<b>BTC Price:</b> ${price:,.2f}\n"
                f"<b>Regime:</b> <code>{regime}</code>\n"
                f"<b>Nearest Support:</b> ${nearest_sup:,.2f}\n"
                f"<b>Nearest Resistance:</b> ${nearest_res:,.2f}\n"
                f"<b>Immediate Runway:</b> +{imm_runway:.2f}%\n"
                f"<b>Macro Runway:</b> +{macro_runway:.2f}% (Ceiling: ${macro_ceil:,.2f})\n"
                f"<b>Balloon Expanding:</b> {'YES' if is_expanding else 'NO'}\n"
                f"<b>Slow Market:</b> {'YES' if is_slow else 'NO'}\n"
                f"<b>Order Book Skew:</b> {tanh_imb:+.2f}\n"
                f"<b>Absorption Index:</b> {absorption:.1f}\n\n"
            )

            belief = getattr(self.brain, "belief_system", None)
            if belief and hasattr(belief, "state"):
                b_state = belief.state
                status_msg += (
                    f"<b>Explicit Belief:</b> <code>{b_state.regime_belief}</code> (Bias: {b_state.directional_bias:+.2f}, Pers: {b_state.persistence_ticks})\n"
                    f"<b>Adaptive Hurdles:</b> Runway >= {b_state.adaptive_runway_hurdle:.2f}% | Conf >= {b_state.adaptive_conf_hurdle:.2f}\n"
                )

            # Governor & Escalation status
            gov = getattr(self.risk_gate, "governor", None)
            esc = getattr(self.risk_gate, "escalation", None)
            if gov and esc:
                breakout_health = gov.get_health("MACRO_BALLOON_BREAKOUT")
                dip_health = gov.get_health("DIP_ABSORPTION_TURN")
                status_msg += (
                    f"<b>Governor Health:</b> Breakout {breakout_health.health_score:.0f}/100 (Size: {breakout_health.size_multiplier*100:.0f}%) | Dip {dip_health.health_score:.0f}/100\n"
                    f"<b>Escalation:</b> {esc.consecutive_losses} Losses (Hike: +{esc.confidence_hike*100:.0f}%)\n\n"
                )

            if active:
                entry = active.get("entry", 0.0)
                gain = ((price - entry) / entry) * 100.0 if entry > 0 else 0.0
                target = active.get("target_price", 0.0)
                floor = active.get("invalidation_floor", 0.0)
                trailing = active.get("trailing_stop", floor)
                scenario = active.get("scenario", "TRADE")
                status_msg += (
                    f"<b>Active Position:</b> LONG ({scenario})\n"
                    f"<b>Blended Entry:</b> ${entry:,.2f}\n"
                    f"<b>Target:</b> ${target:,.2f}\n"
                    f"<b>Trailing Stop:</b> ${trailing:,.2f}\n"
                    f"<b>Floor:</b> ${floor:,.2f}\n"
                    f"<b>Unrealized Net PnL:</b> {gain - 0.20:+.2f}%\n"
                    f"<b>Lot 2 Deployed:</b> {'YES' if active.get('tranche_2_added') else 'NO'}\n"
                )
            else:
                gate_str = "SLOW MARKET (Chop Filter)" if is_slow else ("WAITING FOR RUNWAY" if imm_runway < 0.45 else "PATIENT SCANNING")
                status_msg += f"<b>Active Position:</b> 100% DEFENSIVE CASH ({gate_str})\n"

            self.notifier.send_message(status_msg, target_chat_id=sender_chat_id)


def main():
    port = int(os.environ.get("PORT", "10000"))
    start_health_server(port)

    clean_start = "--clean" in sys.argv
    engine = ZebraBotEngine(clean_start=clean_start)
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("[Zebra] Stopped by user.")


if __name__ == "__main__":
    main()
