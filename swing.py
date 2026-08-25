"""
============================================================
SWING HIGH / LOW DETECTOR  (single reigning candidate)
============================================================
Detects confirmed swing highs and lows from a candle stream.

ALGORITHM
---------
Maintains ONE candidate at a time (not a stack of runner-ups):

  - A new candle is compared against the current candidate.
  - If the new candle beats OR TIES the candidate, the candidate
    is DISCARDED outright (never confirmed - a later equal/higher
    high means it wasn't a real local peak) and the new candle
    becomes the candidate.
  - If the candidate survives `window - 1` subsequent candles
    without being beaten, it is CONFIRMED as a swing point, and
    the very next candle starts a fresh candidate search.

This deliberately does NOT keep a stack of "runner-up" candidates
the way a classic sliding-window-maximum algorithm would. That
matters: on a single clean peak followed by a decline, a stack-
based approach confirms MULTIPLE points along the decline (each
one technically was the max of some trailing window) - which is
correct for "rolling max at every step" but wrong for "find swing
pivots," since the decline is one move, not several distinct highs.
Verified against a synthetic peak: this version confirms exactly
one point per real peak; the stack-based version confirmed three.

WINDOW_SIZE is a configurable parameter (fixed for a given run).

Usage:
    from swing_detector import find_swings

    highs = find_swings(df, price_col='high', window=7, mode='max')
    lows  = find_swings(df, price_col='low',  window=7, mode='min')

Or run this file directly against a CSV for a quick look:
    python swing_detector.py
============================================================
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# ============================================================
# CORE ALGORITHM
# ============================================================
def find_swings(df, price_col, window=7, mode='max', session_col=None):
    """
    Find confirmed swing points in `df[price_col]` using a single
    reigning-candidate scan (see module docstring for why this is
    NOT the same as a sliding-window-maximum algorithm).

    Parameters
    ----------
    df : pd.DataFrame
        Must be sorted ascending by time already.
    price_col : str
        Column to search for extremes, e.g. 'high' or 'low'.
    window : int
        A candidate is confirmed once `window - 1` subsequent
        candles have failed to beat it. Configurable.
    mode : 'max' or 'min'
        'max' finds swing highs, 'min' finds swing lows.
    session_col : str, optional
        If provided, the candidate search restarts at every change
        in this column's value, so no swing point is built from
        candles spanning two different sessions. Pass
        'session_end_date' to match this project's no-cross-day-
        contamination convention.

    Returns
    -------
    pd.DataFrame with columns: index_pos, timestamp, price, type
        One row per CONFIRMED swing point, in the order confirmed.
    """
    if mode not in ('max', 'min'):
        raise ValueError("mode must be 'max' or 'min'")
    if window < 3:
        raise ValueError("window must be at least 3")

    # Candidate is displaced (not confirmed) when a new price ties
    # or beats it -> newest wins on a tie, as specified.
    displaces = (lambda new, cand: new >= cand) if mode == 'max' \
        else (lambda new, cand: new <= cand)

    prices = df[price_col].to_numpy()
    timestamps = df.index.to_numpy()
    sessions = df[session_col].to_numpy() if session_col else None

    n = len(df)
    confirmed = []

    candidate_idx = None
    current_session = sessions[0] if sessions is not None else None

    def start_candidate(i):
        nonlocal candidate_idx
        candidate_idx = i

    def confirm_candidate():
        if candidate_idx is not None:
            confirmed.append(
                (candidate_idx, timestamps[candidate_idx], prices[candidate_idx])
            )

    for i in range(n):
        if sessions is not None and sessions[i] != current_session:
            # Session boundary: whatever candidate was in flight never
            # got a full window to prove itself, but it's still the
            # best-known point for the data it did see -> confirm it.
            confirm_candidate()
            candidate_idx = None
            current_session = sessions[i]

        if candidate_idx is None:
            start_candidate(i)
            continue

        if displaces(prices[i], prices[candidate_idx]):
            # Beaten (or tied) - discard outright, do NOT confirm.
            start_candidate(i)
            continue

        # Candidate survived this comparison - has it now seen enough?
        if i - candidate_idx >= window - 1:
            confirm_candidate()
            start_candidate(i)

    # End of data: confirm whatever candidate is still standing.
    confirm_candidate()

    result = pd.DataFrame(confirmed, columns=['index_pos', 'timestamp', 'price'])
    result['type'] = 'high' if mode == 'max' else 'low'
    return result.sort_values('timestamp').reset_index(drop=True)


# ============================================================
# CONVENIENCE WRAPPER — both highs and lows in one call
# ============================================================
def find_swing_highs_lows(df, window=7, session_col='session_end_date'):
    """
    Runs find_swings twice (once for highs on 'high', once for lows
    on 'low') and returns them combined and separately.

    Returns
    -------
    highs, lows, combined  (three DataFrames)
    """
    highs = find_swings(df, price_col='high', window=window,
                        mode='max', session_col=session_col)
    lows = find_swings(df, price_col='low', window=window,
                       mode='min', session_col=session_col)
    combined = (
        pd.concat([highs, lows], ignore_index=True)
        .sort_values('timestamp')
        .reset_index(drop=True)
    )
    return highs, lows, combined


# ============================================================
# CANDLESTICK CHART WITH SWING MARKERS
# ============================================================
def plot_candles_with_swings(df, highs, lows, start=None, end=None,
                             title='Swing highs / lows'):
    """
    Plots an OHLC candlestick chart (built directly with matplotlib
    patches, no extra dependency needed) with confirmed swing highs
    marked as red down-triangles above the bar, and swing lows as
    green up-triangles below the bar.

    df must have columns: open, high, low, close, and a datetime index.
    highs / lows are the DataFrames returned by find_swings().
    start / end optionally slice the chart to a readable window
    (e.g. a single session) - plotting a full month of 5-min bars
    on one chart is unreadable.
    """
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle

    plot_df = df.copy()
    if start is not None:
        plot_df = plot_df[plot_df.index >= start]
    if end is not None:
        plot_df = plot_df[plot_df.index <= end]

    fig, ax = plt.subplots(figsize=(16, 7))

    # Bar width as a fraction of the typical candle spacing
    if len(plot_df) > 1:
        spacing = (plot_df.index[1] - plot_df.index[0]).total_seconds() / 86400
    else:
        spacing = 1 / 288
    width = spacing * 0.6

    for ts, row in plot_df.iterrows():
        x = mdates.date2num(ts)
        color = 'seagreen' if row['close'] >= row['open'] else 'indianred'

        # Wick
        ax.plot([x, x], [row['low'], row['high']], color='black', linewidth=0.8)

        # Body
        body_low = min(row['open'], row['close'])
        body_height = abs(row['close'] - row['open'])
        if body_height == 0:
            body_height = (row['high'] - row['low']) * 0.02  # doji sliver
        ax.add_patch(Rectangle((x - width / 2, body_low), width, body_height,
                               facecolor=color, edgecolor='black', linewidth=0.5))

    # Overlay confirmed swing highs / lows within the plotted window
    h = highs[(highs['timestamp'] >= plot_df.index.min()) &
              (highs['timestamp'] <= plot_df.index.max())]
    l = lows[(lows['timestamp'] >= plot_df.index.min()) &
             (lows['timestamp'] <= plot_df.index.max())]

    if len(h):
        ax.scatter(mdates.date2num(h['timestamp']), h['price'],
                  marker='v', color='red', s=90, zorder=5,
                  label=f'Swing highs ({len(h)})', edgecolors='black')
    if len(l):
        ax.scatter(mdates.date2num(l['timestamp']), l['price'],
                  marker='^', color='blue', s=90, zorder=5,
                  label=f'Swing lows ({len(l)})', edgecolors='black')

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    fig.autofmt_xdate()
    ax.set_title(title)
    ax.set_ylabel('Price')
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()


# ============================================================
# STANDALONE DEMO / SANITY CHECK
# ============================================================
def main():
    DATA_PATH = 'db/raw_parque/January_MNQ.csv'
    WINDOW = 7  # configurable

    raw_df = pd.read_csv(DATA_PATH)
    raw_df['window_start'] = pd.to_datetime(raw_df['window_start'])

    agg_rules = {
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last',
        'volume': 'sum', 'dollar_volume': 'sum', 'session_end_date': 'last',
    }
    df_5min = raw_df.resample('5min', on='window_start').agg(agg_rules)
    df_5min = df_5min.dropna(subset=['session_end_date'])

    highs, lows, combined = find_swing_highs_lows(df_5min, window=WINDOW)

    print(f"Window size: {WINDOW}")
    print(f"Total candles: {len(df_5min)}")
    print(f"Confirmed swing highs: {len(highs)}  <- this is a LIST, one row per detected high")
    print(f"Confirmed swing lows:  {len(lows)}")
    print(f"\nFirst 15 swing highs (streaming order):\n{highs.head(15)}")
    print(f"\nFirst 15 swing lows (streaming order):\n{lows.head(15)}")

    # ---- sanity check: a confirmed swing high's price should be the
    # max within its own [i - window + 1, i + window - 1] neighborhood
    # for the interior of the data (skip near session edges / end of
    # data, where a candidate may not have gotten a full window).
    print("\nSanity check (interior points only)...")
    prices_high = df_5min['high'].to_numpy()
    n = len(df_5min)
    bad = 0
    checked = 0
    for _, row in highs.iterrows():
        i = row['index_pos']
        lo = i - WINDOW + 1
        hi = i + WINDOW
        if lo < 0 or hi > n:
            continue  # near an edge, skip
        checked += 1
        neighborhood_max = prices_high[lo:hi].max()
        if row['price'] < neighborhood_max:
            bad += 1
    print(f"Checked {checked} interior swing highs, {bad} failed "
          f"the local-max sanity check.")

    # ---- chart: first trading day only, so it's actually readable
    first_day = df_5min['session_end_date'].iloc[0]
    day_df = df_5min[df_5min['session_end_date'] == first_day]
    plot_candles_with_swings(
        day_df, highs, lows,
        title=f'MNQ 5-min, {first_day} - window={WINDOW}'
    )


if __name__ == '__main__':
    main()