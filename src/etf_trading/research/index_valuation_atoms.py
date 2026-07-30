"""Deterministic, local-only valuation atoms for an index profile."""

from __future__ import annotations

import numpy as np
import pandas as pd


VALUATION_PERCENTILE_WINDOWS = (("3y", 3, 500), ("5y", 5, 900), ("10y", 10, 1800))

_DIRECT_VALUE_COLUMNS = (
    "pe_static",
    "pe_ttm",
    "pb",
    "total_mv",
    "float_mv",
    "total_share",
    "float_share",
    "free_share",
    "turnover_rate",
    "turnover_rate_f",
)

_DIRECT_LABELS = {
    "pe_static": "静态PE",
    "pe_ttm": "PE-TTM",
    "pb": "PB",
    "total_mv": "总市值",
    "float_mv": "流通市值",
    "total_share": "总股本",
    "float_share": "流通股本",
    "free_share": "自由流通股本",
    "turnover_rate": "换手率",
    "turnover_rate_f": "自由流通换手率",
}


def valuation_band(percentile: float) -> str:
    """Return the fixed descriptive band for a historical percentile."""

    if percentile < 0.20:
        return "历史低位"
    if percentile < 0.40:
        return "偏低"
    if percentile <= 0.60:
        return "中部"
    if percentile <= 0.80:
        return "偏高"
    return "历史高位"


def build_index_valuation_atoms(
    index_code: str,
    valuations: pd.DataFrame,
    price_as_of_date: pd.Timestamp,
    price_trade_dates: pd.Series,
    *,
    supported: bool,
) -> list[dict[str, object]]:
    """Build independently available valuation observations for one index.

    Percentile tracks deliberately use only positive, finite numeric values and
    keep their sample counts and exact calendar-year windows on every atom.
    """

    code = str(index_code)
    price_date = _timestamp(price_as_of_date)
    if not supported:
        return _unsupported_atoms(code, price_date)

    history = _prepare_history(valuations, code, price_date)
    current = history.iloc[-1] if not history.empty else None
    as_of_date = _date_text(current.get("trade_date")) if current is not None else ""
    source = _text(current.get("data_source")) if current is not None else ""
    lag_days = _trading_day_lag(price_trade_dates, current.get("trade_date") if current is not None else None, price_date)
    freshness = _freshness(lag_days, current is not None)

    rows = [
        _atom(code, "valuation_support_status", "估值支持状态", "supported", "computed", "官方估值支持", price_date),
        _atom(
            code,
            "valuation_as_of_date",
            "估值日期",
            as_of_date or pd.NA,
            "computed" if as_of_date else "missing_data",
            "估值历史为空" if not as_of_date else "取不晚于行情观察日的最近估值记录",
            as_of_date,
            data_source=source,
        ),
        _atom(
            code,
            "valuation_lag_trading_days",
            "估值滞后交易日",
            lag_days,
            "computed" if not pd.isna(lag_days) else "missing_data",
            "按行情交易日计数" if not pd.isna(lag_days) else "缺少可用行情交易日或估值日期",
            as_of_date,
            data_source=source,
        ),
        _atom(code, "valuation_source", "估值数据源", source or pd.NA, "computed" if source else "missing_data", "最近估值记录的数据源", as_of_date, data_source=source),
        _atom(code, "valuation_freshness_status", "估值新鲜度", freshness, "computed" if freshness != "missing" else "missing_data", "估值日期滞后超过5个交易日时为stale", as_of_date, data_source=source),
    ]
    rows.extend(_direct_value_atoms(code, history, source))
    rows.extend(_percentile_atoms(code, history, price_date, as_of_date, source))
    rows.extend(_turnover_atoms(code, history, source))
    return rows


def _unsupported_atoms(index_code: str, price_date: pd.Timestamp) -> list[dict[str, object]]:
    reason = "该指数没有官方估值支持"
    return [
        _atom(index_code, "valuation_support_status", "估值支持状态", "unsupported", "unsupported", reason, price_date),
        _atom(index_code, "valuation_as_of_date", "估值日期", pd.NA, "unsupported", reason),
        _atom(index_code, "valuation_lag_trading_days", "估值滞后交易日", pd.NA, "unsupported", reason),
        _atom(index_code, "valuation_source", "估值数据源", pd.NA, "unsupported", reason),
        _atom(index_code, "valuation_freshness_status", "估值新鲜度", "unsupported", "unsupported", reason),
    ]


