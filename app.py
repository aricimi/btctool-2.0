"""
btctool 2.0 - Quantitative Trading Probability & Predictive Advisory Dashboard
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import time

from engine import (
    QuantitativeDataEngine,
    PredictiveEnsembleEngine,
    AdvisoryReport
)

# Page configuration
st.set_page_config(
    page_title="btctool 2.0 | BTC/USDT Predictive Advisory Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom High-Tech Styling
st.markdown("""
<style>
    /* Metric Card Styling */
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700;
        color: #00FFA3;
    }
    
    /* Custom advisory container */
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

    .badge-squeeze {
        background-color: rgba(239, 68, 68, 0.2);
        color: #F87171;
        border: 1px dashed #EF4444;
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: bold;
        animation: pulse 2s infinite;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: #131B2E;
        border-radius: 6px 6px 0 0;
        padding: 10px 20px;
        color: #94A3B8;
    }

    .stTabs [aria-selected="true"] {
        background-color: #1E293B !important;
        color: #00FFA3 !important;
        border-bottom: 2px solid #00FFA3 !important;
    }
</style>
""", unsafe_allow_html=True)


# Sidebar controls
st.sidebar.image("https://cryptologos.cc/logos/bitcoin-btc-logo.png", width=60)
st.sidebar.title("btctool 2.0")
st.sidebar.caption("Advanced Predictive Advisory Engine")
st.sidebar.markdown("---")

selected_pair = st.sidebar.selectbox("Trading Pair", ["BTC-USD"], index=0)
active_timeframe = st.sidebar.radio("Active Timeframe", ["1h", "4h"], index=0, horizontal=True)

auto_refresh = st.sidebar.checkbox("Auto-Refresh Data", value=False)
refresh_interval = st.sidebar.slider("Refresh Interval (s)", 30, 300, 60, disabled=not auto_refresh)

if st.sidebar.button("🔄 Refresh Market Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 🧠 Analytical Brains
- **Statistical Brain**: Bollinger Bands, %B, Z-score mean-reversion.
- **Momentum Brain**: RSI exhaustion & MACD acceleration.
- **Volatility Brain**: ATR compression & Squeeze Breakout alert.
""")

st.sidebar.markdown("---")
st.sidebar.caption("🚀 Architecture: Python / Streamlit / yfinance")


# Fetching Engine Data
@st.cache_data(ttl=60)
def load_advisory_data(symbol: str, timeframe: str):
    report = PredictiveEnsembleEngine.generate_advisory(symbol=symbol, timeframe=timeframe)
    df = QuantitativeDataEngine.fetch_data(symbol=symbol, interval=timeframe)
    return report, df


with st.spinner("Analyzing real-time order flow and volatility distributions..."):
    try:
        report_1h, df_1h = load_advisory_data(selected_pair, "1h")
        report_4h, df_4h = load_advisory_data(selected_pair, "4h")
        
        current_report = report_1h if active_timeframe == "1h" else report_4h
        current_df = df_1h if active_timeframe == "1h" else df_4h
    except Exception as e:
        st.error(f"Error connecting to market data feed: {str(e)}")
        st.stop()


# Top Header
col_title, col_time = st.columns([3, 1])
with col_title:
    st.title("⚡ btctool 2.0: Predictive Advisory Engine")
    st.caption("Multi-Methodology Quantitative Probabilities for BTC/USDT")
with col_time:
    st.markdown(f"**Last Sync:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}`")
    st.markdown(f"**Active Bar:** `{current_report.timestamp}`")

st.markdown("---")


