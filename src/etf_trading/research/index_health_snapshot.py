"""Build local-only index health snapshots for the NiceGUI market map."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

from etf_trading.data.indexes import DEFAULT_INDEXES, IndexDefinition
from etf_trading.data.index_valuations import CORE_VALUATION_METRICS
from etf_trading.research.regime import TrendRegimeClassifier, add_trend_regime_features


INDEX_HEALTH_SUMMARY_COLUMNS = [
    "index_code",
    "index_name",
    "market",
    "category",
    "latest_date",
    "history_rows",
    "large_trend",
    "medium_trend",
    "small_trend",
    "allows_new_position",
    "trend_health_status",
    "trend_health_reason",
    "valuation_overview_label",
    "valuation_health_status",
    "valuation_health_reason",
    "valuation_latest_date",
    "valuation_coverage_years",
    "valuation_primary_source",
]

INDEX_HEALTH_DETAIL_COLUMNS = [
    "index_code",
    "detail_kind",
    "metric_name",
    "metric_label",
    "current_value",
    "status",
    "reason",
    "display_direction",
    "historical_percentile",
    "window_years",
    "first_date",
    "latest_date",
    "sample_count",
    "data_source",
]

VALUATION_METRIC_LABELS = {
    "pe_ttm": "市盈率TTM",
    "pb": "市净率",
    "erp": "股债风险溢价",
}

VALUATION_DIRECTIONS = {
    "pe_ttm": "higher_is_more_expensive",
    "pb": "higher_is_more_expensive",
    "erp": "higher_is_more_attractive",
}


def build_index_health_snapshot(
    parquet_store,
    definitions: Sequence[IndexDefinition] = DEFAULT_INDEXES,
    *,
    as_of_date: pd.Timestamp | str | None = None,
    min_price_history_rows: int = 252,
    min_valuation_history_rows: int = 756,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build summary and long-form atomic diagnostics from local Parquet only."""

    summary_rows: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []
    max_date = pd.Timestamp(as_of_date) if as_of_date is not None else None

    for definition in definitions:
        prices, price_error = _read_frame(lambda: parquet_store.read_index_prices(definition.index_code))
        trend_summary, trend_details = _trend_diagnostics(definition, prices, price_error, min_price_history_rows, max_date)

        valuations, valuation_error = _read_frame(lambda: parquet_store.read_index_valuations(definition.index_code))
        valuation_summary, valuation_details = _valuation_diagnostics(
            definition,
            valuations,
            valuation_error,
            min_valuation_history_rows,
            max_date,
        )

        row = _identity_row(definition)
        row.update(trend_summary)
        row.update(valuation_summary)
        summary_rows.append(row)
        detail_rows.extend(trend_details)
        detail_rows.extend(valuation_details)

    summary = pd.DataFrame(summary_rows, columns=INDEX_HEALTH_SUMMARY_COLUMNS)
    details = pd.DataFrame(detail_rows, columns=INDEX_HEALTH_DETAIL_COLUMNS)
    return summary, details


def _read_frame(loader) -> tuple[pd.DataFrame, str]:
    try:
        frame = loader()
    except Exception as exc:  # noqa: BLE001 - surface local cache read failures as diagnostics
        return pd.DataFrame(), str(exc)
    return frame, ""


def _identity_row(definition: IndexDefinition) -> dict[str, object]:
    return {
        "index_code": definition.index_code,
        "index_name": definition.name,
        "market": definition.market,
        "category": definition.category,
    }


