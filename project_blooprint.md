# 🏛️ btctool 2.0 — System Architecture & Project Blueprint
**Document:** `project_blooprint.md`  
**Version:** 2.0.0-PROD  
**System:** Institutional Quantitative Predictive Advisory Engine for BTC/USDT  
**Core Target:** Multi-methodology probability modeling & risk advisory without automated order execution  

---

## 1. Executive Summary & Philosophy

**btctool 2.0** is an institutional-grade algorithmic advisory framework designed specifically for Bitcoin (BTC/USDT). Traditional trading bots focus on automated order execution, which often leads to devastating drawdowns during regime shifts and black-swan events. 

In contrast, **btctool 2.0** adheres to the **"Human-in-the-Loop Quantitative Advisory"** paradigm:
1. **Mathematical Probability Distributions:** It transforms raw market ticks into statistically backed directional odds (e.g., *65% Buy / 20% Neutral / 15% Sell*).
2. **Tri-Brain Consensus:** It decouples market dynamics into three distinct behavioral axes: **Statistical Mean-Reversion**, **Momentum Velocity**, and **Volatility Compression**.
3. **Actionable Advisory Reporting:** It outputs structured institutional reports featuring key support/resistance pivots, compression alerts, and scenario playbooks, leaving the final execution choice to the human risk manager.

---

## 2. High-Level System Architecture

```
                                  ┌──────────────────────────────┐
                                  │   Real-Time Market Ingestion │
                                  │   yfinance (BTC-USD / 1h/4h) │
                                  └──────────────┬───────────────┘
                                                 │
                   ┌─────────────────────────────┼─────────────────────────────┐
                   │                             │                             │
                   ▼                             ▼                             ▼
        ┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
        │  Statistical Brain  │       │   Momentum Brain    │       │  Volatility Brain   │
        ├─────────────────────┤       ├─────────────────────┤       ├─────────────────────┤
        │ • Bollinger Bands   │       │ • RSI (14) Slope    │       │ • ATR 14 & ATR %    │
        │ • Bandwidth & %B    │       │ • MACD (12,26,9)    │       │ • BB inside Keltner │
        │ • Z-Score Gaussian  │       │ • Acceleration Delta│       │ • Coiling Squeeze   │
        └──────────┬──────────┘       └──────────┬──────────┘       └──────────┬──────────┘
                   │                             │                             │
                   └──────────────────────┬──────┴─────────────────────────────┘
                                          │
                                          ▼
                         ┌─────────────────────────────────┐
                         │    Dynamic Ensemble Engine      │
                         │  • Contextual Weight Allocation │
                         │  • Probability Normalization    │
                         │  • Confidence Scoring           │
                         └────────────────┬────────────────┘
                                          │
                                          ▼
                         ┌─────────────────────────────────┐
                         │     Trader Advisory Report      │
                         │  • Directional Bias & Odds      │
                         │  • Tactical Pivot Points        │
                         │  • Imminent Breakout Warnings   │
                         └────────────────┬────────────────┘
                                          │
                         ┌────────────────┴────────────────┐
                         ▼                                 ▼
             ┌───────────────────────┐         ┌───────────────────────┐
             │ Interactive Dashboard │         │ Multi-Cloud Hosting   │
             │ (Streamlit + Plotly)  │         │ (Render / Cloudflare) │
             └───────────────────────┘         └───────────────────────┘
```

---

## 3. Deep Dive: The Tri-Brain Methodology

### 3.1. The Statistical Brain (`StatisticalBrain`)
* **Objective:** Determine if price is trading at statistical extremes and calculate mean-reversion probabilities.
* **Core Indicators:**
  - **Bollinger Bands ($N=20, K=2$):**
    $$\text{SMA}_{20} = \frac{1}{20}\sum_{i=0}^{19} P_{t-i}$$
    $$\sigma_{20} = \sqrt{\frac{1}{20}\sum_{i=0}^{19} (P_{t-i} - \text{SMA}_{20})^2}$$
    $$\text{Upper} = \text{SMA}_{20} + 2\sigma_{20}, \quad \text{Lower} = \text{SMA}_{20} - 2\sigma_{20}$$
  - **Percent %B:**
    $$\%B = \frac{\text{Price} - \text{Lower}}{\text{Upper} - \text{Lower}}$$
  - **Price Z-Score:**
    $$Z = \frac{\text{Price} - \text{SMA}_{20}}{\sigma_{20}}$$
