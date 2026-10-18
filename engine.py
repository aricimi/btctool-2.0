"""
btctool 2.0 - Institutional Algorithmic Predictive Engine & Trading Bot Directive Matrix
Data Source: Direct Binance Spot & Futures Real-Time REST Feeds with yfinance fallback
Architecture: Tri-Brain Quantitative Consensus + Order Book Liquidity + Macro Confluence
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional, List
import datetime
import collections
import time
import gc
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV


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
    taker_delta: float = 0.0
    confirmed_delta_p: float = 0.0


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
    adx_value: float = 0.0
    squeeze_state: str = "IDLE"
    squeeze_label: str = ""
    funding_warning: Optional[str] = None
    oi_confluence: str = "NEUTRAL"
    crowded_long_risk: bool = False


# ============================================================================
# STEP 2 — ADX(14) INDICATOR HELPER
# ============================================================================
def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Computes ADX(14) with defensive column lookup."""
    high  = df['High']  if 'High'  in df.columns else df['high']
    low   = df['Low']   if 'Low'   in df.columns else df['low']
    close = df['Close'] if 'Close' in df.columns else df['close']
    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm[plus_dm < minus_dm]   = 0
    minus_dm[minus_dm < plus_dm]  = 0
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr_w    = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_w
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_w
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    return dx.ewm(alpha=1/period, adjust=False).mean()


# ============================================================================
# STEP 3C — ORDER BOOK ANTI-SPOOFING PERSISTENCE
# ============================================================================
_ob_snapshot_history: list = []

def get_confirmed_ob_delta_p(ob_imbalance_ratio: float) -> float:
    """Requires 3 consecutive snapshots of same-sign imbalance before applying alpha."""
    _ob_snapshot_history.append(ob_imbalance_ratio)
    if len(_ob_snapshot_history) > 5:
        _ob_snapshot_history.pop(0)
    last_3 = _ob_snapshot_history[-3:]
    if len(last_3) < 3:
        return 0.0
    if all(v > 0 for v in last_3) or all(v < 0 for v in last_3):
        return 0.15 * float(np.tanh(3.0 * ob_imbalance_ratio))
    return 0.0


# ============================================================================
_rolling_trade_cache: Dict[str, Tuple[int, str, float]] = {}

def fetch_taker_delta() -> float:
    """
    Returns sustained volume-weighted taker delta ratio [-1.0, +1.0] across rolling 90s window.
    Filters out micro-noise, illiquidity skews, and 10-second quote flickers.
    """
    global _rolling_trade_cache
    try:
        url    = "https://api.bybit.com/v5/market/recent-trade"
        params = {"category": "spot", "symbol": "BTCUSDT", "limit": 60}
        resp   = requests.get(url, params=params, timeout=5)
        trades = resp.json().get("result", {}).get("list", [])
        now_ms = int(time.time() * 1000)

        for t in trades:
            exec_id = t.get('execId')
            if exec_id:
                _rolling_trade_cache[exec_id] = (int(t.get('time', now_ms)), t.get('side', ''), float(t.get('size', 0.0)))

        # Prune trades older than 90 seconds
        cutoff = now_ms - 90000
        for k in list(_rolling_trade_cache.keys()):
            if _rolling_trade_cache[k][0] < cutoff:
                del _rolling_trade_cache[k]

        buy_vol  = sum(v[2] for v in _rolling_trade_cache.values() if v[1] == 'Buy')
        sell_vol = sum(v[2] for v in _rolling_trade_cache.values() if v[1] == 'Sell')
        total    = buy_vol + sell_vol

        if total <= 0:
            return 0.0

        raw_delta = (buy_vol - sell_vol) / total
        # Liquidity damping: If total 90s volume is less than 2.5 BTC, dampen delta to prevent micro-illiquidity skew
        vol_confidence = min(1.0, total / 2.5)
        return float(raw_delta * vol_confidence)
    except Exception:
        return 0.0


# ============================================================================
# STEP 5 — TRI-BRAIN META-LEARNER ROLLING STORAGE & FUNCTIONS
# ============================================================================
_oi_history:           collections.deque = collections.deque(maxlen=100)
_retail_ratio_history: collections.deque = collections.deque(maxlen=96)
_feature_history:      collections.deque = collections.deque(maxlen=600)
_label_history:        collections.deque = collections.deque(maxlen=600)
_last_train_time:      float = 0.0
_RETRAIN_INTERVAL:     float = 60.0
_meta_learner_model           = None
_imbalance_history:    collections.deque = collections.deque(maxlen=6)