def _trend_diagnostics(
    definition: IndexDefinition,
    prices: pd.DataFrame,
    read_error: str,
    min_price_history_rows: int,
    as_of_date: pd.Timestamp | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    base = {
        "latest_date": "",
        "history_rows": 0,
        "large_trend": "UNKNOWN",
        "medium_trend": "UNKNOWN",
        "small_trend": "UNKNOWN",
        "allows_new_position": False,
        "trend_health_status": "missing_history",
        "trend_health_reason": "没有本地指数历史",
    }
    if read_error:
        base["trend_health_status"] = "read_failed"
        base["trend_health_reason"] = f"读取指数历史失败：{read_error}"
        return base, [_detail(definition.index_code, "trend", "price_history", "指数历史", pd.NA, "read_failed", base["trend_health_reason"])]

    if prices.empty:
        return base, [_detail(definition.index_code, "trend", "price_history", "指数历史", pd.NA, "missing_history", "没有本地指数历史")]

    data = prices.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    if as_of_date is not None:
        data = data[data["trade_date"] <= as_of_date]
    data = data.sort_values("trade_date").reset_index(drop=True)
    if data.empty:
        reason = "截至所选日期没有本地指数历史"
        base["trend_health_reason"] = reason
        return base, [_detail(definition.index_code, "trend", "price_history", "指数历史", pd.NA, "missing_history", reason)]

    try:
        featured = add_trend_regime_features(data)
        last = featured.iloc[-1]
        regime = TrendRegimeClassifier().classify(last)
    except Exception as exc:  # noqa: BLE001 - one broken index should not break the whole board
        reason = f"趋势特征计算失败：{exc}"
        latest_date = _date_text(data["trade_date"].iloc[-1])
        base.update({"latest_date": latest_date, "history_rows": int(len(data)), "trend_health_status": "feature_failed", "trend_health_reason": reason})
        return base, [_detail(definition.index_code, "trend", "trend_features", "趋势特征", pd.NA, "feature_failed", reason, latest_date=latest_date, sample_count=len(data))]

    latest_date = _date_text(last["trade_date"])
    history_rows = int(len(featured))
    if history_rows < min_price_history_rows:
        status = "insufficient_history"
        reason = f"本地指数历史只有 {history_rows} 行，少于 {min_price_history_rows} 行"
    elif regime.allows_new_position:
        status = "normal"
        reason = "大/中/小趋势门槛通过"
    else:
        status = "blocked"
        reason = f"趋势门槛未通过：{regime.large_trend}/{regime.medium_trend}/{regime.small_trend}"

    summary = {
        "latest_date": latest_date,
        "history_rows": history_rows,
        "large_trend": regime.large_trend,
        "medium_trend": regime.medium_trend,
        "small_trend": regime.small_trend,
        "allows_new_position": bool(regime.allows_new_position),
        "trend_health_status": status,
        "trend_health_reason": reason,
    }
    details = [
        _detail(definition.index_code, "trend", "price_history", "指数历史", history_rows, "normal" if status != "insufficient_history" else status, reason, latest_date=latest_date, sample_count=history_rows, data_source=_data_source(last)),
        _trend_detail(definition.index_code, "large_trend", "大趋势", regime.large_trend, regime.large_trend in {"UP", "RECOVERY"}, latest_date, history_rows, reason, _data_source(last)),
        _trend_detail(definition.index_code, "medium_trend", "中趋势", regime.medium_trend, regime.medium_trend in {"UP", "TURNING_UP"}, latest_date, history_rows, reason, _data_source(last)),
        _trend_detail(definition.index_code, "small_trend", "小趋势", regime.small_trend, regime.small_trend in {"RIGHT_SIDE_START", "PULLBACK"}, latest_date, history_rows, reason, _data_source(last)),
        _detail(definition.index_code, "trend", "allows_new_position", "允许新开仓", bool(regime.allows_new_position), "normal" if regime.allows_new_position else "blocked", reason, latest_date=latest_date, sample_count=history_rows, data_source=_data_source(last)),
    ]
    for metric, label in (
        ("close_above_ma20", "收盘站上20日线"),
        ("ma20_above_ma60", "20日线高于60日线"),
        ("close_above_ma60", "收盘站上60日线"),
        ("ma250_slope_60", "250日线60日斜率"),
        ("drawdown_120", "120日回撤"),
    ):
        details.append(_feature_detail(definition.index_code, metric, label, last, latest_date, history_rows))
    return summary, details


def _trend_detail(index_code: str, metric: str, label: str, value: object, is_ok: bool, latest_date: str, sample_count: int, reason: str, data_source: str) -> dict[str, object]:
    status = "normal" if is_ok else "blocked"
    return _detail(index_code, "trend", metric, label, value, status, reason, latest_date=latest_date, sample_count=sample_count, data_source=data_source)


def _feature_detail(index_code: str, metric: str, label: str, row: pd.Series, latest_date: str, sample_count: int) -> dict[str, object]:
    value = row.get(metric, pd.NA)
    status = "missing_features" if _missing(value) else "computed"
    reason = "指标字段缺失" if status == "missing_features" else "已从本地指数历史计算"
    return _detail(index_code, "trend", metric, label, value, status, reason, latest_date=latest_date, sample_count=sample_count, data_source=_data_source(row))


def _valuation_diagnostics(
    definition: IndexDefinition,
    valuations: pd.DataFrame,
    read_error: str,
    min_history_rows: int,
    as_of_date: pd.Timestamp | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if read_error:
        reason = f"读取指数估值历史失败：{read_error}"
        return _valuation_summary("missing", "read_failed", reason), [
            _valuation_missing_detail(definition.index_code, metric, "read_failed", reason) for metric in CORE_VALUATION_METRICS
        ]

    if valuations.empty:
        reason = "没有本地估值历史"
        return _valuation_summary("missing", "missing_valuation", reason), [
            _valuation_missing_detail(definition.index_code, metric, "missing_valuation", reason) for metric in CORE_VALUATION_METRICS
        ]

    data = valuations.copy()
    if "trade_date" not in data.columns:
        reason = "估值缓存缺少 trade_date 字段"
        return _valuation_summary("missing", "read_failed", reason), [
            _valuation_missing_detail(definition.index_code, metric, "read_failed", reason) for metric in CORE_VALUATION_METRICS
        ]
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    if as_of_date is not None:
        data = data[data["trade_date"] <= as_of_date]
    data = data.sort_values("trade_date").reset_index(drop=True)
    if data.empty:
        reason = "截至所选日期没有本地估值历史"
        return _valuation_summary("missing", "missing_valuation", reason), [
            _valuation_missing_detail(definition.index_code, metric, "missing_valuation", reason) for metric in CORE_VALUATION_METRICS
        ]

    latest_date = _date_text(data["trade_date"].max())
    first_date = _date_text(data["trade_date"].min())
    window_years = _year_span(data["trade_date"].min(), data["trade_date"].max())
    source = _latest_text(data, "data_source")
    details: list[dict[str, object]] = []
    statuses: list[str] = []
    expensiveness_percentiles: list[float] = []
    for metric in CORE_VALUATION_METRICS:
        if metric not in data.columns:
            reason = f"估值缓存缺少 {metric} 字段"
            details.append(_valuation_missing_detail(definition.index_code, metric, "missing_field", reason, latest_date=latest_date, first_date=first_date, window_years=window_years, data_source=source))
            statuses.append("missing_field")
            continue

        series = pd.to_numeric(data[metric], errors="coerce")
        valid = data.loc[series.notna()].copy()
        valid[metric] = pd.to_numeric(valid[metric], errors="coerce")
        if valid.empty:
            reason = f"{VALUATION_METRIC_LABELS[metric]} 没有可用数值"
            details.append(_valuation_missing_detail(definition.index_code, metric, "missing_field", reason, latest_date=latest_date, first_date=first_date, window_years=window_years, data_source=source))
            statuses.append("missing_field")
            continue

        current = float(valid[metric].iloc[-1])
        percentile = _historical_percentile(valid[metric], current)
        sample_count = int(len(valid))
        status = "computed" if sample_count >= min_history_rows else "insufficient_history"
        reason = "已计算历史分位" if status == "computed" else f"估值历史只有 {sample_count} 行，少于 {min_history_rows} 行"
        details.append(
            _detail(
                definition.index_code,
                "valuation",
                metric,
                VALUATION_METRIC_LABELS[metric],
                current,
                status,
                reason,
                display_direction=VALUATION_DIRECTIONS[metric],
                historical_percentile=percentile,
                window_years=window_years,
                first_date=first_date,
                latest_date=_date_text(valid["trade_date"].iloc[-1]),
                sample_count=sample_count,
                data_source=_latest_text(valid, "data_source") or source,
            )
        )
        statuses.append(status)
        expensiveness_percentiles.append(percentile if metric in {"pe_ttm", "pb"} else 100.0 - percentile)

    overview_label = _valuation_overview_label(statuses, expensiveness_percentiles)
    health_status = _valuation_health_status(statuses)
    reason = _valuation_health_reason(health_status, statuses)
    return (
        {
            "valuation_overview_label": overview_label,
            "valuation_health_status": health_status,
            "valuation_health_reason": reason,
            "valuation_latest_date": latest_date,
            "valuation_coverage_years": round(window_years, 1),
            "valuation_primary_source": source,
        },
        details,
    )


def _valuation_summary(label: str, status: str, reason: str) -> dict[str, object]:
    return {
        "valuation_overview_label": label,
        "valuation_health_status": status,
        "valuation_health_reason": reason,
        "valuation_latest_date": "",
        "valuation_coverage_years": 0.0,
        "valuation_primary_source": "",
    }


def _valuation_missing_detail(
    index_code: str,
    metric: str,
    status: str,
    reason: str,
    *,
    latest_date: str = "",
    first_date: str = "",
    window_years: float = 0.0,
    data_source: str = "",
) -> dict[str, object]:
    return _detail(
        index_code,
        "valuation",
        metric,
        VALUATION_METRIC_LABELS[metric],
        pd.NA,
        status,
        reason,
        display_direction=VALUATION_DIRECTIONS[metric],
        window_years=window_years,
        first_date=first_date,
        latest_date=latest_date,
        sample_count=0,
        data_source=data_source,
    )


def _valuation_overview_label(statuses: list[str], expensiveness_percentiles: list[float]) -> str:
    if not statuses or all(status == "missing_valuation" for status in statuses):
        return "missing"
    if not expensiveness_percentiles:
        return "insufficient_history" if any(status == "insufficient_history" for status in statuses) else "missing"
    if any(status == "insufficient_history" for status in statuses) and not any(status == "computed" for status in statuses):
        return "insufficient_history"
    average = sum(expensiveness_percentiles) / len(expensiveness_percentiles)
    if average <= 30:
        return "low_percentile"
    if average >= 70:
        return "high_percentile"
    return "mid_percentile"


def _valuation_health_status(statuses: list[str]) -> str:
    if statuses and all(status == "computed" for status in statuses):
        return "complete"
    if statuses and all(status == "missing_valuation" for status in statuses):
        return "missing_valuation"
    if any(status == "read_failed" for status in statuses):
        return "read_failed"
    if any(status == "missing_field" for status in statuses):
        return "partial"
    if any(status == "insufficient_history" for status in statuses):
        return "insufficient_history"
    return "missing_valuation"


def _valuation_health_reason(health_status: str, statuses: list[str]) -> str:
    if health_status == "complete":
        return "核心估值指标均可计算"
    if health_status == "partial":
        return "部分核心估值字段缺失"
    if health_status == "insufficient_history":
        return "核心估值历史不足"
    if health_status == "read_failed":
        return "估值缓存读取失败"
    return "没有本地估值历史"


def _detail(
    index_code: str,
    detail_kind: str,
    metric_name: str,
    metric_label: str,
    current_value: object,
    status: str,
    reason: str,
    *,
    display_direction: str = "",
    historical_percentile: float | object = pd.NA,
    window_years: float | object = pd.NA,
    first_date: str = "",
    latest_date: str = "",
    sample_count: int | object = 0,
    data_source: str = "",
) -> dict[str, object]:
    return {
        "index_code": index_code,
        "detail_kind": detail_kind,
        "metric_name": metric_name,
        "metric_label": metric_label,
        "current_value": current_value,
        "status": status,
        "reason": reason,
        "display_direction": display_direction,
        "historical_percentile": historical_percentile,
        "window_years": window_years,
        "first_date": first_date,
        "latest_date": latest_date,
        "sample_count": sample_count,
        "data_source": data_source,
    }


def _historical_percentile(series: pd.Series, current: float) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty or math.isnan(float(current)):
        return math.nan
    return float((clean <= current).mean() * 100.0)


def _year_span(first: object, latest: object) -> float:
    first_ts = pd.Timestamp(first)
    latest_ts = pd.Timestamp(latest)
    return max((latest_ts - first_ts).days / 365.25, 0.0)


def _latest_text(frame: pd.DataFrame, column: str) -> str:
    if column not in frame or frame.empty:
        return ""
    values = frame[column].dropna().astype(str)
    if values.empty:
        return ""
    return values.iloc[-1]


def _data_source(row: pd.Series) -> str:
    value = row.get("data_source", "")
    return "" if _missing(value) else str(value)


def _date_text(value: object) -> str:
    if _missing(value):
        return ""
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _missing(value: object) -> bool:
    return bool(pd.isna(value))
