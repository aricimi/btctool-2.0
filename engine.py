"""
btctool 2.0 - Advanced Predictive Advisory Engine for BTC/USDT
Author: Quantitative Engineering Team
Architecture: Ensemble of Statistical, Momentum, and Volatility Brains
"""

from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class BrainVote:
    buy_prob: float
    neutral_prob: float
    sell_prob: float
    confidence: float
    signal: str
    details: Dict[str, Any]


@dataclass
class AdvisoryReport:
    symbol: str
    timeframe: str
    latest_price: float
    price_change_24h_pct: float
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
    statistical_brain: BrainVote
    momentum_brain: BrainVote
    volatility_brain: BrainVote
    advisory_summary: str
    actionable_notes: list


class QuantitativeDataEngine:
    """Fetches and cleans live market data for BTC/USDT pairs."""

    @staticmethod
    def fetch_data(symbol: str = "BTC-USD", interval: str = "1h", period: str = "30d") -> pd.DataFrame:
        """
        Fetches historical candle data. For 4h, pulls 1h data and resamples to 4h bars.
        """
        try:
            ticker = yf.Ticker(symbol)
            if interval == "4h":
                # Yahoo Finance does not have native 4h candles; resample from 1h
                raw_df = ticker.history(period="60d", interval="1h")
                if raw_df.empty:
                    raise ValueError(f"No data returned for {symbol} on 1h interval.")
                
                # Resample 1h to 4h
                resampled = raw_df.resample("4h").agg({
                    "Open": "first",
                    "High": "max",
                    "Low": "min",
                    "Close": "last",
                    "Volume": "sum"
                }).dropna()
                df = resampled.copy()
            else:
                df = ticker.history(period=period, interval=interval)
                if df.empty:
                    raise ValueError(f"No data returned for {symbol} on interval {interval}.")
            
            # Clean dataframe
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.dropna(inplace=True)
            return df
        except Exception as e:
            raise RuntimeError(f"Error fetching data from yfinance: {str(e)}")


