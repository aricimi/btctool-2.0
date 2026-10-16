# 🏛️ PROJECT_BLUEPRINT.md — btctool 2.0 Master Blueprint
**System:** btctool 2.0 — Advanced Predictive Advisory Engine for BTC/USDT  
**Root Directory:** `C:\gemini proyect\btctool 2.0`  
**GitHub Repository:** [https://github.com/aricimi/btctool-2.0](https://github.com/aricimi/btctool-2.0)  
**Branch:** `main`  
**Status:** Operational / Live  

---

## ⚠️ STRICT OPERATIONAL COMMAND & PROTOCOL

> ### **THE GOLDEN COMMUNICATION RULE:**
> **Whenever the user asks a question or asks for information, the assistant MUST ALWAYS answer directly in text first without taking ANY background actions, running unprompted commands, or modifying files.**
> Actions, code edits, and terminal commands may ONLY be executed when the user explicitly commands: *"Do it"*, *"Proceed"*, *"Deploy"*, or gives a direct imperative command.

---

## 🔄 Continuity Protocol: "Read the blueprint and continue"

This document serves as the **Single Source of Truth** for the entire project. 
- **Automatic Synchronization:** Whenever any architectural change, new formula, or configuration update is made, `PROJECT_BLUEPRINT.md` must be updated immediately.
- **Session Recovery:** If power is lost, or a fresh session is started, all the user needs to say is:
  > **"Read the blueprint and continue"**
  The assistant will immediately read this blueprint, verify active processes, and resume with 100% full context.

---

## 1. Core Architecture & Stack

| Layer | Technology | File / Path | Configuration Details |
| :--- | :--- | :--- | :--- |
| **Backend Engine** | Python 3.10+ | [`engine.py`](file:///c:/gemini%20proyect/btctool%202.0/engine.py) | Mathematical engine, yfinance live feeds, 1h/4h resampler, Tri-Brain ensemble |
| **Frontend UI** | Streamlit + Plotly | [`app.py`](file:///c:/gemini%20proyect/btctool%202.0/app.py) | High-tech dark theme, multi-timeframe matrices, advisory card, subplots, persistent disclaimers |
| **Theme / Server** | Streamlit Config | [`.streamlit/config.toml`](file:///c:/gemini%20proyect/btctool%202.0/.streamlit/config.toml) | Primary: `#00FFA3`, Background: `#0A0E17`, Secondary: `#131B2E`, Headless: `true` |
| **Dependencies** | Python PIP | [`requirements.txt`](file:///c:/gemini%20proyect/btctool%202.0/requirements.txt) | `pandas`, `numpy`, `yfinance`, `streamlit`, `requests`, `gunicorn`, `plotly` |
| **PaaS Hosting** | Render / Heroku | [`Procfile`](file:///c:/gemini%20proyect/btctool%202.0/Procfile) | `web: streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true` |
| **Infrastructure** | Render Blueprint | [`render.yaml`](file:///c:/gemini%20proyect/btctool%202.0/render.yaml) | Zero-config build: `pip install -r requirements.txt`, autoDeploy: `true`, plan: `free` |
| **Edge Tunnel** | Cloudflare Tunnel | Daemon Process | Maps local `http://localhost:8501` to public edge URL |

---

## 2. Trading Formulas & Quantitative Brains

The engine decouples market dynamics into three behavioral dimensions, voting on **1-Hour (Tactical)** and **4-Hour (Structural)** timeframes.

### 2.1. The Statistical Brain (`StatisticalBrain`)
* **Mathematical Focus:** Gaussian standard deviations and channel positioning.
* **Formulas:**
  - 20-period Simple Moving Average ($\text{SMA}_{20}$) and Standard Deviation ($\sigma_{20}$).
  - **Upper Band:** $\text{SMA}_{20} + (2 \times \sigma_{20})$
  - **Lower Band:** $\text{SMA}_{20} - (2 \times \sigma_{20})$
  - **Percent %B:** $\frac{\text{Close} - \text{Lower}}{\text{Upper} - \text{Lower}}$
  - **Bandwidth:** $\frac{\text{Upper} - \text{Lower}}{\text{SMA}_{20}}$
  - **Price Z-Score:** $\frac{\text{Close} - \text{SMA}_{20}}{\sigma_{20}}$
* **Regime Probability Logic:**
  - $\%B \le 0.15 \implies$ Deep oversold statistical channel $\to$ High-probability mean-reversion bounce (**Buy bias**).
  - $\%B \ge 0.85 \implies$ Deep overbought statistical channel $\to$ High-probability mean-reversion exhaustion (**Sell bias**).
  - $0.15 < \%B < 0.85 \implies$ Normal channel ranging biased by distance from $\text{SMA}_{20}$.

### 2.2. The Momentum Brain (`MomentumBrain`)
* **Mathematical Focus:** Trend acceleration derivatives and momentum exhaustion.
* **Formulas:**
  - **Wilder's RSI (14-period):** Tracks speed and change of price movements.
  - **RSI Slope:** $\Delta \text{RSI} = \text{RSI}_t - \text{RSI}_{t-1}$
  - **MACD (12, 26, 9):**
    - $\text{MACD Line} = \text{EMA}_{12}(\text{Close}) - \text{EMA}_{26}(\text{Close})$
    - $\text{Signal Line} = \text{EMA}_9(\text{MACD Line})$
    - $\text{Histogram} = \text{MACD Line} - \text{Signal Line}$
    - **Histogram Acceleration:** $\Delta \text{Hist} = \text{Hist}_t - \text{Hist}_{t-1}$
* **Regime Probability Logic:**
  - $\text{RSI} < 30 \implies$ Severely oversold momentum exhaustion.
  - $\text{RSI} > 70 \implies$ Severely overbought momentum exhaustion.
  - $\text{MACD} > \text{Signal} \land \Delta \text{Hist} > 0 \implies$ Bullish momentum expansion/acceleration.
  - $\text{MACD} < \text{Signal} \land \Delta \text{Hist} < 0 \implies$ Bearish momentum expansion/acceleration.

### 2.3. The Volatility Brain (`VolatilityBrain`)
* **Mathematical Focus:** Market compression, volatility dispersion, and imminent breakout risk.
* **Formulas:**
  - **True Range (TR):** $\max(H - L, |H - C_{t-1}|, |L - C_{t-1}|)$
  - **ATR (14-period):** Rolling 14-period smoothed average of TR.
  - **ATR% of Price:** $(\text{ATR} / \text{Close}) \times 100$
  - **Keltner Channels (20, 1.5):** $\text{SMA}_{20} \pm (1.5 \times \text{ATR})$
  - **Squeeze Detection:** $\text{Upper BB} < \text{Upper KC} \land \text{Lower BB} > \text{Lower KC}$
* **Regime Probability Logic:**
  - If $\text{Squeeze On}$ or $\text{ATR Percentile} < 15\% \implies$ `CRITICAL_BREAKOUT_IMMINENT`.
  - Directional breakout lean: Assigned based on whether price is pressing above or below $\text{SMA}_{20}$ with volume support.

---

## 3. Dynamic Ensemble Engine & Advisory Output

The model combines sub-votes with adaptive weights depending on market state:

$$\text{Probability} = (w_{\text{stat}} \times P_{\text{stat}}) + (w_{\text{mom}} \times P_{\text{mom}}) + (w_{\text{vol}} \times P_{\text{vol}})$$

* **Standard Regime:** $w_{\text{stat}} = 0.35, \, w_{\text{mom}} = 0.40, \, w_{\text{vol}} = 0.25$
* **Squeeze / Breakout Active:** $w_{\text{stat}} = 0.25, \, w_{\text{mom}} = 0.40, \, w_{\text{vol}} = 0.35$ (mean-reversion weight decreased; momentum & volatility breakout weights increased).
* **Strict Normalization:** $\text{Buy \%} + \text{Neutral \%} + \text{Sell \%} = 100.0\%$

### Trader Advisory Report Contents:
1. **Directional Percentages:** Clean odds rather than raw execution triggers.
2. **Overall Verdict:** `STRONG_BUY_PROBABILITY`, `MODERATE_BUY_BIAS`, `NEUTRAL_CONSOLIDATION`, `MODERATE_SELL_BIAS`, `STRONG_SELL_PROBABILITY`.
3. **Model Confidence Score:** $0\% - 100\%$.
4. **Classical Floor Pivot Levels:**
   - $\text{Pivot} = \frac{H_{24} + L_{24} + C}{3}$
   - $R_1 = (2 \times \text{Pivot}) - L_{24}, \quad R_2 = \text{Pivot} + (H_{24} - L_{24})$
   - $S_1 = (2 \times \text{Pivot}) - H_{24}, \quad S_2 = \text{Pivot} - (H_{24} - L_{24})$
5. **Actionable Notes & Tactical Playbooks.**

---

## 4. Legal & Regulatory Shield Architecture

1. **Persistent Top Header Pill:** Amber alert on every page view specifying *Educational & Quantitative Research Only — Not Financial Advice (NFA)*.
2. **Persistent Sidebar Badge:** Dedicated legal notice box visible throughout navigation.
3. **Bottom Terms & Liability Waiver:** Explicit clause stating that the user holds sole responsibility for all financial decisions and capital, with zero liability accrued to developers/contributors.
4. **MIT License:** Complete exclusion of warranty and liability under open-source governance.
5. **Non-Custodial:** Zero exchange API keys, zero wallet connection, zero automated order routing.

---

## 5. Active Live Ports & Endpoints

- **Local Dashboard:** `http://localhost:8501`
- **Cloudflare Edge Tunnel:** `https://conflicts-bright-investigate-steam.trycloudflare.com`
- **GitHub Repository:** `https://github.com/aricimi/btctool-2.0`
- **1-Click Streamlit Cloud Deploy:** `https://share.streamlit.io/deploy?repository=aricimi/btctool-2.0&branch=main&mainModule=app.py`
- **1-Click Render Deploy Blueprint:** `https://render.com/deploy?repo=https://github.com/aricimi/btctool-2.0`

---

## 6. Maintenance & Session Resumption Checklist

When starting a new session or resuming after a disconnect:
1. Confirm local directory: `C:\gemini proyect\btctool 2.0`
2. Check `git status` to verify repo is clean.
3. Check running background tasks: Streamlit server and Cloudflare tunnel.
4. Review this blueprint before suggesting or implementing changes.
