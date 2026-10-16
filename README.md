# btctool 2.0 ⚡
### Advanced Predictive Advisory Engine for BTC/USDT

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit App](https://static.streamlit.io/badge/streamlit_badge_black_white.svg)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**btctool 2.0** is an institutional-grade, multi-methodology quantitative advisory engine engineered for Bitcoin (BTC/USDT). Instead of emitting raw execution orders, it synthesizes three analytical brains into an ensemble trading probability dashboard and outputs a clean **Trader Advisory Report** with directional percentages (e.g., 65% Buy Probability), leaving the final risk decision in the hands of the human trader.

---

## 🧠 System Architecture

```
                                  [ Live BTC/USDT Data Feed (yfinance) ]
                                                    │
                 ┌──────────────────────────────────┼──────────────────────────────────┐
                 │                                  │                                  │
                 ▼                                  ▼                                  ▼
      ┌────────────────────┐             ┌────────────────────┐             ┌────────────────────┐
      │ The Statistical    │             │ The Momentum       │             │ The Volatility     │
      │ Brain              │             │ Brain              │             │ Brain              │
      ├────────────────────┤             ├────────────────────┤             ├────────────────────┤
      │ • Bollinger Bands  │             │ • RSI (14) slope   │             │ • ATR & ATR %      │
      │ • %B & Bandwidth   │             │ • MACD & Signal    │             │ • BB / KC Squeeze  │
      │ • Z-Score Dist.    │             │ • Hist. Accelerat. │             │ • Compression Risk │
      └─────────┬──────────┘             └─────────┬──────────┘             └─────────┬──────────┘
                │                                  │                                  │
                └───────────────────┬──────────────┴──────────────────────────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │ Ensemble Voting Engine       │
                     │ (Dynamic Probabilistic Model)│
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │   Trader Advisory Report     │
                     │  • Directional Percentages   │
                     │  • Multi-Timeframe (1H & 4H) │
                     │  • Pivots & Volatility Alert │
                     └──────────────────────────────┘
```

### 1. The Statistical Brain 📐
- **Bollinger Bands & %B**: Tracks structural positioning of price relative to the 20-period moving average and ±2 standard deviations.
- **Mean-Reversion vs Trend Probability**: Computes historical Gaussian probability distributions and evaluates ranging vs breakout regimes.
- **Price Z-Score**: Quantifies how stretched prices are relative to statistical variance.

### 2. The Momentum Brain ⚡
- **RSI (Relative Strength Index)**: Identifies oversold accumulation zones (< 30) and overbought exhaustion zones (> 70).
- **MACD (12, 26, 9)**: Monitors histogram acceleration/deceleration and zero-line crossovers to detect trend exhaustion before it becomes visually apparent.

### 3. The Volatility Brain 🌋
- **Average True Range (ATR)**: Measures normalized market dispersion and percentage of price volatility.
- **Squeeze Detection**: Compares Bollinger Bands to Keltner Channels to detect market compression (energy coiling) and alert when high-velocity breakouts are imminent.

---

## 🖥️ Web Dashboard Features

- **Persistent Legal & Compliance Notices**: Prominent disclaimers across the header, sidebar, and footer.
- **Real-Time Market Ribbon**: Current BTC/USDT spot price, 24-hour delta, and instant ensemble probabilities.
- **Trader Advisory Report Card**: Directional percentages, primary bias verdict, confidence index, pivot levels (Pivot, S1, S2, R1, R2), and actionable trade notes.
- **Interactive Technical Candlestick Chart**: Plotly chart featuring Bollinger Bands, volume, RSI subplots, and MACD histograms.
- **Multi-Timeframe Matrix**: Live side-by-side comparison of 1-Hour (Tactical) and 4-Hour (Structural) models.
- **Brain Diagnostics Explorer**: In-depth transparency into the sub-votes, formulas, and parameters driving each analytical brain.

---

## 🚀 Local Installation & Execution

1. **Clone the repository:**
   ```bash
   git clone https://github.com/aricimi/btctool-2.0.git
   cd btctool-2.0
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Predictive Advisory Engine CLI test:**
   ```bash
   python engine.py
   ```

4. **Launch the Streamlit Web Dashboard:**
   ```bash
   streamlit run app.py
   ```
   Open your browser at `http://localhost:8501`.

---

## ☁️ Cloud Deployment

### Deploy on Render
This repository includes a pre-configured `render.yaml` blueprint and `Procfile`:
1. Connect your GitHub account to [Render](https://render.com).
2. Create a new **Web Service** and link this repository (`btctool-2.0`).
3. Set:
   - **Environment:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
4. Click **Deploy**.

---

## ⚖️ Legal Disclaimer & Terms of Use

> **CRITICAL NOTICE: NOT FINANCIAL, INVESTMENT, LEGAL, OR TAX ADVICE.**
>
> 1. **Educational & Research Purpose Only:** *btctool 2.0* is an open-source quantitative research software designed to calculate statistical distributions and mathematical indicators on public market data. None of the content, calculations, directional percentages, pivot points, or commentary constitutes financial, trading, investment, tax, or legal advice.
> 2. **No Warranties & Limitation of Liability:** This software is provided under the **MIT License** on an "AS IS" and "AS AVAILABLE" basis, without warranty of any kind, express or implied. Under no circumstances shall the author, developers, or copyright holders be liable for any claim, loss, damages, or financial loss arising from the use of or reliance upon this software.
> 3. **Market Risk Acknowledgment:** Cryptocurrency trading and digital asset markets exhibit extreme price volatility and carry a substantial risk of total financial loss. Past performance and statistical modeling are no guarantee of future market results. 
> 4. **User Responsibility:** The application does not provide trade execution or custody services. Any trading or financial decisions are executed solely and independently at the user's own discretion and risk.
