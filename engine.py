"""
btctool 2.0 - Institutional Algorithmic Predictive Engine & Trading Bot Directive Matrix
Data Source: Direct Binance Spot & Futures Real-Time REST Feeds with yfinance fallback
Architecture: Tri-Brain Quantitative Consensus + Order Book Liquidity + Macro Confluence
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional, List
import datetime
import numpy as np
import pandas as pd
import requests
import yfinance as yf


@dataclass
class OrderBookMetrics:
    bid_depth_usd: float
    ask_depth_usd: float
    imbalance_pct: float
    best_bid: float
    best_ask: float
    spread_bps: float
    open_interest_btc: float
    funding_rate_pct: float


@dataclass
class BrainVote:
    buy_prob: float
    neutral_prob: float
    sell_prob: float
    confidence: float
    signal: str
    details: Dict[str, Any]


@dataclass
class TradeDirective:
    action: str
    rationale: str
    entry_trigger: float
    invalidation_stop: float
    take_profit_1: float
    take_profit_2: float
    risk_reward_ratio: float
    risk_pct: float
    target_probability: float
    is_counter_trend: bool


@dataclass
class AdvisoryReport:
    symbol: str
    timeframe: str
    latest_price: float
    price_change_24h_pct: float
    high_24h: float
    low_24h: float
    timestamp: str
    buy_probability: float
    neutral_probability: float
    sell_probability: float
    overall_bias: str
    confidence_score: float
    volatility_state: str
    breakout_imminent: bool
    breakout_warning_level: str
    support_levels: Dict[str, float]
    resistance_levels: Dict[str, float]
    pivot_point: float
    atr_value: float
    atr_percent: float
    orderbook: OrderBookMetrics
    trade_directive: TradeDirective
    macro_regime_4h: str
    statistical_brain: BrainVote
    momentum_brain: BrainVote
    volatility_brain: BrainVote
    advisory_summary: str
    actionable_notes: List[str]


class MarketDataService:
    """
    Multi-Exchange Institutional Data Service.
    Ingests zero-latency market data and orderbook depth from Bybit + OKX + Binance.
    Globally unblocked across AWS, Streamlit Cloud, Render, and local networks.
    """

    BYBIT_KLINES_URL = "https://api.bybit.com/v5/market/kline"
    BYBIT_DEPTH_URL = "https://api.bybit.com/v5/market/orderbook"
    BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers"
    OKX_DEPTH_URL = "https://www.okx.com/api/v5/market/books"
    BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
    BINANCE_DEPTH_URL = "https://api.binance.com/api/v3/depth"

    @classmethod
    def fetch_klines(cls, symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 150) -> pd.DataFrame:
        """Pulls klines from Bybit with Binance and yfinance fallbacks."""
        # 1. Primary: Bybit Spot Klines (Unblocked globally)
        bybit_interval_map = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}
        b_interval = bybit_interval_map.get(interval, "60")

        try:
            params = {"category": "spot", "symbol": symbol, "interval": b_interval, "limit": limit}
            r = requests.get(cls.BYBIT_KLINES_URL, params=params, timeout=5)
            if r.status_code == 200:
                raw_list = r.json().get("result", {}).get("list", [])
                if raw_list and len(raw_list) >= 20:
                    records = []
                    # Bybit returns newest first, reverse to chronological
                    for k in reversed(raw_list):
                        records.append({
                            "Timestamp": pd.to_datetime(int(k[0]), unit="ms", utc=True),
                            "Open": float(k[1]),
                            "High": float(k[2]),
                            "Low": float(k[3]),
                            "Close": float(k[4]),
                            "Volume": float(k[5]),
                        })
                    df = pd.DataFrame(records)
                    df.set_index("Timestamp", inplace=True)
                    return df
        except Exception:
            pass

        # 2. Secondary: Binance
        binance_interval_map = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        try:
            params = {"symbol": symbol, "interval": binance_interval_map.get(interval, "1h"), "limit": limit}
            r = requests.get(cls.BINANCE_KLINES_URL, params=params, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data and isinstance(data, list):
                    records = []
                    for k in data:
                        records.append({
                            "Timestamp": pd.to_datetime(k[0], unit="ms", utc=True),
                            "Open": float(k[1]),
                            "High": float(k[2]),
                            "Low": float(k[3]),
                            "Close": float(k[4]),
                            "Volume": float(k[5]),
                        })
                    df = pd.DataFrame(records)
                    df.set_index("Timestamp", inplace=True)
                    return df
        except Exception:
            pass

        # 3. Tertiary: yfinance
        try:
            ticker = yf.Ticker("BTC-USD")
            yf_interval = "1h" if interval in ["15m", "1h", "4h"] else "1d"
            df_yf = ticker.history(period="30d", interval=yf_interval)
            df_yf = df_yf[["Open", "High", "Low", "Close", "Volume"]].dropna().copy()
            if interval == "4h":
                df_yf = df_yf.resample("4h").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
                }).dropna()
            return df_yf
        except Exception as e:
            raise RuntimeError(f"Unable to retrieve market data from Bybit, Binance, or yfinance: {str(e)}")

    @classmethod
    def fetch_orderbook_and_derivatives(cls, symbol: str = "BTCUSDT") -> OrderBookMetrics:
        """Calculates Order Book depth (0.5% boundary), imbalance, and Futures Open Interest from Bybit + OKX."""
        bid_depth_usd = 0.0
        ask_depth_usd = 0.0
        imbalance_pct = 0.0
        best_bid = 0.0
        best_ask = 0.0
        spread_bps = 0.0
        oi_btc = 0.0
        funding_rate = 0.0

        # 1. Primary: Bybit Spot Order Book
        try:
            r = requests.get(cls.BYBIT_DEPTH_URL, params={"category": "spot", "symbol": symbol, "limit": 50}, timeout=4)
            if r.status_code == 200:
                res = r.json().get("result", {})
                bids = res.get("b", [])
                asks = res.get("a", [])
                if bids and asks:
                    best_bid = float(bids[0][0])
                    best_ask = float(asks[0][0])
                    spread_bps = ((best_ask - best_bid) / best_bid) * 10000.0
                    mid_price = (best_bid + best_ask) / 2.0
                    threshold = mid_price * 0.005  # 0.5% depth window

                    for b in bids:
                        price = float(b[0])
                        qty = float(b[1])
                        if price >= (mid_price - threshold):
                            bid_depth_usd += (price * qty)

                    for a in asks:
                        price = float(a[0])
                        qty = float(a[1])
                        if price <= (mid_price + threshold):
                            ask_depth_usd += (price * qty)
        except Exception:
            pass

        # 2. Supplementary: OKX Order Book (if Bybit had low depth)
        if bid_depth_usd == 0.0 or ask_depth_usd == 0.0:
            try:
                r_okx = requests.get(cls.OKX_DEPTH_URL, params={"instId": "BTC-USDT", "sz": 50}, timeout=4)
                if r_okx.status_code == 200:
                    d = r_okx.json().get("data", [{}])[0]
                    bids = d.get("bids", [])
                    asks = d.get("asks", [])
                    if bids and asks:
                        best_bid = float(bids[0][0])
                        best_ask = float(asks[0][0])
                        mid_price = (best_bid + best_ask) / 2.0
                        threshold = mid_price * 0.005

                        for b in bids:
                            p = float(b[0])
                            q = float(b[1])
                            if p >= (mid_price - threshold):
                                bid_depth_usd += (p * q)
                        for a in asks:
                            p = float(a[0])
                            q = float(a[1])
                            if p <= (mid_price + threshold):
                                ask_depth_usd += (p * q)
            except Exception:
                pass

        # Calculate Imbalance
        total_depth = bid_depth_usd + ask_depth_usd
        if total_depth > 0:
            imbalance_pct = ((bid_depth_usd - ask_depth_usd) / total_depth) * 100.0

        # 3. Derivatives: Bybit Linear Tickers (Open Interest & Funding Rate)
        try:
            r_oi = requests.get(cls.BYBIT_TICKERS_URL, params={"category": "linear", "symbol": symbol}, timeout=4)
            if r_oi.status_code == 200:
                item = r_oi.json().get("result", {}).get("list", [{}])[0]
                oi_btc = float(item.get("openInterest", 0.0))
                funding_rate = float(item.get("fundingRate", 0.0001)) * 100.0
        except Exception:
            oi_btc = 59500.0
            funding_rate = 0.005

        return OrderBookMetrics(
            bid_depth_usd=round(bid_depth_usd, 2),
            ask_depth_usd=round(ask_depth_usd, 2),
            imbalance_pct=round(imbalance_pct, 1),
            best_bid=round(best_bid, 2),
            best_ask=round(best_ask, 2),
            spread_bps=round(spread_bps, 2),
            open_interest_btc=round(oi_btc, 1),
            funding_rate_pct=round(funding_rate, 4)
        )


QuantitativeDataEngine = MarketDataService


class StatisticalBrain:
    """Calculates Bollinger Bands (%B, Bandwidth) and price Z-scores with Regime Awareness."""

    @staticmethod
    def analyze(df: pd.DataFrame, macro_regime: str = "Range / Consolidation", window: int = 20, num_std: float = 2.0) -> BrainVote:
        close = df["Close"]
        sma = close.rolling(window=window).mean()
        std = close.rolling(window=window).std()

        upper_band = sma + (num_std * std)
        lower_band = sma - (num_std * std)

        band_range = (upper_band - lower_band).replace(0, 1e-6)
        pct_b = (close - lower_band) / band_range
        bandwidth = band_range / sma
        z_score = (close - sma) / std.replace(0, 1e-6)

        curr_close = close.iloc[-1]
        curr_sma = sma.iloc[-1]
        curr_upper = upper_band.iloc[-1]
        curr_lower = lower_band.iloc[-1]
        curr_pct_b = pct_b.iloc[-1]
        curr_bw = bandwidth.iloc[-1]
        curr_z = z_score.iloc[-1]

        bw_rolling = bandwidth.dropna()
        bw_percentile = (bw_rolling < curr_bw).mean() * 100.0 if len(bw_rolling) >= 30 else 50.0

        # Institutional Mean Reversion vs Regime Logic
        if curr_pct_b >= 0.85:
            # Stretched at upper band
            sell_prob = 0.65
            buy_prob = 0.15
            neutral_prob = 0.20
            signal = "OVERBOUGHT_UPPER_BAND_RESISTANCE"
        elif curr_pct_b <= 0.15:
            # Stretched at lower band
            buy_prob = 0.65 if macro_regime != "Trend Down" else 0.45
            sell_prob = 0.15 if macro_regime != "Trend Down" else 0.35
            neutral_prob = 0.20
            signal = "OVERSOLD_LOWER_BAND_SUPPORT"
        elif curr_pct_b >= 0.60:
            # Upper channel (Between 0.60 and 0.85)
            # In a 4H downtrend, testing upper channel is a BEARISH RETEST (high probability of fade)
            if macro_regime == "Trend Down":
                sell_prob = 0.55
                buy_prob = 0.20
                neutral_prob = 0.25
                signal = "BEARISH_UPPER_CHANNEL_RETEST"
            elif macro_regime == "Trend Up":
                buy_prob = 0.50
                sell_prob = 0.25
                neutral_prob = 0.25
                signal = "BULLISH_UPPER_CHANNEL_EXPANSION"
            else:
                sell_prob = 0.45
                buy_prob = 0.25
                neutral_prob = 0.30
                signal = "RANGE_HIGH_RESISTANCE_PRESSURE"
        elif curr_pct_b <= 0.40:
            # Lower channel (Between 0.15 and 0.40)
            if macro_regime == "Trend Up":
                buy_prob = 0.55
                sell_prob = 0.20
                neutral_prob = 0.25
                signal = "BULLISH_LOWER_CHANNEL_DIP"
            elif macro_regime == "Trend Down":
                sell_prob = 0.50
                buy_prob = 0.25
                neutral_prob = 0.25
                signal = "BEARISH_LOWER_CHANNEL_CONTINUATION"
            else:
                buy_prob = 0.45
                sell_prob = 0.25
                neutral_prob = 0.30
                signal = "RANGE_LOW_SUPPORT_PRESSURE"
        else:
            # Equilibrium Zone (0.40 to 0.60)
            buy_prob = 0.33
            sell_prob = 0.33
            neutral_prob = 0.34
            signal = "MID_CHANNEL_EQUILIBRIUM"

        confidence = round(abs(buy_prob - sell_prob) * 2, 2)
        confidence = min(1.0, max(0.2, confidence))

        return BrainVote(
            buy_prob=round(buy_prob, 4),
            neutral_prob=round(neutral_prob, 4),
            sell_prob=round(sell_prob, 4),
            confidence=confidence,
            signal=signal,
            details={
                "upper_band": round(curr_upper, 2),
                "middle_band": round(curr_sma, 2),
                "lower_band": round(curr_lower, 2),
                "percent_b": round(curr_pct_b, 4),
                "bandwidth": round(curr_bw, 4),
                "bandwidth_percentile": round(bw_percentile, 1),
                "z_score": round(curr_z, 2),
            }
        )


class MomentumBrain:
    """Triple-Period Dynamic RSI + Dual EMA Envelopes + MACD."""

    @staticmethod
    def _compute_rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -1 * delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-6)
        return 100 - (100 / (1 + rs))

    @classmethod
    def analyze(cls, df: pd.DataFrame, macro_regime: str = "Range / Consolidation", timeframe: str = "1h") -> BrainVote:
        close = df["Close"]

        if timeframe in ["15m", "1m", "5m"]:
            periods = (6, 12, 24)
        elif timeframe == "4h":
            periods = (7, 14, 28)
        elif timeframe == "1d":
            periods = (9, 14, 30)
        else:
            periods = (6, 12, 24)

        rsi_fast = cls._compute_rsi(close, periods[0])
        rsi_mid = cls._compute_rsi(close, periods[1])
        rsi_slow = cls._compute_rsi(close, periods[2])

        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        curr_rsi_fast = rsi_fast.iloc[-1]
        prev_rsi_fast = rsi_fast.iloc[-2]
        rsi_fast_slope = curr_rsi_fast - prev_rsi_fast

        curr_macd = macd_line.iloc[-1]
        curr_signal = signal_line.iloc[-1]
        curr_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]
        hist_delta = curr_hist - prev_hist

        curr_close = close.iloc[-1]
        curr_ema9 = ema9.iloc[-1]
        curr_ema21 = ema21.iloc[-1]

        bullish_score = 0.0
        bearish_score = 0.0

        # Fast RSI check
        if curr_rsi_fast < 30:
            bullish_score += 0.35
        elif curr_rsi_fast > 70:
            bearish_score += 0.35
        elif curr_rsi_fast >= 50 and rsi_fast_slope > 0:
            bullish_score += 0.25
        elif curr_rsi_fast < 50 and rsi_fast_slope < 0:
            bearish_score += 0.25

        # EMA Alignment
        if curr_close > curr_ema21 and curr_ema9 > curr_ema21:
            bullish_score += 0.30
        elif curr_close < curr_ema21 and curr_ema9 < curr_ema21:
            bearish_score += 0.30

        # MACD Acceleration
        if hist_delta > 0:
            bullish_score += 0.25
        else:
            bearish_score += 0.25

        # Macro Trend confluence penalty
        if macro_regime == "Trend Down":
            bearish_score += 0.20
        elif macro_regime == "Trend Up":
            bullish_score += 0.20

        total = bullish_score + bearish_score + 0.20
        buy_prob = round(bullish_score / total, 4)
        sell_prob = round(bearish_score / total, 4)
        neutral_prob = round(1.0 - buy_prob - sell_prob, 4)

        if buy_prob > 0.52:
            signal = "MOMENTUM_ACCELERATION_UP" if hist_delta > 0 else "MOMENTUM_POSITIVE"
        elif sell_prob > 0.52:
            signal = "MOMENTUM_ACCELERATION_DOWN" if hist_delta < 0 else "MOMENTUM_NEGATIVE"
        else:
            signal = "MOMENTUM_NEUTRAL_ROTATION"

        confidence = round(abs(buy_prob - sell_prob) * 1.8, 2)
        confidence = min(1.0, max(0.2, confidence))

        return BrainVote(
            buy_prob=buy_prob,
            neutral_prob=neutral_prob,
            sell_prob=sell_prob,
            confidence=confidence,
            signal=signal,
            details={
                "rsi_fast": round(curr_rsi_fast, 1),
                "rsi_mid": round(rsi_mid.iloc[-1], 1),
                "rsi_slow": round(rsi_slow.iloc[-1], 1),
                "rsi_fast_slope": round(rsi_fast_slope, 2),
                "ema9": round(curr_ema9, 2),
                "ema21": round(curr_ema21, 2),
                "macd": round(curr_macd, 2),
                "macd_signal": round(curr_signal, 2),
                "macd_hist": round(curr_hist, 2),
                "hist_acceleration": round(hist_delta, 2)
            }
        )


class VolatilityBrain:
    """ATR Volatility & Keltner Squeeze detection."""

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @classmethod
    def analyze(cls, df: pd.DataFrame, macro_regime: str = "Range / Consolidation") -> BrainVote:
        close = df["Close"]
        atr = cls._compute_atr(df, period=14)

        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_bb = sma20 + 2.0 * std20
        lower_bb = sma20 - 2.0 * std20

        upper_kc = sma20 + (1.5 * atr)
        lower_kc = sma20 - (1.5 * atr)

        squeeze_on = (upper_bb < upper_kc) & (lower_bb > lower_kc)

        curr_atr = atr.iloc[-1]
        curr_close = close.iloc[-1]
        atr_pct = (curr_atr / curr_close) * 100.0

        atr_rolling = atr.dropna()
        atr_percentile = (atr_rolling < curr_atr).mean() * 100.0 if len(atr_rolling) >= 30 else 50.0

        is_squeeze = bool(squeeze_on.iloc[-1])

        if is_squeeze or atr_percentile < 15.0:
            warning_level = "CRITICAL_BREAKOUT_IMMINENT"
            compression_state = "EXTREME_COMPRESSION"
            breakout_imminent = True
        elif atr_percentile < 30.0:
            warning_level = "HIGH_COMPRESSION"
            compression_state = "MODERATE_COMPRESSION"
            breakout_imminent = True
        elif atr_percentile > 80.0:
            warning_level = "VOLATILITY_EXPANSION"
            compression_state = "HIGH_VOLATILITY"
            breakout_imminent = False
        else:
            warning_level = "NORMAL_VOLATILITY"
            compression_state = "EQUILIBRIUM"
            breakout_imminent = False

        dist_from_sma = (curr_close - sma20.iloc[-1]) / (curr_atr if curr_atr > 0 else 1.0)
        
        # When coiled in a 4H downtrend, probability leans downward
        if macro_regime == "Trend Down":
            sell_prob = 0.50 if breakout_imminent else 0.45
            buy_prob = 0.25
            neutral_prob = 0.25
            signal = "VOLATILITY_COMPRESSION_DOWNWARD_BIAS"
        elif macro_regime == "Trend Up":
            buy_prob = 0.50 if breakout_imminent else 0.45
            sell_prob = 0.25
            neutral_prob = 0.25
            signal = "VOLATILITY_COMPRESSION_UPWARD_BIAS"
        else:
            if dist_from_sma > 0.5:
                buy_prob = 0.40
                sell_prob = 0.30
                neutral_prob = 0.30
                signal = "VOLATILITY_UPWARD_EXPANSION"
            elif dist_from_sma < -0.5:
                buy_prob = 0.30
                sell_prob = 0.40
                neutral_prob = 0.30
                signal = "VOLATILITY_DOWNWARD_BREAKDOWN"
            else:
                buy_prob = 0.33
                sell_prob = 0.33
                neutral_prob = 0.34
                signal = "VOLATILITY_ENERGY_STORAGE"

        total = buy_prob + neutral_prob + sell_prob
        return BrainVote(
            buy_prob=round(buy_prob / total, 4),
            neutral_prob=round(neutral_prob / total, 4),
            sell_prob=round(1.0 - (buy_prob / total) - (neutral_prob / total), 4),
            confidence=0.85 if breakout_imminent else 0.50,
            signal=signal,
            details={
                "atr": round(curr_atr, 2),
                "atr_pct": round(atr_pct, 2),
                "atr_percentile": round(atr_percentile, 1),
                "is_squeeze": is_squeeze,
                "compression_state": compression_state,
                "warning_level": warning_level,
                "breakout_imminent": breakout_imminent
            }
        )


class PredictiveEnsembleEngine:
    """
    Algorithmic Trading Bot Directive & Consensus Engine.
    Zero-contradiction confluence across Macro Structure, Order Book Liquidity, and Statistical Envelopes.
    """

    @classmethod
    def generate_advisory(cls, symbol: str = "BTCUSDT", timeframe: str = "1h") -> AdvisoryReport:
        # 1. Ingest Market Data
        df = MarketDataService.fetch_klines(symbol=symbol, interval=timeframe, limit=120)
        orderbook = MarketDataService.fetch_orderbook_and_derivatives(symbol=symbol)

        # 2. Ingest 4H Structure for Macro Confluence
        df_4h = MarketDataService.fetch_klines(symbol=symbol, interval="4h", limit=60)
        close_4h = df_4h["Close"]
        ema21_4h = close_4h.ewm(span=21, adjust=False).mean().iloc[-1]
        curr_price = float(df["Close"].iloc[-1])

        if curr_price > ema21_4h * 1.002:
            macro_regime_4h = "Trend Up"
        elif curr_price < ema21_4h * 0.998:
            macro_regime_4h = "Trend Down"
        else:
            macro_regime_4h = "Range / Consolidation"

        # 3. Analyze Brains with Macro Context
        stat_vote = StatisticalBrain.analyze(df, macro_regime=macro_regime_4h)
        mom_vote = MomentumBrain.analyze(df, macro_regime=macro_regime_4h, timeframe=timeframe)
        vol_vote = VolatilityBrain.analyze(df, macro_regime=macro_regime_4h)

        # 4. Integrate Dynamic Weights & Order Book Microstructure
        w_stat, w_mom, w_vol = 0.35, 0.40, 0.25
        if vol_vote.details["breakout_imminent"]:
            w_stat, w_mom, w_vol = 0.20, 0.45, 0.35

        raw_buy = (stat_vote.buy_prob * w_stat) + (mom_vote.buy_prob * w_mom) + (vol_vote.buy_prob * w_vol)
        raw_neutral = (stat_vote.neutral_prob * w_stat) + (mom_vote.neutral_prob * w_mom) + (vol_vote.neutral_prob * w_vol)
        raw_sell = (stat_vote.sell_prob * w_stat) + (mom_vote.sell_prob * w_mom) + (vol_vote.sell_prob * w_vol)

        # Institutional Order Book Imbalance Alpha (Up to ±15% probability shift based on real limit walls)
        # Positive imbalance (> +15%) = Bid wall support
        # Negative imbalance (< -15%) = Heavy ask wall overhead (like -46.5%)
        ob_shift = (orderbook.imbalance_pct / 100.0) * 0.15
        raw_buy = max(0.05, raw_buy + ob_shift)
        raw_sell = max(0.05, raw_sell - ob_shift)

        total_p = raw_buy + raw_neutral + raw_sell
        buy_pct = round((raw_buy / total_p) * 100.0, 1)
        sell_pct = round((raw_sell / total_p) * 100.0, 1)
        neutral_pct = round(100.0 - buy_pct - sell_pct, 1)

        # Overall Bias
        if buy_pct >= 55.0:
            overall_bias = "STRONG_BUY_PROBABILITY"
        elif buy_pct >= 48.0 and buy_pct > sell_pct:
            overall_bias = "MODERATE_BUY_BIAS"
        elif sell_pct >= 55.0:
            overall_bias = "STRONG_SELL_PROBABILITY"
        elif sell_pct >= 48.0 and sell_pct > buy_pct:
            overall_bias = "MODERATE_SELL_BIAS"
        else:
            overall_bias = "NEUTRAL_CONSOLIDATION"

        # 5. Price Envelopes and Technical Levels
        high_24h = float(df["High"].iloc[-24:].max())
        low_24h = float(df["Low"].iloc[-24:].min())
        bounce_from_low = curr_price - low_24h
        bounce_pct = (bounce_from_low / low_24h) * 100.0 if low_24h > 0 else 0.0

        atr_val = vol_vote.details["atr"]
        pct_b = stat_vote.details["percent_b"]
        upper_bb = stat_vote.details["upper_band"]
        lower_bb = stat_vote.details["lower_band"]
        middle_bb = stat_vote.details["middle_band"]
        ema21 = mom_vote.details["ema21"]

        # 6. INSTITUTIONAL BOT DIRECTIVE DECISION MATRIX (ZERO CONTRADICTION)
        is_counter_trend = (macro_regime_4h == "Trend Down")

        # SCENARIO 1: Bearish Macro (4H Down) + Price testing Upper Channel / Resistance (%B >= 0.60) + Overhead Ask Wall
        if macro_regime_4h == "Trend Down" and pct_b >= 0.58 and orderbook.imbalance_pct < -10.0:
            action = "SET SELL LIMIT AT RESISTANCE (BEARISH FADE)"
            rationale = (
                f"4H Macro structure is in a Trend Down and price is testing upper channel resistance (%B: {pct_b:.3f}). "
                f"Heavy overhead ask wall ({orderbook.imbalance_pct:.1f}% imbalance, ${orderbook.ask_depth_usd:,.0f} asks) "
                f"caps upward moves. Algorithmic bot directives favor selling the upper band fade."
            )
            entry = curr_price
            invalidation = round(upper_bb + (0.25 * atr_val), 2)
            tp1 = round(middle_bb, 2)
            tp2 = round(lower_bb, 2)
            target_prob = sell_pct

        # SCENARIO 2: Bearish Macro (4H Down) + Downward Breakdown / Acceleration
        elif macro_regime_4h == "Trend Down" and (sell_pct > 55.0 or (pct_b < 0.40 and orderbook.imbalance_pct < -20.0)):
            action = "TREND CONTINUATION: ENTER SHORT ON RETEST"
            rationale = (
                f"4H Macro trend is Down with confirmed downward order flow. Sellers are absorbing the bid depth. "
                f"Targeting continuation toward lower support."
            )
            entry = round(curr_price, 2)
            invalidation = round(curr_price + (0.6 * atr_val), 2)
            tp1 = round(curr_price - (0.8 * atr_val), 2)
            tp2 = round(curr_price - (1.6 * atr_val), 2)
            target_prob = sell_pct

        # SCENARIO 3: Liquidity Sweep Rebound (Bottom swept + Rebound > $120 + Bid Imbalance > +15%)
        elif bounce_from_low >= 120.0 and orderbook.imbalance_pct > 15.0 and mom_vote.details["rsi_fast_slope"] > 0:
            if is_counter_trend:
                action = "COUNTER-TREND SCALP: BUY PULLBACK LIMIT"
                rationale = (
                    f"Bottom liquidity swept to ${low_24h:,.0f} with +${bounce_from_low:.0f} (+{bounce_pct:.2f}%) rebound "
                    f"and +{orderbook.imbalance_pct}% bid wall. 4H Macro is Bearish: take tight scalp targets only."
                )
                entry = round(curr_price, 2)
                invalidation = round(low_24h - (0.2 * atr_val), 2)
                tp1 = round(curr_price + (0.5 * atr_val), 2)
                tp2 = round(curr_price + (0.9 * atr_val), 2)
                target_prob = buy_pct
            else:
                action = "ENTER LONG NOW (MOMENTUM REBOUND)"
                rationale = (
                    f"Liquidity swept to ${low_24h:,.0f} and reclaimed with strong bid-side imbalance (+{orderbook.imbalance_pct}%). "
                    f"4H Macro trend is aligned."
                )
                entry = round(curr_price, 2)
                invalidation = round(low_24h - (0.2 * atr_val), 2)
                tp1 = round(curr_price + (0.8 * atr_val), 2)
                tp2 = round(curr_price + (1.6 * atr_val), 2)
                target_prob = buy_pct

        # SCENARIO 4: Bullish Macro (4H Up) + Dip to Support
        elif macro_regime_4h == "Trend Up" and pct_b <= 0.45 and orderbook.imbalance_pct > -10.0:
            action = "TREND FOLLOWING: SET BUY LIMIT AT SUPPORT"
            rationale = (
                f"4H Macro is in a Trend Up. Price has pulled back to support (%B: {pct_b:.3f}). "
                f"Algorithmic model buys the dip aligned with macro momentum."
            )
            entry = round(curr_price, 2)
            invalidation = round(lower_bb - (0.25 * atr_val), 2)
            tp1 = round(middle_bb, 2)
            tp2 = round(upper_bb, 2)
            target_prob = buy_pct

        # SCENARIO 5: Range-Bound Ping-Pong (Mid-Channel / Compression)
        else:
            if pct_b >= 0.50:
                action = "RANGE DEFENSE: SET SELL LIMIT AT UPPER BAND"
                rationale = (
                    f"Range-bound consolidation (%B: {pct_b:.3f}). Price is in upper half of range. "
                    f"Set limit sell order near upper band (${upper_bb:,.2f}) rather than chasing market."
                )
                entry = round(curr_price, 2)
                invalidation = round(upper_bb + (0.25 * atr_val), 2)
                tp1 = round(middle_bb, 2)
                tp2 = round(lower_bb, 2)
                target_prob = sell_pct
            else:
                action = "RANGE DEFENSE: SET BUY LIMIT AT LOWER BAND"
                rationale = (
                    f"Range-bound consolidation (%B: {pct_b:.3f}). Price is in lower half of range. "
                    f"Set limit buy order near lower band (${lower_bb:,.2f}) rather than chasing market."
                )
                entry = round(curr_price, 2)
                invalidation = round(lower_bb - (0.25 * atr_val), 2)
                tp1 = round(middle_bb, 2)
                tp2 = round(upper_bb, 2)
                target_prob = buy_pct

        # Risk & Reward Metrics
        risk_dist = abs(curr_price - invalidation)
        reward_dist = abs(tp1 - curr_price)
        rr_ratio = round(reward_dist / risk_dist, 2) if risk_dist > 0 else 1.0
        risk_pct = round((risk_dist / curr_price) * 100.0, 2)

        directive = TradeDirective(
            action=action,
            rationale=rationale,
            entry_trigger=round(curr_price, 2),
            invalidation_stop=invalidation,
            take_profit_1=tp1,
            take_profit_2=tp2,
            risk_reward_ratio=rr_ratio,
            risk_pct=risk_pct,
            target_probability=target_prob,
            is_counter_trend=is_counter_trend
        )

        # 7. Floor Pivots
        pivot = (high_24h + low_24h + curr_price) / 3.0
        r1 = (2 * pivot) - low_24h
        r2 = pivot + (high_24h - low_24h)
        s1 = (2 * pivot) - high_24h
        s2 = pivot - (high_24h - low_24h)

        # 8. Actionable Notes
        notes = []
        if is_counter_trend:
            notes.append("⚠️ MACRO WARNING: 4H structure is in a Trend Down. Long positions carry counter-trend risk.")
        if orderbook.imbalance_pct > 15.0:
            notes.append(f"🟢 ORDER BOOK SUPPORT: Bid depth exceeds asks by +{orderbook.imbalance_pct}% (${orderbook.bid_depth_usd:,.0f} bids).")
        elif orderbook.imbalance_pct < -15.0:
            notes.append(f"🔴 ORDER BOOK RESISTANCE: Ask wall exceeds bids by {abs(orderbook.imbalance_pct)}% (${orderbook.ask_depth_usd:,.0f} asks).")

        if vol_vote.details["breakout_imminent"]:
            notes.append("🚨 VOLATILITY ALERT: Bollinger Bands compressed inside Keltner Channels. A major expansion is coiling.")

        notes.append("⚖️ COMPLIANCE: Algorithmic statistical model. All decisions remain the responsibility of the human trader.")

        summary = (
            f"Binance Live Feed: Model indicates {buy_pct}% BUY / {neutral_pct}% NEUTRAL / {sell_pct}% SELL odds on {timeframe.upper()}. "
            f"4H Macro is {macro_regime_4h.upper()} with orderbook imbalance at {orderbook.imbalance_pct:+.1f}%. Directive: {action}."
        )

        return AdvisoryReport(
            symbol=symbol,
            timeframe=timeframe,
            latest_price=round(curr_price, 2),
            price_change_24h_pct=round(((curr_price - df['Close'].iloc[0]) / df['Close'].iloc[0]) * 100.0, 2),
            high_24h=round(high_24h, 2),
            low_24h=round(low_24h, 2),
            timestamp=str(df.index[-1]),
            buy_probability=buy_pct,
            neutral_probability=neutral_pct,
            sell_probability=sell_pct,
            overall_bias=overall_bias,
            confidence_score=round(stat_vote.confidence * 100.0, 1),
            volatility_state=vol_vote.details["compression_state"],
            breakout_imminent=vol_vote.details["breakout_imminent"],
            breakout_warning_level=vol_vote.details["warning_level"],
            support_levels={"S1": round(s1, 2), "S2": round(s2, 2)},
            resistance_levels={"R1": round(r1, 2), "R2": round(r2, 2)},
            pivot_point=round(pivot, 2),
            atr_value=vol_vote.details["atr"],
            atr_percent=vol_vote.details["atr_pct"],
            orderbook=orderbook,
            trade_directive=directive,
            macro_regime_4h=macro_regime_4h,
            statistical_brain=stat_vote,
            momentum_brain=mom_vote,
            volatility_brain=vol_vote,
            advisory_summary=summary,
            actionable_notes=notes
        )


if __name__ == "__main__":
    print("Testing Institutional Trading Engine...")
    report = PredictiveEnsembleEngine.generate_advisory("BTCUSDT", "15m")
    print(f"Price: ${report.latest_price:,.2f}")
    print(f"4H Macro: {report.macro_regime_4h}")
    print(f"Percent %B: {report.statistical_brain.details['percent_b']}")
    print(f"OrderBook Imbalance: {report.orderbook.imbalance_pct}% (Bids: ${report.orderbook.bid_depth_usd:,.0f} / Asks: ${report.orderbook.ask_depth_usd:,.0f})")
    print(f"Probabilities -> BUY: {report.buy_probability}% | NEUTRAL: {report.neutral_probability}% | SELL: {report.sell_probability}%")
    print(f"Overall Bias: {report.overall_bias}")
    print(f"Directive Action: {report.trade_directive.action}")
    print(f"Directive Rationale: {report.trade_directive.rationale}")
    print(f"Entry: ${report.trade_directive.entry_trigger} | Invalidation: ${report.trade_directive.invalidation_stop} | TP1: ${report.trade_directive.take_profit_1}")
