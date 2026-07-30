"""Build local-only, atomic index indicator snapshots from price history."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from etf_trading.data.indexes import DEFAULT_INDEXES, IndexDefinition
from etf_trading.data.index_valuations import OFFICIAL_INDEX_VALUATION_TS_CODES
from etf_trading.research.index_valuation_atoms import build_index_valuation_atoms


INDEX_ATOMIC_SUMMARY_COLUMNS = [
    "index_code",
    "index_name",
    "market",
    "category",
    "pool",
    "index_base_date",
    "catalog_order",
    "history_completeness_status",
    "history_completeness_message",
    "history_status",
    "history_reason",
    "latest_date",
    "history_rows",
    "data_source",
    "error_text",
    "snapshot_status",
    "snapshot_reason",
    "close",
    "close_status",
    "ma_20",
    "ma_20_status",
    "ma_60",
    "ma_60_status",
    "ma_120",
    "ma_120_status",
    "ma_250",
    "ma_250_status",
    "close_above_ma_20",
    "close_above_ma_60",
    "close_above_ma_120",
    "close_above_ma_250",
    "close_vs_ma_20",
    "close_vs_ma_60",
    "close_vs_ma_120",
    "close_vs_ma_250",
    "range_20_high",
    "range_20_low",
    "range_20_status",
    "return_20",
    "return_20_status",
    "valuation_support_status",
    "valuation_as_of_date",
    "valuation_freshness_status",
    "valuation_source",
    "pe_static",
    "pe_ttm",
    "pe_ttm_5y_percentile",
    "pb",
    "pb_5y_percentile",
]

INDEX_ATOMIC_DETAIL_COLUMNS = [
    "index_code",
    "group_key",
    "metric_key",
    "metric_label",
    "value",
    "status",
    "reason",
    "as_of_date",
    "sample_count",
    "data_source",
    "window_start_date",
    "window_end_date",
]

_MA_WINDOWS = (20, 60, 120, 250)
_RANGE_WINDOWS = (20, 60, 120, 250)
_RETURN_WINDOWS = (5, 20, 60, 120, 250)

_METRIC_SPECS = (
    *(("price_ma", "close", "收盘价"),),
    *(("price_ma", f"ma_{window}", f"{window}日均线") for window in _MA_WINDOWS),
    *(("price_ma", f"close_above_ma_{window}", f"收盘高于{window}日均线") for window in _MA_WINDOWS),
    *(("price_ma", f"close_vs_ma_{window}", f"相对{window}日均线偏离率") for window in _MA_WINDOWS),
    *(("ma_cross", f"ma_cross_up_{window}", f"向上穿越{window}日均线") for window in _MA_WINDOWS),
    *(("ma_cross", f"ma_cross_down_{window}", f"向下穿越{window}日均线") for window in _MA_WINDOWS),
    *(("ma_cross", f"days_since_ma_cross_up_{window}", f"距最近向上穿越{window}日均线交易日") for window in _MA_WINDOWS),
    *(("ma_cross", f"days_since_ma_cross_down_{window}", f"距最近向下穿越{window}日均线交易日") for window in _MA_WINDOWS),
    *(("range_position", f"range_{window}_high", f"{window}日收盘新高") for window in _RANGE_WINDOWS),
    *(("range_position", f"range_{window}_low", f"{window}日收盘新低") for window in _RANGE_WINDOWS),
    *(("range_position", f"range_{window}_from_high", f"距{window}日收盘最高偏离率") for window in _RANGE_WINDOWS),
    *(("range_position", f"range_{window}_from_low", f"距{window}日收盘最低偏离率") for window in _RANGE_WINDOWS),
    *(("return_drawdown", f"return_{window}", f"{window}日收益率") for window in _RETURN_WINDOWS),
    *(("return_drawdown", f"drawdown_{window}", f"{window}日回撤") for window in _RETURN_WINDOWS),
    *(("price_ma", f"ma_{window}_change_20", f"{window}日均线20日变化") for window in (20, 60, 120)),
    ("return_drawdown", "rsi_14", "14日相对强弱指标"),
    ("return_drawdown", "up_day_ratio_20", "20日上涨日占比"),
    *(("return_drawdown", f"max_drawdown_{window}", f"{window}日最大回撤") for window in (60, 120, 250)),
    ("volatility_volume", "atr_14", "ATR14"),
    ("volatility_volume", "atr_14_pct", "ATR14占收盘价比例"),
    ("volatility_volume", "return_std_20", "20日收益率标准差"),
    *(("volatility_volume", f"annualized_volatility_{window}", f"{window}日年化波动率") for window in (20, 60)),
    ("volatility_volume", "downside_volatility_60", "60日下行波动率"),
    ("volatility_volume", "amount_avg_5", "5日平均成交额"),
    ("volatility_volume", "amount_avg_20", "20日平均成交额"),
    ("volatility_volume", "amount_avg_ratio_5_20", "5日与20日平均成交额比值"),
    ("volatility_volume", "amount_avg_60", "60日平均成交额"),
    *(("volatility_volume", f"amount_vs_avg_{window}", f"当前成交额相对{window}日平均成交额") for window in (20, 60)),
)


@dataclass(frozen=True)
class IndexAtomicSnapshotProgress:
    """One completed local index in an atomic snapshot build."""

    done: int
    total: int
    index_code: str


def build_index_atomic_snapshot(
    parquet_store,
    definitions: Sequence[IndexDefinition] = DEFAULT_INDEXES,
    *,
    coverage: pd.DataFrame | None = None,
    as_of_date: pd.Timestamp | str | None = None,
    min_history_rows: int = 252,
    on_progress: Callable[[IndexAtomicSnapshotProgress], None] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return summary and long-form local price indicators for each index.

    Every atom is calculated independently.  A short or incomplete price file
    therefore only marks the atoms that require unavailable inputs as such.
    """

    max_date, as_of_error = _as_of_date(as_of_date)
    coverage_by_code = _coverage_by_index_code(coverage)
    summary_rows: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []

    for catalog_order, definition in enumerate(definitions):
        identity = _identity_row(definition, catalog_order, coverage_by_code.get(definition.index_code, {}))
        if as_of_error:
            summary, details = _failed_snapshot(identity, "calculation_failed", as_of_error)
        else:
            prices, read_error = _read_frame(lambda: parquet_store.read_index_prices(definition.index_code))
            if read_error:
                summary, details = _failed_snapshot(identity, "read_failed", f"读取指数历史失败：{read_error}")
            else:
                summary, details = _snapshot_from_prices(identity, prices, max_date, min_history_rows)
                if summary["latest_date"]:
                    valuation_details = _valuation_details(
                        parquet_store,
                        definition.index_code,
                        prices,
                        summary["latest_date"],
                        max_date,
                    )
                    details.extend(valuation_details)
                    _merge_valuation_summary(summary, valuation_details)
        summary_rows.append(summary)
        detail_rows.extend(details)
        if on_progress is not None:
            on_progress(
                IndexAtomicSnapshotProgress(
                    done=catalog_order + 1,
                    total=len(definitions),
                    index_code=definition.index_code,
                )
            )

    summary = pd.DataFrame(summary_rows, columns=INDEX_ATOMIC_SUMMARY_COLUMNS)
    for column in (
        "close_above_ma_20",
        "close_above_ma_60",
        "close_above_ma_120",
        "close_above_ma_250",
        "range_20_high",
        "range_20_low",
    ):
        if column in summary:
            summary[column] = summary[column].astype(object)
    details = pd.DataFrame(detail_rows, columns=INDEX_ATOMIC_DETAIL_COLUMNS)
    return summary, details


