"""
============================================================
SIGNED CLOSE POSITION — EXPLORATORY ANALYSIS
============================================================
Pure exploration, NOT hypothesis testing. No band, no hit/miss.

For every candle t, measures:

    signed_pct = (close(t+1) - close(t)) / ATR(t)

i.e. where the NEXT candle's close actually lands, as a signed
fraction of the current candle's ATR. Positive = closed higher,
negative = closed lower. This says nothing about range/TR (that
was Hypothesis 1) and nothing about touching a threshold (that
was the zone idea, now scrapped) - it's just: where does price
actually net out, one candle later.

Bucketed into 10% increments and plotted as a histogram per
timeframe, so you can see where the mass concentrates and
whether the distribution is skewed, symmetric, single- or
multi-modal.

Timeframes tested: 15min, 5min, 2min
ATR: Wilder, period configurable below (ATR_PERIOD)

No cross-session contamination - ATR and the close(t+1) lookup
are computed per trading day, same as prior scripts.

Usage:
    python signed_close_position.py
============================================================
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.append(str(Path.cwd().parent))
from lab.atr_study import AverageTrueRange, AtrType


# ============================================================
# CONFIG
# ============================================================
DATA_PATH = 'db/raw_parque/January_MNQ.csv'

ATR_PERIOD = 14          # <-- change this to adjust the ATR period everywhere
ATR_TYPE = AtrType.WLDR  # Wilder, per current focus

TIMEFRAMES = ['15min', '5min', '2min']

BUCKET_WIDTH_PCT = 10    # 10% increments, as requested
BUCKET_RANGE_PCT = 150   # buckets span -150% to +150% of ATR (widen if data needs it)

AGG_RULES = {
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum',
    'dollar_volume': 'sum',
    'session_end_date': 'last',
}


# ============================================================
# PIPELINE: per-session ATR, no cross-day contamination
# ============================================================
def build_research(raw_df, timeframe, period=ATR_PERIOD, atr_type=ATR_TYPE):
    resampled = raw_df.resample(timeframe, on='window_start').agg(AGG_RULES)
    clean = resampled.dropna(subset=['session_end_date']).reset_index()

    research_list = []

    for _, day_df in clean.groupby('session_end_date'):
        day_df = day_df.sort_values('window_start').reset_index(drop=True)
        if len(day_df) <= period:
            continue

        atr_calc = AverageTrueRange(period, atr_type, day_df)
        atr_rolling = atr_calc.get_rolling_atr()
        atr_rolling['window_start'] = pd.to_datetime(atr_rolling['window_start'])
        atr_rolling.set_index('window_start', inplace=True)

        day_research = day_df.set_index('window_start').copy()
        day_research['atr'] = atr_rolling['atr']

        # close(t+1), shifted WITHIN this session only
        day_research['close_next'] = day_research['close'].shift(-1)

        research_list.append(day_research)

    if not research_list:
        return None

    research = pd.concat(research_list).sort_index()
    research = research.dropna(subset=['atr', 'close_next']).copy()

    # The core measurement
    research['signed_pct'] = (
        (research['close_next'] - research['close']) / research['atr']
    ) * 100

    return research


# ============================================================
# BUCKETING
# ============================================================
def bucket_counts(signed_pct, width=BUCKET_WIDTH_PCT, span=BUCKET_RANGE_PCT):
    """
    Bucket signed_pct values into `width`-wide bins from -span to +span,
    plus open-ended tails for anything beyond. Returns a Series indexed
    by bucket label, in display order.
    """
    edges = np.arange(-span, span + width, width)
    labels = [f"{int(edges[i])} to {int(edges[i+1])}" for i in range(len(edges) - 1)]

    binned = pd.cut(signed_pct, bins=edges, labels=labels, include_lowest=True)
    counts = binned.value_counts().reindex(labels, fill_value=0)

    below = (signed_pct < -span).sum()
    above = (signed_pct > span).sum()

    return counts, below, above


# ============================================================
# REPORTING
# ============================================================
def report(research, label):
    sp = research['signed_pct']
    print(f"\n--- {label} ---")
    print(f"n = {len(sp)}")
    print(sp.describe().round(2))
    print(f"skew: {sp.skew():.3f}   "
          f"% positive closes: {(sp > 0).mean()*100:.1f}%   "
          f"% negative closes: {(sp < 0).mean()*100:.1f}%   "
          f"% exactly 0: {(sp == 0).mean()*100:.2f}%")

    counts, below, above = bucket_counts(sp)
    print(f"\nTop 5 buckets by frequency:")
    print(counts.sort_values(ascending=False).head(5).to_string())
    if below or above:
        print(f"(beyond +/-{BUCKET_RANGE_PCT}%: {below} below, {above} above)")


# ============================================================
# PLOTTING
# ============================================================
def plot_all(results):
    fig, axes = plt.subplots(1, len(results), figsize=(6 * len(results), 5.5),
                              sharey=False)
    if len(results) == 1:
        axes = [axes]

    for ax, (label, research) in zip(axes, results.items()):
        sp = research['signed_pct']
        counts, below, above = bucket_counts(sp)

        # Color bars by bucket midpoint sign (red = negative, green = positive)
        edges = np.arange(-BUCKET_RANGE_PCT, BUCKET_RANGE_PCT + BUCKET_WIDTH_PCT,
                          BUCKET_WIDTH_PCT)
        midpoints = [(edges[i] + edges[i+1]) / 2 for i in range(len(edges) - 1)]
        colors = ['indianred' if m < 0 else 'seagreen' for m in midpoints]

        ax.bar(range(len(counts)), counts.values, color=colors, edgecolor='black',
               alpha=0.8)
        ax.axvline(len(counts) / 2 - 0.5, color='black', linestyle='--',
                   linewidth=1.5, label='0% (no move)')

        # Sparse tick labels so it's readable
        tick_step = max(1, len(counts) // 10)
        ax.set_xticks(range(0, len(counts), tick_step))
        ax.set_xticklabels(
            [counts.index[i].split(' to ')[1] for i in range(0, len(counts), tick_step)],
            rotation=45, ha='right'
        )

        ax.set_xlabel('Signed close position (% of ATR)')
        ax.set_ylabel('Frequency')
        ax.set_title(f'{label}  (n={len(sp)})\n'
                     f'skew={sp.skew():.2f}, '
                     f'+{(sp>0).mean()*100:.0f}% / -{(sp<0).mean()*100:.0f}%')
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, axis='y')

    plt.tight_layout()
    plt.show()


def plot_overlay(results):
    """Overlay all timeframes' distributions (as % of sample, not raw count)
    on one axis so their shapes are directly comparable."""
    plt.figure(figsize=(11, 6))

    for label, research in results.items():
        sp = research['signed_pct']
        counts, below, above = bucket_counts(sp)
        pct = counts / counts.sum() * 100
        edges = np.arange(-BUCKET_RANGE_PCT, BUCKET_RANGE_PCT + BUCKET_WIDTH_PCT,
                          BUCKET_WIDTH_PCT)
        midpoints = [(edges[i] + edges[i+1]) / 2 for i in range(len(edges) - 1)]
        plt.plot(midpoints, pct.values, marker='o', markersize=3,
                 label=f'{label} (n={len(sp)})', linewidth=1.8)

    plt.axvline(0, color='black', linestyle='--', linewidth=1.5)
    plt.xlabel('Signed close position (% of ATR)')
    plt.ylabel('% of candles')
    plt.title('Where does the next candle close, relative to ATR? (overlay)')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.xlim(-100, 100)
    plt.show()


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 70)
    print("SIGNED CLOSE POSITION — EXPLORATORY ANALYSIS")
    print(f"  ATR: Wilder, period={ATR_PERIOD}")
    print(f"  Timeframes: {TIMEFRAMES}")
    print(f"  Bucket width: {BUCKET_WIDTH_PCT}%")
    print("=" * 70)

    raw_df = pd.read_csv(DATA_PATH)
    raw_df['window_start'] = pd.to_datetime(raw_df['window_start'])

    results = {}
    for tf in TIMEFRAMES:
        research = build_research(raw_df, tf)
        if research is None or len(research) == 0:
            print(f"{tf}: not enough data, skipping")
            continue
        results[tf] = research
        report(research, tf)

    if not results:
        print("No results to plot.")
        return

    plot_all(results)
    plot_overlay(results)

    for tf, research in results.items():
        out_path = f'signed_close_position_{tf}.csv'
        research[['close', 'atr', 'close_next', 'signed_pct',
                  'session_end_date']].to_csv(out_path)
        print(f"Saved {out_path}")


if __name__ == '__main__':
    main()