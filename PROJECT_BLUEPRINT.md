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
* **Distance-Weighted Order Book Depth & tanh Imbalance (Bybit + OKX):**
  - Evaluates live bid vs. ask depth with exponential distance decay: $w_i = \exp\left(-40.0 \times \frac{|\text{price}_i - \text{mid}|}{\text{mid}}\right)$.
  - **Weighted Imbalance Ratio:** $\frac{\sum \text{bid\_usd} \times w_{\text{bid}} - \sum \text{ask\_usd} \times w_{\text{ask}}}{\sum \text{bid\_usd} \times w_{\text{bid}} + \sum \text{ask\_usd} \times w_{\text{ask}}}$.
  - **tanh Probability Alpha:** $\Delta P = 0.15 \times \tanh(3.0 \times \text{ob\_imbalance\_ratio})$.
  - **Anti-Spoofing Filter:** Requires 3 consecutive snapshots of same-sign imbalance before applying $\Delta P$.
* **Taker Delta:** Real-time taker flow ratio $[-1.0, +1.0]$ via Bybit recent trades (`/v5/market/recent-trade`).
* **Futures Derivatives & Z-Score:**
  - Real-time Open Interest in BTC from Bybit Linear Tickers (`/v5/market/tickers`).
  - Rolling 20-period OI change Z-score: $Z_{\text{OI}} = \frac{\Delta \text{OI} - \mu_{20}}{\sigma_{20}}$. Confluence gates: $Z > 2.0$ confirms trend; $Z < -2.0$ triggers exhaustion and tightens targets by 25%.
  - Real-time funding rate from Bybit Linear perpetuals in raw decimal format.

---

## 3. Trading Formulas, Quantitative Brains & Meta-Learner

### 3.1. The Statistical Brain (`StatisticalBrain`)
- Bollinger Bands ($N=20, K=2.0$).
- $\%B = \frac{\text{Close} - \text{Lower}}{\text{Upper} - \text{Lower}}$
- **Regime-Aware Envelopes:**
  - When 4H Macro is `Trend Down` and $\%B \ge 0.60$: Evaluated as a **Bearish Retest Resistance Zone** (`sell_prob = 0.55`, `buy_prob = 0.20`), preventing buy traps into overhead resistance.
  - When 4H Macro is `Trend Up` and $\%B \le 0.40$: Evaluated as a **Bullish Dip Support Zone** (`buy_prob = 0.55`, `sell_prob = 0.20`).

### 3.2. The Momentum Brain (`MomentumBrain`)
- **Triple-Period Dynamic RSI:** Tailored periods `(6, 12, 24)` on 1H/15M to detect fast micro-reversals before 14-period RSI catches up.
- **Dual EMA Envelopes:** Fast EMA(9) and Slow EMA(21).
- **MACD (12, 26, 9):** Histogram slope derivative $\Delta \text{Hist} = \text{Hist}_t - \text{Hist}_{t-1}$ to track momentum acceleration.

### 3.3. The Volatility Brain (`VolatilityBrain`) & Squeeze State Machine
- True Range & 14-period smoothed ATR.
- **5-State Squeeze Machine:** Evaluates Bollinger Bands compressing inside Keltner Channels ($1.5 \times \text{ATR}$).
  - `IDLE`: Normal volatility ($BB \ge KC$).
  - `BUILDING`: $BB < KC$ for $< 3$ cycles (or $< 5$ on $1\text{m}/5\text{m}$).
  - `LOADED`: $BB < KC$ sustained for $\ge 3$ cycles (`🟡 SQUEEZE LOADED — WATCH FOR BREAK`).
  - `FIRING`: Breakout active as BB expands outside KC (`🔴 SQUEEZE FIRING — BREAKOUT ACTIVE`). Overrules trend-fade scenarios.
  - `TRENDING`: Post-squeeze expansion with trailing stop (`🟢 POST-SQUEEZE TREND — TRAIL STOP`).

### 3.4. Level 2 Meta-Learner & Macro ADX(14)
- **ADX(14) Macro Gating:** Computed on 4H klines. If $\text{ADX}_{14} > 22$ or $\Delta \text{ADX} > 0$: Trend Up / Down based on EMA 9/21. Otherwise: Range regime.
- **Stacked Meta-Learner:** Calibrated `HistGradientBoostingClassifier` with sigmoid calibration sitting above all 3 brains.
- **Cold-Start Fallback:** `REGIME_WEIGHTS` (Breakout, Chop, Range, Trend Up, Trend Down) until 200 labeled observations are collected.

---

## 4. Institutional Algorithmic Bot Decision Matrix & Pre-Filter

### 4.1. Derivatives Pre-Filter (Raw Bybit Decimals)
- **Funding Rate Gate:**
  - $\text{Funding} > +0.0005$ (+0.05%): Suppresses aggressive `ENTER LONG NOW`, converting to `SET BUY LIMIT ORDER`.
  - $\text{Funding} < -0.0003$ (-0.03%): Suppresses aggressive `ENTER SHORT NOW`, converting to `SET SELL LIMIT ORDER`.
- **Adaptive Liquidation Trap:** Activates after 24h history if retail long ratio $> \text{mean}_{24h} + 0.08$ and distance to liquidation cluster $< 1.5 \times \text{ATR}$.