def _as_of_date(value: pd.Timestamp | str | None) -> tuple[pd.Timestamp | None, str]:
    if value is None:
        return None, ""
    try:
        return pd.Timestamp(value), ""
    except (TypeError, ValueError) as exc:
        return None, f"截至日期无效：{exc}"


def _read_frame(loader) -> tuple[pd.DataFrame, str]:
    try:
        return loader(), ""
    except Exception as exc:  # noqa: BLE001 - report one cache failure without blocking other indexes
        return pd.DataFrame(), str(exc)


def _identity_row(definition: IndexDefinition, catalog_order: int, coverage: dict[str, object]) -> dict[str, object]:
    base_date = definition.index_base_date.isoformat() if definition.index_base_date is not None else ""
    return {
        "index_code": definition.index_code,
        "index_name": definition.name,
        "market": definition.market,
        "category": definition.category,
        "pool": definition.pool or "core",
        "index_base_date": base_date,
        "catalog_order": catalog_order,
        "history_completeness_status": _text(coverage.get("completeness_status"), "NOT_VALIDATED"),
        "history_completeness_message": _text(coverage.get("completeness_message"), "尚未校验历史完整性"),
    }


def _coverage_by_index_code(coverage: pd.DataFrame | None) -> dict[str, dict[str, object]]:
    if coverage is None or coverage.empty or "index_code" not in coverage:
        return {}
    result: dict[str, dict[str, object]] = {}
    for row in coverage.to_dict("records"):
        code = _text(row.get("index_code"))
        if code:
            result[code] = row
    return result


