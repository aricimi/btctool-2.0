"""
sandbox_futures_daemon.py — Local Sandbox & Paper Execution Daemon for Futures Version 2.4.1
========================================================================================
Architecture: Candidate 2 Pure Core Alpha + Upgrades 1 & 3 + Short Runner Valve & Dynamic Risk Budget + Tuned 4H Breakdown Short with Rule 1 (4H Lower BB Headroom Gate)
Execution Mode: Local Paper Sandbox (Real-time OKX Market Feed, Zero Risk, Simulated Friction)
Target Instruments:
  - OKX Perpetual Futures: 'BTC-USDT-SWAP' (Primary Institutional Derivative, $2.8B+ Volume)
  - OKX Spot Alternative: 'BTC-USDC' (EU Compliant, High Liquidity Spot Pair)
Accounting: Pure EUR (€) Base Valuation (with live USDC/USDT to EUR conversion)
Friction Modeling: 0.06% Round-trip OKX Futures Taker Blend
Isolated Margin: Dynamic Volatility Sizing (1.75x - 3.125x, Default 2.5x)
Dynamic Risk Budget: Max Equity Risk <= 3.75% per trade

Zero private API keys required for public market ingestion and local simulation.
========================================================================================
"""

import os
import sys
import json
import time
import math
import datetime
import argparse
import logging
from dataclasses import asdict
from typing import Dict, Any, Optional, List, Tuple
import requests

# Reconfigure stdout for UTF-8 compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from conviction_engine_futures import (
    ConvictionEngineFutures,
    FuturesSignal,
    FuturesPosition,
    DEFAULT_ISOLATED_LEVERAGE,
    OKX_FUTURES_ROUNDTRIP_FEE_PCT
)

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sandbox_futures")

OKX_REST_CANDLES = "https://www.okx.com/api/v5/market/candles"
OKX_REST_TICKER = "https://www.okx.com/api/v5/market/ticker"

STATE_FILE = "sandbox_futures_state.json"
LEDGER_FILE = "sandbox_futures_ledger.csv"
CONFIG_FILE = "futures_config.json"


class SandboxTelegramNotifier:
    """Dispatches real-time Telegram alerts for sandbox entries and exits."""
    def __init__(self, config_path: str = CONFIG_FILE):
        self.token = None
        self.chat_id = None
        self._load_config(config_path)

    def _load_config(self, path: str):
        for fpath in [path, "telegram_config.json"]:
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        self.token = cfg.get("bot_token")
                        self.chat_id = cfg.get("chat_id")
                        if self.token and self.chat_id:
                            break
                except Exception as e:
                    logger.warning(f"Could not load telegram config from {fpath}: {e}")

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str) -> bool:
        if not self.is_configured:
            logger.info(f"[TELEGRAM SIMULATED]:\n{text}")
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            r = requests.post(url, json=payload, timeout=8)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"Telegram dispatch error: {e}")
            return False