### 4.2. Unified ATR Stops & Targets Standard
- **Longs:** Stop = $\text{Entry} - 1.5 \times \text{ATR}$; $TP_1 = \text{Entry} + 0.5 \times \text{ATR}$; $TP_2 = \text{Entry} + 1.0 \times \text{ATR}$.
- **Shorts:** Stop = $\text{Entry} + 1.5 \times \text{ATR}$; $TP_1 = \text{Entry} - 0.5 \times \text{ATR}$; $TP_2 = \text{Entry} - 1.0 \times \text{ATR}$.
- Exhaustion modifier: targets tightened by 25% if $Z_{\text{OI}} < -2.0$.

### 4.3. 5 Scenarios & Conflict Resolution Hierarchy
1. **Scenario 1 (Downtrend Resistance Fade):** 4H Trend Down + $\%B \ge 0.58$ + Ask Imbalance $< -10\% \rightarrow$ `SET SELL LIMIT AT RESISTANCE (BEARISH FADE)`.
2. **Scenario 2 (Downtrend Continuation):** 4H Trend Down + Breakdown momentum $\rightarrow$ `TREND CONTINUATION: ENTER SHORT ON RETEST`.
3. **Scenario 3 (Bottom Sweep Rebound):** Low swept + Rebound $\ge 0.5 \times \text{ATR}$ + Bid Imbalance $> +15\%$. If Volume $\ge 1.8 \times \text{SMA}_{20}$: `ENTER LONG NOW` or `COUNTER-TREND SCALP`. Else: `LOW-VOLUME RETEST: SET PULLBACK LIMIT`.
4. **Scenario 4 (Uptrend Dip Buy):** 4H Trend Up + $\%B \le 0.45 \rightarrow$ `TREND FOLLOWING: SET BUY LIMIT AT SUPPORT`.
5. **Scenario 5 (Range-Bound Ping-Pong):** Consolidation $\rightarrow$ Limit Buy at Lower Band / Limit Sell at Upper Band.
- **Conflict Resolution Pipeline:** 5 sequential gates (Derivatives $\rightarrow$ Macro ADX $\rightarrow$ Squeeze FIRING $\rightarrow$ OB tiebreaker $\rightarrow$ %B boundaries).

---

## 5. Active Endpoints & Live Deployment

- **Local Dashboard:** `http://localhost:8501`
- **Cloudflare Edge Tunnel:** `https://oven-internationally-denver-salem.trycloudflare.com`
- **Streamlit Cloud Dashboard:** `https://btctool-2-0.streamlit.app`
- **24/7 Telegram Alert Bot (Render Cloud):** `https://btctool-alerts.onrender.com`
- **GitHub Repository:** [https://github.com/aricimi/btctool-2.0](https://github.com/aricimi/btctool-2.0)

---

## 6. Telegram Mobile Spot Execution Copilot (`alert_bot.py`)

* **Spot-Only Execution Copilot Architecture (`SpotExecutionCopilot`):**
  - Designed specifically for spot traders (e.g. Revolut X with 0.00% maker fee, or OKX spot).
  - Eliminates micro-scalp fee drag by targeting high-conviction trend breakouts, compression coils, and liquidity reversals (+1.5% to +3.5%+).
* **Complete Spot Trade Lifecycle:**
  1. **Early Trend Ignition (Phase 1 -> Phase 2 Coil):** Squeeze `LOADED` or `FIRING` with order book absorption $\ge +8\%$ and $\%B \le 0.55$. Enters *before* the impulse candle accelerates.
  2. **Bottom Sweep Rebound:** Channel sweep ($\%B \le 0.30$) with heavy bid wall ($\ge +15\%$).
  3. **Bullish Dip Support:** 4H Macro Trend Up + Pullback to dynamic support ($0.35 \le \%B \le 0.48$).
  4. **Target 1 Milestone & Breakeven Protection:** When price reaches Target 1 ($1.0 \times \text{ATR}$), moves stop to entry $+ 0.15 \times \text{ATR}$ for guaranteed breakeven.
  5. **Parabolic Trailing Ratchet:** Follows new higher swing lows, ratcheting stop up behind price ($0.9 \times \text{ATR}$ under peak) to lock in profit up to the trend crest.
  6. **Emergency Whale Invalidation Shield:** If price is near breakeven and the order book violently flips (imbalance $\le -25\%$), sends immediate market exit alert to protect capital.
  7. **Hard Stop Capital Defense:** Server-synced ATR stop loss ($1.2 \times \text{ATR}$) strictly caps risk on unexpected flash flushes.
* **24/7 Cloud Architecture (Render + UptimeRobot):**
  - Integrated HTTP Health Check endpoint on `$PORT` (default 10000) supporting both `HEAD` and `GET`.
  - Keeps Render service permanently awake via UptimeRobot 5-minute HTTP keep-alive pings.
  - Zero local PC dependency: runs 24/7/365 in the cloud without sleeping.

---

## 7. OKX Auto-Execution Architecture & Roadmap (`okx_trader.py`)

* **Target Account:** OKX Spot BTC/USDT starting with €50 (~$54) with 0.08% Maker Fee.
* **4 Defensive Engineering Shields:**
  1. **Anti-Hanging Order Shield:** Auto-cancels limit buy orders after 3 minutes or if price escapes $> 0.35 \times \text{ATR}$.
  2. **Dynamic Partial Fill Tracking:** Queries `get_order_details()` on fill and binds trailing stop strictly to actual `filled_sz`.
  3. **Server-Side Trigger Stops & API Backoff:** Places hard stops natively on OKX's servers (OCO/Trigger orders) with exponential backoff on HTTP 429.
  4. **Slippage-Capped Emergency Exits:** Uses Immediate-Or-Cancel (IOC) limit sells at `best_bid - 0.05%` to prevent slippage during whale dumps.


