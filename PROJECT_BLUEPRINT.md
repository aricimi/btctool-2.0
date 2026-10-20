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
| **Backend Engine** | Python 3.10+ | [`engine.py`](file:///c:/gemini%20proyect/btctool%202.0/engine.py) | Bybit/OKX live spot & futures feeds, order book depth, Tri-Brain ensemble, macro confluence |
| **Execution Daemon** | Python Async / Event Loop | [`alert_bot.py`](file:///c:/gemini%20proyect/btctool%202.0/alert_bot.py) | 24/7 continuous autonomous spot execution, Telegram mobile alerts, Render health keep-alive |
| **OKX Spot Client** | REST API V5 | [`okx_trader.py`](file:///c:/gemini%20proyect/btctool%202.0/okx_trader.py) | Automated execution on OKX Spot with anti-hanging, partial fill, server stops, and IOC whale defense |
| **Trade Journal & Ledger** | Python CSV / Markdown | [`trade_logger.py`](file:///c:/gemini%20proyect/btctool%202.0/trade_logger.py) | Real-time dual recording to Excel [`trade_journal.csv`](file:///c:/gemini%20proyect/btctool%202.0/trade_journal.csv) and [`trade_journal.md`](file:///c:/gemini%20proyect/btctool%202.0/trade_journal.md) |
| **Trade History Data** | JSON Persistence | [`trade_history.json`](file:///c:/gemini%20proyect/btctool%202.0/trade_history.json) | Structured trade lifecycle database with full duration, fee, and PnL metrics |
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

* **Primary Engine: Zebra Bot 100-Screen Real-Time Quant Engine (`ZebraBotEngine`):**
  - Continuous sub-second WebSocket event loop (`market_stream.py` + `market_state.py` + `conviction_engine.py` + `execution_manager.py`).
  - Completely eliminates the legacy 20-second sleep polling loop.
  - Deploys Kinetic Push vs Structural Barrier mechanics, 3-snapshot anti-spoofing, OI Z-scores, and multi-lot scaling.
* **Legacy Reference Architecture (`AutonomousExecutionEngine`):**
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
    - `BANK_PROFIT`: Sells at market to bank profit when 1M volume collapses and candle thrust flattens at resistance with guaranteed fee-shield threshold (`gain_pct >= +0.30%` to guarantee clean net profit in wallet after OKX 0.20% round-trip fees).
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
  4. `⚠️ SELL SPOT NOW (CATASTROPHIC ORDER BOOK COLLAPSE)`: Whale defense order cutting trade before stop loss when order book support collapses.
  5. `🏁 SELL SPOT NOW (BANK YOUR PROFIT)`: Direct sell order banking cash at 1M volume/thrust exhaustion at ceiling (`gain_pct >= 0.30%`).
  6. `🛑 STOP LOSS HIT (EXIT TRADE)`: Memory-based soft stop exit when bids collapse.
  7. `⚠️ MOMENTUM STALLING AT RESISTANCE · DO NOT BUY`: Notifies trader of upper ceiling and stays in cash while tracking dip support floor.
  8. `📈 UPDATE: RATCHET STOP LOSS HIGHER`: Dynamically ratchets trailing stop as price pushes higher into profit.
  9. `🛡️ UPDATE: MOVE STOP TO BREAKEVEN`: Breakeven locking order once price pushes forward into profit.
  10. `📡 On-Demand Telemetry via Telegram (/status)`: Sub-second (<1s) live engine status check via Telegram command listener with 100% spot-pure metrics.
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

---

## 8. Automated Trade Journal & Excel PnL Ledger (`trade_logger.py`)

The system automatically records, audits, and publishes every trade lifecycle in real-time without manual intervention:
1. **Underlying Persistent Database (`trade_history.json`):**
   - Stores structured JSON objects for each trade: `id`, `type`, `setup`, `entry_time`, `entry_price`, `exit_time`, `exit_price`, `duration`, `target_1`, `target_2`, `stop_loss`, `gross_pnl_pct`, `okx_fee_pct`, `net_pnl_pct`, `exit_reason`, and `status`.
   - Running stats: `total_closed_trades`, `wins`, `losses`, `win_rate_pct`, `gross_cumulative_pct`, `total_fees_pct`, `net_cumulative_pct`.
2. **Native Microsoft Excel Spreadsheet (`trade_journal.csv`):**
   - Formatted with `UTF-8 with BOM` (`utf-8-sig`) encoding for full-screen display in Microsoft Excel on Windows without text import wizards.
   - Clean columns: `Trade #`, `Status`, `Type`, `Setup`, `Entry Time`, `Exit Time`, `Hold Duration`, `Entry Price ($)`, `Exit Price ($)`, `Target 1 ($)`, `Target 2 ($)`, `Stop Loss ($)`, `Gross PnL (%)`, `OKX Fee (%)`, `Net PnL (%)`, `Result`, and `Exit Reason`.
   - Includes bottom `=== SUMMARY PERFORMANCE ===` statistics block.
3. **Markdown Visual Report (`trade_journal.md`):**
   - Formatted GitHub-style Markdown table and executive summary for rapid preview in Cursor, VS Code, or web dashboards.
4. **Exchange Fee Accounting Model:**
   - Standard OKX Spot taker rate: **0.10% buy taker + 0.10% sell taker = 0.20% round-trip**.
   - Net profit accounting: $\text{Net PnL} = \text{Gross PnL} - 0.20\%$.
5. **Excel Lock Protection & Zero-Loss Background Auto-Flush:**
   - If [`trade_journal.csv`](file:///c:/gemini%20proyect/btctool%202.0/trade_journal.csv) is open in Microsoft Excel, Windows locks the file. The logger catches `PermissionError` without interrupting execution, preserves the trade in memory and [`trade_history.json`](file:///c:/gemini%20proyect/btctool%202.0/trade_history.json), and flags `pending_csv_update = True`.
   - On every 20-second evaluation tick in `evaluate_market_cycle()`, `flush_pending_csv()` automatically attempts to flush the queue. The moment Excel is closed, the spreadsheet is updated immediately with all pending trades.

---

## 9. Enforced Blueprint Synchronization & Git Pre-Commit Guardrails

To prevent code drift, feature loss, and AI context amnesia, the repository enforces **Atomic Blueprint Synchronization**:
1. **Git `pre-commit` Hook (`.git/hooks/pre-commit`):**
   - Programmatically intercepts every `git commit`.
   - If any Python file (`*.py`) is staged, git checks whether `PROJECT_BLUEPRINT.md` is also staged.
   - **Rejection Rule:** If `PROJECT_BLUEPRINT.md` is NOT modified and staged in the exact same commit, the commit is physically aborted with code 1.
2. **Workspace Architecture Directive (`AGENTS.md`):**
   - Loaded hierarchically by Antigravity in every turn.
   - Mandates that no code task is complete until `PROJECT_BLUEPRINT.md` is updated.
3. **The Atomic Definition of Done:**
   $$\text{Task Complete} \iff \text{Code Tested} \land \text{Blueprint Updated} \land \text{Committed Together}$$

---

## 10. Zebra Bot Architecture: The Institutional 100-Screen Real-Time Quant Engine

### 10.1. Mission & Core Operating Directives
1. **Single Objective Function:** Maximize Net Realized PnL ($\mathbb{E}[\text{PnL}_{\text{net}}]$) on BTC/USDT 24/7/365 with **zero sleep blindness**.
2. **Strict Confinement:** All operations, files, scripts, logs, and state reside strictly within `c:\gemini proyect\btctool 2.0`.
3. **Dynamic Volatility Relativity:** Zero hardcoded percentage limits or rigid "if/else" boxes. All distances, targets, and invalidations are measured in **dynamic volatility units (ATR multiples)** and **market structure swings (higher-lows/lower-highs)**.
4. **Fee Friction Gate:** Every execution must mathematically exceed the **OKX 0.20% round-trip spot fee + live order book slippage hurdle**. The engine never churns capital for micro-crumbs.
5. **Multi-Timeframe Confluence:** High-conviction trades occur only when the **Macro Tide (1D–2H)**, **Structural Battleground (1H–15M)**, and **Micro Trigger/Tape (5M–1S)** align.

---

### 10.2. The 5 Mathematical Upgrades Absorbed into Zebra Bot
1. **Kinetic Push vs Structural Barrier Engine:**
   - Instead of brittle boolean `if/else` checks, price movement is modeled as physics:
     - **Kinetic Energy (Push):** Measured by volume surge + taker delta + MACD velocity + EMA momentum.
     - **Structural Barrier (Resistance/Support):** Nearest Bollinger Band envelope + real L2 order book walls.
   - Prevents premature exits: When Kinetic Push is expanding, riding the upper band is recognized as **bullish momentum**, NOT an exit ceiling.
2. **3-Snapshot Anti-Spoofing Order Book Filter:**
   - Tracks order book bid/ask walls across 3 consecutive time snapshots.
   - If a wall flickers or disappears before price touches it, it is flagged as **spoofing** and purged from depth calculations.
3. **Open Interest (OI) Change Z-Score:**
   - Measures statistical standard deviations of OI change: $Z_{\Delta \text{OI}} = \frac{\Delta \text{OI} - \mu_{20}}{\sigma_{20}}$.
   - $Z > +2.0$ confirms genuine institutional leverage inflow; $Z \approx 0$ flags retail noise.
4. **`tanh`-Smoothed Order Book Imbalance Normalization:**
   - Compresses raw bid/ask volume ratios smoothly into a bounded range of $[-1.0, +1.0]$:
     $$\text{Imbalance}_{\text{normalized}} = \tanh(\text{Bid/Ask Ratio} - 1)$$
   - Eliminates formula explosion caused by single massive whale blocks.
5. **Sticky Lifecycle State Machine:**
   - Eliminates "tick-jitter" and panic flipping.
   - State progression: `OPTIMAL_ENTRY` $\rightarrow$ `IN_PROGRESS` $\rightarrow$ `EXHAUSTION` $\rightarrow$ `TARGET`.
   - Once a trade enters `IN_PROGRESS`, the engine is prohibited from flipping to a sell on minor wicks unless it reaches `EXHAUSTION` or breaks structural invalidation.

---

### 10.3. The 4 Decoupled Subsystems

```
┌────────────────────────────────────────────────────────────────────────┐
│                   SUBSYSTEM 1: SENSORY INGESTION                       │
│  WebSocket Asynchronous Event Loop (Sub-Second Ingestion, Zero Sleep)   │
│  • Public Trades Tape      • L2 Order Book Depth 50                    │
│  • Derivatives OI & Funding • Multi-TF Ring Buffers (1s to 1D)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   SUBSYSTEM 2: THE 100-SCREEN MATRIX                   │
│  Vectorized Rolling Calculations (Numpy Ring Buffers < 10ms execution) │
│  • 11 Timeframes: 1s, 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 1D         │
│  • Full Indicator Suite: EMA 9-200, MACD/DEA, RSI, Stoch, Bands, ATR   │
│  • Order Flow: Session VWAP ±3σ, Volume Profile POC, Live CVD, Delta    │
│  • Microstructure: Absorption Index, Anti-Spoof Depth, Book Skew       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   SUBSYSTEM 3: CONVICTION & EV BRAIN                   │
│  Kinetic Push vs Barrier Machine & Real-Time Probability Classifier   │
│  • Macro Regime Classifier (Bull / Bear / Neutral Tide)                │
│  • Volatility State Governor (Expansion / Compression / Chop)          │
│  • Bullish Absorption Dip Classifier (Fake Dip vs Trend Break)         │
│  • Expected Value Engine (E[Net PnL] > Fee Hurdle)                     │
│  • Sticky Lifecycle State Machine (Zero Tick-Jitter)                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  SUBSYSTEM 4: ASYMMETRIC EXECUTION                     │
│  Multi-Lot Capital Allocator & Dynamic Lifecycle Manager               │
│  • Lot 1 (Core Position) + Lot 2 (Absorption Dip Scaling)              │
│  • Uncapped Structural Trailing (Riding 1%, 2%, 5%+ Trends)            │
│  • Ruthless Invalidation Cuts (Zero bag-holding on structural failure)  │
│  • Real-Time Ledger Sync (UTF-8-BOM CSV, Excel Lock-Proof, Markdown)   │
└────────────────────────────────────────────────────────────────────────┘
```

#### Detailed Component Specifications:
1. **`market_stream.py` (Sensory Ingress — Eyes):**
   - Asynchronous WebSocket listener (`asyncio` + `websockets`) streaming OKX public channels (`trades`, `books50-l2-tbt`, `open-interest`, `funding-rate`, `tickers`).
   - Circular ring buffers maintaining rolling OHLCV for 11 horizons: `[1s, 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 1D]`.
2. **`market_state.py` (The 100-Screen Vectorized State Matrix — Perception):**
   - Computes technical indicators across all 11 horizons in $<5\text{ms}$:
     - EMAs (9, 21, 50), RSI, MACD (DIF, DEA, Histogram), Bollinger Bands (%B, Bandwidth), dynamic ATR.
     - Anchored Session VWAP ($\pm 1\sigma, \pm 2\sigma$), Cumulative Volume Delta (CVD), Trade Velocity, $\Delta \text{OI}$ Z-score, Funding Rate.
     - 3-Snapshot Anti-Spoof Depth Ratios and Real-Time **Absorption Index** ($A_i$).
     - **Dynamic Multi-Screen Boundaries (`extract_multi_screen_boundaries`):** Gathers all 33 Bollinger bands, pooled swing highs, and `composite_atr` (median across active horizons). Zero single-timeframe proxy lock.
     - **Balloon Geometry Analyzer (`compute_balloon_and_regimes`):** Evaluates whether Bollinger bands are actively blowing open outward (`EXPANDING_BALLOON`) or horizontal and slow (`SLOW_MARKET`).
     - **Micro Turn (`compute_micro_turn`):** Sub-minute kinetic deceleration and velocity slowing.
3. **`conviction_engine.py` (Policy Engine — Mind):**
   - Pure cognitive modeling: Evaluates Kinetic Push vs Structural Barrier and emits structured `TradeIntent` objects (`ENTER_CORE_LOT_1`, `SCALE_IN_LOT_2`, `BANK_PROFIT`, `CUT_THESIS`, `RIDE_UNCAPPED`, `HOLD_POSITION`, `WAIT_IN_CASH`).
   - Evaluates Expected Value ($\mathbb{E}[\text{Net PnL}] > \text{fee}$) and asymmetric runways without touching balance or order execution APIs.
4. **`risk_engine.py` (Independent Deterministic Risk Gate — Conscience):**
   - **Core Invariant:** *"Models Propose, Risk Disposes."*
   - Independent deterministic gate evaluating `TradeIntent` against 5 non-negotiable safety laws:
     1. *Expectancy Gate:* Rejects entries with projected runway $< 0.45\%$ or reward-to-risk $< 2.0:1$.
     2. *Noise-Immune Floor Gate:* Enforces ATR-anchored structural stop buffers ($\min(P - 0.8\text{ATR}, P - \text{clamped\_risk})$).
     3. *Anti-Churn / Post-Stop Clearance:* Vetoes breakout intents proposed at or below previous invalidation exit price levels.
     4. *Scale-In / Invalidation Harmonization:* Verifies stop sits strictly below Lot 2 scale-in discount zone.
     5. *In-Situ Memory Soft Stop:* Queries live order book depth when floor is touched. Holds with noise immunity if resting bids absorb sweep ($A_i > 15.0$); approves cut only on bid collapse. Hard backstop ($0.8 \times \text{ATR}$) prevents bag-holding.
5. **`execution_manager.py` (Execution Adapters & Memory — Hands & Ledger):**
   - Clean-slate archiving: Legacy logs safely archived to `archive_legacy_trades/`. Fresh autonomous ledger starting from Trade #1.
   - Manages active thesis parameters: `scenario`, `target_price`, `invalidation_floor`, `trailing_stop`.
   - Dynamic trailing stop updates (`update_trailing_stop`) and macro target stepping (`update_target_price`).
   - Dispatches rich instant Telegram alerts on every action (Entry, Scale-in, Bank Profit, Trailing Stop Ratchet, Thesis Cut).
   - Synchronizes `bot_state.json`, `trade_journal.csv` (UTF-8-BOM Excel lock-proof), `trade_journal.md`, and `trade_history.json`.





