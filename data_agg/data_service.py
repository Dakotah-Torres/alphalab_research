import re
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import select

from data_agg.massive_data_provider import MassiveDataProvider
from db.models import CandleItem
from db.postgress import PostgresDB


QUARTER_MONTHS = [3, 6, 9, 12]
MONTH_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}

TIMEFRAME_RE = re.compile(r"^(\d+)(min|hour|day)$")


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    """'1min' -> timedelta(minutes=1), '4hour' -> timedelta(hours=4), etc."""
    match = TIMEFRAME_RE.match(timeframe)
    if not match:
        raise ValueError(f"Unrecognized timeframe format: {timeframe!r}")
    n, unit = match.groups()
    unit_map = {"min": "minutes", "hour": "hours", "day": "days"}
    return timedelta(**{unit_map[unit]: int(n)})


def _quarter_end(year: int, month: int) -> datetime:
    if month == 12:
        return datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(year, month + 1, 1, tzinfo=timezone.utc)


def contract_periods(symbol: str, start: datetime, end: datetime) -> list[dict]:
    """
    Split [start, end] into quarterly-contract chunks, one per ticker.

    Approximates each contract's active window as a calendar quarter
    (Jan-Mar -> H, Apr-Jun -> M, Jul-Sep -> U, Oct-Dec -> Z) -- this mirrors
    the logic MassiveDataProvider already uses to pick a ticker from a date,
    so the tickers computed here stay consistent with what the provider
    will derive on its own.

    NOTE: real CME rollover dates don't line up exactly with calendar
    quarter boundaries. Treat this as a working approximation for now.
    """
    periods = []
    cursor = start

    while cursor <= end:
        contract_month = next((m for m in QUARTER_MONTHS if cursor.month <= m), None)
        year = cursor.year
        if contract_month is None:
            contract_month = QUARTER_MONTHS[0]
            year += 1

        period_end = min(_quarter_end(year, contract_month), end + timedelta(seconds=1))
        ticker = f"{symbol}{MONTH_CODE[contract_month]}{str(year)[-1]}"

        periods.append({
            "ticker": ticker,
            "period_start": cursor,
            "period_end": min(period_end, end),
        })

        cursor = period_end

    return periods


def find_missing_ranges(
    existing_timestamps: list[datetime],
    requested_start: datetime,
    requested_end: datetime,
    expected_interval: timedelta,
    max_allowed_gap: timedelta,
) -> list[tuple[datetime, datetime]]:
    """
    Compare what's already in the DB (sorted existing_timestamps) against the
    requested range and return (start, end) tuples for anything missing.

    max_allowed_gap should be a bit bigger than expected_interval so the
    daily maintenance break doesn't get flagged as missing data. Tune
    max_allowed_gap_minutes on DataService if you see false positives/negatives.
    """
    if not existing_timestamps:
        return [(requested_start, requested_end)]

    gaps = []

    if existing_timestamps[0] - requested_start > max_allowed_gap:
        gaps.append((requested_start, existing_timestamps[0] - expected_interval))

    for prev, curr in zip(existing_timestamps, existing_timestamps[1:]):
        if curr - prev > max_allowed_gap:
            gaps.append((prev + expected_interval, curr - expected_interval))

    if requested_end - existing_timestamps[-1] > max_allowed_gap:
        gaps.append((existing_timestamps[-1] + expected_interval, requested_end))

    return gaps


def _datetime_to_tuple(dt: datetime) -> tuple:
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


class DataService:
    """
    Single entry point for notebooks:

        from data_agg.data_service import DataService
        ds = DataService()
        df = ds.get_candles("MNQ", "1min", datetime(2026, 1, 1), datetime(2026, 12, 31))

    Checks Postgres first, backfills any missing candles from the API
    (per contract, per gap), and returns the full requested range as a
    DataFrame.
    """

    def __init__(self, max_allowed_gap_minutes: int = 90):
        self.db = PostgresDB()
        self.max_allowed_gap_minutes = max_allowed_gap_minutes

    def get_candles(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        expected_interval = timeframe_to_timedelta(timeframe)
        max_allowed_gap = max(expected_interval * 2, timedelta(minutes=self.max_allowed_gap_minutes))

        for period in contract_periods(symbol, start, end):
            self._backfill_period(
                symbol=symbol,
                ticker=period["ticker"],
                timeframe=timeframe,
                period_start=period["period_start"],
                period_end=period["period_end"],
                expected_interval=expected_interval,
                max_allowed_gap=max_allowed_gap,
            )

        return self.db.get_candles_df(symbol, timeframe, start, end)

    def _backfill_period(self, symbol, ticker, timeframe, period_start, period_end, expected_interval, max_allowed_gap):
        existing = self.db.get_existing_timestamps(ticker, timeframe, period_start, period_end)
        missing_ranges = find_missing_ranges(
            existing, period_start, period_end, expected_interval, max_allowed_gap
        )

        for gap_start, gap_end in missing_ranges:
            provider = MassiveDataProvider(
                symbol,
                timeframe,
                start=_datetime_to_tuple(gap_start),
                end=_datetime_to_tuple(gap_end),
                limit=10000,
            )
            bars = provider.get_futures_bars()
            if not bars:
                continue
            candles = self.db.prep_data_for_insert(bars)
            self.db.bulk_insert_candles(candles)