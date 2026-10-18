# Autonomous Trading Directive & Execution Manifesto

> [!IMPORTANT]
> **Core Mandate:** This is the permanent memory document defining the operating philosophy of **btctool 2.0**. It replaces rigid programmer-style "rule cages" with **adaptive context awareness, asymmetric opportunity evaluation, and rapid tape reaction**. It remains a living document that can be updated, expanded, or pruned at any time.

---

## 1. The Core Philosophy: Adaptive Context & Pure Reaction

1. **No Artificial Cages or "Checklists":**
   * The market is a continuous, fluid auction. It cannot be boxed into rigid boolean conditions like *"must be a green candle"*, *"must wait 2 bars"*, or *"must wait 15 minutes"*.
   * Every rigid rule added creates a blind spot that misses legitimate moves (like a sudden V-reversal off an exhaustion low).
2. **Asymmetry Over Prediction:**
   * The bot does not claim to know the future or guess the exact bottom tick.
   * It evaluates asymmetric opportunity:
     1. Where is the immediate structural floor where this trade concept is wrong? (Risk)
     2. Where is the open room above before heavy overhead sell resistance? (Reward)
   * If the potential reward heavily outweighs the risk and buyers are active on the tape, it engages.
3. **Zero-Ego Re-Engagement:**
   * Getting out of a bad trade must never paralyze the bot from taking the next good one.
   * If the bot enters a trade and bails early because bids evaporate $\rightarrow$ that is good risk management.
   * If the market dips further, finds an exhaustion floor, and presents a fresh opportunity $\rightarrow$ **it engages again immediately without hesitation, cooldown timers, or ego**.

---

## 2. The Adaptive Context Framework (Two Trading Modes)

The bot does not treat every market environment the same way. It shifts its expectations dynamically:

### Mode A: Counter-Trend Dip Scalp Mode (Relief Bounces)
* **Context:** When the larger timeframe is in a macro downtrend or post-flush state.
* **Expectation:** The bot understands that the bounce is a **fast relief scalp**, not a multi-day moonshot.
* **Objective:** Extract the quick +0.20% to +0.50% impulse off the floor.
* **Exit Trigger:** **1-Minute Volume & Thrust Exhaustion.** The moment 1M volume dries up and candle range flattens at resistance, exit at market immediately and bank the profit.

### Mode B: Trend-Aligned Expansion Mode (Breakout Runners)
* **Context:** When market structure is breaking out with higher timeframe alignment.
* **Expectation:** Sustained directional expansion.
* **Objective:** Let runners ride, ratcheting stops to lock in guaranteed profit while trailing higher swing lows.

---

## 3. The Three Cardinal Reactive Principles

### A. The Early Bail (Preserve Capital Before the Hard Stop)
* If price is slightly underwater and the tape/order book bid support collapses, **exit immediately at market**.
* Do not passively sit and wait for the hard stop loss to be struck. 
* Preserves 99.9% of capital for the real bottom.

### B. The Breakeven Shield (The "Free Bet" Transformation)
* As soon as an entered trade moves into profit by one impulse wave:
  * **Immediately ratchet the stop loss in memory to the exact entry price.**
  * The trade is now mathematically risk-free ($0 risk). 
  * If the market dumps back down, you break even with $0 loss. If it explodes, you ride the wave for free.

### C. The 1-Minute Exhaustion Exit (Banking at the Ceiling)
* In scalp trades, monitor the 1-minute candle volume and range progression:
  * As long as 1M candles make higher highs and expand, hold.
  * The second 1M volume evaporates and candle bodies compress near upper resistance, **sell at market and bank cash immediately** before the next pullback candle opens.

---

## 4. Explicit Prohibitions (What the Bot Must NEVER Do)

1. **NO Higher-Timeframe Macro Vetoes on Micro-Scalps:**
   * A 1M/5M spot bounce cannot be held hostage by a 4H "Trend Down" indicator. 
   * Macro indicators lag for days after a dump; waiting for 4H macro permission guarantees missing every bottom.
2. **NO Candle-Shape or Color Mandates:**
   * Never require specific candle colors (e.g. "must be green") or fixed bar counts before buying. Bottoms occur in dojis, sudden wicks, consolidation shelves, and V-spikes alike.
3. **NO Fixed Post-Exit Time Quarantines:**
   * Never put the bot in a "cooldown timeout" after an exit. The next opportunity can appear 30 seconds after a flush.
4. **NO Stale Historical Anchors:**
   * Never calculate local high ceilings or dip floors from hours in the past. Projections must be strictly anchored in current price action, and projected dip floors must always be mathematically lower than the current price.

---

## 5. Review & Change Log

| Date | Proposed By | Change Description | Status |
| :--- | :--- | :--- | :--- |
| **2026-10-18** | User / Assistant | Removed hardcoded numbers from examples. Codified Adaptive Context Framework (Dip Scalp vs Expansion Runner) and 1M Volume/Thrust Exhaustion Sensor. | **Active Baseline** |
