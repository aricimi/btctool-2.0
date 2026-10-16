"""
btctool 2.0 - Quantitative Predictive Advisory & Execution Directive Dashboard
Data Source: Direct Binance Real-Time Spot & Futures Engine
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import time

from engine import (
    MarketDataService,
    PredictiveEnsembleEngine,
    AdvisoryReport
)

# Page configuration
st.set_page_config(
    page_title="btctool 2.0 | Binance Real-Time Predictive Advisory",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom High-Tech Styling & Persistent Legal Banners
st.markdown("""
<style>
    /* Metric Card Styling */
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700;
        color: #00FFA3;
    }
    
    /* Custom container */
    .directive-card {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        border: 1px solid #38BDF8;
        border-left: 6px solid #38BDF8;
        border-radius: 10px;
        padding: 18px 22px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45);
    }
    
    .advisory-box {
        background: linear-gradient(135deg, #131b2e 0%, #1e293b 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    
    .badge-buy {
        background-color: rgba(0, 255, 163, 0.15);
        color: #00FFA3;
        border: 1px solid #00FFA3;
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.9rem;
    }
    
    .badge-sell {
        background-color: rgba(255, 75, 75, 0.15);
        color: #FF4B4B;
        border: 1px solid #FF4B4B;
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.9rem;
    }
    
    .badge-neutral {
        background-color: rgba(245, 158, 11, 0.15);
        color: #F59E0B;
        border: 1px solid #F59E0B;
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.9rem;
    }

    .badge-directive {
        background-color: rgba(56, 189, 248, 0.18);
        color: #38BDF8;
        border: 1px solid #38BDF8;
        padding: 6px 14px;
        border-radius: 6px;
        font-weight: 800;
        font-size: 1.05rem;
        letter-spacing: 0.03em;
    }

    /* Top Persistent Disclaimer Banner */
    .top-disclaimer-pill {
        background: rgba(245, 158, 11, 0.10);
        border: 1px solid rgba(245, 158, 11, 0.35);
        color: #FCD34D;
        border-radius: 6px;
        padding: 8px 14px;
        font-size: 0.84rem;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 16px;
    }

    /* Bottom Comprehensive Legal Disclaimer Box */
    .disclaimer-box {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.9) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid rgba(245, 158, 11, 0.4);
        border-left: 5px solid #F59E0B;
        border-radius: 8px;
        padding: 16px 20px;
        margin: 25px 0 20px 0;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.35);
    }
    
    .disclaimer-title {
        color: #F59E0B;
        font-weight: 700;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .disclaimer-body {
        color: #CBD5E1;
        font-size: 0.82rem;
        line-height: 1.55;
        margin: 0;
    }

    .disclaimer-sidebar {
        background: rgba(245, 158, 11, 0.08);
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 6px;
        padding: 10px;
        font-size: 0.78rem;
        color: #CBD5E1;
        line-height: 1.4;
        margin-top: 15px;
    }
</style>
""", unsafe_allow_html=True)


# Sidebar controls
st.sidebar.image("https://cryptologos.cc/logos/bitcoin-btc-logo.png", width=60)
st.sidebar.title("btctool 2.0")
st.sidebar.caption("Binance Real-Time Quantitative Engine")
st.sidebar.markdown("---")

selected_pair = st.sidebar.selectbox("Trading Pair", ["BTCUSDT"], index=0)
active_timeframe = st.sidebar.selectbox("Active Timeframe", ["15m", "1h", "4h", "1d"], index=1)

auto_refresh = st.sidebar.checkbox("Auto-Refresh Data", value=True)
refresh_interval = st.sidebar.slider("Refresh Interval (s)", 15, 120, 30, disabled=not auto_refresh)

if st.sidebar.button("🔄 Refresh Binance Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 🧠 Engine Capabilities
- **Feed:** Direct Binance Spot & Futures API.
- **Order Book:** 0.5% Depth & Bid/Ask Imbalance.
- **Macro Confluence:** 4H Trend alignment filter.
- **Triple RSI:** Dynamic periods `(6, 12, 24)`.
- **Anti-Contradiction:** Calibrated probabilities.
""")

