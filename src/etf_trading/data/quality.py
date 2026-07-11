"""Shared local market-data readiness assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Iterable

import pandas as pd


class HistoryReadiness(StrEnum):
    """Primary, mutually exclusive readiness of a local price history."""

    READY = "ready"
    STALE = "stale"
    SHORT_HISTORY = "short_history"
    MISSING_HISTORY = "missing_history"
    READ_FAILED = "read_failed"


@dataclass(frozen=True)
class HistoryAssessment:
    """Readiness evidence for one local price history."""

    readiness: HistoryReadiness
    latest_trade_date: str
    expected_trade_date: str
    history_rows: int
    trading_day_lag: int | None
    reason_codes: tuple[str, ...]


_READINESS_LABELS = {
    HistoryReadiness.READY: "数据可用",
    HistoryReadiness.STALE: "行情滞后",
    HistoryReadiness.SHORT_HISTORY: "历史不足",
    HistoryReadiness.MISSING_HISTORY: "历史缺失",
    HistoryReadiness.READ_FAILED: "读取失败",
}


def expected_latest_trade_date(
    as_of: date | pd.Timestamp | str | None = None,
    holidays: Iterable[date | pd.Timestamp | str] = (),
) -> pd.Timestamp:
    """Return the most recent weekday that is not in explicit market holidays."""

    current = pd.Timestamp(date.today() if as_of is None else as_of).normalize()
    holiday_dates = _holiday_dates(holidays)
    while not _is_trading_day(current, holiday_dates):
        current -= pd.Timedelta(days=1)
    return current


def trading_day_lag(
    latest_trade_date: date | pd.Timestamp | str | None,
    expected_trade_date: date | pd.Timestamp | str | None,
    holidays: Iterable[date | pd.Timestamp | str] = (),
) -> int | None:
    """Count expected trading days after the latest local trade date."""

    latest = _parse_date(latest_trade_date)
    expected = _parse_date(expected_trade_date)
    if latest is None or expected is None:
        return None
    if latest >= expected:
        return 0

    holiday_dates = _holiday_dates(holidays)
    days = pd.date_range(latest + pd.Timedelta(days=1), expected, freq="D")
    return sum(_is_trading_day(day, holiday_dates) for day in days)


def assess_price_history(
    prices: pd.DataFrame,
    expected_trade_date: date | pd.Timestamp | str,
    min_history_rows: int,
    holidays: Iterable[date | pd.Timestamp | str] = (),
) -> HistoryAssessment:
    """Assess one successfully read local price frame."""

    expected = pd.Timestamp(expected_trade_date).normalize()
    expected_text = expected.strftime("%Y-%m-%d")
    if prices.empty:
        return HistoryAssessment(
            readiness=HistoryReadiness.MISSING_HISTORY,
            latest_trade_date="",
            expected_trade_date=expected_text,
            history_rows=0,
            trading_day_lag=None,
            reason_codes=("missing_history",),
        )
    if "trade_date" not in prices:
        return read_failed_assessment(expected, history_rows=int(len(prices)), reason_code="missing_trade_date")

    trade_dates = pd.to_datetime(prices["trade_date"], errors="coerce").dropna()
    if trade_dates.empty:
        return read_failed_assessment(expected, history_rows=int(len(prices)), reason_code="invalid_trade_date")

    latest = pd.Timestamp(trade_dates.max()).normalize()
    rows = int(len(prices))
    lag = trading_day_lag(latest, expected, holidays)
    reasons: list[str] = []
    if lag and lag > 0:
        reasons.append("stale")
    if rows < min_history_rows:
        reasons.append("short_history")

    readiness = (
        HistoryReadiness.STALE
        if "stale" in reasons
        else HistoryReadiness.SHORT_HISTORY
        if "short_history" in reasons
        else HistoryReadiness.READY
    )
    return HistoryAssessment(
        readiness=readiness,
        latest_trade_date=latest.strftime("%Y-%m-%d"),
        expected_trade_date=expected_text,
        history_rows=rows,
        trading_day_lag=lag,
        reason_codes=tuple(reasons),
    )


def read_failed_assessment(
    expected_trade_date: date | pd.Timestamp | str,
    *,
    history_rows: int = 0,
    reason_code: str = "read_failed",
) -> HistoryAssessment:
    """Represent a local-file read or validation failure."""

    expected = pd.Timestamp(expected_trade_date).normalize()
    return HistoryAssessment(
        readiness=HistoryReadiness.READ_FAILED,
        latest_trade_date="",
        expected_trade_date=expected.strftime("%Y-%m-%d"),
        history_rows=history_rows,
        trading_day_lag=None,
        reason_codes=(reason_code,),
    )


def history_readiness_label(readiness: HistoryReadiness | str) -> str:
    """Translate an internal readiness code to its user-facing Chinese label."""

    try:
        normalized = HistoryReadiness(readiness)
    except ValueError:
        return str(readiness)
    return _READINESS_LABELS[normalized]


def _holiday_dates(values: Iterable[date | pd.Timestamp | str]) -> set[pd.Timestamp]:
    return {parsed for value in values if (parsed := _parse_date(value)) is not None}


def _is_trading_day(value: pd.Timestamp, holidays: set[pd.Timestamp]) -> bool:
    return value.weekday() < 5 and value.normalize() not in holidays


def _parse_date(value: date | pd.Timestamp | str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()