def _snapshot_from_prices(
    identity: dict[str, object],
    prices: pd.DataFrame,
    as_of_date: pd.Timestamp | None,
    min_history_rows: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    try:
        data = _prepare_prices(prices, as_of_date)
    except Exception as exc:  # noqa: BLE001 - make malformed local data inspectable
        return _failed_snapshot(identity, "calculation_failed", f"指数历史整理失败：{exc}")

    if data.empty:
        return _failed_snapshot(identity, "missing_input", "截至所选日期没有本地指数历史")

    latest_date = _date_text(data["trade_date"].iloc[-1])
    sample_count = int(len(data))
    data_source = _latest_text(data, "data_source")
    close = _numeric_series(data, "close")
    details = _atomic_metric_rows(identity["index_code"], data, close, latest_date, sample_count, data_source)
    history_status = "computed"
    history_reason = "已读取本地指数历史"
    snapshot_status = "computed" if sample_count >= min_history_rows else "insufficient_history"
    snapshot_reason = (
        "原子快照可用"
        if snapshot_status == "computed"
        else f"本地指数历史只有 {sample_count} 行，少于 {min_history_rows} 行"
    )
    details.extend(
        _data_quality_rows(
            identity["index_code"],
            identity,
            history_status,
            history_reason,
            latest_date,
            sample_count,
            data_source,
            "",
        )
    )
    return _summary_from_details(
        identity,
        details,
        history_status,
        history_reason,
        latest_date,
        sample_count,
        data_source,
        "",
        snapshot_status,
        snapshot_reason,
    ), details


def _valuation_details(
    parquet_store,
    index_code: str,
    prices: pd.DataFrame,
    latest_date: str,
    as_of_date: pd.Timestamp | None,
) -> list[dict[str, object]]:
    prepared_prices = _prepare_prices(prices, as_of_date)
    price_date = pd.Timestamp(latest_date)
    supported = index_code in OFFICIAL_INDEX_VALUATION_TS_CODES
    if not supported:
        return build_index_valuation_atoms(
            index_code,
            pd.DataFrame(),
            price_date,
            prepared_prices["trade_date"],
            supported=False,
        )

    valuations, read_error = _read_frame(lambda: parquet_store.read_index_valuations(index_code))
    atoms = build_index_valuation_atoms(
        index_code,
        valuations,
        price_date,
        prepared_prices["trade_date"],
        supported=True,
    )
    if not read_error:
        return atoms

    for atom in atoms:
        atom["status"] = "read_failed"
        atom["reason"] = f"读取本地官方估值失败：{read_error}"
        if atom["metric_key"] != "valuation_support_status":
            atom["value"] = pd.NA
            atom["as_of_date"] = ""
            atom["data_source"] = ""
    return atoms


def _merge_valuation_summary(summary: dict[str, object], details: list[dict[str, object]]) -> None:
    values = {str(detail["metric_key"]): detail["value"] for detail in details}
    summary_keys = {
        "valuation_support_status": "valuation_support_status",
        "valuation_as_of_date": "valuation_as_of_date",
        "valuation_freshness_status": "valuation_freshness_status",
        "valuation_source": "valuation_source",
        "pe_static": "pe_static",
        "pe_ttm": "pe_ttm",
        "pe_ttm_5y_percentile": "pe_ttm_percentile_5y",
        "pb": "pb",
        "pb_5y_percentile": "pb_percentile_5y",
    }
    for summary_key, metric_key in summary_keys.items():
        summary[summary_key] = values.get(metric_key, pd.NA)


def _failed_snapshot(
    identity: dict[str, object], status: str, reason: str
) -> tuple[dict[str, object], list[dict[str, object]]]:
    index_code = str(identity["index_code"])
    details = [
        _detail(index_code, group_key, metric_key, metric_label, pd.NA, status, reason)
        for group_key, metric_key, metric_label in _METRIC_SPECS
    ]
    details.extend(_data_quality_rows(index_code, identity, status, reason, "", 0, "", reason))
    return _summary_from_details(
        identity,
        details,
        status,
        reason,
        "",
        0,
        "",
        reason,
        status,
        reason,
    ), details


def _prepare_prices(prices: pd.DataFrame, as_of_date: pd.Timestamp | None) -> pd.DataFrame:
    if "trade_date" not in prices:
        raise ValueError("缺少 trade_date 字段")
    data = prices.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
    data = data[data["trade_date"].notna()]
    if as_of_date is not None:
        data = data[data["trade_date"] <= as_of_date]
    return data.drop_duplicates(subset=["trade_date"], keep="last").sort_values("trade_date").reset_index(drop=True)


def _atomic_metric_rows(
    index_code: object,
    data: pd.DataFrame,
    close: pd.Series | None,
    latest_date: str,
    sample_count: int,
    data_source: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    ma_results: dict[int, tuple[object, str, str]] = {}
    close_value, close_status, close_reason = _last_close(close)
    rows.append(_detail(index_code, "price_ma", "close", "收盘价", close_value, close_status, close_reason, latest_date, sample_count, data_source))

    for window in _MA_WINDOWS:
        value, status, reason = _mean(close, window)
        ma_results[window] = (value, status, reason)
        rows.append(_detail(index_code, "price_ma", f"ma_{window}", f"{window}日均线", value, status, reason, latest_date, sample_count, data_source))

    for window in _MA_WINDOWS:
        ma_value, ma_status, ma_reason = ma_results[window]
        value, status, reason = _close_relative_to_ma(close_value, close_status, close_reason, ma_value, ma_status, ma_reason, window)
        rows.append(_detail(index_code, "price_ma", f"close_above_ma_{window}", f"收盘高于{window}日均线", value, status, reason, latest_date, sample_count, data_source))
        rows.append(_detail(index_code, "price_ma", f"close_vs_ma_{window}", f"相对{window}日均线偏离率", value if status != "computed" else (float(close_value) / float(ma_value) - 1), status, reason, latest_date, sample_count, data_source))

    for window in _MA_WINDOWS:
        up, down, status, reason = _ma_crosses(close, window)
        rows.append(_detail(index_code, "ma_cross", f"ma_cross_up_{window}", f"向上穿越{window}日均线", up, status, reason, latest_date, sample_count, data_source))
        rows.append(_detail(index_code, "ma_cross", f"ma_cross_down_{window}", f"向下穿越{window}日均线", down, status, reason, latest_date, sample_count, data_source))
        up_days, up_days_reason = _days_since_cross(close, window, upward=True, status=status, reason=reason)
        down_days, down_days_reason = _days_since_cross(close, window, upward=False, status=status, reason=reason)
        rows.append(_detail(index_code, "ma_cross", f"days_since_ma_cross_up_{window}", f"距最近向上穿越{window}日均线交易日", up_days, status, up_days_reason, latest_date, sample_count, data_source))
        rows.append(_detail(index_code, "ma_cross", f"days_since_ma_cross_down_{window}", f"距最近向下穿越{window}日均线交易日", down_days, status, down_days_reason, latest_date, sample_count, data_source))

    for window in _RANGE_WINDOWS:
        high, low, from_high, from_low, status, reason = _range_position(close, window)
        rows.append(_detail(index_code, "range_position", f"range_{window}_high", f"{window}日收盘新高", high, status, reason, latest_date, sample_count, data_source))
        rows.append(_detail(index_code, "range_position", f"range_{window}_low", f"{window}日收盘新低", low, status, reason, latest_date, sample_count, data_source))
        rows.append(_detail(index_code, "range_position", f"range_{window}_from_high", f"距{window}日收盘最高偏离率", from_high, status, reason, latest_date, sample_count, data_source))
        rows.append(_detail(index_code, "range_position", f"range_{window}_from_low", f"距{window}日收盘最低偏离率", from_low, status, reason, latest_date, sample_count, data_source))

    for window in _RETURN_WINDOWS:
        value, status, reason = _return(close, window)
        rows.append(_detail(index_code, "return_drawdown", f"return_{window}", f"{window}日收益率", value, status, reason, latest_date, sample_count, data_source))
        value, status, reason = _drawdown(close, window)
        rows.append(_detail(index_code, "return_drawdown", f"drawdown_{window}", f"{window}日回撤", value, status, reason, latest_date, sample_count, data_source))

    for window in (20, 60, 120):
        value, status, reason = _ma_change(close, window)
        rows.append(_detail(index_code, "price_ma", f"ma_{window}_change_20", f"{window}日均线20日变化", value, status, reason, latest_date, sample_count, data_source))
    value, status, reason = _rsi_14(close)
    rows.append(_detail(index_code, "return_drawdown", "rsi_14", "14日相对强弱指标", value, status, reason, latest_date, sample_count, data_source))
    value, status, reason = _up_day_ratio_20(close)
    rows.append(_detail(index_code, "return_drawdown", "up_day_ratio_20", "20日上涨日占比", value, status, reason, latest_date, sample_count, data_source))
    for window in (60, 120, 250):
        value, status, reason = _maximum_drawdown(close, window)
        rows.append(_detail(index_code, "return_drawdown", f"max_drawdown_{window}", f"{window}日最大回撤", value, status, reason, latest_date, sample_count, data_source))

    atr_close_values, atr_close_status, atr_close_reason = _positive_finite_close_tail(close, 1)
    atr_close = pd.NA if atr_close_values is None else float(atr_close_values.iloc[-1])
    value, status, reason = _atr_14(data, close)
    rows.append(_detail(index_code, "volatility_volume", "atr_14", "ATR14", value, status, reason, latest_date, sample_count, data_source))
    atr_value, atr_status, atr_reason = value, status, reason
    value, status, reason = _atr_percent(
        atr_value,
        atr_status,
        atr_reason,
        atr_close,
        atr_close_status,
        atr_close_reason,
    )
    rows.append(_detail(index_code, "volatility_volume", "atr_14_pct", "ATR14占收盘价比例", value, status, reason, latest_date, sample_count, data_source))
    value, status, reason = _return_std_20(close)
    rows.append(_detail(index_code, "volatility_volume", "return_std_20", "20日收益率标准差", value, status, reason, latest_date, sample_count, data_source))
    for window in (20, 60):
        value, status, reason = _annualized_volatility(close, window)
        rows.append(_detail(index_code, "volatility_volume", f"annualized_volatility_{window}", f"{window}日年化波动率", value, status, reason, latest_date, sample_count, data_source))
    value, status, reason = _downside_volatility_60(close)
    rows.append(_detail(index_code, "volatility_volume", "downside_volatility_60", "60日下行波动率", value, status, reason, latest_date, sample_count, data_source))

    amount = _numeric_series(data, "amount")
    amount_averages: dict[int, tuple[object, str, str]] = {}
    for window in (5, 20, 60):
        value, status, reason = _mean(amount, window, column="amount")
        amount_averages[window] = (value, status, reason)
        rows.append(_detail(index_code, "volatility_volume", f"amount_avg_{window}", f"{window}日平均成交额", value, status, reason, latest_date, sample_count, data_source))
    amount_5, amount_5_status, amount_5_reason = amount_averages[5]
    amount_20, amount_20_status, amount_20_reason = amount_averages[20]
    if amount_5_status != "computed":
        value, status, reason = pd.NA, amount_5_status, amount_5_reason
    elif amount_20_status != "computed":
        value, status, reason = pd.NA, amount_20_status, amount_20_reason
    elif float(amount_20) == 0:
        value, status, reason = pd.NA, "calculation_failed", "20日平均成交额为零，无法计算比值"
    else:
        value, status, reason = float(amount_5) / float(amount_20), "computed", "已从本地指数历史计算"
    rows.append(_detail(index_code, "volatility_volume", "amount_avg_ratio_5_20", "5日与20日平均成交额比值", value, status, reason, latest_date, sample_count, data_source))
    for window in (20, 60):
        average, average_status, average_reason = amount_averages[window]
        value, status, reason = _amount_vs_average(amount, average, average_status, average_reason, window)
        rows.append(_detail(index_code, "volatility_volume", f"amount_vs_avg_{window}", f"当前成交额相对{window}日平均成交额", value, status, reason, latest_date, sample_count, data_source))
    return rows


def _numeric_series(data: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in data:
        return None
    return pd.to_numeric(data[column], errors="coerce")


def _last_close(close: pd.Series | None) -> tuple[object, str, str]:
    values, status, reason = _tail(close, 1, "close")
    return (pd.NA, status, reason) if values is None else (float(values.iloc[-1]), "computed", "已从本地指数历史计算")


def _tail(close: pd.Series | None, rows: int, column: str) -> tuple[pd.Series | None, str, str]:
    if close is None:
        return None, "missing_input", f"缺少 {column} 字段"
    if len(close) < rows:
        return None, "insufficient_history", f"本地指数历史只有 {len(close)} 行，少于计算所需 {rows} 行"
    values = close.iloc[-rows:]
    if values.isna().any():
        return None, "missing_input", f"最近 {rows} 行 {column} 存在缺失值"
    return values, "computed", "已从本地指数历史计算"


def _positive_finite_close_tail(close: pd.Series | None, rows: int) -> tuple[pd.Series | None, str, str]:
    if close is None:
        return None, "missing_input", "缺少 close 字段"
    if len(close) < rows:
        return None, "insufficient_history", f"本地指数历史只有 {len(close)} 行，少于计算所需 {rows} 行"
    values = close.iloc[-rows:]
    try:
        numeric_values = values.to_numpy(dtype=float)
    except (TypeError, ValueError):
        return None, "calculation_failed", "收盘价包含非正或非有限值"
    if (~np.isfinite(numeric_values) | (numeric_values <= 0)).any():
        return None, "calculation_failed", "收盘价包含非正或非有限值"
    return values, "computed", "已从本地指数历史计算"


def _mean(close: pd.Series | None, window: int, *, column: str = "close") -> tuple[object, str, str]:
    values, status, reason = _tail(close, window, column)
    return (pd.NA, status, reason) if values is None else (float(values.mean()), "computed", reason)


def _close_relative_to_ma(
    close_value: object,
    close_status: str,
    close_reason: str,
    ma_value: object,
    ma_status: str,
    ma_reason: str,
    window: int,
) -> tuple[object, str, str]:
    if close_status != "computed":
        return pd.NA, close_status, close_reason
    if ma_status != "computed":
        return pd.NA, ma_status, ma_reason
    if float(ma_value) == 0:
        return pd.NA, "calculation_failed", f"{window}日均线为零，无法计算偏离率"
    return bool(float(close_value) > float(ma_value)), "computed", "已从本地指数历史计算"


def _ma_crosses(close: pd.Series | None, window: int) -> tuple[object, object, str, str]:
    values, status, reason = _tail(close, window + 1, "close")
    if values is None:
        return pd.NA, pd.NA, status, reason
    previous_ma = float(values.iloc[:-1].mean())
    current_ma = float(values.iloc[-window:].mean())
    previous_close = float(values.iloc[-2])
    current_close = float(values.iloc[-1])
    return (
        bool(previous_close <= previous_ma and current_close > current_ma),
        bool(previous_close >= previous_ma and current_close < current_ma),
        "computed",
        "已按相邻交易日收盘价与均线位置计算",
    )


def _days_since_cross(
    close: pd.Series | None,
    window: int,
    *,
    upward: bool,
    status: str,
    reason: str,
) -> tuple[object, str]:
    if status != "computed" or close is None:
        return pd.NA, reason
    moving_average = close.rolling(window=window, min_periods=window).mean()
    if upward:
        events = (close.shift(1) <= moving_average.shift(1)) & (close > moving_average)
        event_name = "向上"
    else:
        events = (close.shift(1) >= moving_average.shift(1)) & (close < moving_average)
        event_name = "向下"
    positions = events[events].index
    if len(positions) == 0:
        return pd.NA, f"可用历史内没有{event_name}穿越{window}日均线"
    return int(len(close) - 1 - positions[-1]), "已从最近一次均线穿越计算"


def _range_position(close: pd.Series | None, window: int) -> tuple[object, object, object, object, str, str]:
    values, status, reason = _tail(close, window, "close")
    if values is None:
        return pd.NA, pd.NA, pd.NA, pd.NA, status, reason
    current = float(values.iloc[-1])
    highest = float(values.max())
    lowest = float(values.min())
    if highest == 0 or lowest == 0:
        return pd.NA, pd.NA, pd.NA, pd.NA, "calculation_failed", f"{window}日区间存在零值，无法计算位置比例"
    return (
        bool(current == highest),
        bool(current == lowest),
        current / highest - 1,
        current / lowest - 1,
        "computed",
        "已从本地指数历史计算",
    )


def _return(close: pd.Series | None, window: int) -> tuple[object, str, str]:
    values, status, reason = _tail(close, window + 1, "close")
    if values is None:
        return pd.NA, status, reason
    reference = float(values.iloc[0])
    if reference == 0:
        return pd.NA, "calculation_failed", f"{window}日前收盘价为零，无法计算收益率"
    return float(values.iloc[-1]) / reference - 1, "computed", "已从本地指数历史计算"


def _drawdown(close: pd.Series | None, window: int) -> tuple[object, str, str]:
    values, status, reason = _tail(close, window, "close")
    if values is None:
        return pd.NA, status, reason
    highest = float(values.max())
    if highest == 0:
        return pd.NA, "calculation_failed", f"{window}日最高收盘价为零，无法计算回撤"
    return float(values.iloc[-1]) / highest - 1, "computed", "已从本地指数历史计算"


def _atr_14(data: pd.DataFrame, close: pd.Series | None) -> tuple[object, str, str]:
    if close is None or "high" not in data or "low" not in data:
        return pd.NA, "missing_input", "ATR14 需要 high、low 和 close 字段"
    if len(data) < 15:
        return pd.NA, "insufficient_history", f"本地指数历史只有 {len(data)} 行，少于计算 ATR14 所需 15 行"
    high = pd.to_numeric(data["high"], errors="coerce")
    low = pd.to_numeric(data["low"], errors="coerce")
    if high.iloc[-14:].isna().any() or low.iloc[-14:].isna().any() or close.iloc[-15:].isna().any():
        return pd.NA, "missing_input", "最近 14 个真实波幅所需 high、low、close 存在缺失值"
    previous_close = close.shift(1)
    ranges = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1)
    return float(ranges.max(axis=1, skipna=False).iloc[-14:].mean()), "computed", "已从本地 high、low、close 计算"


def _return_std_20(close: pd.Series | None) -> tuple[object, str, str]:
    values, status, reason = _tail(close, 21, "close")
    if values is None:
        return pd.NA, status, reason
    return float(values.pct_change().iloc[1:].std()), "computed", "已从本地指数历史计算"


def _annualized_volatility(close: pd.Series | None, window: int) -> tuple[object, str, str]:
    values, status, reason = _positive_finite_close_tail(close, window + 1)
    if values is None:
        return pd.NA, status, reason
    return float(values.pct_change().iloc[1:].std() * np.sqrt(252)), "computed", "按日收益率样本标准差年化"


def _maximum_drawdown(close: pd.Series | None, window: int) -> tuple[object, str, str]:
    values, status, reason = _positive_finite_close_tail(close, window)
    if values is None:
        return pd.NA, status, reason
    drawdowns = values / values.cummax() - 1
    return float(drawdowns.min()), "computed", "按窗口内此前累计最高收盘计算"


def _rsi_14(close: pd.Series | None) -> tuple[object, str, str]:
    values, status, reason = _positive_finite_close_tail(close, 15)
    if values is None:
        return pd.NA, status, reason
    changes = values.diff().iloc[1:]
    gains = changes.clip(lower=0).mean()
    losses = -changes.clip(upper=0).mean()
    if losses == 0:
        return 100.0, "computed", "最近14日没有下跌变动"
    return float(100 - 100 / (1 + gains / losses)), "computed", "按14日平均涨跌幅计算"


def _ma_change(close: pd.Series | None, ma_window: int, lookback: int = 20) -> tuple[object, str, str]:
    values, status, reason = _positive_finite_close_tail(close, ma_window + lookback)
    if values is None:
        return pd.NA, status, reason
    moving_average = values.rolling(ma_window).mean().dropna()
    reference = float(moving_average.iloc[-lookback - 1])
    if reference == 0:
        return pd.NA, "calculation_failed", f"{ma_window}日均线参考值为零"
    return float(moving_average.iloc[-1]) / reference - 1, "computed", "按20个交易日均线变化计算"


def _up_day_ratio_20(close: pd.Series | None) -> tuple[object, str, str]:
    values, status, reason = _positive_finite_close_tail(close, 21)
    if values is None:
        return pd.NA, status, reason
    returns = values.pct_change().iloc[1:]
    return float((returns > 0).mean()), "computed", "按最近20日收益方向计算"


def _downside_volatility_60(close: pd.Series | None) -> tuple[object, str, str]:
    values, status, reason = _positive_finite_close_tail(close, 61)
    if values is None:
        return pd.NA, status, reason
    returns = values.pct_change().iloc[1:].to_numpy(dtype=float)
    downside = np.minimum(returns, 0.0)
    return float(np.sqrt(np.square(downside).mean()) * np.sqrt(252)), "computed", "按60日下行收益均方根年化"


def _atr_percent(
    atr_value: object,
    atr_status: str,
    atr_reason: str,
    close_value: object,
    close_status: str,
    close_reason: str,
) -> tuple[object, str, str]:
    if close_status != "computed":
        return pd.NA, close_status, close_reason
    if atr_status != "computed":
        return pd.NA, atr_status, atr_reason
    if not np.isfinite(float(atr_value)):
        return pd.NA, "calculation_failed", "ATR14非有限，无法计算ATR比例"
    return float(atr_value) / float(close_value), "computed", "ATR14除以最新正收盘价"


def _amount_vs_average(
    amount: pd.Series | None,
    average: object,
    average_status: str,
    average_reason: str,
    window: int,
) -> tuple[object, str, str]:
    values, status, reason = _tail(amount, 1, "amount")
    if values is None:
        return pd.NA, status, reason
    if average_status != "computed":
        return pd.NA, average_status, average_reason
    if float(average) <= 0:
        return pd.NA, "calculation_failed", f"{window}日平均成交额非正，无法计算偏离率"
    return float(values.iloc[-1]) / float(average) - 1, "computed", "当前成交额相对窗口平均成交额"


def _data_quality_rows(
    index_code: object,
    identity: dict[str, object],
    history_status: str,
    history_reason: str,
    latest_date: str,
    sample_count: int,
    data_source: str,
    error_text: str,
) -> list[dict[str, object]]:
    status = history_status
    reason = history_reason
    return [
        _detail(index_code, "data_quality", "history_status", "历史状态", history_status, status, reason, latest_date, sample_count, data_source),
        _detail(index_code, "data_quality", "latest_date", "最新交易日", latest_date or pd.NA, status, reason, latest_date, sample_count, data_source),
        _detail(index_code, "data_quality", "history_rows", "历史行数", sample_count, status, reason, latest_date, sample_count, data_source),
        _detail(index_code, "data_quality", "history_completeness_status", "历史完整性状态", identity["history_completeness_status"], "computed", "来自历史覆盖记录", latest_date, sample_count, data_source),
        _detail(index_code, "data_quality", "history_completeness_message", "历史完整性说明", identity["history_completeness_message"], "computed", "来自历史覆盖记录", latest_date, sample_count, data_source),
        _detail(index_code, "data_quality", "data_source", "数据源", data_source or pd.NA, status, reason, latest_date, sample_count, data_source),
        _detail(index_code, "data_quality", "error_text", "错误文本", error_text or "", "computed", "无错误" if not error_text else history_reason, latest_date, sample_count, data_source),
    ]


def _summary_from_details(
    identity: dict[str, object],
    details: list[dict[str, object]],
    history_status: str,
    history_reason: str,
    latest_date: str,
    history_rows: int,
    data_source: str,
    error_text: str,
    snapshot_status: str,
    snapshot_reason: str,
) -> dict[str, object]:
    row = {column: pd.NA for column in INDEX_ATOMIC_SUMMARY_COLUMNS}
    row.update(identity)
    row.update(
        {
            "history_status": history_status,
            "history_reason": history_reason,
            "latest_date": latest_date,
            "history_rows": history_rows,
            "data_source": data_source,
            "error_text": error_text,
            "snapshot_status": snapshot_status,
            "snapshot_reason": snapshot_reason,
        }
    )
    metrics = {detail["metric_key"]: detail for detail in details}
    for key in (
        "close",
        "ma_20",
        "ma_60",
        "ma_120",
        "ma_250",
        "close_above_ma_20",
        "close_above_ma_60",
        "close_above_ma_120",
        "close_above_ma_250",
        "close_vs_ma_20",
        "close_vs_ma_60",
        "close_vs_ma_120",
        "close_vs_ma_250",
        "range_20_high",
        "range_20_low",
        "return_20",
    ):
        metric = metrics[key]
        row[key] = metric["value"]
        row[f"{key}_status"] = metric["status"]
    row["range_20_status"] = metrics["range_20_high"]["status"]
    return row


def _detail(
    index_code: object,
    group_key: str,
    metric_key: str,
    metric_label: str,
    value: object,
    status: str,
    reason: str,
    as_of_date: str = "",
    sample_count: int = 0,
    data_source: str = "",
    window_start_date: str = "",
    window_end_date: str = "",
) -> dict[str, object]:
    return {
        "index_code": index_code,
        "group_key": group_key,
        "metric_key": metric_key,
        "metric_label": metric_label,
        "value": value,
        "status": status,
        "reason": reason,
        "as_of_date": as_of_date,
        "sample_count": sample_count,
        "data_source": data_source,
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
    }


def _date_text(value: object) -> str:
    return "" if pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")


def _latest_text(frame: pd.DataFrame, column: str) -> str:
    if column not in frame or frame.empty:
        return ""
    values = frame[column].dropna().astype(str)
    return "" if values.empty else values.iloc[-1]


def _text(value: object, default: str = "") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    return text or default
