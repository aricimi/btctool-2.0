import json
import math
import datetime
import csv
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots

with open('historical_btc_180d_1m.json', 'r', encoding='utf-8') as f:
    hist = json.load(f)
bars_1m = sorted(hist, key=lambda x: x['ts'])

def resample_bars(bars, tf_seconds):
    resampled = []
    curr_bucket = None
    curr_bar = None
    for b in bars:
        bucket = (b['ts'] // tf_seconds) * tf_seconds
        if curr_bucket != bucket:
            if curr_bar is not None: resampled.append(curr_bar)
            curr_bucket = bucket
            curr_bar = {
                'ts': bucket,
                'datetime': datetime.datetime.fromtimestamp(bucket, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
                'open': b['open'], 'high': b['high'], 'low': b['low'], 'close': b['close'], 'vol': b.get('vol', 0.0)
            }
        else:
            curr_bar['high'] = max(curr_bar['high'], b['high'])
            curr_bar['low'] = min(curr_bar['low'], b['low'])
            curr_bar['close'] = b['close']
            curr_bar['vol'] += b.get('vol', 0.0)
    if curr_bar is not None: resampled.append(curr_bar)
    return resampled

bars_15m = resample_bars(bars_1m, 900)
highs = [b['high'] for b in bars_15m]
lows = [b['low'] for b in bars_15m]
closes = [b['close'] for b in bars_15m]
opens = [b['open'] for b in bars_15m]
vols = [b['vol'] for b in bars_15m]
n = len(bars_15m)

bars_4h = resample_bars(bars_1m, 14400)
closes_4h = [b['close'] for b in bars_4h]
highs_4h = [b['high'] for b in bars_4h]
n_4h = len(bars_4h)
ema50_4h = [0.0] * n_4h
for i in range(n_4h):
    if i == 0: ema50_4h[i] = closes_4h[i]
    else: ema50_4h[i] = closes_4h[i] * (2/51) + ema50_4h[i-1] * (49/51)

map_15m_to_4h = []
curr_4h_idx = 0
for b in bars_15m:
    while curr_4h_idx < len(bars_4h) - 1 and bars_4h[curr_4h_idx + 1]['ts'] <= b['ts']:
        curr_4h_idx += 1
    map_15m_to_4h.append(curr_4h_idx)

# 1H Timeframe for Multi-Timeframe Trend Shield (v4.1.0)
bars_1h = resample_bars(bars_1m, 3600)
closes_1h = [b['close'] for b in bars_1h]
n_1h = len(bars_1h)
ema20_1h = [0.0] * n_1h
for i in range(n_1h):
    if i == 0: ema20_1h[i] = closes_1h[i]
    else: ema20_1h[i] = closes_1h[i] * (2/21) + ema20_1h[i-1] * (19/21)

map_15m_to_1h = []
curr_1h_idx = 0
for b in bars_15m:
    while curr_1h_idx < len(bars_1h) - 1 and bars_1h[curr_1h_idx + 1]['ts'] <= b['ts']:
        curr_1h_idx += 1
    map_15m_to_1h.append(curr_1h_idx)

# 15M Bollinger Bands (20, 2)
bb_mid = [0.0] * n
bb_upper = [0.0] * n
bb_lower = [0.0] * n
for i in range(19, n):
    mean = sum(closes[i-19:i+1]) / 20.0
    var = sum((c - mean)**2 for c in closes[i-19:i+1]) / 20.0
    std = math.sqrt(var)
    bb_mid[i] = mean
    bb_upper[i] = mean + 2.0 * std
    bb_lower[i] = mean - 2.0 * std

# ATR(14)
tr = [0.0] * n
for i in range(n):
    if i == 0: tr[i] = highs[i] - lows[i]
    else: tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
atr = [0.0] * n
for i in range(13, n):
    if i == 13: atr[i] = sum(tr[:14]) / 14.0
    else: atr[i] = (atr[i-1] * 13.0 + tr[i]) / 14.0

vol_sma20 = [0.0] * n
for i in range(19, n):
    vol_sma20[i] = sum(vols[i-19:i+1]) / 20.0

# 15M RSI(14)
rsi = [50.0] * n
gains = [0.0] * n
losses = [0.0] * n
for i in range(1, n):
    diff = closes[i] - closes[i-1]
    gains[i] = max(0.0, diff)
    losses[i] = max(0.0, -diff)
if n > 14:
    avg_g = sum(gains[1:15]) / 14.0
    avg_l = sum(losses[1:15]) / 14.0
    for i in range(14, n):
        if i > 14:
            avg_g = (avg_g * 13.0 + gains[i]) / 14.0
            avg_l = (avg_l * 13.0 + losses[i]) / 14.0
        rs = avg_g / avg_l if avg_l > 0 else 999.0
        rsi[i] = 100.0 - (100.0 / (1.0 + rs))

def run_simulation():
    capital = 1000.0
    peak = 1000.0
    max_dd = 0.0
    pos = None
    trades = []
    trail_atr = 4.5
    stop_pct = 0.015
    min_vr = 2.2
    min_clv = 0.70
    
    for i in range(192, n):
        b = bars_15m[i]
        dt = b['datetime']
        atr_val = atr[i]
        
        # Position Exit Management
        if pos is not None:
            entry_p = pos['entry_p']
            bars_held = i - pos['entry_idx']
            exited = False
            exit_p = None
            exit_reason = None
            
            if b['high'] > pos['peak_p']:
                pos['peak_p'] = b['high']
            peak_gain_pct = (pos['peak_p'] - entry_p) / entry_p * 100.0
            
            # 1. MEAN REVERSION EXIT (For 24H Sweep Reclaims)
            if pos['type'] == 'SWEEP_24H_RECLAIM':
                if (b['high'] - entry_p) >= (2.0 * atr_val):
                    pos['hard_stop'] = max(pos['hard_stop'], entry_p * 1.002) # lock in fee
                tp_p = entry_p + (2.5 * atr_val)
                if b['high'] >= tp_p:
                    exit_p = tp_p
                    exit_reason = "TAKE_PROFIT_2.5_ATR"
                    exited = True
                elif b['low'] <= pos['hard_stop']:
                    exit_p = pos['hard_stop']
                    exit_reason = "HARD_STOP"
                    exited = True
                elif bars_held >= 32:
                    exit_p = b['close']
                    exit_reason = "TIME_STOP_8H"
                    exited = True

            # 2. CAPITULATION SWEEP GRADUATED RATCHET (For 48H Sweeps: v4.1.0)
            elif pos['type'] == 'CAPITULATION_SWEEP_48H':
                if peak_gain_pct >= 3.0:
                    pos['hard_stop'] = max(pos['hard_stop'], entry_p * 1.020) # lock +2.0%
                elif peak_gain_pct >= 2.0:
                    pos['hard_stop'] = max(pos['hard_stop'], entry_p * 1.010) # lock +1.0%
                elif peak_gain_pct >= 1.0:
                    pos['hard_stop'] = max(pos['hard_stop'], entry_p * 1.002) # lock fee cover

                new_floor = b['high'] - (trail_atr * atr_val)
                if new_floor > pos['trail_floor']:
                    pos['trail_floor'] = new_floor
                if bars_held >= 1:
                    if b['low'] <= pos['hard_stop']:
                        exit_p = pos['hard_stop']
                        exit_reason = "SWEEP_RATCHET_STOP" if pos['hard_stop'] > entry_p else "HARD_STOP"
                        exited = True
                    elif b['low'] <= pos['trail_floor']:
                        exit_p = pos['trail_floor']
                        exit_reason = "TRAILING_ATR"
                        exited = True

            # 3. BREAKOUT RUNNERS: 1H EMA20 TREND SHIELD (v4.1.0)
            else:
                if peak_gain_pct >= 2.5:
                    # Guaranteed profit floor (+1.5% profit protection)
                    pos['hard_stop'] = max(pos['hard_stop'], entry_p * 1.015)
                    h1_idx = map_15m_to_1h[i]
                    is_1h_close = (i % 4 == 3)
                    if is_1h_close and (bars_1h[h1_idx]['close'] < ema20_1h[h1_idx]):
                        exit_p = b['close']
                        exit_reason = "1H_EMA20_TREND_EXIT"
                        exited = True
                    elif b['low'] <= pos['hard_stop']:
                        exit_p = pos['hard_stop']
                        exit_reason = "PROFIT_PROTECTION_STOP"
                        exited = True
                else:
                    new_floor = b['high'] - (trail_atr * atr_val)
                    if new_floor > pos['trail_floor']:
                        pos['trail_floor'] = new_floor
                    if bars_held >= 1:
                        if b['low'] <= pos['trail_floor']:
                            exit_p = pos['trail_floor']
                            exit_reason = "TRAILING_ATR"
                            exited = True
                        elif b['low'] <= pos['hard_stop']:
                            exit_p = pos['hard_stop']
                            exit_reason = "HARD_STOP"
                            exited = True
                        
            if exited:
                gross = (exit_p - entry_p) / entry_p
                net = gross - 0.0020
                pnl = capital * net
                capital += pnl
                if capital > peak: peak = capital
                dd = (peak - capital) / peak * 100.0
                if dd > max_dd: max_dd = dd
                trades.append({
                    'id': len(trades) + 1,
                    'type': pos['type'],
                    'entry_idx': pos['entry_idx'],
                    'exit_idx': i,
                    'entry_t': pos['entry_t'],
                    'exit_t': dt,
                    'entry_p': entry_p,
                    'exit_p': exit_p,
                    'gross_pct': gross * 100.0,
                    'net_pct': net * 100.0,
                    'pnl': pnl,
                    'cap': capital,
                    'reason': exit_reason,
                    'bars': bars_held,
                    'minutes': bars_held * 15,
                    'rsi_entry': pos['rsi_entry'],
                    'vr_entry': pos['vr_entry'],
                    'dist_ema50': pos['dist_ema50']
                })
                pos = None
                continue
                
        # Trigger Evaluation
        if pos is None:
            h4_idx = map_15m_to_4h[i]
            is_bull_4h = b['close'] > ema50_4h[h4_idx]
            dt_obj = datetime.datetime.fromtimestamp(b['ts'], tz=datetime.timezone.utc)
            is_weekend = dt_obj.weekday() in [5, 6]
            
            v_sma = vol_sma20[i-1]
            vr = b['vol'] / v_sma if v_sma > 0 else 1.0
            body_pct = (b['close'] - b['open']) / b['open'] * 100.0
            rng = b['high'] - b['low']
            clv = (b['close'] - b['low']) / rng if rng > 0 else 0.5
            dist_ema = (b['close'] - ema50_4h[h4_idx]) / ema50_4h[h4_idx] * 100.0
            
            # TRIGGER 1: Macro 48h Capitulation Sweep (Extreme volume)
            sl_48h = min(lows[i-192:i])
            if b['low'] < sl_48h and b['close'] > sl_48h:
                if vr >= 2.5 and body_pct >= 0.20 and clv >= 0.70:
                    take_sweep = is_bull_4h or (vr >= 3.5)
                    if take_sweep:
                        pos = {
                            'type': 'CAPITULATION_SWEEP_48H', 'entry_idx': i, 'entry_t': dt, 'entry_p': b['close'],
                            'hard_stop': b['close'] * (1.0 - stop_pct), 'trail_floor': b['close'] - (trail_atr * atr_val),
                            'rsi_entry': rsi[i], 'vr_entry': vr, 'dist_ema50': dist_ema, 'peak_p': b['close']
                        }
                        continue

            # TRIGGER 2: 24H Liquidity Sweep & Reclaim (Pin Bar / Hammer Rejection)
            if is_bull_4h:
                sl_24h = min(lows[i-96:i])
                if b['low'] < sl_24h and b['close'] > sl_24h:
                    if vr >= 2.5 and clv >= 0.80 and body_pct >= -0.10:
                        pos = {
                            'type': 'SWEEP_24H_RECLAIM', 'entry_idx': i, 'entry_t': dt, 'entry_p': b['close'],
                            'hard_stop': min(b['low'] * 0.998, b['close'] * (1.0 - stop_pct)),
                            'trail_floor': b['close'] - (trail_atr * atr_val),
                            'rsi_entry': rsi[i], 'vr_entry': vr, 'dist_ema50': dist_ema, 'peak_p': b['close']
                        }
                        continue

            # Standard Breakouts: Block weekends
            if is_weekend:
                continue
                
            start_4h = max(0, h4_idx - 42)
            res_4h = max(highs_4h[start_4h:h4_idx+1]) if h4_idx > start_4h else b['close'] * 1.05
            headroom = (res_4h - b['close']) / b['close'] * 100.0
            
            # Multi-Horizon Breakouts (v4.2.0: Mandatory >= +0.80% 4H EMA50 Trend Clearance Gate)
            if is_bull_4h and clv >= min_clv:
                sh_48h = max(highs[i-192:i])
                is_48h_break = b['close'] > sh_48h and closes[i-1] <= sh_48h
                if is_48h_break:
                    if dist_ema < 0.80:
                        # Vetoed as low-momentum range chop; suppress fallthrough to shorter breakout horizons
                        continue
                    elif vr >= min_vr and body_pct >= 0.25 and headroom >= 0.5:
                        pos = {
                            'type': 'MACRO_BREAK_48H', 'entry_idx': i, 'entry_t': dt, 'entry_p': b['close'],
                            'hard_stop': b['close'] * (1.0 - stop_pct), 'trail_floor': b['close'] - (trail_atr * atr_val),
                            'rsi_entry': rsi[i], 'vr_entry': vr, 'dist_ema50': dist_ema, 'peak_p': b['close']
                        }
                        continue

                sh_24h = max(highs[i-96:i])
                if b['close'] > sh_24h and closes[i-1] <= sh_24h:
                    if vr >= min_vr and body_pct >= 0.25 and headroom >= 0.8:
                        pos = {
                            'type': 'BREAK_24H', 'entry_idx': i, 'entry_t': dt, 'entry_p': b['close'],
                            'hard_stop': b['close'] * (1.0 - stop_pct), 'trail_floor': b['close'] - (trail_atr * atr_val),
                            'rsi_entry': rsi[i], 'vr_entry': vr, 'dist_ema50': dist_ema, 'peak_p': b['close']
                        }
                        continue

                sh_12h = max(highs[i-48:i])
                if b['close'] > sh_12h and closes[i-1] <= sh_12h:
                    if vr >= min_vr and body_pct >= 0.25 and headroom >= 1.0:
                        # Bollinger Upper Band Exhaustion Shield
                        if b['close'] <= bb_upper[i]:
                            pos = {
                                'type': 'BREAK_12H', 'entry_idx': i, 'entry_t': dt, 'entry_p': b['close'],
                                'hard_stop': b['close'] * (1.0 - stop_pct), 'trail_floor': b['close'] - (trail_atr * atr_val),
                                'rsi_entry': rsi[i], 'vr_entry': vr, 'dist_ema50': dist_ema, 'peak_p': b['close']
                            }
                            continue

    wins = [t for t in trades if t['net_pct'] > 0]
    losses = [t for t in trades if t['net_pct'] <= 0]
    wr = len(wins)/len(trades)*100.0 if trades else 0.0
    gp = sum(t['pnl'] for t in wins)
    gl = sum(abs(t['pnl']) for t in losses)
    pf = gp/gl if gl > 0 else 999.0
    ret = (capital - 1000.0) / 10.0
    
    print("="*80)
    print("FINAL INTEGRATED ARCHITECTURE SIMULATION RESULTS (180 DAYS):")
    print(f"Total Trades: {len(trades)} | Win Rate: {wr:.1f}% | Profit Factor: {pf:.2f} | MaxDD: -{max_dd:.1f}% | Final Capital: €{capital:.2f} ({ret:+.2f}%)")
    by_type = {}
    for t in trades:
        by_type[t['type']] = by_type.get(t['type'], 0) + 1
    print(f"Breakdown: {by_type}")
    print("="*80)
    
    # Export to Trade_Log.csv
    csv_file = 'Trade_Log.csv'
    fieldnames = [
        'Trade_ID', 'Horizon_Type', 'Entry_Timestamp_UTC', 'Exit_Timestamp_UTC',
        'Entry_Price', 'Exit_Price', 'Hold_Duration_Bars', 'Hold_Duration_Minutes',
        'RSI_15M_At_Entry', 'Volume_Multiplier_At_Entry', 'Dist_From_4H_EMA50_Pct_At_Entry',
        'Gross_PnL_Pct', 'Net_PnL_Pct', 'PnL_EUR', 'Exit_Reason', 'Capital_After_Trade_EUR'
    ]
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for t in trades:
            writer.writerow({
                'Trade_ID': f"TRADE_{t['id']:02d}",
                'Horizon_Type': t['type'],
                'Entry_Timestamp_UTC': t['entry_t'],
                'Exit_Timestamp_UTC': t['exit_t'],
                'Entry_Price': f"{t['entry_p']:.2f}",
                'Exit_Price': f"{t['exit_p']:.2f}",
                'Hold_Duration_Bars': t['bars'],
                'Hold_Duration_Minutes': t['minutes'],
                'RSI_15M_At_Entry': f"{t['rsi_entry']:.1f}",
                'Volume_Multiplier_At_Entry': f"{t['vr_entry']:.2f}x",
                'Dist_From_4H_EMA50_Pct_At_Entry': f"{t['dist_ema50']:+.2f}%",
                'Gross_PnL_Pct': f"{t['gross_pct']:+.2f}%",
                'Net_PnL_Pct': f"{t['net_pct']:+.2f}%",
                'PnL_EUR': f"€{t['pnl']:+.2f}",
                'Exit_Reason': t['reason'],
                'Capital_After_Trade_EUR': f"€{t['cap']:.2f}"
            })
    print(f"Updated {csv_file} with {len(trades)} trades.")

    # Generate Plotly charts
    os.makedirs('trade_charts', exist_ok=True)
    for t in trades:
        e_idx = t['entry_idx']
        x_idx = t['exit_idx']
        start_idx = max(0, e_idx - 50)
        end_idx = min(n, x_idx + 50)
        
        sub_bars = bars_15m[start_idx:end_idx]
        dts = [b['datetime'] for b in sub_bars]
        sub_highs = highs[start_idx:end_idx]
        sub_lows = lows[start_idx:end_idx]
        sub_opens = opens[start_idx:end_idx]
        sub_closes = closes[start_idx:end_idx]
        sub_vols = vols[start_idx:end_idx]
        
        sub_ema50 = [ema50_4h[map_15m_to_4h[i]] for i in range(start_idx, end_idx)]
        sub_trail = [None] * len(sub_bars)
        
        run_trail = t['entry_p'] - (trail_atr * atr[e_idx])
        for idx_rel, abs_i in enumerate(range(start_idx, end_idx)):
            if e_idx <= abs_i <= x_idx:
                new_fl = highs[abs_i] - (trail_atr * atr[abs_i])
                if new_fl > run_trail: run_trail = new_fl
                sub_trail[idx_rel] = run_trail
                
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
        fig.add_trace(go.Candlestick(
            x=dts, open=sub_opens, high=sub_highs, low=sub_lows, close=sub_closes,
            name='15M BTC Price', increasing_line_color='#00FFA3', decreasing_line_color='#FF4B4B'
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(x=dts, y=sub_ema50, mode='lines', line=dict(color='#38bdf8', width=2), name='4H EMA50 Shield'), row=1, col=1)
        if t['type'] != 'SWEEP_24H_RECLAIM':
            fig.add_trace(go.Scatter(x=dts, y=sub_trail, mode='lines', line=dict(color='#fbbf24', width=2, dash='dot'), name='Trailing ATR Floor'), row=1, col=1)
            
        color_res = '#00FFA3' if t['net_pct'] > 0 else '#FF4B4B'
        fig.add_annotation(
            x=t['entry_t'], y=t['entry_p'], text=f"BUY: ${t['entry_p']:,.1f}",
            showarrow=True, arrowhead=2, arrowcolor='#00FFA3', arrowsize=1.5, arrowwidth=2,
            bgcolor='#131B2E', bordercolor='#00FFA3', font=dict(color='#00FFA3', size=11, family='monospace'),
            ay=35, row=1, col=1
        )
        fig.add_annotation(
            x=t['exit_t'], y=t['exit_p'], text=f"EXIT: ${t['exit_p']:,.1f} ({t['net_pct']:+.2f}%)",
            showarrow=True, arrowhead=2, arrowcolor=color_res, arrowsize=1.5, arrowwidth=2,
            bgcolor='#131B2E', bordercolor=color_res, font=dict(color=color_res, size=11, family='monospace'),
            ay=-35, row=1, col=1
        )
        
        vol_colors = ['#00FFA3' if sub_closes[k] >= sub_opens[k] else '#FF4B4B' for k in range(len(sub_bars))]
        fig.add_trace(go.Bar(x=dts, y=sub_vols, marker_color=vol_colors, name='Volume', opacity=0.8), row=2, col=1)
        
        fig.update_layout(
            title=f"<b>Trade #{t['id']:02d}: {t['type']}</b> | Net PnL: <b style='color:{color_res}'>{t['net_pct']:+.2f}% (€{t['pnl']:+.2f})</b> | Hold: {t['bars']} bars ({t['minutes']}m) | Exit: {t['reason']}",
            template='plotly_dark', paper_bgcolor='#0A0E17', plot_bgcolor='#0F172A',
            xaxis_rangeslider_visible=False, height=650, margin=dict(l=50, r=50, t=70, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        chart_path = f"trade_charts/trade_{t['id']:02d}.html"
        fig.write_html(chart_path, include_plotlyjs='cdn')

    print(f"Updated all {len(trades)} trade charts in trade_charts/")

    # Master visualizer
    options_html = ""
    for t in trades:
        res_str = f"+{t['net_pct']:.2f}%" if t['net_pct'] > 0 else f"{t['net_pct']:.2f}%"
        color = "#00FFA3" if t['net_pct'] > 0 else "#FF4B4B"
        options_html += f'<option value="trade_{t["id"]:02d}.html">Trade #{t["id"]:02d}: {t["type"]} ({res_str}) - {t["entry_t"][:10]}</option>\n'

    master_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>btctool 2.0 - Integrated Dual-Engine Trade Visualizer (45 Trades)</title>
    <style>
        body {{
            margin: 0; padding: 0; background-color: #0A0E17; color: #E2E8F0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
        }}
        .header {{
            padding: 12px 24px; background-color: #131B2E; border-bottom: 1px solid #1E293B;
            display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 15px;
        }}
        .title {{ font-size: 18px; font-weight: 700; color: #00FFA3; }}
        .controls {{ display: flex; align-items: center; gap: 10px; }}
        select, button {{
            background-color: #0F172A; color: #00FFA3; border: 1px solid #334155;
            padding: 8px 14px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer;
        }}
        button:hover {{ background-color: #1E293B; border-color: #00FFA3; }}
        iframe {{ width: 100%; height: calc(100vh - 65px); border: none; display: block; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">⚡ btctool 2.0 · Integrated Dual-Engine Visualizer (45 Trades · 180 Days Live BTC)</div>
        <div class="controls">
            <button onclick="prevTrade()">◀ Previous</button>
            <select id="tradeSelect" onchange="loadTrade(this.value)">
                {options_html}
            </select>
            <button onclick="nextTrade()">Next ▶</button>
        </div>
    </div>
    <iframe id="chartFrame" src="trade_charts/trade_01.html"></iframe>
    <script>
        function loadTrade(filename) {{
            document.getElementById('chartFrame').src = 'trade_charts/' + filename;
        }}
        function prevTrade() {{
            const sel = document.getElementById('tradeSelect');
            if (sel.selectedIndex > 0) {{ sel.selectedIndex--; loadTrade(sel.value); }}
        }}
        function nextTrade() {{
            const sel = document.getElementById('tradeSelect');
            if (sel.selectedIndex < sel.options.length - 1) {{ sel.selectedIndex++; loadTrade(sel.value); }}
        }}
        window.addEventListener('keydown', function(e) {{
            if (e.key === 'ArrowLeft') prevTrade();
            else if (e.key === 'ArrowRight') nextTrade();
        }});
    </script>
</body>
</html>"""
    with open('trades_visualizer.html', 'w', encoding='utf-8') as f:
        f.write(master_html)
    print("Updated trades_visualizer.html.")

if __name__ == '__main__':
    run_simulation()
