"""Shared local market-data readiness assessment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
import re
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


@dataclass(frozen=True)
class IndexHistoryCompleteness:
    """Evidence for whether an index starts at its verified official base date."""

    status: str
    message: str
    local_first_trade_date: str | None
    latest_trade_date: str | None
    history_rows: int
    index_base_date: str | None
    baseline_source: str

    def to_storage_values(self, *, source_first_trade_date: str | None = None) -> dict[str, object]:
        return {
            "index_base_date": self.index_base_date,
            "baseline_source": self.baseline_source,
            "local_first_trade_date": self.local_first_trade_date,
            "source_first_trade_date": source_first_trade_date or self.local_first_trade_date,
            "latest_trade_date": self.latest_trade_date,
            "history_rows": self.history_rows,
            "completeness_status": self.status,
            "completeness_message": self.message,
        }


_READINESS_LABELS = {
    HistoryReadiness.READY: "数据可用",
    HistoryReadiness.STALE: "行情滞后",
    HistoryReadiness.SHORT_HISTORY: "历史不足",
    HistoryReadiness.MISSING_HISTORY: "历史缺失",
    HistoryReadiness.READ_FAILED: "读取失败",
}

_LEGACY_BASELINE_UNVERIFIED_MESSAGES = frozenset({"基日待核验", "基日待核验，不能判定历史完整"})
_LEGACY_MISSING_HISTORY_MESSAGES = frozenset({"", "历史数据缺失"})
_LEGACY_STALE_MESSAGE = re.compile(
    r"^本地最新交易日 (?P<latest>\d{4}-\d{2}-\d{2})，未达到目标交易日 (?P<expected>\d{4}-\d{2}-\d{2})$"
)
_OFFICIAL_BASELINE_SOURCES = frozenset({"official_methodology", "official_factsheet", "official_api"})


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


def has_official_baseline(source: str, base_date: object) -> bool:
    """Return whether a parseable base date came from an official source."""

    return source in _OFFICIAL_BASELINE_SOURCES and _parse_date(base_date) is not None


def assess_index_history_completeness(
    prices: pd.DataFrame,
    index_base_date: date | pd.Timestamp | str | None,
    *,
    baseline_source: str,
    index_code: str | None = None,
    source_kind: str | None = None,
    evidence_name: str = "",
    evidence_kind: str = "",
) -> IndexHistoryCompleteness:
    """Assess coverage against a verified index base date without guessing it.

    An unknown base date is deliberately not treated as complete even when the
    provider returns a long history. This prevents research-only catalogue rows
    from becoming tradeable through a false completeness claim.
    """

    base = _parse_date(index_base_date)
    base_text = base.strftime("%Y-%m-%d") if base is not None else None
    rows = int(len(prices))
    if prices.empty:
        return IndexHistoryCompleteness(
            status="MISSING_HISTORY",
            message=index_history_missing_message(index_code, source_kind),
            local_first_trade_date=None,
            latest_trade_date=None,
            history_rows=0,
            index_base_date=base_text,
            baseline_source=baseline_source,
        )
    if "trade_date" not in prices:
        return IndexHistoryCompleteness(
            status="READ_FAILED",
            message="历史数据缺少交易日字段",
            local_first_trade_date=None,
            latest_trade_date=None,
            history_rows=rows,
            index_base_date=base_text,
            baseline_source=baseline_source,
        )

    dates = pd.to_datetime(prices["trade_date"], errors="coerce").dropna()
    if dates.empty:
        return IndexHistoryCompleteness(
            status="READ_FAILED",
            message="历史数据交易日无效",
            local_first_trade_date=None,
            latest_trade_date=None,
            history_rows=rows,
            index_base_date=base_text,
            baseline_source=baseline_source,
        )

    first = pd.Timestamp(dates.min()).normalize()
    latest = pd.Timestamp(dates.max()).normalize()
    first_text = first.strftime("%Y-%m-%d")
    latest_text = latest.strftime("%Y-%m-%d")
    if baseline_source in {"third_party_reference", "third_party_publication"} and base is not None:
        evidence_label = evidence_name or "第三方来源"
        date_label = "发布日期" if evidence_kind == "publication_date" else "参考基日"
        prefix = "参考起点" if evidence_kind == "publication_date" else "参考基日"
        return IndexHistoryCompleteness(
            status="BASELINE_REFERENCED",
            message=(
                f"{prefix} {base_text}（第三方：{evidence_label}，{date_label}）；"
                "不用于长周期回测或新开仓。"
            ),
            local_first_trade_date=first_text,
            latest_trade_date=latest_text,
            history_rows=rows,
            index_base_date=base_text,
            baseline_source=baseline_source,
        )
    if not has_official_baseline(baseline_source, base):
        return IndexHistoryCompleteness(
            status="BASELINE_UNVERIFIED",
            message=(
                f"已有 {first_text} 至 {latest_text} 的行情，但缺少官方基日；"
                "暂时无法判断是否从指数起点完整，不作为交易依据。"
            ),
            local_first_trade_date=first_text,
            latest_trade_date=latest_text,
            history_rows=rows,
            index_base_date=base_text,
            baseline_source=baseline_source,
        )
    if first <= base:
        return IndexHistoryCompleteness(
            status="COMPLETE",
            message=f"历史从官方基日 {base_text} 开始，当前覆盖 {first_text} 至 {latest_text}，数据完整。",
            local_first_trade_date=first_text,
            latest_trade_date=latest_text,
            history_rows=rows,
            index_base_date=base_text,
            baseline_source=baseline_source,
        )
    return IndexHistoryCompleteness(
        status="INCOMPLETE",
        message=f"应从 {base_text} 开始，当前仅有 {first_text} 起的数据。",
        local_first_trade_date=first_text,
        latest_trade_date=latest_text,
        history_rows=rows,
        index_base_date=base_text,
        baseline_source=baseline_source,
    )


def index_history_freshness_message(
    latest_trade_date: date | pd.Timestamp | str | None,
    expected_trade_date: date | pd.Timestamp | str | None,
) -> str:
    """Describe the next required index trading date with normalized dates."""

    return f"已更新至 {_date_text(latest_trade_date)}，缺少 {_date_text(expected_trade_date)} 行情。"


def upgrade_legacy_index_history_message(
    status: str | None,
    message: object,
    *,
    first_trade_date: date | pd.Timestamp | str | None = None,
    latest_trade_date: date | pd.Timestamp | str | None = None,
    index_code: str | None = None,
    source_kind: str | None = None,
) -> str:
    """Upgrade only recognized pre-localization index-history messages."""

    normalized_status = str(status or "").strip()
    text = "" if message is None else str(message)
    legacy_text = text.strip()
    if normalized_status == "BASELINE_UNVERIFIED" and legacy_text in _LEGACY_BASELINE_UNVERIFIED_MESSAGES:
        first = _parse_date(first_trade_date)
        latest = _parse_date(latest_trade_date)
        if first is not None and latest is not None:
            return (
                f"已有 {first.strftime('%Y-%m-%d')} 至 {latest.strftime('%Y-%m-%d')} 的行情，但缺少官方基日；"
                "暂时无法判断是否从指数起点完整，不作为交易依据。"
            )
    if normalized_status == "STALE":
        match = _LEGACY_STALE_MESSAGE.fullmatch(legacy_text)
        if match is not None:
            return index_history_freshness_message(match["latest"], match["expected"])
    if normalized_status in {"EMPTY", "MISSING_HISTORY"} and legacy_text in _LEGACY_MISSING_HISTORY_MESSAGES:
        return index_history_missing_message(index_code, source_kind)
    return text


def index_history_missing_message(index_code: str | None, source_kind: str | None) -> str:
    if index_code and source_kind:
        return f"{_source_kind_label(source_kind)}未返回 {index_code} 的历史行情。"
    if index_code:
        return f"数据源未返回 {index_code} 的历史行情。"
    return "数据源未返回该指数的历史行情。"


def _source_kind_label(source_kind: str) -> str:
    return {
        "csi": "中证数据源",
        "shenwan": "申万数据源",
        "hk": "港股数据源",
    }.get(source_kind, "数据源")


def _date_text(value: date | pd.Timestamp | str | None) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%Y-%m-%d") if parsed is not None else str(value)


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
