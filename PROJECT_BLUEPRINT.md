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

## 6. Telegram Mobile Autonomous Execution Engine (`alert_bot.py`)

* **Continuous Multi-Scale Autonomous Architecture (`AutonomousExecutionEngine`):**
  - **Dynamic Volatility & Structural Invalidation Shelf:**
    - Stop loss is anchored below the local micro-swing low / order book bid shelf ($P - \text{Floor} + 0.15 \times \text{ATR}$).
    - Target 1 is anchored dynamically to structural resistance with minimum $1.5\times \text{Risk}$ positive asymmetry (zero arbitrary percentage floors).
    - Target 2 (Runner) expands dynamically up to $2.8\times \text{Risk}$ for sustained expansion waves.
  - **Continuous Multivariate Confluence Engine (Zero Macro Vetoes):** Method `_compute_confluence_score()` calculates continuous $0.0 \rightarrow 100.0$ multivariate conviction score without macro gatekeeping:
    $$S_{\text{total}} = S_{\text{tape}} + S_{\text{depth}} + S_{\text{micro}} + S_{\text{structure}}$$
    1. **$S_{\text{tape}} \in [0, 35]$:** $17.5 \times (1.0 + \tanh(2.5 \times \text{taker\_delta}))$.
    2. **$S_{\text{depth}} \in [0, 25]$:** $12.5 \times (1.0 + \tanh(3.0 \times \text{imbalance\_ratio}))$.
    3. **$S_{\text{micro}} \in [0, 25]$:** Dynamic swing low rejection across visible chart $+$ Bollinger band inflection.
    4. **$S_{\text{structure}} \in [0, 15]$:** Breakout squeeze firing OR exhaustion dip recovery in expanded volatility.
    - **Trigger Threshold:** Executes Spot Buy when $S_{\text{total}} \ge 65.0$. 4H macro trend never vetoes a micro-scalp.
  - **State-Action Policy Engine (`_manage_active_trade`):**
    - `EARLY_BAIL`: Cuts losses immediately before stop if order book depth or taker bids collapse ($<-18\%$ depth or $<-0.40$ delta).
    - `HOLD_AND_STRETCH`: If buyer momentum is accelerating ($>+0.20$ delta), delays selling, expands target, and ratchets stop to guaranteed profit.
    - `SCALE_IN`: Adds Tranche 2 on confirmed breakout acceleration with combined risk-free stop.
    - `BANK_PROFIT`: Sells at market to bank profit when 1M volume collapses and candle thrust flattens at resistance (zero Target 1 lock!).
    - `MEMORY_SOFT_STOP`: Stop loss is tracked in memory; when touched, inspects tape live. Holds if buyers are absorbing the wick sweep, exits if bids truly collapse.
  - **Persistent State File (`bot_state.json`):**
    - State is persisted to disk on trade open, ratchet update, and close.
    - Automatically recovers active trades and state after Render container restarts or redeployments.
    - Features a 4-hour staleness guard (`time.time() - saved_at > 14400`) to safely discard expired positions.
  - **Regression State Recovery & Zero-Ego Re-engagement:**
    - Auto-resets `REGRESSING` back to `SCANNING` if price recovers to peak zone ($P \ge \text{tracked\_peak} \times 0.998$).
    - Zero cooldown timeouts: ready to engage immediately after an exit.
* **Directive Action Order Spectrum (Zero Clock Spam):**
  1. `🟢 BUY SPOT NOW (ENTER TRADE)`: Direct market buy directive with entry, Target 1, Target 2 runner, stop loss, and R:R $\ge 1.5:1$.
  2. `📈 HOLD POSITION (DO NOT SELL YET)`: Clear directive to hold active spot coins while momentum surges, expanding target and ratcheting stop to guaranteed profit.
  3. `➕ BUY MORE SPOT (ADD TO POSITION)`: Tranche 2 scale-in order upon confirmed breakout continuation with stop ratcheted to total breakeven.
  4. `⚠️ SELL SPOT NOW (EXIT TRADE EARLY)`: Early bail order cutting trade before stop loss when order book support collapses.
  5. `🏁 SELL SPOT NOW (BANK YOUR PROFIT)`: Direct sell order banking cash at 1M volume/thrust exhaustion at ceiling.
  6. `🛑 STOP LOSS HIT (EXIT TRADE)`: Memory-based soft stop exit when bids collapse.
  7. `📍 UPDATE: MOVE LIMIT BUY UP TO $...`: Dynamic limit buy order repositioning during dip absorption.
  8. `🛡️ UPDATE: MOVE STOP TO BREAKEVEN`: Breakeven locking order once price pushes forward into profit.
  9. `📡 On-Demand Telemetry via Telegram (/status)`: Sub-second (<1s) live engine status check via Telegram command listener with 100% spot-pure metrics.
* **24/7 Cloud Architecture (Render + UptimeRobot):**
  - Integrated HTTP Health Check endpoint on `$PORT` (default 10000) supporting both `HEAD` and `GET`.
  - Keeps Render service permanently awake via UptimeRobot 5-minute HTTP keep-alive pings.
  - Zero local PC dependency: runs 24/7/365 in the cloud without sleeping.

---

## 7. Dual-Mode Execution Architecture (OKX Auto-Trade & Revolut X Copilot)

The engine functions in dual-mode through `OKXSpotClient` (`okx_trader.py`):
1. **Copilot Mode (Default / Revolut X 0% Maker Fee):**
   - Without OKX API keys, alerts arrive in Telegram as unambiguous manual orders (`BUY SPOT NOW`, `SELL SPOT NOW`, `HOLD`, `MOVE STOP`).
2. **Autonomous OKX Auto-Execution Mode:**
   - When OKX credentials (`OKX_API_KEY`, `OKX_API_SECRET`, `OKX_PASSPHRASE` or `okx_config.json`) are supplied, the bot automatically executes spot buy/sell orders directly on OKX V5 REST API while simultaneously broadcasting confirmations to Telegram.
   - **4 Defensive Engineering Shields:**
     1. **Anti-Hanging Order Shield:** Auto-cancels limit buy orders if price escapes $> 0.35 \times \text{ATR}$.
     2. **Dynamic Partial Fill Tracking:** Automatically queries wallet balances and calculates exact available BTC quantity for sells.
     3. **Server-Side Trigger Stops:** Direct OCO/Trigger stops placed natively on OKX servers with exponential backoff on HTTP 429.
     4. **Slippage-Capped Emergency Exits:** Immediate-Or-Cancel (IOC) limit sells at `best_bid - 0.05%` to prevent slippage during whale dumps.