* **Voting Logic:**
  - When $\%B \le 0.15$ (deep oversold channel): Signals high-probability statistical mean-reversion upward.
  - When $\%B \ge 0.85$ (deep overbought channel): Signals mean-reversion pullbacks.
  - Within $0.15 < \%B < 0.85$: Evaluates channel positioning relative to $\text{SMA}_{20}$.

---

### 3.2. The Momentum Brain (`MomentumBrain`)
* **Objective:** Track trend acceleration, exhaustion, and directional momentum velocity.
* **Core Indicators:**
  - **Relative Strength Index (RSI 14):**
    $$RS = \frac{\text{EMA}(\text{Gain}, 14)}{\text{EMA}(\text{Loss}, 14)}, \quad \text{RSI} = 100 - \frac{100}{1 + RS}$$
    Calculates 1-period momentum slope: $\Delta \text{RSI} = \text{RSI}_t - \text{RSI}_{t-1}$.
  - **Moving Average Convergence Divergence (MACD 12, 26, 9):**
    $$\text{MACD Line} = \text{EMA}_{12}(\text{Price}) - \text{EMA}_{26}(\text{Price})$$
    $$\text{Signal Line} = \text{EMA}_9(\text{MACD Line})$$
    $$\text{Histogram} = \text{MACD Line} - \text{Signal Line}$$
    $$\text{Acceleration} = \text{Histogram}_t - \text{Histogram}_{t-1}$$
* **Voting Logic:**
  - Combines RSI exhaustion boundaries (<30 oversold, >70 overbought) with MACD histogram derivatives.
  - Detects "hidden momentum" when the histogram is accelerating even before price breaks key levels.

---

### 3.3. The Volatility Brain (`VolatilityBrain`)
* **Objective:** Measure structural compression and warn against imminent explosive volatility expansion.
* **Core Indicators:**
  - **Average True Range (ATR 14):**
    $$\text{TR} = \max\left(H - L, |H - C_{t-1}|, |L - C_{t-1}|\right)$$
    $$\text{ATR} = \frac{1}{14}\sum_{i=0}^{13} \text{TR}_{t-i}, \quad \text{ATR}\% = \left(\frac{\text{ATR}}{\text{Close}}\right) \times 100$$
  - **Bollinger Squeeze inside Keltner Channels:**
    $$\text{Keltner Upper} = \text{SMA}_{20} + (1.5 \times \text{ATR})$$
    $$\text{Keltner Lower} = \text{SMA}_{20} - (1.5 \times \text{ATR})$$
    $$\text{Squeeze On} \iff \text{Upper BB} < \text{Keltner Upper} \land \text{Lower BB} > \text{Keltner Lower}$$
* **Voting Logic:**
  - When a Squeeze is detected or ATR is in the bottom 15th percentile, the system triggers `CRITICAL_BREAKOUT_IMMINENT`.
  - Directional breakout lean is determined by price positioning relative to $\text{SMA}_{20}$ combined with volume expansion.

---

## 4. The Dynamic Ensemble Voting Engine

The Ensemble Engine aggregates the 3 sub-votes using a dynamic weighting mechanism:

$$\text{Probability} = w_{\text{stat}} \cdot P_{\text{stat}} + w_{\text{mom}} \cdot P_{\text{mom}} + w_{\text{vol}} \cdot P_{\text{vol}}$$

* **Standard Market Regime:**
  - $w_{\text{stat}} = 0.35$ (Mean Reversion)
  - $w_{\text{mom}} = 0.40$ (Trend Following)
  - $w_{\text{vol}} = 0.25$ (Dispersion)
* **Volatility Squeeze Regime (Breakout Imminent):**
  - $w_{\text{stat}} = 0.25$ (Mean reversion disabled during strong breakouts)
  - $w_{\text{mom}} = 0.40$ (Momentum dictates exit direction)
  - $w_{\text{vol}} = 0.35$ (High weight on volatility expansion)

