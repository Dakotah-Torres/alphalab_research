# ============================================================
# SETUP
# ============================================================
import sys
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

sys.path.append(str(Path.cwd().parent))
from lab.atr_study import AverageTrueRange, AtrType

raw_df = pd.read_csv('db/raw_parque/January_MNQ.csv')
raw_df['window_start'] = pd.to_datetime(raw_df['window_start'])

agg_rules = {
    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
    'volume': 'sum', 'dollar_volume': 'sum', 'session_end_date': 'last'
}

ratio_cols = [
    ('ratio_wilder_tr', 'Wilder ATR vs True Range'),
    ('ratio_simple_tr', 'Simple ATR vs True Range'),
    ('ratio_wilder_range', 'Wilder ATR vs Range (H-L)'),
    ('ratio_simple_range', 'Simple ATR vs Range (H-L)')
]

# ============================================================
# FUNCTION: build the clean, ratio-ready research df for one timeframe
# ============================================================
def build_research(raw_df, timeframe, period=14):
    resampled = raw_df.resample(timeframe, on='window_start').agg(agg_rules)
    clean = resampled.dropna(subset=['session_end_date']).reset_index()

    research_list = []
    for session_date, day_df in clean.groupby('session_end_date'):
        day_df = day_df.sort_values('window_start').reset_index(drop=True)

        # Skip sessions too short to even build one warm-up window
        if len(day_df) <= period:
            continue

        wild_atr = AverageTrueRange(period, AtrType.WLDR, day_df)
        simp_atr = AverageTrueRange(period, AtrType.SIMP, day_df)
        tr_calc = AverageTrueRange(period, AtrType.WLDR, day_df)

        wild_atr_rolling = wild_atr.get_rolling_atr()
        simp_atr_rolling = simp_atr.get_rolling_atr()
        tr_all = tr_calc.get_true_range()

        for piece in (wild_atr_rolling, simp_atr_rolling, tr_all):
            piece['window_start'] = pd.to_datetime(piece['window_start'])
            piece.set_index('window_start', inplace=True)

        day_research = day_df.set_index('window_start').copy()
        day_research['atr_wilder'] = wild_atr_rolling['atr']
        day_research['atr_simple'] = simp_atr_rolling['atr']
        day_research['tr'] = tr_all['tr']
        day_research['range'] = day_research['high'] - day_research['low']
        day_research['tr_next'] = day_research['tr'].shift(-1)
        day_research['range_next'] = day_research['range'].shift(-1)

        research_list.append(day_research)

    if not research_list:
        return None

    research = pd.concat(research_list).sort_index()
    research_clean = research.dropna(subset=['atr_wilder', 'atr_simple', 'tr_next', 'range_next']).copy()

    research_clean['ratio_wilder_tr'] = research_clean['tr_next'] / research_clean['atr_wilder']
    research_clean['ratio_simple_tr'] = research_clean['tr_next'] / research_clean['atr_simple']
    research_clean['ratio_wilder_range'] = research_clean['range_next'] / research_clean['atr_wilder']
    research_clean['ratio_simple_range'] = research_clean['range_next'] / research_clean['atr_simple']

    return research_clean

# ============================================================
# FUNCTION: sweep band widths, return capture-rate curves
# ============================================================
def sweep_bands(research_clean, band_widths=np.arange(0.01, 1.01, 0.01)):
    avg_tr = research_clean['tr_next'].mean()
    naive_ratio = research_clean['tr_next'] / avg_tr

    capture_rates = {col: [] for col, _ in ratio_cols}
    naive_capture_rates = []

    for w in band_widths:
        lower, upper = 1 - w, 1 + w
        for col, _ in ratio_cols:
            capture_rates[col].append(research_clean[col].between(lower, upper).mean() * 100)
        naive_capture_rates.append(naive_ratio.between(lower, upper).mean() * 100)

    return capture_rates, naive_capture_rates

# ============================================================
# RUN ACROSS TIMEFRAMES
# ============================================================
timeframes = {
    '1H': '1h', '30min': '30min', '15min': '15min',
    '5min': '5min', '2min': '2min', '1min': '1min'
}

band_widths = np.arange(0.01, 1.01, 0.01)
results_by_tf = {}

for label, freq in timeframes.items():
    rc = build_research(raw_df, freq)
    if rc is None or len(rc) < 30:
        print(f"{label}: not enough data, skipping")
        continue
    capture_rates, naive_rates = sweep_bands(rc, band_widths)
    results_by_tf[label] = {
        'research_clean': rc,
        'capture_rates': capture_rates,
        'naive_rates': naive_rates,
        'n': len(rc)
    }
    print(f"{label}: {len(rc)} valid candles")

# ============================================================
# VISUAL — compare one ratio type (Wilder TR) across all timeframes
# ============================================================
plt.figure(figsize=(13, 8))
for label in results_by_tf:
    rates = results_by_tf[label]['capture_rates']['ratio_wilder_tr']
    plt.plot(band_widths * 100, rates, label=f"{label} (n={results_by_tf[label]['n']})", linewidth=2)

plt.axhline(70, color='red', linestyle=':', label='70% threshold')
plt.xlabel('Band half-width (%)')
plt.ylabel('% of candles captured')
plt.title('Wilder ATR vs True Range — capture rate by timeframe')
plt.legend()
plt.grid(alpha=0.3)
plt.show()

# ============================================================
# NUMERIC — optimal band width to hit 70%, per timeframe, per ratio type
# ============================================================
print("\n" + "="*70)
print("BAND WIDTH NEEDED TO HIT 70% CAPTURE, BY TIMEFRAME")
print("="*70)

summary_rows = []
for label in results_by_tf:
    rc = results_by_tf[label]['research_clean']
    capture_rates = results_by_tf[label]['capture_rates']
    naive_rates = np.array(results_by_tf[label]['naive_rates'])

    naive_idx = np.argmax(naive_rates >= 70)
    naive_width = band_widths[naive_idx] * 100 if naive_rates[naive_idx] >= 70 else None

    for col, title in ratio_cols:
        rates = np.array(capture_rates[col])
        idx = np.argmax(rates >= 70)
        if rates[idx] >= 70:
            width = band_widths[idx] * 100
            edge = (naive_width - width) if naive_width else None
        else:
            width = None
            edge = None
        summary_rows.append({
            'timeframe': label, 'ratio_type': title,
            'n': results_by_tf[label]['n'],
            'band_width_for_70pct': width,
            'edge_vs_naive': edge
        })

summary_df = pd.DataFrame(summary_rows)
print(summary_df.to_string(index=False))