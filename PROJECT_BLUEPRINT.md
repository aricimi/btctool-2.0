# 🏛️ PROJECT_BLUEPRINT.md — btctool 2.0 Master Blueprint
**System:** btctool 2.0 — Institutional Predictive Advisory & Directive Engine for BTC/USDT  
**Root Directory:** `C:\gemini proyect\btctool 2.0`  
**GitHub Repository:** [https://github.com/aricimi/btctool-2.0](https://github.com/aricimi/btctool-2.0)  
**Branch:** `main`  
**Status:** Operational / Live with Zero-Contradiction Institutional Bot Matrix  

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

* **Multi-Exchange Primary Market Feed:** Direct **Bybit Spot Klines API** (with Binance and yfinance fallbacks), unblocked across all global cloud networks (AWS, Streamlit Cloud, Render).
* **Order Book Depth & Imbalance (Bybit + OKX):**
  - Evaluates live bid vs. ask depth within the **0.5% mid-price boundary** from Bybit Level 2 order book (`/v5/market/orderbook?category=spot`) and OKX books (`/api/v5/market/books`).
  - **Imbalance %:** $\frac{\text{Bid Depth} - \text{Ask Depth}}{\text{Bid Depth} + \text{Ask Depth}} \times 100$
  - Injects dynamic probability alpha ($\pm 15\%$ probability shift) based on real institutional limit order walls.
* **Futures Derivatives:**
  - Real-time Open Interest in BTC from Bybit Linear Tickers (`/v5/market/tickers`).
  - Real-time funding rate from Bybit Linear perpetuals.

---

## 3. Trading Formulas & Quantitative Brains

### 3.1. The Statistical Brain (`StatisticalBrain`)
- Bollinger Bands ($N=20, K=2.0$).
- $\%B = \frac{\text{Close} - \text{Lower}}{\text{Upper} - \text{Lower}}$
- **Regime-Aware Envelopes:**
  - When 4H Macro is `Trend Down` and $\%B \ge 0.60$ (upper half of band): Evaluated as a **Bearish Retest Resistance Zone** (`sell_prob = 0.55`, `buy_prob = 0.20`), preventing buy traps into overhead resistance.
  - When 4H Macro is `Trend Up` and $\%B \le 0.40$ (lower half of band): Evaluated as a **Bullish Dip Support Zone** (`buy_prob = 0.55`, `sell_prob = 0.20`).

### 3.2. The Momentum Brain (`MomentumBrain`)
- **Triple-Period Dynamic RSI:** Tailored periods `(6, 12, 24)` on 1H/15M to detect fast micro-reversals before 14-period RSI catches up.
- **Dual EMA Envelopes:** Fast EMA(9) and Slow EMA(21).
- **MACD (12, 26, 9):** Histogram slope derivative $\Delta \text{Hist} = \text{Hist}_t - \text{Hist}_{t-1}$ to track momentum acceleration.

### 3.3. The Volatility Brain (`VolatilityBrain`)
- True Range & 14-period smoothed ATR.
- **Squeeze Detection:** Bollinger Bands compressing inside Keltner Channels ($1.5 \times \text{ATR}$).
- Flags `CRITICAL_BREAKOUT_IMMINENT` when compressed.

---

## 4. Institutional Algorithmic Bot Decision Matrix (Zero Contradictions)

The engine acts as a professional algorithmic trading bot where all parameters are strictly co-aligned:

1. **Scenario 1 (Downtrend Resistance Fade):**
   - **Trigger:** 4H Macro is `Trend Down` + $\%B \ge 0.58$ (price in upper channel) + Order Book Imbalance $< -10\%$ (overhead ask wall).
   - **Directive:** `SET SELL LIMIT AT RESISTANCE (BEARISH FADE)`
   - **Levels:** Invalidation strictly above Upper BB ($+0.25 \times \text{ATR}$); $TP_1$ at Middle Band; $TP_2$ at Lower Band.
2. **Scenario 2 (Downtrend Continuation):**
   - **Trigger:** 4H Macro is `Trend Down` + Breakdown momentum or $\%B < 0.40$ with heavy sell flow.
   - **Directive:** `TREND CONTINUATION: ENTER SHORT ON RETEST`
3. **Scenario 3 (Bottom Sweep Rebound):**
   - **Trigger:** 24h Low swept + Rebound $\ge \$120$ + Bid Imbalance $> +15\%$.
   - **Directive:** If 4H is Down: `COUNTER-TREND SCALP: BUY PULLBACK LIMIT` (tight scalp targets, explicit counter-trend flag). If 4H is Up: `ENTER LONG NOW (MOMENTUM REBOUND)`.
4. **Scenario 4 (Uptrend Dip Buy):**
   - **Trigger:** 4H Macro is `Trend Up` + $\%B \le 0.45$ + Order Book has bid support.
   - **Directive:** `TREND FOLLOWING: SET BUY LIMIT AT SUPPORT`
5. **Scenario 5 (Range-Bound Ping-Pong):**
   - **Trigger:** Consolidation / Equilibrium.
   - **Directive:** If $\%B \ge 0.50$: `RANGE DEFENSE: SET SELL LIMIT AT UPPER BAND`. If $\%B < 0.50$: `RANGE DEFENSE: SET BUY LIMIT AT LOWER BAND`. Never buys the top of the range.

---

## 5. Active Endpoints & Live Deployment

- **Local Dashboard:** `http://localhost:8501`
- **Cloudflare Edge Tunnel:** `https://conflicts-bright-investigate-steam.trycloudflare.com`
- **GitHub Repository:** [https://github.com/aricimi/btctool-2.0](https://github.com/aricimi/btctool-2.0)