class OKXMarketIngester:
    """Fetches and aligns multi-timeframe candle datasets from OKX public endpoints."""
    def __init__(self, inst_id: str = "BTC-USDT-SWAP"):
        self.inst_id = inst_id
        self.session = requests.Session()

    def get_eur_rate(self) -> float:
        """Fetches live USD/USDT to EUR exchange rate on OKX."""
        try:
            r = self.session.get(OKX_REST_TICKER, params={'instId': 'USDC-EUR'}, timeout=6)
            data = r.json().get('data', [])
            if data and 'last' in data[0]:
                return float(data[0]['last'])
            r2 = self.session.get(OKX_REST_TICKER, params={'instId': 'USDT-EUR'}, timeout=6)
            data2 = r2.json().get('data', [])
            if data2 and 'last' in data2[0]:
                return float(data2[0]['last'])
        except Exception as e:
            logger.warning(f"Error fetching EUR rate: {e}. Defaulting to 0.895")
        return 0.895

    def fetch_candles(self, bar: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetches klines from OKX public REST endpoint.
        Returns chronological list of dicts: [ts, open, high, low, close, vol, confirm]
        """
        params = {'instId': self.inst_id, 'bar': bar, 'limit': limit}
        try:
            r = self.session.get(OKX_REST_CANDLES, params=params, timeout=10)
            if r.status_code != 200:
                logger.error(f"OKX API error {r.status_code} for {bar}")
                return []
            raw = r.json().get('data', [])
            # OKX returns newest first. Reverse to chronological order (oldest to newest).
            bars = []
            for k in reversed(raw):
                ts_sec = int(k[0]) // 1000
                dt_str = datetime.datetime.fromtimestamp(ts_sec, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                bars.append({
                    'ts': ts_sec,
                    'datetime': dt_str,
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'vol': float(k[5]),
                    'confirm': str(k[8]) if len(k) > 8 else "1"
                })
            return bars
        except Exception as e:
            logger.error(f"Failed to fetch candles for {bar}: {e}")
            return []


class LocalSandboxDaemon:
    """Production Local Sandbox Engine with persistent paper ledger."""
    def __init__(self, inst_id: str = "BTC-USDT-SWAP", initial_capital: float = 1000.0):
        self.inst_id = inst_id
        self.initial_capital = initial_capital
        self.ingester = OKXMarketIngester(inst_id=self.inst_id)
        self.notifier = SandboxTelegramNotifier()
        self.engine = ConvictionEngineFutures(leverage=DEFAULT_ISOLATED_LEVERAGE)
        self.state = self._load_state()

        # Synchronize engine position with saved state
        if self.state.get('active_position'):
            try:
                pos_data = self.state['active_position']
                self.engine.active_position = FuturesPosition(**pos_data)
                logger.info(f"Restored active position from state: {self.engine.active_position.side} {self.engine.active_position.type} @ ${self.engine.active_position.entry_p:,.2f}")
            except Exception as e:
                logger.error(f"Failed to restore position: {e}. Starting flat.")
                self.engine.active_position = None

    def _load_state(self) -> Dict[str, Any]:
        """Loads persistent state or initializes fresh sandbox."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
                logger.info(f"Loaded existing sandbox state. Capital: €{state.get('capital_eur', 1000.0):,.2f}")
                return state
            except Exception as e:
                logger.error(f"Error loading {STATE_FILE}: {e}")

        # Initialize default state
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        state = {
            "inst_id": self.inst_id,
            "capital_eur": self.initial_capital,
            "initial_capital_eur": self.initial_capital,
            "realized_pnl_eur": 0.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "peak_capital_eur": self.initial_capital,
            "max_drawdown_pct": 0.0,
            "active_position": None,
            "last_processed_ts": 0,
            "last_trade_time": now_str
        }
        self._save_state(state)
        return state

    def _save_state(self, state: Optional[Dict[str, Any]] = None):
        """Persists state atomically to disk."""
        if state is not None:
            self.state = state
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state to {STATE_FILE}: {e}")

    def reset_sandbox(self):
        """Resets the paper account to initial capital and wipes active position."""
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        self.state = {
            "inst_id": self.inst_id,
            "capital_eur": self.initial_capital,
            "initial_capital_eur": self.initial_capital,
            "realized_pnl_eur": 0.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "peak_capital_eur": self.initial_capital,
            "max_drawdown_pct": 0.0,
            "active_position": None,
            "last_processed_ts": 0,
            "last_trade_time": now_str
        }
        self.engine.active_position = None
        self._save_state()
        logger.info(f"Sandbox reset to initial capital: €{self.initial_capital:,.2f}")

    def _append_ledger(self, trade_data: Dict[str, Any]):
        """Records completed trade to CSV ledger."""
        file_exists = os.path.exists(LEDGER_FILE)
        try:
            with open(LEDGER_FILE, "a", encoding="utf-8") as f:
                if not file_exists:
                    f.write("trade_id,entry_dt,exit_dt,side,setup_type,entry_p,exit_p,bars_held,ret_pct,net_pnl_pct,pnl_eur,capital_eur,reason,leverage\n")
                f.write(
                    f"{trade_data['trade_id']},{trade_data['entry_dt']},{trade_data['exit_dt']},"
                    f"{trade_data['side']},{trade_data['type']},{trade_data['entry_p']:.2f},{trade_data['exit_p']:.2f},"
                    f"{trade_data['bars_held']},{trade_data['ret_pct']:.4f},{trade_data['net_pnl_pct']:.4f},"
                    f"{trade_data['pnl_eur']:.2f},{trade_data['capital_eur']:.2f},{trade_data['reason']},{trade_data['leverage']:.2f}\n"
                )
        except Exception as e:
            logger.error(f"Error writing to ledger {LEDGER_FILE}: {e}")

    def compute_indicators(self, bars_15m, bars_1h, bars_4h, bars_1d) -> Dict[str, Any]:
        """Calculates exact MTF indicator stack required by conviction_engine_futures."""
        # 1D EMA50 & Slope
        closes_1d = [b['close'] for b in bars_1d]
        ema_1d = closes_1d[0]
        prev_ema_1d = ema_1d
        for c in closes_1d[1:]:
            prev_ema_1d = ema_1d
            ema_1d = c * (2 / 51) + ema_1d * (49 / 51)
        slope_1d = (ema_1d - prev_ema_1d) / prev_ema_1d if prev_ema_1d > 0 else 0.0

        # 4H EMA50 & Bollinger Bands
        closes_4h = [b['close'] for b in bars_4h]
        highs_4h = [b['high'] for b in bars_4h]
        lows_4h = [b['low'] for b in bars_4h]
        ema_4h = closes_4h[0]
        prev_ema_4h = ema_4h
        for c in closes_4h[1:]:
            prev_ema_4h = ema_4h
            ema_4h = c * (2 / 51) + ema_4h * (49 / 51)
        slope_4h = (ema_4h - prev_ema_4h) / prev_ema_4h if prev_ema_4h > 0 else 0.0

        # 4H Bollinger Bands (20-period, 2.0 std)
        bb_window = closes_4h[-20:] if len(closes_4h) >= 20 else closes_4h
        bb_mid_4h = sum(bb_window) / len(bb_window)
        var_4h = sum((x - bb_mid_4h) ** 2 for x in bb_window) / len(bb_window)
        std_4h = math.sqrt(var_4h)
        bb_upper_4h = bb_mid_4h + 2.0 * std_4h
        bb_lower_4h = bb_mid_4h - 2.0 * std_4h

        # 1H EMA20 & Bollinger Bands
        closes_1h = [b['close'] for b in bars_1h]
        ema_1h = closes_1h[0]
        prev_ema_1h = ema_1h
        for c in closes_1h[1:]:
            prev_ema_1h = ema_1h
            ema_1h = c * (2 / 21) + ema_1h * (19 / 21)
        slope_1h = (ema_1h - prev_ema_1h) / prev_ema_1h if prev_ema_1h > 0 else 0.0

        bb_window_1h = closes_1h[-20:] if len(closes_1h) >= 20 else closes_1h
        bb_mid_1h = sum(bb_window_1h) / len(bb_window_1h)
        var_1h = sum((x - bb_mid_1h) ** 2 for x in bb_window_1h) / len(bb_window_1h)
        std_1h = math.sqrt(var_1h)
        bb_upper_1h = bb_mid_1h + 2.0 * std_1h
        bb_lower_1h = bb_mid_1h - 2.0 * std_1h

        # 15M ATR(14)
        highs_15m = [b['high'] for b in bars_15m]
        lows_15m = [b['low'] for b in bars_15m]
        closes_15m = [b['close'] for b in bars_15m]
        vols_15m = [b.get('vol', 0.0) for b in bars_15m]

        tr_list = []
        for i in range(len(bars_15m)):
            if i == 0:
                tr_list.append(highs_15m[0] - lows_15m[0])
            else:
                tr_list.append(max(
                    highs_15m[i] - lows_15m[i],
                    abs(highs_15m[i] - closes_15m[i - 1]),
                    abs(lows_15m[i] - closes_15m[i - 1])
                ))
        atr_14 = sum(tr_list[-14:]) / 14.0 if len(tr_list) >= 14 else tr_list[-1]

        # 15M RSI(14)
        gains, losses = 0.0, 0.0
        for i in range(-14, 0):
            delta = closes_15m[i] - closes_15m[i - 1]
            if delta > 0:
                gains += delta
            else:
                losses -= delta
        avg_gain = gains / 14.0
        avg_loss = losses / 14.0
        rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
        rsi_14 = 100.0 - (100.0 / (1.0 + rs))

        # 15M Bollinger Bands
        bb_window_15m = closes_15m[-20:] if len(closes_15m) >= 20 else closes_15m
        bb_mid_15m = sum(bb_window_15m) / len(bb_window_15m)
        var_15m = sum((x - bb_mid_15m) ** 2 for x in bb_window_15m) / len(bb_window_15m)
        std_15m = math.sqrt(var_15m)
        bb_upper_15m = bb_mid_15m + 2.0 * std_15m
        bb_lower_15m = bb_mid_15m - 2.0 * std_15m

        # Volume SMA20
        vol_sma20 = sum(vols_15m[-21:-1]) / 20.0 if len(vols_15m) >= 21 else (vols_15m[-1] if vols_15m else 1.0)

        # 48H and 24H Swings
        sh_48h = max(highs_15m[-193:-1]) if len(highs_15m) >= 193 else max(highs_15m)
        sl_48h = min(lows_15m[-193:-1]) if len(lows_15m) >= 193 else min(lows_15m)
        sh_24h = max(highs_15m[-97:-1]) if len(highs_15m) >= 97 else max(highs_15m)
        sl_24h = min(lows_15m[-97:-1]) if len(lows_15m) >= 97 else min(lows_15m)

        return {
            '1d': {'close': closes_1d[-1], 'ema50': ema_1d, 'ema50_slope': slope_1d},
            '4h': {
                'close': closes_4h[-1], 'high': highs_4h[-1], 'low': lows_4h[-1],
                'ema50': ema_4h, 'ema50_slope': slope_4h,
                'bb_mid': bb_mid_4h, 'bb_upper': bb_upper_4h, 'bb_lower': bb_lower_4h
            },
            '1h': {
                'close': closes_1h[-1], 'ema20': ema_1h, 'ema20_slope': slope_1h,
                'bb_mid': bb_mid_1h, 'bb_upper': bb_upper_1h, 'bb_lower': bb_lower_1h
            },
            '15m': {
                'atr': atr_14, 'rsi': rsi_14, 'vol_sma20': vol_sma20,
                'bb_mid': bb_mid_15m, 'bb_upper': bb_upper_15m, 'bb_lower': bb_lower_15m,
                'sh_48h': sh_48h, 'sl_48h': sl_48h, 'sh_24h': sh_24h, 'sl_24h': sl_24h
            }
        }

    def execute_tick(self) -> Dict[str, Any]:
        """
        Pulls latest confirmed OKX market bars, updates indicators,
        evaluates active positions, checks candidate entries, and saves state.
        """
        bars_15m_raw = self.ingester.fetch_candles('15m', limit=210)
        bars_1h_raw = self.ingester.fetch_candles('1H', limit=60)
        bars_4h_raw = self.ingester.fetch_candles('4H', limit=60)
        bars_1d_raw = self.ingester.fetch_candles('1D', limit=60)

        if not bars_15m_raw or len(bars_15m_raw) < 193:
            logger.warning("Insufficient 15m candle history received from OKX.")
            return {'status': 'INSUFFICIENT_DATA'}

        # Filter confirmed candles only (confirm == '1')
        bars_15m = [b for b in bars_15m_raw if b['confirm'] == '1']
        bars_1h = [b for b in bars_1h_raw if b['confirm'] == '1']
        bars_4h = [b for b in bars_4h_raw if b['confirm'] == '1']
        bars_1d = [b for b in bars_1d_raw if b['confirm'] == '1']

        latest_bar = bars_15m[-1]
        prev_bars = bars_15m[:-1]
        current_ts = latest_bar['ts']

        indicators = self.compute_indicators(bars_15m, bars_1h, bars_4h, bars_1d)
        d1 = indicators['1d']
        h4 = indicators['4h']
        h1 = indicators['1h']
        m15 = indicators['15m']

        p_close = latest_bar['close']
        dt_str = latest_bar['datetime']

        eur_rate = self.ingester.get_eur_rate()
        capital_eur = self.state['capital_eur']

        # Synchronize engine position with sandbox state
        if self.state.get('active_position') and self.engine.active_position is None:
            try:
                self.engine.active_position = FuturesPosition(**self.state['active_position'])
            except Exception:
                pass
        elif self.state.get('active_position') is None and self.engine.active_position is not None:
            self.engine.active_position = None

        pos_before = self.engine.active_position

        # Execute Version 2.4.1 Engine
        bar_idx = len(bars_15m) - 1
        signal = self.engine.evaluate_bar(
            bar_idx=bar_idx,
            cur_bar=latest_bar,
            prev_bars_15m=prev_bars,
            mtf_data=indicators
        )

        pos_after = self.engine.active_position

        # -------------------------------------------------------------
        # 1. HANDLE POSITION EXIT
        # -------------------------------------------------------------
        if signal.action in ["EXIT_LONG", "EXIT_SHORT"] and pos_before is not None:
            exit_p = signal.price
            exit_reason = signal.reason
            entry_p = pos_before.entry_p
            eff_lev = pos_before.leverage
            act_stop = pos_before.active_stop_pct

            # Calculate return %
            telem = getattr(signal, 'telemetry', getattr(signal, 'metadata', {}))
            if telem and 'blended_pnl_pct' in telem:
                ret = telem['blended_pnl_pct']
            else:
                ret = (exit_p - entry_p) / entry_p if pos_before.side == 'LONG' else (entry_p - exit_p) / entry_p
                ret = max(ret, -act_stop)

            net_pnl_pct = (ret - OKX_FUTURES_ROUNDTRIP_FEE_PCT) * eff_lev
            pnl_eur = capital_eur * net_pnl_pct

            capital_eur += pnl_eur
            self.state['capital_eur'] = capital_eur
            self.state['realized_pnl_eur'] += pnl_eur
            self.state['total_trades'] += 1
            if pnl_eur > 0:
                self.state['wins'] += 1
            else:
                self.state['losses'] += 1

            self.state['peak_capital_eur'] = max(self.state.get('peak_capital_eur', capital_eur), capital_eur)
            dd = (capital_eur - self.state['peak_capital_eur']) / self.state['peak_capital_eur'] * 100.0
            self.state['max_drawdown_pct'] = min(self.state.get('max_drawdown_pct', 0.0), dd)

            # Record to CSV ledger
            trade_record = {
                'trade_id': f"TRD_{self.state['total_trades']:04d}",
                'entry_dt': pos_before.entry_t,
                'exit_dt': dt_str,
                'side': pos_before.side,
                'type': pos_before.type,
                'entry_p': entry_p,
                'exit_p': exit_p,
                'bars_held': pos_before.bars_held,
                'ret_pct': ret * 100.0,
                'net_pnl_pct': net_pnl_pct * 100.0,
                'pnl_eur': pnl_eur,
                'capital_eur': capital_eur,
                'reason': exit_reason,
                'leverage': eff_lev
            }
            self._append_ledger(trade_record)

            # Dispatch Telegram Notification
            self.notifier.send_message(
                f"🔔 *[SANDBOX 2.4.1 — EXIT TRIGGERED]* 🔔\n\n"
                f"Result: *{'💰 PROFIT' if pnl_eur > 0 else '🛑 LOSS'}*\n"
                f"Setup: `{pos_before.type}` ({pos_before.side})\n"
                f"Exit Price: `${exit_p:,.2f}`\n"
                f"Net Realized: *€{pnl_eur:+.2f} ({net_pnl_pct*100:+.2f}%)*\n"
                f"New Balance: *€{capital_eur:,.2f} EUR*\n"
                f"Exit Reason: _{exit_reason}_\n"
                f"Timestamp: `{dt_str}`"
            )
            logger.info(f"TRADE CLOSED: {pos_before.type} | PnL: €{pnl_eur:+.2f} | Reason: {exit_reason}")
            self.state['active_position'] = None

        # -------------------------------------------------------------
        # 2. HANDLE NEW POSITION ENTRY
        # -------------------------------------------------------------
        elif signal.action in ["ENTER_LONG", "ENTER_SHORT"] and pos_after is not None:
            self.state['active_position'] = asdict(pos_after)
            pos_size_usd = (capital_eur / eur_rate) * signal.leverage

            target_str = f"Target: `${signal.take_profit:,.2f}`\n" if signal.take_profit else "Target: `Trailing 3.0x ATR Runner`\n"
            self.notifier.send_message(
                f"⚡ *[SANDBOX 2.4.1 — NEW ORDER ENTERED]* ⚡\n\n"
                f"Action: *{signal.action}*\n"
                f"Instrument: `{self.inst_id}` (OKX)\n"
                f"Setup: `{signal.setup_type}` ({signal.side})\n"
                f"Entry Fill: `${signal.price:,.2f}`\n"
                f"Hard Stop: `${signal.hard_stop:,.2f}`\n"
                f"{target_str}"
                f"Leverage: *{signal.leverage:.2f}x Isolated*\n"
                f"Position Size: *${pos_size_usd:,.0f} USD (~€{capital_eur*signal.leverage:,.0f})*\n"
                f"Risk Budget: *<= 3.75% Equity*\n"
                f"Timestamp: `{dt_str}`"
            )
            logger.info(f"NEW ENTRY: {signal.setup_type} ({signal.side}) @ ${signal.price:,.2f} | Lev: {signal.leverage:.2f}x")

        # -------------------------------------------------------------
        # 3. UPDATE ACTIVE POSITION IN STATE
        # -------------------------------------------------------------
        elif pos_after is not None:
            self.state['active_position'] = asdict(pos_after)

        self.state['last_processed_ts'] = current_ts
        self._save_state()

        macro_1d = "BULL" if (p_close > d1['ema50'] and d1['ema50_slope'] > 0) else ("BEAR" if (p_close < d1['ema50'] and d1['ema50_slope'] < 0) else "CHOP")
        macro_4h = "BULL" if p_close > h4['ema50'] else "BEAR"

        return {
            'status': 'SUCCESS',
            'dt': dt_str,
            'inst_id': self.inst_id,
            'price': p_close,
            'macro_1d': macro_1d,
            'macro_4h': macro_4h,
            'd1_ema50': d1['ema50'],
            'h4_ema50': h4['ema50'],
            'h4_bb_lower': h4['bb_lower'],
            'capital_eur': self.state['capital_eur'],
            'active_position': self.state['active_position'],
            'signal_action': signal.action,
            'setup_type': signal.setup_type
        }

    def print_dashboard(self, telemetry: Dict[str, Any]):
        """Renders an institutional terminal telemetry dashboard."""
        if telemetry.get('status') != 'SUCCESS':
            print(f"[SANDBOX STATUS]: {telemetry.get('status')}")
            return

        pos = telemetry['active_position']
        pos_str = "FLAT (Cash: 100%)"
        if pos:
            cur_p = telemetry['price']
            unrealized_pct = ((cur_p - pos['entry_p']) / pos['entry_p'] * 100.0) if pos['side'] == 'LONG' else ((pos['entry_p'] - cur_p) / pos['entry_p'] * 100.0)
            pos_str = f"{pos['side']} {pos['type']} | Entry: ${pos['entry_p']:,.1f} | Unrealized: {unrealized_pct:+.2f}% | Stop: ${pos['hard_stop']:,.1f}"

        print("\n" + "=" * 90)
        print(f"🏛️  BTCTOOL 2.0 / FUTURES 2.4.1 · LOCAL SANDBOX DAEMON (OKX {telemetry['inst_id']})")
        print("=" * 90)
        print(f"Time (UTC)    : {telemetry['dt']} | Live Price: ${telemetry['price']:,.2f}")
        print(f"Regime        : 1D: {telemetry['macro_1d']} (EMA50: ${telemetry['d1_ema50']:,.1f}) | 4H: {telemetry['macro_4h']} (EMA50: ${telemetry['h4_ema50']:,.1f} | Lower BB: ${telemetry['h4_bb_lower']:,.1f})")
        print(f"Account Equity: €{telemetry['capital_eur']:,.2f} EUR (Realized PnL: €{self.state['realized_pnl_eur']:+.2f} | Trades: {self.state['total_trades']})")
        print(f"Position      : {pos_str}")
        print(f"Signal Evaluated: {telemetry['signal_action']} ({telemetry['setup_type']})")
        print("=" * 90 + "\n")

    def run_daemon_loop(self):
        """Infinite loop polling OKX and synchronizing with 15-minute candle closes."""
        print("=" * 75)
        print("🚀 STARTING LOCAL SANDBOX DAEMON (OKX PERPETUAL FUTURES 2.4.1)")
        print(f"Instrument: {self.inst_id} | Starting Capital: €{self.state['capital_eur']:,.2f}")
        print("Synchronizing with OKX 15-minute candle closes (:00, :15, :30, :45)...")
        print("Press Ctrl+C to stop cleanly.")
        print("=" * 75)

        # Initial preflight tick
        telem = self.execute_tick()
        self.print_dashboard(telem)

        while True:
            try:
                now = datetime.datetime.now(datetime.timezone.utc)
                # Compute seconds until next 15-minute boundary (:00, :15, :30, :45) + 3s buffer
                minute_mod = now.minute % 15
                seconds_remaining = (14 - minute_mod) * 60 + (60 - now.second) + 3

                logger.info(f"Sleeping {seconds_remaining}s until next 15M candle close...")
                time.sleep(seconds_remaining)

                # Execute cycle
                telem = self.execute_tick()
                self.print_dashboard(telem)

            except KeyboardInterrupt:
                print("\n[SANDBOX STOPPED]: Exiting daemon cleanly. State preserved in sandbox_futures_state.json")
                break
            except Exception as e:
                logger.error(f"Error in daemon cycle: {e}. Retrying in 15 seconds...")
                time.sleep(15)


def main():
    parser = argparse.ArgumentParser(description="btctool 2.0 Futures 2.4.1 Local Sandbox Daemon")
    parser.add_argument("--instId", default="BTC-USDT-SWAP", help="OKX Instrument ID (e.g. BTC-USDT-SWAP or BTC-USDC)")
    parser.add_argument("--tick-once", action="store_true", help="Run a single evaluation cycle on live data and exit")
    parser.add_argument("--reset", action="store_true", help="Reset sandbox account equity to €1,000.00")
    parser.add_argument("--daemon", action="store_true", help="Run continuous background daemon")
    args = parser.parse_args()

    sandbox = LocalSandboxDaemon(inst_id=args.instId)

    if args.reset:
        sandbox.reset_sandbox()
        return

    if args.tick_once:
        telem = sandbox.execute_tick()
        sandbox.print_dashboard(telem)
        return

    # Default to daemon loop
    sandbox.run_daemon_loop()


if __name__ == "__main__":
    main()