All probabilities are normalized to strictly satisfy:
$$\text{Buy \%} + \text{Neutral \%} + \text{Sell \%} = 100.0\%$$

---

## 5. Tactical Quantitative Pivots

The engine continuously computes classical floor pivots over the rolling 24-period high, low, and close:
$$\text{Pivot} = \frac{\text{High} + \text{Low} + \text{Close}}{3}$$
$$\text{Resistance 1 } (R_1) = (2 \times \text{Pivot}) - \text{Low}$$
$$\text{Resistance 2 } (R_2) = \text{Pivot} + (\text{High} - \text{Low})$$
$$\text{Support 1 } (S_1) = (2 \times \text{Pivot}) - \text{High}$$
$$\text{Support 2 } (S_2) = \text{Pivot} - (\text{High} - \text{Low})$$

---

## 6. Frontend UI & Dashboard Architecture (`app.py`)

* **Framework:** Streamlit (Python 3.10+) with custom dark-mode CSS styling.
* **Component Layout:**
  1. **Top Header & Sync Ribbon:** Live BTC/USDT spot price, 24h delta, active candle bar, and auto-refresh controls.
  2. **Top Legal Banner:** Persistent amber disclaimer establishing educational status.
  3. **Trader Advisory Box:** Dynamic card styling matching bias classification (Green for Accumulate, Red for Defensive, Amber for Range).
  4. **Multi-Timeframe Matrix:** Direct side-by-side comparison of 1-Hour (Tactical) and 4-Hour (Structural) models.
  5. **Interactive Plotly Chart:** 3-tier subplot (Candlesticks with Bollinger Bands + Volume, RSI with threshold guides, and MACD Histogram).
  6. **Brain Diagnostics Explorer:** Transparent sub-tabs detailing the underlying math, formulas, and individual votes.
  7. **Comprehensive Footer Disclaimer:** Full liability waiver and MIT licensing terms.

---

## 7. Cloud Deployment & CI/CD Pipeline

| Layer | Configuration / File | Purpose |
| :--- | :--- | :--- |
| **Dependencies** | [`requirements.txt`](file:///c:/gemini%20proyect/btctool%202.0/requirements.txt) | `pandas`, `numpy`, `yfinance`, `streamlit`, `plotly`, `gunicorn`, `requests` |
| **PaaS Hosting** | [`Procfile`](file:///c:/gemini%20proyect/btctool%202.0/Procfile) | Web worker execution command for Heroku/Render |
| **Render Blueprint**| [`render.yaml`](file:///c:/gemini%20proyect/btctool%202.0/render.yaml) | Zero-configuration Infrastructure-as-Code spec |
| **Streamlit Config**| [`.streamlit/config.toml`](file:///c:/gemini%20proyect/btctool%202.0/.streamlit/config.toml) | Custom color palette, headless server flags, CORS settings |
| **Source Control** | Git / GitHub | Public repository (`aricimi/btctool-2.0`) on branch `main` |
| **Live Tunneling**  | Cloudflare Tunnel | Instant edge proxy to local Streamlit daemon |

---

## 8. Legal, Compliance & Risk Governance

1. **Explicit NFA Designation:** Every screen, sidebar, and report asserts that outputs are algorithmic probability estimates, not financial or investment advice.
2. **Zero Custodial Risk:** No API keys for exchanges (Binance, Bybit, Coinbase) are accepted or stored. The engine is strictly read-only.
3. **MIT License Limitation:** The software includes an absolute limitation of liability:
   > *"In no event shall the authors or copyright holders be liable for any claim, damages, or other liability arising from the software."*

---

## 9. Future Extensibility & Roadmap

- **Phase 2.1:** Machine Learning Integration (LightGBM / XGBoost classifier trained on historical ensemble features).
- **Phase 2.2:** On-Chain & Order Book Metrics (Binance Futures Long/Short ratio, funding rates, and CVD cumulative volume delta).
- **Phase 2.3:** Webhook Alerts (Telegram & Discord probabilistic advisory alerts for high-conviction signals).
- **Phase 2.4:** Multi-Asset Expansion (ETH/USDT, SOL/USDT, and Macro DXY correlation matrix).
