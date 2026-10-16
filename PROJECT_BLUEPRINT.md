# 🏛️ PROJECT_BLUEPRINT.md — btctool 2.0 Master Blueprint
**System:** btctool 2.0 — Advanced Predictive Advisory & Directive Engine for BTC/USDT  
**Root Directory:** `C:\gemini proyect\btctool 2.0`  
**GitHub Repository:** [https://github.com/aricimi/btctool-2.0](https://github.com/aricimi/btctool-2.0)  
**Branch:** `main`  
**Status:** Operational / Live with Binance Real-Time Feeds  

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
| **Backend Engine** | Python 3.10+ | [`engine.py`](file:///c:/gemini%20proyect/btctool%202.0/engine.py) | Binance live spot & futures feeds, order book depth, Tri-Brain ensemble, macro confluence |
| **Frontend UI** | Streamlit + Plotly | [`app.py`](file:///c:/gemini%20proyect/btctool%202.0/app.py) | Interactive dark theme, multi-timeframe matrices, trade directive card, triple RSI subplots, persistent disclaimers |
| **Theme / Server** | Streamlit Config | [`.streamlit/config.toml`](file:///c:/gemini%20proyect/btctool%202.0/.streamlit/config.toml) | Primary: `#00FFA3`, Background: `#0A0E17`, Secondary: `#131B2E`, Headless: `true` |
| **Dependencies** | Python PIP | [`requirements.txt`](file:///c:/gemini%20proyect/btctool%202.0/requirements.txt) | `pandas`, `numpy`, `yfinance`, `streamlit`, `requests`, `gunicorn`, `plotly` |
| **Edge Tunnel** | Cloudflare Tunnel | Daemon Process | Maps local `http://localhost:8501` to live public edge URL |

---

## 2. Market Ingestion & Order Book Microstructure

* **Primary Market Feed:** Direct **Binance REST API** (`https://api.binance.com/api/v3/klines` for `BTCUSDT`), with automatic fallback to yfinance if throttled.
* **Order Book Depth & Imbalance:**
  - Evaluates live bid vs. ask depth within the **0.5% mid-price boundary** from Binance Level 2 order book (`/api/v3/depth?limit=100`).
  - **Imbalance %:** $\frac{\text{Bid Depth} - \text{Ask Depth}}{\text{Bid Depth} + \text{Ask Depth}} \times 100$
  - Identifies real institutional limit order absorption walls.
* **Futures Derivatives:**
  - Open Interest in BTC from Binance Futures (`/fapi/v1/openInterest`).
  - Real-time funding rate from `/fapi/v1/premiumIndex`.

---

## 3. Trading Formulas & Quantitative Brains

### 3.1. The Statistical Brain (`StatisticalBrain`)
- Bollinger Bands ($N=20, K=2.0$).
- $\%B = \frac{\text{Close} - \text{Lower}}{\text{Upper} - \text{Lower}}$
- Bandwidth $= \frac{\text{Upper} - \text{Lower}}{\text{SMA}_{20}}$
- Price $Z$-Score relative to moving average.
- Mean-reversion probability vs. channel expansion.

### 3.2. The Momentum Brain (`MomentumBrain`)
- **Triple-Period Dynamic RSI:** Tailored periods `(6, 12, 24)` on 1H/15M to detect fast micro-reversals before 14-period RSI catches up.
- **Dual EMA Envelopes:** Fast EMA(9) and Slow EMA(21).
- **MACD (12, 26, 9):** Histogram slope derivative $\Delta \text{Hist} = \text{Hist}_t - \text{Hist}_{t-1}$ to track momentum acceleration.

### 3.3. The Volatility Brain (`VolatilityBrain`)
- True Range & 14-period smoothed ATR.
- **Squeeze Detection:** Bollinger Bands compressing inside Keltner Channels ($1.5 \times \text{ATR}$).
- Flags `CRITICAL_BREAKOUT_IMMINENT` when compressed.

---

## 4. Anti-Contradiction Confluence & Actionable Directives

Unlike legacy tools that issue blind `ENTER LONG NOW` directives with inflated probabilities, **btctool 2.0** enforces strict confluence:

1. **4H Macro Trend Confluence Filter:**
   - Evaluates the 4H trend structure (Price relative to 4H 21 EMA).
   - If 4H is in a **`Trend Down`**, the engine **forbids aggressive buy calls**. Bounces off lower wicks are strictly downgraded to:
     `COUNTER-TREND SCALP: BUY PULLBACK LIMIT` with tight targets and explicit counter-trend risk flags.
2. **Harmonized Probability Model:**
   - The trade directive's target reach probability is mathematically bound to the ensemble probability model. No arbitrary 87% claims when the model calculates 52%.
3. **Execution Levels Provided:**
   - **Entry Trigger Price**
   - **Invalidation Stop Loss** (calculated dynamically off the sweep wick and ATR buffer)
   - **Take-Profit 1 (Scalp Target)**
   - **Take-Profit 2 (Runner Target)**
   - **Risk % calculation**

---

## 5. Active Endpoints & Live Deployment

- **Local Dashboard:** `http://localhost:8501`
- **Cloudflare Edge Tunnel:** `https://conflicts-bright-investigate-steam.trycloudflare.com`
- **GitHub Repository:** [https://github.com/aricimi/btctool-2.0](https://github.com/aricimi/btctool-2.0)