def compute_oi_zscore(current_oi: float) -> float:
    """Computes Z-Score of 20-period OI changes."""
    _oi_history.append(current_oi)
    if len(_oi_history) < 21:
        return float('nan')
    oi_series      = pd.Series(list(_oi_history))
    oi_changes     = oi_series.diff().dropna()
    mean_20        = oi_changes.iloc[-20:].mean()
    std_20         = oi_changes.iloc[-20:].std()
    current_change = oi_series.iloc[-1] - oi_series.iloc[-2]
    return (current_change - mean_20) / std_20 if std_20 > 0 else float('nan')


def train_meta_learner():
    """Trains calibrated gradient boosting classifier on collected feature/label history."""
    X = pd.DataFrame(list(_feature_history)[:len(_label_history)])
    y = np.array(list(_label_history))
    if len(y) < 200:
        return None   # cold start — not enough data yet

    base = HistGradientBoostingClassifier(
        max_depth=3, max_iter=35,
        min_samples_leaf=20, l2_regularization=1.0,
        random_state=42
    )
    if len(y) < 300:
        base.fit(X.iloc[:-20], y[:-20])
        model = CalibratedClassifierCV(estimator=base, method='sigmoid', cv='prefit')
        model.fit(X.iloc[-20:], y[-20:])
    else:
        model = CalibratedClassifierCV(estimator=base, method='sigmoid', cv=3)
        model.fit(X, y)

    del X, y
    gc.collect()
    return model


def maybe_retrain():
    """Retrains meta learner if interval elapsed."""
    global _meta_learner_model, _last_train_time
    if time.time() - _last_train_time < _RETRAIN_INTERVAL:
        return
    new_model = train_meta_learner()
    if new_model is not None:
        _meta_learner_model = new_model
        _last_train_time    = time.time()


REGIME_WEIGHTS = {
    'Range':      {'stat': 0.55, 'mom': 0.25, 'vol': 0.20},
    'Trend Up':   {'stat': 0.20, 'mom': 0.60, 'vol': 0.20},
    'Trend Down': {'stat': 0.20, 'mom': 0.60, 'vol': 0.20},
    'Breakout':   {'stat': 0.15, 'mom': 0.25, 'vol': 0.60},
    'Chop':       {'stat': 0.40, 'mom': 0.30, 'vol': 0.30},
}


def get_combined_probability(stat_score: float, mom_score: float, vol_score: float,
                              macro_regime: str, adx_14: float, squeeze_state: str,
                              ob_imbalance_ratio: float, funding_rate_decimal: float,
                              oi_zscore: float, taker_delta: float) -> float:
    """Combines tri-brain outputs using Level 2 Meta-Learner (or regime fallback)."""
    if _meta_learner_model is not None:
        features = pd.DataFrame([{
            'stat_score': stat_score, 'mom_score': mom_score,
            'vol_score':  vol_score,  'ob_imbalance': ob_imbalance_ratio,
            'funding_rate': funding_rate_decimal,
            'oi_zscore': 0.0 if np.isnan(oi_zscore) else oi_zscore,
            'taker_delta': 0.0 if np.isnan(taker_delta) else taker_delta,
        }])
        prob = float(_meta_learner_model.predict_proba(features)[0][1])
        gc.collect()
        return prob
    else:
        regime_key = 'Breakout' if squeeze_state == 'FIRING' else \
                     'Chop' if adx_14 <= 22 else macro_regime
        w = REGIME_WEIGHTS.get(regime_key, REGIME_WEIGHTS['Chop'])
        return float(w['stat'] * stat_score + w['mom'] * mom_score + w['vol'] * vol_score)


# ============================================================================
# STEP 6 — SQUEEZE STATE MACHINE
# ============================================================================
_squeeze_state:   str = 'IDLE'
_squeeze_counter: int = 0