# Persistent Sidebar Legal Notice
st.sidebar.markdown("""
<div class="disclaimer-sidebar">
    <b>⚖️ Legal Notice:</b><br>
    This software is strictly for educational & quantitative research purposes. It is <b>NOT</b> financial, investment, or trading advice.
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.caption("🚀 Architecture: Python / Streamlit / Binance REST")


# Load Live Data
@st.cache_data(ttl=20)
def load_market_data(symbol: str, timeframe: str):
    report = PredictiveEnsembleEngine.generate_advisory(symbol=symbol, timeframe=timeframe)
    df = MarketDataService.fetch_klines(symbol=symbol, interval=timeframe, limit=120)
    return report, df


with st.spinner("Connecting to Binance WebSocket & orderbook feed..."):
    try:
        current_report, current_df = load_market_data(selected_pair, active_timeframe)
    except Exception as e:
        st.error(f"Error connecting to Binance data feed: {str(e)}")
        st.stop()


# Top Header
col_title, col_time = st.columns([3, 1])
with col_title:
    st.title("⚡ btctool 2.0: Binance Real-Time Engine")
    st.caption(f"Real-Time Order Book, Liquidity Sweeps & Calibrated Probabilities on **{active_timeframe.upper()}**")
with col_time:
    st.markdown(f"**Last Sync:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}`")
    st.markdown(f"**Active Bar:** `{current_report.timestamp}`")

# Top Persistent Disclaimer Pill
st.markdown("""
<div class="top-disclaimer-pill">
    <span>⚠️</span>
    <span><b>EDUCATIONAL & RESEARCH USE ONLY — NOT FINANCIAL ADVICE (NFA):</b> All outputs represent automated statistical probabilities. No automated trade execution. You assume full responsibility for your capital and trading decisions.</span>
</div>
""", unsafe_allow_html=True)

st.markdown("---")


# Key Performance Metrics Ribbon
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric(
        "Binance Spot Price",
        f"${current_report.latest_price:,.2f}",
        delta=f"{current_report.price_change_24h_pct:+.2f}% 24h"
    )
with m2:
    bias_color = "🟢" if "BUY" in current_report.overall_bias else ("🔴" if "SELL" in current_report.overall_bias else "🟡")
    st.metric("Directional Bias", f"{bias_color} {current_report.overall_bias.replace('_', ' ')}")
with m3:
    st.metric("Buy Probability", f"{current_report.buy_probability}%")
with m4:
    st.metric("Sell Probability", f"{current_report.sell_probability}%")
with m5:
    st.metric("4H Macro Regime", current_report.macro_regime_4h)


# ORDER BOOK & DERIVATIVES MICROSTRUCTURE RIBBON
st.markdown("### 📊 Order Book Liquidity & Derivatives (Binance)")
d1, d2, d3, d4 = st.columns(4)
ob = current_report.orderbook
with d1:
    imb_color = "🟢" if ob.imbalance_pct > 0 else "🔴"
    st.metric("Order Book Imbalance (0.5%)", f"{imb_color} {ob.imbalance_pct:+.1f}%")
with d2:
    st.metric("Near-Mid Bid Depth", f"${ob.bid_depth_usd:,.0f}")
with d3:
    st.metric("Near-Mid Ask Depth", f"${ob.ask_depth_usd:,.0f}")
with d4:
    st.metric("Futures Open Interest", f"{ob.open_interest_btc:,.0f} BTC", delta=f"Funding: {ob.funding_rate_pct:+.4f}%")


# ACTIONABLE TRADE DIRECTIVE CARD
st.markdown("### 🎯 Trade Execution Directive")
td = current_report.trade_directive

st.markdown(f"""
<div class="directive-card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <span class="badge-directive">{td.action}</span>
        <span style="font-size: 0.95rem; color: #94A3B8;">
            Calibrated Model Odds: <b style="color: #00FFA3;">{td.target_probability}%</b> | Risk: <b style="color: #F87171;">{td.risk_pct}%</b>
        </span>
    </div>
    <p style="font-size: 1.05rem; color: #E2E8F0; line-height: 1.6; margin-bottom: 14px;">
        <b>Strategy Rationale:</b> {td.rationale}
    </p>
    <div style="display: flex; gap: 20px; flex-wrap: wrap; background: rgba(0,0,0,0.3); padding: 12px 16px; border-radius: 8px;">
        <div><b>Entry Trigger:</b> ${td.entry_trigger:,.2f}</div>
        <div><b>Invalidation (Stop):</b> <span style="color: #F87171;">${td.invalidation_stop:,.2f}</span></div>
        <div><b>Target 1 (Scalp):</b> <span style="color: #00FFA3;">${td.take_profit_1:,.2f}</span></div>
        <div><b>Target 2 (Runner):</b> <span style="color: #00FFA3;">${td.take_profit_2:,.2f}</span></div>
        <div><b>Counter-Trend Flag:</b> {"⚠️ YES (4H Bearish)" if td.is_counter_trend else "🟢 NO (Trend Aligned)"}</div>
    </div>
</div>
""", unsafe_allow_html=True)


# Probability Breakdown & Tactical Observations
col_chart, col_notes = st.columns([1, 1])

with col_chart:
    st.subheader(f"📊 Probability Distribution ({active_timeframe.upper()})")
    labels = ['Buy Probability', 'Neutral Probability', 'Sell Probability']
    values = [current_report.buy_probability, current_report.neutral_probability, current_report.sell_probability]
    colors = ['#00FFA3', '#F59E0B', '#FF4B4B']

    fig_donut = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=.55,
        marker=dict(colors=colors, line=dict(color='#0A0E17', width=2)),
        textinfo='label+percent',
        hoverinfo='label+value+percent'
    )])
    fig_donut.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=260,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#E2E8F0')
    )
    st.plotly_chart(fig_donut, use_container_width=True)

with col_notes:
    st.subheader("💡 Tactical Quantitative Observations")
    for note in current_report.actionable_notes:
        st.write(note)
    st.markdown(f"""
    - **Floor Pivot Point:** `${current_report.pivot_point:,.2f}`
    - **Support ($S_1$ / $S_2$):** `${current_report.support_levels['S1']:,.2f}` / `${current_report.support_levels['S2']:,.2f}`
    - **Resistance ($R_1$ / $R_2$):** `${current_report.resistance_levels['R1']:,.2f}` / `${current_report.resistance_levels['R2']:,.2f}`
    - **Expected Move (ATR):** `±${current_report.atr_value:,.2f}` (`{current_report.atr_percent:.2f}%`)
    """)


# Interactive Plotly Chart with Dual EMA and Triple RSI
st.markdown("---")
st.subheader(f"📈 Quantitative Chart & Structural Envelopes ({active_timeframe.upper()})")

df_plot = current_df.copy()
sma20 = df_plot["Close"].rolling(20).mean()
std20 = df_plot["Close"].rolling(20).std()
df_plot["BB_Upper"] = sma20 + (2.0 * std20)
df_plot["BB_Lower"] = sma20 - (2.0 * std20)
df_plot["EMA9"] = df_plot["Close"].ewm(span=9, adjust=False).mean()
df_plot["EMA21"] = df_plot["Close"].ewm(span=21, adjust=False).mean()

fig = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.04,
    row_heights=[0.60, 0.20, 0.20],
    specs=[[{"secondary_y": True}], [{"secondary_y": False}], [{"secondary_y": False}]]
)

# 1. Candlestick
fig.add_trace(
    go.Candlestick(
        x=df_plot.index,
        open=df_plot['Open'],
        high=df_plot['High'],
        low=df_plot['Low'],
        close=df_plot['Close'],
        name='BTC/USDT',
        increasing_line_color='#00FFA3',
        decreasing_line_color='#FF4B4B'
    ),
    row=1, col=1, secondary_y=False
)

# Bollinger & EMAs
fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Upper'], line=dict(color='rgba(0, 255, 163, 0.35)', width=1), name='Upper BB'), row=1, col=1)
fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['BB_Lower'], line=dict(color='rgba(255, 75, 75, 0.35)', width=1), name='Lower BB'), row=1, col=1)
fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA9'], line=dict(color='#38BDF8', width=1.2), name='EMA 9'), row=1, col=1)
fig.add_trace(go.Scatter(x=df_plot.index, y=df_plot['EMA21'], line=dict(color='#F59E0B', width=1.2, dash='dot'), name='EMA 21'), row=1, col=1)

# Volume
fig.add_trace(
    go.Bar(x=df_plot.index, y=df_plot['Volume'], marker_color='rgba(148, 163, 184, 0.2)', name='Volume', showlegend=False),
    row=1, col=1, secondary_y=True
)

# 2. Triple RSI (6, 12, 24)
delta = df_plot['Close'].diff()
gain = delta.clip(lower=0)
loss = -1 * delta.clip(upper=0)

def calc_rsi(g, l, p):
    ag = g.ewm(alpha=1/p, adjust=False).mean()
    al = l.ewm(alpha=1/p, adjust=False).mean()
    rs = ag / al.replace(0, 1e-6)
    return 100 - (100 / (1 + rs))

rsi6 = calc_rsi(gain, loss, 6)
rsi12 = calc_rsi(gain, loss, 12)
rsi24 = calc_rsi(gain, loss, 24)

fig.add_trace(go.Scatter(x=df_plot.index, y=rsi6, line=dict(color='#00FFA3', width=1.5), name='RSI 6'), row=2, col=1)
fig.add_trace(go.Scatter(x=df_plot.index, y=rsi12, line=dict(color='#38BDF8', width=1.2), name='RSI 12'), row=2, col=1)
fig.add_trace(go.Scatter(x=df_plot.index, y=rsi24, line=dict(color='#94A3B8', width=1, dash='dot'), name='RSI 24'), row=2, col=1)
fig.add_hline(y=70, line_dash="dot", line_color="rgba(255, 75, 75, 0.5)", row=2, col=1)
fig.add_hline(y=30, line_dash="dot", line_color="rgba(0, 255, 163, 0.5)", row=2, col=1)

# 3. MACD Subplot
ema12 = df_plot['Close'].ewm(span=12, adjust=False).mean()
ema26 = df_plot['Close'].ewm(span=26, adjust=False).mean()
macd = ema12 - ema26
signal = macd.ewm(span=9, adjust=False).mean()
hist = macd - signal

fig.add_trace(go.Scatter(x=df_plot.index, y=macd, line=dict(color='#818CF8', width=1.2), name='MACD'), row=3, col=1)
fig.add_trace(go.Scatter(x=df_plot.index, y=signal, line=dict(color='#F43F5E', width=1.2), name='Signal'), row=3, col=1)
fig.add_trace(
    go.Bar(x=df_plot.index, y=hist, marker_color=np.where(hist >= 0, 'rgba(0, 255, 163, 0.7)', 'rgba(255, 75, 75, 0.7)'), name='Histogram', showlegend=False),
    row=3, col=1
)

fig.update_layout(
    height=650,
    margin=dict(t=20, b=20, l=10, r=10),
    paper_bgcolor='#0A0E17',
    plot_bgcolor='#0A0E17',
    xaxis_rangeslider_visible=False,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    font=dict(color='#94A3B8')
)
fig.update_yaxes(gridcolor='#1E293B', secondary_y=False)
fig.update_yaxes(showgrid=False, secondary_y=True)
fig.update_xaxes(gridcolor='#1E293B')

st.plotly_chart(fig, use_container_width=True)


# Brain Diagnostics Explorer
st.markdown("---")
st.subheader("🔬 Quantitative Brain Diagnostics")
tab_stat, tab_mom, tab_vol = st.tabs(["📐 The Statistical Brain", "⚡ The Momentum Brain", "🌋 The Volatility Brain"])

with tab_stat:
    sb = current_report.statistical_brain
    st.markdown(f"**Brain Verdict:** `{sb.signal}` | **Confidence:** `{int(sb.confidence * 100)}%`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sub-Vote Buy", f"{sb.buy_prob * 100:.1f}%")
    c2.metric("Sub-Vote Neutral", f"{sb.neutral_prob * 100:.1f}%")
    c3.metric("Sub-Vote Sell", f"{sb.sell_prob * 100:.1f}%")
    c4.metric("Percent %B", f"{sb.details['percent_b']:.3f}")
    st.markdown(f"""
    - **Bollinger Upper Band:** `${sb.details['upper_band']:,.2f}`
    - **Bollinger Middle Band (SMA20):** `${sb.details['middle_band']:,.2f}`
    - **Bollinger Lower Band:** `${sb.details['lower_band']:,.2f}`
    - **Bandwidth:** `{sb.details['bandwidth']:.4f}` (Historical Percentile: `{sb.details['bandwidth_percentile']}%`)
    - **Price Z-Score:** `{sb.details['z_score']}` standard deviations from mean
    """)

with tab_mom:
    mb = current_report.momentum_brain
    st.markdown(f"**Brain Verdict:** `{mb.signal}` | **Confidence:** `{int(mb.confidence * 100)}%`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sub-Vote Buy", f"{mb.buy_prob * 100:.1f}%")
    c2.metric("Sub-Vote Neutral", f"{mb.neutral_prob * 100:.1f}%")
    c3.metric("Sub-Vote Sell", f"{mb.sell_prob * 100:.1f}%")
    c4.metric("Fast RSI (6)", f"{mb.details['rsi_fast']}")
    st.markdown(f"""
    - **Triple RSI Breakdown:** `6: {mb.details['rsi_fast']}` | `12: {mb.details['rsi_mid']}` | `24: {mb.details['rsi_slow']}`
    - **RSI Fast Slope:** `{mb.details['rsi_fast_slope']:+.2f}` pts
    - **Dual EMAs:** `EMA 9: ${mb.details['ema9']:,.2f}` | `EMA 21: ${mb.details['ema21']:,.2f}`
    - **MACD (12, 26, 9):** Line `{mb.details['macd']:,.2f}`, Signal `{mb.details['macd_signal']:,.2f}`, Hist `{mb.details['macd_hist']:,.2f}` (Acceleration: `{mb.details['hist_acceleration']:+.2f}`)
    """)

with tab_vol:
    vb = current_report.volatility_brain
    st.markdown(f"**Brain Verdict:** `{vb.signal}` | **Breakout Imminent:** `{vb.details['breakout_imminent']}`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sub-Vote Buy", f"{vb.buy_prob * 100:.1f}%")
    c2.metric("Sub-Vote Neutral", f"{vb.neutral_prob * 100:.1f}%")
    c3.metric("Sub-Vote Sell", f"{vb.sell_prob * 100:.1f}%")
    c4.metric("ATR% of Price", f"{vb.details['atr_pct']:.2f}%")
    st.markdown(f"""
    - **Average True Range (ATR 14):** `${vb.details['atr']:,.2f}`
    - **ATR Historical Percentile:** `{vb.details['atr_percentile']}%`
    - **Bollinger Squeeze inside Keltner:** `{"ACTIVE (Coiled)" if vb.details['is_squeeze'] else "INACTIVE"}`
    - **Warning Classification:** `{vb.details['warning_level']}`
    """)

# Comprehensive Persistent Legal Disclaimer Box
st.markdown("""
<div class="disclaimer-box">
    <div class="disclaimer-title">
        <span>⚖️</span>
        <span>IMPORTANT LEGAL DISCLAIMER & TERMS OF USE — NOT FINANCIAL ADVICE</span>
    </div>
    <p class="disclaimer-body">
        <b>btctool 2.0</b> is provided strictly for educational, informational, and quantitative research purposes only. 
        None of the data, probabilistic calculations, indicator outputs, scores, pivot levels, or commentary provided by this application 
        constitutes financial, investment, legal, tax, or trading advice. 
        <br><br>
        Cryptocurrency assets and digital asset markets exhibit extreme volatility and carry a substantial risk of total financial loss. 
        Past statistical performance, mathematical models, or historical distributions do not guarantee or predict future market results. 
        This application does not provide order execution or custodial services; all trading decisions and actions are executed solely at the user's independent discretion and risk. 
        Under no circumstances shall the creators, authors, developers, or contributors of this software be held liable for any direct, indirect, incidental, or consequential losses, damages, or claims arising from the use of or reliance upon this software.
    </p>
</div>
""", unsafe_allow_html=True)

st.caption("btctool 2.0 | Binance Real-Time Quantitative Engine | Open Source under MIT License.")

# Auto-refresh loop handler
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