# Key Performance Metrics Ribbon
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric(
        "BTC/USDT Spot Price",
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
    vol_status = "⚠️ SQUEEZE ACTIVE" if current_report.breakout_imminent else "STABLE"
    st.metric("Volatility Regime", vol_status, delta=f"ATR: ${current_report.atr_value:,.1f}")


# TRADER ADVISORY REPORT CARD
st.markdown("### 📋 Trader Advisory Report")

advisory_class = "badge-buy" if "BUY" in current_report.overall_bias else ("badge-sell" if "SELL" in current_report.overall_bias else "badge-neutral")

st.markdown(f"""
<div class="advisory-box">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <span style="font-size: 1.25rem; font-weight: 700; color: #FFFFFF;">
            Advisory Verdict: <span class="{advisory_class}">{current_report.overall_bias.replace('_', ' ')}</span>
        </span>
        <span style="font-size: 0.95rem; color: #94A3B8;">
            Model Confidence: <b style="color: #00FFA3;">{current_report.confidence_score}%</b> | Timeframe: <b>{current_report.timeframe.upper()}</b>
        </span>
    </div>
    <p style="font-size: 1.05rem; color: #E2E8F0; line-height: 1.6; margin-bottom: 15px;">
        {current_report.advisory_summary}
    </p>
    <div style="display: flex; gap: 20px; flex-wrap: wrap; background: rgba(0,0,0,0.25); padding: 12px; border-radius: 8px;">
        <div><b>Pivot Point:</b> ${current_report.pivot_point:,.2f}</div>
        <div><b>Support (S1 / S2):</b> ${current_report.support_levels['S1']:,.2f} / ${current_report.support_levels['S2']:,.2f}</div>
        <div><b>Resistance (R1 / R2):</b> ${current_report.resistance_levels['R1']:,.2f} / ${current_report.resistance_levels['R2']:,.2f}</div>
        <div><b>ATR Volatility:</b> {current_report.atr_percent:.2f}% (${current_report.atr_value:,.2f})</div>
    </div>
</div>
""", unsafe_allow_html=True)


# Probability Breakdown & Timeframe Ensemble Comparison
col_chart, col_matrix = st.columns([1, 1])

with col_chart:
    st.subheader(f"📊 Probability Breakdown ({active_timeframe.upper()})")
    
    # Donut gauge chart for probability distribution
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

with col_matrix:
    st.subheader("🌐 Multi-Timeframe Matrix (1H vs 4H)")
    
    matrix_df = pd.DataFrame([
        {
            "Timeframe": "1-Hour (Tactical)",
            "Buy %": f"{report_1h.buy_probability}%",
            "Neutral %": f"{report_1h.neutral_probability}%",
            "Sell %": f"{report_1h.sell_probability}%",
            "Bias": report_1h.overall_bias.replace('_', ' '),
            "Breakout Risk": "🚨 IMMINENT" if report_1h.breakout_imminent else "Normal"
        },
        {
            "Timeframe": "4-Hour (Structural)",
            "Buy %": f"{report_4h.buy_probability}%",
            "Neutral %": f"{report_4h.neutral_probability}%",
            "Sell %": f"{report_4h.sell_probability}%",
            "Bias": report_4h.overall_bias.replace('_', ' '),
            "Breakout Risk": "🚨 IMMINENT" if report_4h.breakout_imminent else "Normal"
        }
    ])
    st.dataframe(matrix_df, hide_index=True, use_container_width=True)

    # Actionable Notes
    st.markdown("**Tactical Observations:**")
    for note in current_report.actionable_notes:
        st.write(note)


# Interactive Quantitative Technical Chart
st.markdown("---")
st.subheader(f"📈 Quantitative Chart & Structural Envelopes ({active_timeframe.upper()})")

# Calculate Bollinger Bands and MACD for chart plotting
df_plot = current_df.copy()
sma20 = df_plot["Close"].rolling(20).mean()
std20 = df_plot["Close"].rolling(20).std()
df_plot["BB_Upper"] = sma20 + (2.0 * std20)
df_plot["BB_Lower"] = sma20 - (2.0 * std20)
df_plot["SMA20"] = sma20

# Create Plotly Subplots: Candlestick + Volume + RSI + MACD
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

# Bollinger Bands
fig.add_trace(
    go.Scatter(x=df_plot.index, y=df_plot['BB_Upper'], line=dict(color='rgba(0, 255, 163, 0.4)', width=1), name='Upper BB'),
    row=1, col=1, secondary_y=False
)
fig.add_trace(
    go.Scatter(x=df_plot.index, y=df_plot['SMA20'], line=dict(color='rgba(255, 255, 255, 0.5)', width=1, dash='dash'), name='SMA 20'),
    row=1, col=1, secondary_y=False
)
fig.add_trace(
    go.Scatter(x=df_plot.index, y=df_plot['BB_Lower'], line=dict(color='rgba(255, 75, 75, 0.4)', width=1), name='Lower BB'),
    row=1, col=1, secondary_y=False
)

# Volume Bars
fig.add_trace(
    go.Bar(
        x=df_plot.index,
        y=df_plot['Volume'],
        marker_color='rgba(148, 163, 184, 0.2)',
        name='Volume',
        showlegend=False
    ),
    row=1, col=1, secondary_y=True
)

# 2. RSI Subplot
delta = df_plot['Close'].diff()
gain = delta.clip(lower=0)
loss = -1 * delta.clip(upper=0)
avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, 1e-6)
rsi = 100 - (100 / (1 + rs))

fig.add_trace(
    go.Scatter(x=df_plot.index, y=rsi, line=dict(color='#38BDF8', width=1.5), name='RSI (14)'),
    row=2, col=1
)
# RSI Overbought/Oversold thresholds
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
    go.Bar(
        x=df_plot.index,
        y=hist,
        marker_color=np.where(hist >= 0, 'rgba(0, 255, 163, 0.7)', 'rgba(255, 75, 75, 0.7)'),
        name='Histogram',
        showlegend=False
    ),
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


# Brain Diagnostics & Methodology Explorer
st.markdown("---")
st.subheader("🔬 Quantitative Brain Diagnostics")

tab_stat, tab_mom, tab_vol = st.tabs([
    "📐 The Statistical Brain",
    "⚡ The Momentum Brain",
    "🌋 The Volatility Brain"
])

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
    c4.metric("RSI (14)", f"{mb.details['rsi']:.1f}")
    
    st.markdown(f"""
    - **RSI Slope:** `{mb.details['rsi_slope']:+.2f}` pts
    - **MACD Value:** `{mb.details['macd']:,.2f}`
    - **MACD Signal:** `{mb.details['macd_signal']:,.2f}`
    - **MACD Histogram:** `{mb.details['macd_hist']:,.2f}` (Acceleration: `{mb.details['hist_acceleration']:+.2f}`)
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

st.markdown("---")
st.caption("btctool 2.0 | Built with Python, Streamlit, and quantitative statistical models.")

# Auto-refresh loop handler
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