class StatisticalBrain:
    """
    Calculates historical probability distributions based on Bollinger Bands,
    price Z-scores, and mean-reverting ranging structures.
    """

    @staticmethod
    def analyze(df: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> BrainVote:
        close = df["Close"]
        sma = close.rolling(window=window).mean()
        std = close.rolling(window=window).std()

        upper_band = sma + (num_std * std)
        lower_band = sma - (num_std * std)
        
        # %B: Position within Bollinger Bands (0 = lower band, 1 = upper band)
        band_range = (upper_band - lower_band).replace(0, 1e-6)
        pct_b = (close - lower_band) / band_range
        bandwidth = band_range / sma

        # Z-score of price relative to 20-period moving average
        z_score = (close - sma) / std.replace(0, 1e-6)

        curr_close = close.iloc[-1]
        curr_sma = sma.iloc[-1]
        curr_upper = upper_band.iloc[-1]
        curr_lower = lower_band.iloc[-1]
        curr_pct_b = pct_b.iloc[-1]
        curr_bw = bandwidth.iloc[-1]
        curr_z = z_score.iloc[-1]

        # Historical percentile of bandwidth over the past window * 3
        bw_rolling = bandwidth.dropna()
        if len(bw_rolling) >= 30:
            bw_percentile = (bw_rolling < curr_bw).mean() * 100
        else:
            bw_percentile = 50.0

        # Mean Reversion vs Trend Probability
        # If %B is below 0.10: Price is stretched at lower band -> Mean reversion probability (Buy) increases
        # If %B is above 0.90: Price is stretched at upper band -> Mean reversion probability (Sell) increases
        # If Bandwidth is expanding sharply with price above upper band -> Momentum breakout overrides mean reversion.
        
        if curr_pct_b <= 0.15:
            # Deep oversold in standard deviation terms
            buy_prob = 0.65 + min(0.20, (0.15 - curr_pct_b) * 0.8)
            sell_prob = 0.15
            neutral_prob = max(0.05, 1.0 - buy_prob - sell_prob)
            signal = "OVERSOLD_MEAN_REVERSION_BUY"
        elif curr_pct_b >= 0.85:
            # Overbought in standard deviation terms
            sell_prob = 0.65 + min(0.20, (curr_pct_b - 0.85) * 0.8)
            buy_prob = 0.15
            neutral_prob = max(0.05, 1.0 - buy_prob - sell_prob)
            signal = "OVERBOUGHT_MEAN_REVERSION_SELL"
        else:
            # Normal distribution ranging
            # Bias according to position relative to SMA
            deviation = (curr_close - curr_sma) / (curr_upper - curr_sma if curr_close >= curr_sma else curr_sma - curr_lower)
            if deviation > 0.3:
                buy_prob = 0.45
                sell_prob = 0.30
                neutral_prob = 0.25
                signal = "UPPER_CHANNEL_ACCUMULATION"
            elif deviation < -0.3:
                buy_prob = 0.30
                sell_prob = 0.45
                neutral_prob = 0.25
                signal = "LOWER_CHANNEL_DISTRIBUTION"
            else:
                buy_prob = 0.33
                sell_prob = 0.33
                neutral_prob = 0.34
                signal = "EQUILIBRIUM_CHANNEL"

        # Normalize to strictly sum to 1.0
        total = buy_prob + neutral_prob + sell_prob
        buy_prob = round(buy_prob / total, 4)
        neutral_prob = round(neutral_prob / total, 4)
        sell_prob = round(1.0 - buy_prob - neutral_prob, 4)

        confidence = round(abs(buy_prob - sell_prob) * 2, 2)
        confidence = min(1.0, max(0.2, confidence))

        return BrainVote(
            buy_prob=buy_prob,
            neutral_prob=neutral_prob,
            sell_prob=sell_prob,
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
    """
    Tracks trend acceleration, exhaustion, and momentum velocity using
    Relative Strength Index (RSI) and Moving Average Convergence Divergence (MACD).
    """

    @staticmethod
    def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -1 * delta.clip(upper=0)
        
        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
        
        rs = avg_gain / avg_loss.replace(0, 1e-6)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def _compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal_span: int = 9):
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_span, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @classmethod
    def analyze(cls, df: pd.DataFrame) -> BrainVote:
        close = df["Close"]
        rsi = cls._compute_rsi(close, period=14)
        macd, signal_line, hist = cls._compute_macd(close)

        curr_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        curr_macd = macd.iloc[-1]
        curr_signal = signal_line.iloc[-1]
        curr_hist = hist.iloc[-1]
        prev_hist = hist.iloc[-2]

        hist_delta = curr_hist - prev_hist
        rsi_slope = curr_rsi - prev_rsi

        # Scoring matrix
        bullish_score = 0.0
        bearish_score = 0.0

        # RSI logic
        if curr_rsi < 30:
            # Severely oversold -> strong bullish reversal probability
            bullish_score += 0.40
        elif curr_rsi > 70:
            # Severely overbought -> strong bearish reversal probability
            bearish_score += 0.40
        elif 50 <= curr_rsi <= 70:
            # Bullish trend zone
            bullish_score += 0.25 if rsi_slope > 0 else 0.15
        elif 30 <= curr_rsi < 50:
            # Bearish trend zone
            bearish_score += 0.25 if rsi_slope < 0 else 0.15

        # MACD logic
        if curr_macd > curr_signal:
            bullish_score += 0.25
            if hist_delta > 0:
                bullish_score += 0.15  # Acceleration
        else:
            bearish_score += 0.25
            if hist_delta < 0:
                bearish_score += 0.15  # Downward Acceleration

        # Zero line alignment
        if curr_macd > 0:
            bullish_score += 0.10
        else:
            bearish_score += 0.10

        # Normalize to probability distribution
        total_score = bullish_score + bearish_score + 0.20
        buy_prob = bullish_score / total_score
        sell_prob = bearish_score / total_score
        neutral_prob = 0.20 / total_score

        # Signal labeling
        if buy_prob > 0.55:
            signal = "BULLISH_MOMENTUM_ACCELERATION" if hist_delta > 0 else "BULLISH_MOMENTUM_CONFIRMED"
        elif sell_prob > 0.55:
            signal = "BEARISH_MOMENTUM_EXPANSION" if hist_delta < 0 else "BEARISH_MOMENTUM_CONFIRMED"
        else:
            signal = "MOMENTUM_CONSOLIDATION"

        buy_prob = round(buy_prob, 4)
        sell_prob = round(sell_prob, 4)
        neutral_prob = round(1.0 - buy_prob - sell_prob, 4)

        confidence = round(abs(buy_prob - sell_prob) * 1.8, 2)
        confidence = min(1.0, max(0.2, confidence))

        return BrainVote(
            buy_prob=buy_prob,
            neutral_prob=neutral_prob,
            sell_prob=sell_prob,
            confidence=confidence,
            signal=signal,
            details={
                "rsi": round(curr_rsi, 2),
                "rsi_slope": round(rsi_slope, 2),
                "macd": round(curr_macd, 2),
                "macd_signal": round(curr_signal, 2),
                "macd_hist": round(curr_hist, 2),
                "hist_acceleration": round(hist_delta, 2),
            }
        )


class VolatilityBrain:
    """
    Measures market compression via ATR and Bollinger Band Squeeze (BB vs Keltner Channels).
    Warns the user if a major breakout is imminent.
    """

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr

    @classmethod
    def analyze(cls, df: pd.DataFrame) -> BrainVote:
        close = df["Close"]
        atr = cls._compute_atr(df, period=14)
        
        # Bollinger Bands (20, 2)
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_bb = sma20 + 2.0 * std20
        lower_bb = sma20 - 2.0 * std20

        # Keltner Channels (20, 1.5 * ATR)
        upper_kc = sma20 + (1.5 * atr)
        lower_kc = sma20 - (1.5 * atr)

        # Squeeze logic: When Bollinger Bands fit inside Keltner Channels
        # Market volatility is compressed like a coiled spring.
        squeeze_on = (upper_bb < upper_kc) & (lower_bb > lower_kc)

        curr_atr = atr.iloc[-1]
        curr_close = close.iloc[-1]
        atr_pct = (curr_atr / curr_close) * 100.0

        # Historical ATR percentile
        atr_rolling = atr.dropna()
        if len(atr_rolling) >= 30:
            atr_percentile = (atr_rolling < curr_atr).mean() * 100.0
        else:
            atr_percentile = 50.0

        is_squeeze = bool(squeeze_on.iloc[-1])
        recent_squeezes = int(squeeze_on.tail(5).sum())

        # Determine Breakout Warning Level
        if is_squeeze or (atr_percentile < 15.0):
            warning_level = "CRITICAL_BREAKOUT_IMMINENT"
            compression_state = "EXTREME_COMPRESSION"
            breakout_imminent = True
        elif atr_percentile < 30.0 or recent_squeezes >= 2:
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

        # Directional lean of the breakout:
        # Based on whether price is pressing above or below the 20-period moving average
        dist_from_sma = (curr_close - sma20.iloc[-1]) / (curr_atr if curr_atr > 0 else 1.0)
        
        if dist_from_sma > 0.5:
            # Bullish expansion bias
            buy_prob = 0.55 if breakout_imminent else 0.45
            sell_prob = 0.25
            neutral_prob = 0.20
            signal = "VOLATILITY_UPWARD_EXPANSION"
        elif dist_from_sma < -0.5:
            # Bearish breakdown bias
            buy_prob = 0.25
            sell_prob = 0.55 if breakout_imminent else 0.45
            neutral_prob = 0.20
            signal = "VOLATILITY_DOWNWARD_BREAKDOWN"
        else:
            # Coiled with equal pressure
            buy_prob = 0.35
            sell_prob = 0.35
            neutral_prob = 0.30
            signal = "VOLATILITY_ENERGY_STORAGE"

        total = buy_prob + neutral_prob + sell_prob
        buy_prob = round(buy_prob / total, 4)
        neutral_prob = round(neutral_prob / total, 4)
        sell_prob = round(1.0 - buy_prob - neutral_prob, 4)

        confidence = 0.85 if breakout_imminent else 0.50

        return BrainVote(
            buy_prob=buy_prob,
            neutral_prob=neutral_prob,
            sell_prob=sell_prob,
            confidence=confidence,
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
    Ensemble engine that combines the Statistical, Momentum, and Volatility Brains
    to output a comprehensive Trader Advisory Report.
    """

    @classmethod
    def generate_advisory(cls, symbol: str = "BTC-USD", timeframe: str = "1h") -> AdvisoryReport:
        # 1. Fetch data
        df = QuantitativeDataEngine.fetch_data(symbol=symbol, interval=timeframe)
        if len(df) < 30:
            raise ValueError(f"Insufficient historical data ({len(df)} bars) for calculation.")

        # 2. Run Brains
        stat_vote = StatisticalBrain.analyze(df)
        mom_vote = MomentumBrain.analyze(df)
        vol_vote = VolatilityBrain.analyze(df)

        # 3. Dynamic Ensemble Weights
        # Baseline: Stat: 0.35, Mom: 0.35, Vol: 0.30
        # If severe squeeze is active, volatility breakout mechanics get higher weight.
        if vol_vote.details.get("breakout_imminent", False):
            w_stat, w_mom, w_vol = 0.25, 0.40, 0.35
        else:
            w_stat, w_mom, w_vol = 0.35, 0.40, 0.25

        raw_buy = (stat_vote.buy_prob * w_stat) + (mom_vote.buy_prob * w_mom) + (vol_vote.buy_prob * w_vol)
        raw_neutral = (stat_vote.neutral_prob * w_stat) + (mom_vote.neutral_prob * w_mom) + (vol_vote.neutral_prob * w_vol)
        raw_sell = (stat_vote.sell_prob * w_stat) + (mom_vote.sell_prob * w_mom) + (vol_vote.sell_prob * w_vol)

        total_p = raw_buy + raw_neutral + raw_sell
        buy_pct = round((raw_buy / total_p) * 100, 1)
        sell_pct = round((raw_sell / total_p) * 100, 1)
        neutral_pct = round(100.0 - buy_pct - sell_pct, 1)

        # 4. Overall Bias Classification
        if buy_pct >= 60.0:
            overall_bias = "STRONG_BUY_PROBABILITY"
        elif buy_pct >= 52.0:
            overall_bias = "MODERATE_BUY_BIAS"
        elif sell_pct >= 60.0:
            overall_bias = "STRONG_SELL_PROBABILITY"
        elif sell_pct >= 52.0:
            overall_bias = "MODERATE_SELL_BIAS"
        else:
            overall_bias = "NEUTRAL_CONSOLIDATION"

        # 5. Price and Support/Resistance (Pivot Points)
        curr_price = float(df["Close"].iloc[-1])
        prev_price = float(df["Close"].iloc[-24 if len(df) >= 24 else 0])
        price_change_24h = ((curr_price - prev_price) / prev_price) * 100.0

        high_recent = float(df["High"].iloc[-24:].max())
        low_recent = float(df["Low"].iloc[-24:].min())
        
        pivot = (high_recent + low_recent + curr_price) / 3.0
        r1 = (2 * pivot) - low_recent
        r2 = pivot + (high_recent - low_recent)
        s1 = (2 * pivot) - high_recent
        s2 = pivot - (high_recent - low_recent)

        # 6. Overall Confidence Score
        confidence = (stat_vote.confidence * w_stat) + (mom_vote.confidence * w_mom) + (vol_vote.confidence * w_vol)
        confidence = round(confidence * 100, 1)

        # 7. Actionable Notes & Advisory Report
        notes = []
        if vol_vote.details.get("breakout_imminent", False):
            notes.append("🚨 VOLATILITY ALERT: Market compression detected. A high-velocity breakout is imminent.")
        
        if mom_vote.details["rsi"] < 30:
            notes.append("📈 RSI OVERSOLD: Downside momentum is heavily exhausted; watch for bullish mean-reversion.")
        elif mom_vote.details["rsi"] > 70:
            notes.append("📉 RSI OVERBOUGHT: Bullish momentum entering exhaustion territory; risk of sharp corrective pullbacks.")

        if stat_vote.details["percent_b"] <= 0.10:
            notes.append("📊 STATISTICAL EXTREME: Price is touching or penetrating the lower Bollinger Band.")
        elif stat_vote.details["percent_b"] >= 0.90:
            notes.append("📊 STATISTICAL EXTREME: Price is riding or exceeding the upper Bollinger Band.")

        if buy_pct > 55.0:
            notes.append("💡 ADVISORY TACTIC: Probabilities favor long positioning or strategic spot accumulation.")
        elif sell_pct > 55.0:
            notes.append("🛡️ ADVISORY TACTIC: Probabilities favor defensive hedging, profit-taking, or short positioning.")
        else:
            notes.append("⚖️ ADVISORY TACTIC: Choppy/ranging market regime. Recommend waiting for band confirmation before executing.")

        notes.append("⚠️ DISCLAIMER: These metrics represent statistical and quantitative odds, not automated execution instructions.")

        summary = (
            f"Ensemble Model indicates a {buy_pct}% BUY probability vs {sell_pct}% SELL probability "
            f"({neutral_pct}% Neutral) on the {timeframe} timeframe. Market regime is characterized by "
            f"{vol_vote.details['compression_state'].replace('_', ' ')} with confidence at {confidence}%."
        )

        return AdvisoryReport(
            symbol=symbol,
            timeframe=timeframe,
            latest_price=round(curr_price, 2),
            price_change_24h_pct=round(price_change_24h, 2),
            timestamp=str(df.index[-1]),
            buy_probability=buy_pct,
            neutral_probability=neutral_pct,
            sell_probability=sell_pct,
            overall_bias=overall_bias,
            confidence_score=confidence,
            volatility_state=vol_vote.details["compression_state"],
            breakout_imminent=vol_vote.details["breakout_imminent"],
            breakout_warning_level=vol_vote.details["warning_level"],
            support_levels={"S1": round(s1, 2), "S2": round(s2, 2)},
            resistance_levels={"R1": round(r1, 2), "R2": round(r2, 2)},
            pivot_point=round(pivot, 2),
            atr_value=vol_vote.details["atr"],
            atr_percent=vol_vote.details["atr_pct"],
            statistical_brain=stat_vote,
            momentum_brain=mom_vote,
            volatility_brain=vol_vote,
            advisory_summary=summary,
            actionable_notes=notes
        )


if __name__ == "__main__":
    print("Testing Predictive Ensemble Engine...")
    report_1h = PredictiveEnsembleEngine.generate_advisory("BTC-USD", "1h")
    print("\n--- 1H ADVISORY REPORT ---")
    print(f"Latest Price: ${report_1h.latest_price:,.2f}")
    print(f"Probabilities -> BUY: {report_1h.buy_probability}% | NEUTRAL: {report_1h.neutral_probability}% | SELL: {report_1h.sell_probability}%")
    print(f"Overall Bias: {report_1h.overall_bias} (Confidence: {report_1h.confidence_score}%)")
    print(f"Breakout Imminent: {report_1h.breakout_imminent} ({report_1h.breakout_warning_level})")
    
    report_4h = PredictiveEnsembleEngine.generate_advisory("BTC-USD", "4h")
    print("\n--- 4H ADVISORY REPORT ---")
    print(f"Latest Price: ${report_4h.latest_price:,.2f}")
    print(f"Probabilities -> BUY: {report_4h.buy_probability}% | NEUTRAL: {report_4h.neutral_probability}% | SELL: {report_4h.sell_probability}%")
    print(f"Overall Bias: {report_4h.overall_bias} (Confidence: {report_4h.confidence_score}%)")