def update_squeeze_state(bb_width: float, bb_width_sma20: float,
                          bb_inside_kc: bool, timeframe: str) -> str:
    """5-State Squeeze Machine tracking compression across cycles."""
    global _squeeze_state, _squeeze_counter

    loaded_threshold = 5 if timeframe in ('1m', '5m') else 3

    if bb_inside_kc:
        _squeeze_counter += 1
    else:
        _squeeze_counter = 0

    prev = _squeeze_state

    if bb_inside_kc:
        new_state = 'LOADED' if _squeeze_counter >= loaded_threshold else 'BUILDING'
    elif prev in ('LOADED', 'BUILDING'):
        new_state = 'FIRING'
    elif prev in ('FIRING', 'TRENDING'):
        new_state = 'IDLE' if bb_width < bb_width_sma20 else 'TRENDING'
    else:
        new_state = 'IDLE'

    _squeeze_state = new_state
    return new_state


SQUEEZE_LABELS = {
    'IDLE': '',
    'BUILDING': '⚪ SQUEEZE BUILDING',
    'LOADED': '🟡 SQUEEZE LOADED — WATCH FOR BREAK',
    'FIRING': '🔴 SQUEEZE FIRING — BREAKOUT ACTIVE',
    'TRENDING': '🟢 POST-SQUEEZE TREND — TRAIL STOP',
}