def _direct_value_atoms(
    index_code: str,
    history: pd.DataFrame,
    source: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for column in _DIRECT_VALUE_COLUMNS:
        value, value_date = _latest_valid_value(history, column)
        rows.append(
            _atom(
                index_code,
                column,
                _DIRECT_LABELS[column],
                value if value is not None else pd.NA,
                "computed" if value is not None else "missing_data",
                "最近估值记录" if value is not None else "当前值不是正的有限数值",
                value_date,
                sample_count=1 if value is not None else 0,
                data_source=source,
            )
        )
    return rows


def _percentile_atoms(
    index_code: str,
    history: pd.DataFrame,
    price_date: pd.Timestamp,
    as_of_date: str,
    source: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metric, label in (("pe_ttm", "PE-TTM"), ("pb", "PB")):
        current_value, current_date_text = _latest_valid_value(history, metric)
        current_date = _timestamp(current_date_text) if current_date_text else None
        for window_name, years, minimum_samples in VALUATION_PERCENTILE_WINDOWS:
            start = price_date - pd.DateOffset(years=years)
            window_start = _date_text(start)
            window_end = _date_text(price_date)
            window_history = history.loc[history["trade_date"].between(start, price_date)]
            valid = _valid_values(window_history[metric]) if metric in window_history else pd.Series(dtype=float)
            sample_count = len(valid)
            status, reason = _percentile_status(current_value, sample_count, minimum_samples)
            if status == "computed":
                percentile = _midrank_percentile(valid, current_value)
                median = float(valid.median())
                deviation = float(current_value / median - 1.0)
                band: object = valuation_band(percentile)
            else:
                percentile = median = deviation = pd.NA
                band = pd.NA
            rows.extend(
                (
                    _atom(index_code, f"{metric}_percentile_{window_name}", f"{label}{window_name}历史分位", percentile, status, reason, as_of_date, sample_count, source, window_start, window_end),
                    _atom(index_code, f"{metric}_median_{window_name}", f"{label}{window_name}历史中位数", median, status, reason, as_of_date, sample_count, source, window_start, window_end),
                    _atom(index_code, f"{metric}_median_deviation_{window_name}", f"{label}相对{window_name}中位数偏离", deviation, status, reason, as_of_date, sample_count, source, window_start, window_end),
                    _atom(index_code, f"{metric}_band_{window_name}", f"{label}{window_name}分位区间", band, status, reason, as_of_date, sample_count, source, window_start, window_end),
                )
            )
            if window_name == "5y" and status == "computed" and current_date is not None:
                event = _band_change_atom(index_code, history, metric, current_date, valid, current_value, as_of_date, source, window_start, window_end)
                if event is not None:
                    rows.append(event)
    return rows


def _band_change_atom(
    index_code: str,
    history: pd.DataFrame,
    metric: str,
    current_date: pd.Timestamp,
    window_values: pd.Series,
    current_value: float,
    as_of_date: str,
    source: str,
    window_start: str,
    window_end: str,
) -> dict[str, object] | None:
    previous = _valid_values(history.loc[history["trade_date"] < current_date, metric])
    if previous.empty:
        return None
    previous_value = float(previous.iloc[-1])
    changed = valuation_band(_midrank_percentile(window_values, previous_value)) != valuation_band(_midrank_percentile(window_values, current_value))
    if not changed:
        return None
    label = "PE-TTM" if metric == "pe_ttm" else "PB"
    return _atom(index_code, f"{metric}_5y_band_changed", f"{label}5年分位区间变化", True, "computed", "最近两个有效观测值位于不同固定分位区间", as_of_date, len(window_values), source, window_start, window_end)


def _turnover_atoms(
    index_code: str,
    history: pd.DataFrame,
    source: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    current_value, current_date = _latest_valid_value(history, "turnover_rate")
    for window in (20, 60):
        valid = _valid_values(history["turnover_rate"].tail(window)) if "turnover_rate" in history else pd.Series(dtype=float)
        sample_count = len(valid)
        status = "computed" if sample_count else "missing_data"
        reason = "最近窗口中的正的有限换手率" if sample_count else "窗口内没有正的有限换手率"
        mean: object = float(valid.mean()) if sample_count else pd.NA
        deviation: object = float(current_value / mean - 1.0) if sample_count and current_value is not None else pd.NA
        deviation_status = status if current_value is not None else "missing_data"
        deviation_reason = reason if current_value is not None else "当前换手率不是正的有限数值"
        rows.extend(
            (
            _atom(index_code, f"turnover_rate_mean_{window}d", f"{window}日平均换手率", mean, status, reason, current_date, sample_count, source),
            _atom(index_code, f"turnover_rate_deviation_{window}d", f"相对{window}日平均换手率偏离", deviation, deviation_status, deviation_reason, current_date, sample_count, source),
            )
        )
    return rows


def _prepare_history(valuations: pd.DataFrame, index_code: str, price_date: pd.Timestamp) -> pd.DataFrame:
    if valuations is None or valuations.empty or "trade_date" not in valuations:
        return pd.DataFrame(columns=["trade_date"])
    history = valuations.copy()
    history["trade_date"] = pd.to_datetime(history["trade_date"], errors="coerce")
    history = history.dropna(subset=["trade_date"])
    if "index_code" in history:
        history = history[history["index_code"].astype(str) == index_code]
    history = history[history["trade_date"] <= price_date]
    return history.sort_values("trade_date").drop_duplicates(subset=["trade_date"], keep="last").reset_index(drop=True)


def _valid_values(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric[(numeric > 0) & np.isfinite(numeric)].astype(float)


def _latest_valid_value(history: pd.DataFrame, column: str) -> tuple[float | None, str]:
    if column not in history:
        return None, ""
    valid = _valid_values(history[column])
    if valid.empty:
        return None, ""
    index = valid.index[-1]
    return float(valid.iloc[-1]), _date_text(history.loc[index, "trade_date"])


def _midrank_percentile(values: pd.Series, current: float) -> float:
    return float(((values < current).sum() + 0.5 * (values == current).sum()) / len(values))


def _percentile_status(current_value: float | None, sample_count: int, minimum_samples: int) -> tuple[str, str]:
    if current_value is None:
        return "missing_data", "当前值不是正的有限数值"
    if sample_count < minimum_samples:
        return "insufficient_history", f"有效样本{sample_count}少于所需{minimum_samples}"
    return "computed", "按正的有限历史值计算中位秩分位"


def _trading_day_lag(price_trade_dates: pd.Series, valuation_date: object, price_date: pd.Timestamp) -> object:
    if valuation_date is None:
        return pd.NA
    dates = pd.to_datetime(price_trade_dates, errors="coerce").dropna()
    if dates.empty:
        return pd.NA
    valuation_timestamp = _timestamp(valuation_date)
    return int(((dates > valuation_timestamp) & (dates <= price_date)).sum())


def _freshness(lag_days: object, has_valuation: bool) -> str:
    if not has_valuation or pd.isna(lag_days):
        return "missing"
    return "stale" if int(lag_days) > 5 else "fresh"


def _atom(
    index_code: str,
    metric_key: str,
    metric_label: str,
    value: object,
    status: str,
    reason: str,
    as_of_date: pd.Timestamp | str | None = "",
    sample_count: int = 0,
    data_source: str = "",
    window_start_date: str = "",
    window_end_date: str = "",
) -> dict[str, object]:
    return {
        "index_code": index_code,
        "group_key": "valuation",
        "metric_key": metric_key,
        "metric_label": metric_label,
        "value": value,
        "status": status,
        "reason": reason,
        "as_of_date": _date_text(as_of_date),
        "sample_count": sample_count,
        "data_source": data_source,
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
    }


def _timestamp(value: object) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def _date_text(value: object) -> str:
    if value is None or pd.isna(value) or value == "":
        return ""
    return _timestamp(value).strftime("%Y-%m-%d")


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()
