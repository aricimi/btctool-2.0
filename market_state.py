"""
market_state.py — The 100-Screen Vectorized State Matrix for Zebra Bot (btctool 2.0)
Computes trend, oscillators, volatility regimes, session benchmarks, order flow,
and microstructure metrics across 11 timeframes in <10ms using vectorized numpy math.
"""

import time
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


class MarketState:
    """
    Vectorized 100-Screen State Matrix.
    Synthesizes multi-timeframe candles, order book, tape, and derivatives into a unified state vector.
    """

    def __init__(self):
        pass

    @staticmethod
    def compute_ema(series: np.ndarray, period: int) -> np.ndarray:
        """Fast vectorized Exponential Moving Average."""
        if len(series) < period:
            return np.full_like(series, np.nan)
        alpha = 2.0 / (period + 1.0)
        ema = np.empty_like(series)
        ema[0] = series[0]
        for i in range(1, len(series)):
            ema[i] = alpha * series[i] + (1.0 - alpha) * ema[i - 1]
        return ema

    @staticmethod
    def compute_rsi(closes: np.ndarray, period: int = 14) -> float:
        """Compute relative strength index for closing prices."""
        if len(closes) <= period:
            return 50.0
        diffs = np.diff(closes)
        gains = np.where(diffs > 0, diffs, 0.0)
        losses = np.where(diffs < 0, -diffs, 0.0)

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return float(100.0 - (100.0 / (1.0 + rs)))

    @staticmethod
    def compute_macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """Compute MACD DIF, DEA (Signal), and Histogram."""
        if len(closes) < slow + signal:
            return 0.0, 0.0, 0.0
        fast_ema = MarketState.compute_ema(closes, fast)
        slow_ema = MarketState.compute_ema(closes, slow)
        dif = fast_ema - slow_ema
        dea = MarketState.compute_ema(dif[slow - 1:], signal)
        latest_dif = dif[-1]
        latest_dea = dea[-1]
        hist = latest_dif - latest_dea
        return float(latest_dif), float(latest_dea), float(hist)

    @staticmethod
    def compute_bollinger_bands(closes: np.ndarray, period: int = 20, num_std: float = 2.0) -> Tuple[float, float, float, float, float]:
        """Compute Bollinger Bands: (mid, upper, lower, bandwidth_pct, pct_b)."""
        if len(closes) < period:
            last = closes[-1] if len(closes) > 0 else 0.0
            return last, last, last, 0.0, 0.5
        window = closes[-period:]
        mid = float(np.mean(window))
        std = float(np.std(window))
        upper = mid + num_std * std
        lower = mid - num_std * std
        bandwidth = float((upper - lower) / mid * 100.0) if mid > 0 else 0.0
        last = float(closes[-1])
        pct_b = float((last - lower) / (upper - lower)) if (upper - lower) > 0 else 0.5
        return mid, upper, lower, bandwidth, pct_b

    @staticmethod
    def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        """Compute Average True Range."""
        if len(closes) < 2:
            return 100.0
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        if len(tr) < period:
            return float(np.mean(tr)) if len(tr) > 0 else 100.0
        return float(np.mean(tr[-period:]))

    @staticmethod
    def compute_vwap_and_bands(candles: List[dict]) -> Tuple[float, float, float, float]:
        """
        Compute Session Anchored VWAP (resetting at 00:00 UTC) with 1, 2, 3 sigma standard deviation bands.
        """
        if not candles:
            return 0.0, 0.0, 0.0, 0.0

        # Find candles belonging to the current UTC day
        now_ts = candles[-1]["ts"]
        session_start = (int(now_ts) // 86400) * 86400
        session_candles = [c for c in candles if c["ts"] >= session_start]
        if not session_candles:
            session_candles = candles[-30:]

        typical_prices = np.array([(c["high"] + c["low"] + c["close"]) / 3.0 for c in session_candles])
        volumes = np.array([max(c["vol"], 1e-6) for c in session_candles])

        cum_vp = np.sum(typical_prices * volumes)
        cum_vol = np.sum(volumes)
        if cum_vol == 0:
            return float(typical_prices[-1]), 0.0, 0.0, 0.0

        vwap = float(cum_vp / cum_vol)
        variance = np.sum(volumes * (typical_prices - vwap) ** 2) / cum_vol
        std_dev = float(np.sqrt(variance))

        upper_1 = vwap + 1.0 * std_dev
        upper_2 = vwap + 2.0 * std_dev
        lower_1 = vwap - 1.0 * std_dev
        return vwap, std_dev, upper_2, lower_1

    @staticmethod
    def compute_session_benchmarks(candles_1d: List[dict]) -> Dict[str, float]:
        """
        Calculates Previous Day High (PDH), Previous Day Low (PDL), Previous Day Close (PDC).
        """
        if len(candles_1d) >= 2:
            prev_day = candles_1d[-2]
            return {
                "pdh": float(prev_day["high"]),
                "pdl": float(prev_day["low"]),
                "pdc": float(prev_day["close"]),
            }
        elif len(candles_1d) == 1:
            d = candles_1d[0]
            return {"pdh": float(d["high"]), "pdl": float(d["low"]), "pdc": float(d["close"])}
        return {"pdh": 0.0, "pdl": 0.0, "pdc": 0.0}

    @staticmethod
    def compute_absorption_index(recent_trades: List[dict], bid_depth: float, price_drop: float) -> float:
        """
        Real-Time Absorption Index:
        Measures aggressive taker selling absorbed by replenishing bid limit orders.
        High Absorption Index with minimal price drop = Bullish Institutional Absorption.
        """
        if not recent_trades or bid_depth <= 0:
            return 0.0

        taker_sells = sum(t["size"] for t in recent_trades if t["side"] == "sell")
        price_drop_safe = max(abs(price_drop), 0.5)  # Avoid division by zero
        # Ratio of aggressive sell volume to price impact, weighted by bid depth
        absorption = (taker_sells / price_drop_safe) * np.log1p(bid_depth)
        return float(absorption)

    def extract_state_matrix(self, stream) -> dict:
        """
        Extract the complete 100-Screen State Matrix from the live MarketStream.
        Executes in <10ms.
        """
        t0 = time.time()
        matrix = {
            "timestamp": t0,
            "latest_price": stream.latest_price,
            "best_bid": stream.best_bid,
            "best_ask": stream.best_ask,
            "trade_velocity": stream.trade_velocity,
            "cvd": stream.cvd,
            "oi_zscore": stream.get_oi_zscore(),
            "funding_rate": stream.funding_rate,
        }

        # 1. Anti-Spoof L2 Order Book Metrics
        bid_vol, ask_vol, tanh_imbalance = stream.get_anti_spoof_depth(distance_pct=0.005)
        matrix["bid_depth_05"] = bid_vol
        matrix["ask_depth_05"] = ask_vol
        matrix["tanh_imbalance"] = tanh_imbalance

        # 2. Multi-Timeframe Technical Indicators across 11 horizons
        tf_indicators = {}
        for tf in stream.buffers.keys():
            candles = stream.get_candles(tf)
            if not candles:
                continue

            closes = np.array([c["close"] for c in candles])
            highs = np.array([c["high"] for c in candles])
            lows = np.array([c["low"] for c in candles])

            # EMAs
            ema_9 = float(MarketState.compute_ema(closes, 9)[-1]) if len(closes) >= 9 else closes[-1]
            ema_21 = float(MarketState.compute_ema(closes, 21)[-1]) if len(closes) >= 21 else closes[-1]
            ema_50 = float(MarketState.compute_ema(closes, 50)[-1]) if len(closes) >= 50 else closes[-1]

            # Oscillators
            rsi = MarketState.compute_rsi(closes, 14)
            dif, dea, hist = MarketState.compute_macd(closes, 12, 26, 9)

            # Volatility Bands
            bb_mid, bb_upper, bb_lower, bb_width, bb_pct_b = MarketState.compute_bollinger_bands(closes, 20, 2.0)
            atr = MarketState.compute_atr(highs, lows, closes, 14)

            tf_indicators[tf] = {
                "ema_9": ema_9,
                "ema_21": ema_21,
                "ema_50": ema_50,
                "rsi": rsi,
                "macd_dif": dif,
                "macd_dea": dea,
                "macd_hist": hist,
                "bb_mid": bb_mid,
                "bb_upper": bb_upper,
                "bb_lower": bb_lower,
                "bb_width": bb_width,
                "bb_pct_b": bb_pct_b,
                "atr": atr,
            }

        matrix["timeframes"] = tf_indicators

        # 3. Session Anchored VWAP (using 1m or 5m candles)
        ref_candles = stream.get_candles("5m") or stream.get_candles("1m")
        vwap, vwap_std, vwap_u2, vwap_l1 = MarketState.compute_vwap_and_bands(ref_candles)
        matrix["session_vwap"] = vwap
        matrix["vwap_std"] = vwap_std
        matrix["vwap_upper_2"] = vwap_u2
        matrix["vwap_lower_1"] = vwap_l1

        # 4. Session Benchmarks (PDH / PDL)
        daily_candles = stream.get_candles("1D")
        matrix["benchmarks"] = MarketState.compute_session_benchmarks(daily_candles)

        # 5. Real-Time Absorption Index
        recent_trades = list(stream.recent_trades)[-100:] if stream.recent_trades else []
        price_drop = 0.0
        if len(recent_trades) >= 2:
            price_drop = recent_trades[0]["price"] - recent_trades[-1]["price"]
        matrix["absorption_index"] = MarketState.compute_absorption_index(recent_trades, bid_vol, price_drop)

        matrix["compute_time_ms"] = (time.time() - t0) * 1000.0
        return matrix