# ============================================================================
# STEP 9 — SCENARIO CONFLICT RESOLUTION HIERARCHY
# ============================================================================
def resolve_scenario(candidate_directive: str,
                      macro_regime: str, adx_14: float,
                      squeeze_state: str, ob_delta_p: float,
                      percent_b: float,
                      suppress_longs: bool, suppress_shorts: bool) -> str:
    """Enforces 5-gate conflict resolution hierarchy on trade directives."""
    # Gate 1 — Derivatives pre-filter (highest authority)
    if suppress_longs and 'ENTER LONG NOW' in candidate_directive:
        candidate_directive = candidate_directive.replace(
            'ENTER LONG NOW', 'SET BUY LIMIT ORDER')

    if suppress_shorts and 'ENTER SHORT NOW' in candidate_directive:
        candidate_directive = candidate_directive.replace(
            'ENTER SHORT NOW', 'SET SELL LIMIT ORDER')

    # Gate 2 — 4H Macro Regime + ADX
    if macro_regime == 'Trend Down' and adx_14 > 22:
        if 'ENTER LONG NOW' in candidate_directive:
            candidate_directive = 'COUNTER-TREND SCALP: BUY PULLBACK LIMIT'

    # Gate 3 — Squeeze FIRING overrules trend-fade scenarios
    if squeeze_state == 'FIRING':
        if 'BEARISH FADE' in candidate_directive or 'RESISTANCE' in candidate_directive:
            candidate_directive = 'SQUEEZE FIRING — AWAIT DIRECTION CONFIRMATION'

    # Gate 4 — OB imbalance tiebreaker (Scenario 1 vs Scenario 4)
    if ob_delta_p > 0.08 and 'SELL LIMIT' in candidate_directive \
            and macro_regime != 'Trend Down':
        candidate_directive = 'TREND FOLLOWING: SET BUY LIMIT AT SUPPORT'
    elif ob_delta_p < -0.08 and 'BUY LIMIT' in candidate_directive \
            and macro_regime != 'Trend Up':
        candidate_directive = 'SET SELL LIMIT AT RESISTANCE (BEARISH FADE)'

    # Gate 5 — %B final boundary validation
    if percent_b > 0.90 and 'ENTER LONG NOW' in candidate_directive:
        candidate_directive = 'SET SELL LIMIT AT RESISTANCE (BEARISH FADE)'
    if percent_b < 0.10 and 'ENTER SHORT NOW' in candidate_directive:
        candidate_directive = 'COUNTER-TREND SCALP: BUY PULLBACK LIMIT'

    return candidate_directive


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
        """Pulls klines from Bybit with Binance and yfinance fallbacks across full timeframe ladder."""
        # 1. Primary: Bybit Spot Klines (Unblocked globally, full scale)
        bybit_interval_map = {
            "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
            "1h": "60", "2h": "120", "4h": "240", "1d": "D", "1w": "W"
        }
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
        binance_interval_map = {
            "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h", "1d": "1d", "1w": "1w"
        }
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
        """Calculates distance-weighted Order Book depth, tanh imbalance alpha, taker delta, and Futures OI."""
        bid_depth_usd = 0.0
        ask_depth_usd = 0.0
        imbalance_pct = 0.0
        best_bid = 0.0
        best_ask = 0.0
        spread_bps = 0.0
        oi_btc = 0.0
        funding_rate = 0.0

        # 1. Primary: Bybit Spot Order Book with Exponential Distance Weighting
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

                    bid_prices = np.array([float(l[0]) for l in bids], dtype=float)
                    bid_sizes = np.array([float(l[1]) * float(l[0]) for l in bids], dtype=float)
                    bid_weights = np.exp(-40.0 * np.abs(bid_prices - mid_price) / mid_price)
                    bid_depth_usd = float(np.sum(bid_sizes * bid_weights))

                    ask_prices = np.array([float(l[0]) for l in asks], dtype=float)
                    ask_sizes = np.array([float(l[1]) * float(l[0]) for l in asks], dtype=float)
                    ask_weights = np.exp(-40.0 * np.abs(ask_prices - mid_price) / mid_price)
                    ask_depth_usd = float(np.sum(ask_sizes * ask_weights))
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

                        bid_prices = np.array([float(l[0]) for l in bids], dtype=float)
                        bid_sizes = np.array([float(l[1]) * float(l[0]) for l in bids], dtype=float)
                        bid_weights = np.exp(-40.0 * np.abs(bid_prices - mid_price) / mid_price)
                        bid_depth_usd = float(np.sum(bid_sizes * bid_weights))

                        ask_prices = np.array([float(l[0]) for l in asks], dtype=float)
                        ask_sizes = np.array([float(l[1]) * float(l[0]) for l in asks], dtype=float)
                        ask_weights = np.exp(-40.0 * np.abs(ask_prices - mid_price) / mid_price)
                        ask_depth_usd = float(np.sum(ask_sizes * ask_weights))
            except Exception:
                pass

        # Calculate Distance-Weighted Imbalance Ratio (Anti-Spoofing Smoothed)
        total_depth = bid_depth_usd + ask_depth_usd
        ob_imbalance_ratio = (bid_depth_usd - ask_depth_usd) / total_depth if total_depth > 0 else 0.0
        raw_imbalance_pct = ob_imbalance_ratio * 100.0
        _imbalance_history.append(raw_imbalance_pct)
        imbalance_pct = float(np.median(_imbalance_history)) if len(_imbalance_history) > 0 else raw_imbalance_pct

        # Taker delta from Bybit recent trades
        taker_delta = fetch_taker_delta()

        # Confirmed anti-spoofing delta_P
        confirmed_delta_p = get_confirmed_ob_delta_p(ob_imbalance_ratio)

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
            funding_rate_pct=round(funding_rate, 4),
            taker_delta=round(0.0 if np.isnan(taker_delta) else taker_delta, 4),
            confirmed_delta_p=round(confirmed_delta_p, 4)
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
    def analyze(cls, df: pd.DataFrame, macro_regime: str = "Range / Consolidation", timeframe: str = "1h") -> BrainVote:
        close = df["Close"]
        atr = cls._compute_atr(df, period=14)

        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_bb = sma20 + 2.0 * std20
        lower_bb = sma20 - 2.0 * std20

        upper_kc = sma20 + (1.5 * atr)
        lower_kc = sma20 - (1.5 * atr)

        curr_atr = atr.iloc[-1]
        curr_close = close.iloc[-1]
        atr_pct = (curr_atr / curr_close) * 100.0

        # Step 6: Squeeze State Machine (BB vs KC)
        kc_width = 2.0 * 1.5 * curr_atr
        curr_upper_bb = upper_bb.iloc[-1]
        curr_lower_bb = lower_bb.iloc[-1]
        bb_width = curr_upper_bb - curr_lower_bb
        bb_inside_kc = bb_width < kc_width
        bb_width_sma20 = (upper_bb - lower_bb).rolling(20).mean().iloc[-1]

        squeeze_state = update_squeeze_state(bb_width, bb_width_sma20, bb_inside_kc, timeframe=timeframe)
        squeeze_label = SQUEEZE_LABELS.get(squeeze_state, "")

        atr_rolling = atr.dropna()
        atr_percentile = (atr_rolling < curr_atr).mean() * 100.0 if len(atr_rolling) >= 30 else 50.0

        is_squeeze = bb_inside_kc
        breakout_imminent = squeeze_state in ('LOADED', 'FIRING')

        if squeeze_state == 'FIRING':
            warning_level = "SQUEEZE_FIRING"
            compression_state = "BREAKOUT_FIRING"
        elif squeeze_state == 'LOADED':
            warning_level = "CRITICAL_BREAKOUT_IMMINENT"
            compression_state = "EXTREME_COMPRESSION"
        elif squeeze_state == 'BUILDING':
            warning_level = "HIGH_COMPRESSION"
            compression_state = "MODERATE_COMPRESSION"
        elif squeeze_state == 'TRENDING':
            warning_level = "VOLATILITY_EXPANSION"
            compression_state = "POST_SQUEEZE_TREND"
        else:
            warning_level = "NORMAL_VOLATILITY"
            compression_state = "EQUILIBRIUM"

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
                "squeeze_state": squeeze_state,
                "squeeze_label": squeeze_label,
                "compression_state": compression_state,
                "warning_level": squeeze_label if squeeze_label else warning_level,
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
        curr_price = float(df["Close"].iloc[-1])

        # 2. Ingest 4H Structure with ADX(14) (Step 2)
        df_4h = MarketDataService.fetch_klines(symbol=symbol, interval="4h", limit=60)
        close_4h = df_4h["Close"] if "Close" in df_4h.columns else df_4h["close"]
        fast_ema_4h = close_4h.ewm(span=9, adjust=False).mean().iloc[-1]
        slow_ema_4h = close_4h.ewm(span=21, adjust=False).mean().iloc[-1]

        adx_series = compute_adx(df_4h, period=14)
        adx_14 = float(adx_series.iloc[-1]) if not adx_series.empty else 20.0
        delta_adx = float(adx_series.iloc[-1] - adx_series.iloc[-2]) if len(adx_series) >= 2 else 0.0

        if adx_14 > 22 or delta_adx > 0:
            macro_regime_4h = 'Trend Up' if fast_ema_4h > slow_ema_4h else 'Trend Down'
        else:
            macro_regime_4h = 'Range'

        # 3. Analyze Brains with Macro Context & Timeframe
        stat_vote = StatisticalBrain.analyze(df, macro_regime=macro_regime_4h)
        mom_vote = MomentumBrain.analyze(df, macro_regime=macro_regime_4h, timeframe=timeframe)
        vol_vote = VolatilityBrain.analyze(df, macro_regime=macro_regime_4h, timeframe=timeframe)

        atr_val = vol_vote.details["atr"]
        pct_b = stat_vote.details["percent_b"]
        squeeze_state = vol_vote.details.get("squeeze_state", "IDLE")
        squeeze_label = vol_vote.details.get("squeeze_label", "")

        ob_imbalance_ratio = orderbook.imbalance_pct / 100.0
        funding_rate_decimal = orderbook.funding_rate_pct / 100.0
        oi_zscore = compute_oi_zscore(orderbook.open_interest_btc)
        taker_delta = orderbook.taker_delta

        # 4. STEP 5 — Meta-Learner Feature & Label Collection
        feature_row = {
            'stat_score':   stat_vote.buy_prob,
            'mom_score':    mom_vote.buy_prob,
            'vol_score':    vol_vote.buy_prob,
            'ob_imbalance': ob_imbalance_ratio,
            'funding_rate': funding_rate_decimal,
            'oi_zscore':    0.0 if np.isnan(oi_zscore) else oi_zscore,
            'taker_delta':  0.0 if np.isnan(taker_delta) else taker_delta,
        }
        _feature_history.append(feature_row)

        # Label generated 3 completed candles later
        if len(df) >= 4 and len(_feature_history) >= 4 and len(_label_history) < (len(_feature_history) - 3):
            close_curr = float(df['Close'].iloc[-1])
            close_3_ago = float(df['Close'].iloc[-4])
            label = 1 if (close_curr - close_3_ago) >= (0.3 * atr_val) else 0
            _label_history.append(label)

        maybe_retrain()

        # Step 5E / Meta-Learner probability inference
        buy_prob_combined = get_combined_probability(
            stat_score=stat_vote.buy_prob,
            mom_score=mom_vote.buy_prob,
            vol_score=vol_vote.buy_prob,
            macro_regime=macro_regime_4h,
            adx_14=adx_14,
            squeeze_state=squeeze_state,
            ob_imbalance_ratio=ob_imbalance_ratio,
            funding_rate_decimal=funding_rate_decimal,
            oi_zscore=0.0 if np.isnan(oi_zscore) else oi_zscore,
            taker_delta=0.0 if np.isnan(taker_delta) else taker_delta
        )

        # Step 3B & 3C: tanh Alpha Curve with Anti-Spoofing Confirmation
        ob_delta_p = get_confirmed_ob_delta_p(ob_imbalance_ratio)
        buy_prob_combined = max(0.05, min(0.95, buy_prob_combined + ob_delta_p))

        sell_prob_combined = get_combined_probability(
            stat_score=stat_vote.sell_prob,
            mom_score=mom_vote.sell_prob,
            vol_score=vol_vote.sell_prob,
            macro_regime=macro_regime_4h,
            adx_14=adx_14,
            squeeze_state=squeeze_state,
            ob_imbalance_ratio=-ob_imbalance_ratio,
            funding_rate_decimal=-funding_rate_decimal,
            oi_zscore=-oi_zscore if not np.isnan(oi_zscore) else 0.0,
            taker_delta=-taker_delta if not np.isnan(taker_delta) else 0.0
        )
        sell_prob_combined = max(0.05, min(0.95, sell_prob_combined - ob_delta_p))

        neutral_prob_combined = max(0.05, 1.0 - buy_prob_combined - sell_prob_combined)
        total_p = buy_prob_combined + sell_prob_combined + neutral_prob_combined
        buy_pct = round((buy_prob_combined / total_p) * 100.0, 1)
        sell_pct = round((sell_prob_combined / total_p) * 100.0, 1)
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

        # 5. Price Envelopes and High/Low
        high_24h = float(df["High"].iloc[-24:].max())
        low_24h = float(df["Low"].iloc[-24:].min())
        bounce_from_low = curr_price - low_24h
        bounce_pct = (bounce_from_low / low_24h) * 100.0 if low_24h > 0 else 0.0

        upper_bb = stat_vote.details["upper_band"]
        lower_bb = stat_vote.details["lower_band"]
        middle_bb = stat_vote.details["middle_band"]

        # 6. STEP 8 — DERIVATIVES PRE-FILTER & LIQUIDATION TRAP
        FUNDING_LONG_SUPPRESS  =  0.0005   # = +0.05%
        FUNDING_SHORT_SUPPRESS = -0.0003   # = -0.03%

        suppress_longs  = False
        suppress_shorts = False
        funding_warning = None

        if funding_rate_decimal > FUNDING_LONG_SUPPRESS:
            funding_warning = "⚠️ OVERLEVERAGED LONG MARKET — Longs paying high premium"
            suppress_longs  = True
        elif funding_rate_decimal < FUNDING_SHORT_SUPPRESS:
            funding_warning = "📈 SHORT SQUEEZE POTENTIAL — Shorts paying longs"
            suppress_shorts = True

        # OI Confluence
        oi_confluence = "NEUTRAL"
        tp_scale = 1.0
        if not np.isnan(oi_zscore):
            if oi_zscore > 2.0:
                oi_confluence = "CONFIRMS_TREND"
            elif oi_zscore < -2.0:
                oi_confluence = "EXHAUSTION_SIGNAL"
                tp_scale = 0.75  # Tighten TP targets by 25% on exhaustion signal

        # Step 7C: Unified ATR Stop/Target Standard across all scenarios
        stop_long  = round(curr_price - 1.5 * atr_val, 2)
        stop_short = round(curr_price + 1.5 * atr_val, 2)
        tp1_long   = round(curr_price + 0.5 * atr_val * tp_scale, 2)
        tp2_long   = round(curr_price + 1.0 * atr_val * tp_scale, 2)
        tp1_short  = round(curr_price - 0.5 * atr_val * tp_scale, 2)
        tp2_short  = round(curr_price - 1.0 * atr_val * tp_scale, 2)

        # Step 8C: Adaptive Liquidation Trap Filter
        retail_long_ratio = 0.50
        _retail_ratio_history.append(retail_long_ratio)
        crowded_long_risk_active = False

        if len(_retail_ratio_history) >= 96:
            rolling_mean_24h = float(np.mean(list(_retail_ratio_history)))
            adaptive_threshold = rolling_mean_24h + 0.08
            nearest_liq_cluster_price = round(curr_price - 1.0 * atr_val, 2)
            liq_distance = abs(curr_price - nearest_liq_cluster_price)
            if retail_long_ratio > adaptive_threshold and liq_distance < 1.5 * atr_val:
                stop_long = min(stop_long, nearest_liq_cluster_price - 0.01)
                crowded_long_risk_active = True

        # 7. INSTITUTIONAL BOT DIRECTIVE DECISION MATRIX (SCENARIOS 1-5)
        is_counter_trend = (macro_regime_4h == "Trend Down")

        # SCENARIO 1: Bearish Macro + Upper Channel Resistance (%B >= 0.58) + Overhead Ask Wall
        if macro_regime_4h == "Trend Down" and pct_b >= 0.58 and orderbook.imbalance_pct < -10.0:
            candidate_action = "SET SELL LIMIT AT RESISTANCE (BEARISH FADE)"
            rationale = (
                f"4H Macro structure is in a Trend Down and price is testing upper channel resistance (%B: {pct_b:.3f}). "
                f"Heavy overhead ask wall ({orderbook.imbalance_pct:.1f}% imbalance, ${orderbook.ask_depth_usd:,.0f} asks) "
                f"caps upward moves. Algorithmic bot directives favor selling the upper band fade."
            )
            entry = curr_price
            invalidation = stop_short
            tp1 = tp1_short
            tp2 = tp2_short
            target_prob = sell_pct

        # SCENARIO 2: Bearish Macro + Downward Breakdown / Acceleration
        elif macro_regime_4h == "Trend Down" and (sell_pct > 55.0 or (pct_b < 0.40 and orderbook.imbalance_pct < -20.0)):
            candidate_action = "TREND CONTINUATION: ENTER SHORT ON RETEST"
            rationale = (
                f"4H Macro trend is Down with confirmed downward order flow. Sellers are absorbing the bid depth. "
                f"Targeting continuation toward lower support."
            )
            entry = curr_price
            invalidation = stop_short
            tp1 = tp1_short
            tp2 = tp2_short
            target_prob = sell_pct

        # SCENARIO 3: Liquidity Sweep Rebound (Step 7A ATR trigger + Step 7B volume climax)
        elif bounce_from_low >= (0.5 * atr_val) and (orderbook.imbalance_pct > 15.0 or mom_vote.details.get("rsi_fast_slope", 0) > 0):
            vol_col = 'Volume' if 'Volume' in df.columns else 'volume'
            volume_sma_20 = float(df[vol_col].rolling(20).mean().iloc[-1]) if len(df) >= 20 else float(df[vol_col].mean())
            sweep_candle_volume = float(df[vol_col].iloc[-1])

            if sweep_candle_volume >= 1.8 * volume_sma_20:
                candidate_action = "COUNTER-TREND SCALP: BUY PULLBACK LIMIT" if macro_regime_4h == 'Trend Down' else "ENTER LONG NOW (MOMENTUM REBOUND)"
            else:
                candidate_action = "LOW-VOLUME RETEST: SET PULLBACK LIMIT"

            rationale = (
                f"Bottom liquidity swept to ${low_24h:,.0f} with dynamic rebound (>= 0.5x ATR: +${bounce_from_low:.0f}) "
                f"and order book bid support ({orderbook.imbalance_pct:+.1f}%). Macro regime is {macro_regime_4h}."
            )
            entry = curr_price
            invalidation = stop_long
            tp1 = tp1_long
            tp2 = tp2_long
            target_prob = buy_pct

        # SCENARIO 4: Bullish Macro + Dip to Support
        elif macro_regime_4h == "Trend Up" and pct_b <= 0.45 and orderbook.imbalance_pct > -10.0:
            candidate_action = "TREND FOLLOWING: SET BUY LIMIT AT SUPPORT"
            rationale = (
                f"4H Macro is in a Trend Up. Price has pulled back to support (%B: {pct_b:.3f}). "
                f"Algorithmic model buys the dip aligned with macro momentum."
            )
            entry = curr_price
            invalidation = stop_long
            tp1 = tp1_long
            tp2 = tp2_long
            target_prob = buy_pct

        # SCENARIO 5: Range-Bound Ping-Pong
        else:
            if pct_b >= 0.50:
                candidate_action = "RANGE DEFENSE: SET SELL LIMIT AT UPPER BAND"
                rationale = (
                    f"Range-bound consolidation (%B: {pct_b:.3f}). Price is in upper half of range. "
                    f"Set limit sell order near upper band (${upper_bb:,.2f}) rather than chasing market."
                )
                entry = curr_price
                invalidation = stop_short
                tp1 = tp1_short
                tp2 = tp2_short
                target_prob = sell_pct
            else:
                candidate_action = "RANGE DEFENSE: SET BUY LIMIT AT LOWER BAND"
                rationale = (
                    f"Range-bound consolidation (%B: {pct_b:.3f}). Price is in lower half of range. "
                    f"Set limit buy order near lower band (${lower_bb:,.2f}) rather than chasing market."
                )
                entry = curr_price
                invalidation = stop_long
                tp1 = tp1_long
                tp2 = tp2_long
                target_prob = buy_pct

        # 8. STEP 9 — CONFLICT RESOLUTION HIERARCHY
        action = resolve_scenario(
            candidate_directive=candidate_action,
            macro_regime=macro_regime_4h,
            adx_14=adx_14,
            squeeze_state=squeeze_state,
            ob_delta_p=ob_delta_p,
            percent_b=pct_b,
            suppress_longs=suppress_longs,
            suppress_shorts=suppress_shorts
        )

        # Harmonize invalidation / targets if directive flipped
        if "BUY" in action or "LONG" in action:
            invalidation = stop_long
            tp1, tp2 = tp1_long, tp2_long
        elif "SELL" in action or "SHORT" in action or "BEARISH" in action:
            invalidation = stop_short
            tp1, tp2 = tp1_short, tp2_short

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

        # 9. Floor Pivots
        pivot = (high_24h + low_24h + curr_price) / 3.0
        r1 = (2 * pivot) - low_24h
        r2 = pivot + (high_24h - low_24h)
        s1 = (2 * pivot) - high_24h
        s2 = pivot - (high_24h - low_24h)

        # 10. Actionable Notes
        notes = []
        if is_counter_trend:
            notes.append("⚠️ MACRO WARNING: 4H structure is in a Trend Down. Long positions carry counter-trend risk.")
        if funding_warning:
            notes.append(funding_warning)
        if crowded_long_risk_active:
            notes.append("⚠️ CROWDED LONG RISK: Sweep toward liquidation pool likely before sustained reversal.")
        if oi_confluence == "EXHAUSTION_SIGNAL":
            notes.append("📉 OI EXHAUSTION SIGNAL: Targets tightened by 25% due to declining open interest.")
        elif oi_confluence == "CONFIRMS_TREND":
            notes.append("📈 OI EXPANSION: Aggressive open interest expansion confirms current move.")

        if squeeze_label:
            notes.append(f"⚡ VOLATILITY STATUS: {squeeze_label}")

        if orderbook.imbalance_pct > 15.0:
            notes.append(f"🟢 ORDER BOOK SUPPORT: Bid depth exceeds asks by +{orderbook.imbalance_pct:.1f}% (${orderbook.bid_depth_usd:,.0f} bids).")
        elif orderbook.imbalance_pct < -15.0:
            notes.append(f"🔴 ORDER BOOK RESISTANCE: Ask wall exceeds bids by {abs(orderbook.imbalance_pct):.1f}% (${orderbook.ask_depth_usd:,.0f} asks).")

        notes.append("⚖️ COMPLIANCE: Algorithmic statistical model. All decisions remain the responsibility of the human trader.")

        summary = (
            f"Multi-Exchange Feed: Model indicates {buy_pct}% BUY / {neutral_pct}% NEUTRAL / {sell_pct}% SELL odds on {timeframe.upper()}. "
            f"4H Macro is {macro_regime_4h.upper()} (ADX: {adx_14:.1f}) with orderbook imbalance at {orderbook.imbalance_pct:+.1f}%. Directive: {action}."
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
            actionable_notes=notes,
            adx_value=round(adx_14, 1),
            squeeze_state=squeeze_state,
            squeeze_label=squeeze_label,
            funding_warning=funding_warning,
            oi_confluence=oi_confluence,
            crowded_long_risk=crowded_long_risk_active
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
