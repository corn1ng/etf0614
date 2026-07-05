"""Atomic ETF indicator snapshot builders."""

from __future__ import annotations

from typing import Any

import pandas as pd

from etf_trading.strategy.features import add_technical_features, add_weekly_trend_features
from etf_trading.ui.data_coverage import expected_latest_trade_date

ATOMIC_INDICATOR_COLUMNS = [
    "trade_date",
    "etf_code",
    "name",
    "category",
    "exchange",
    "tradability_status",
    "history_status",
    "feature_status",
    "latest_trade_date",
    "history_rows",
    "return_20",
    "return_60",
    "return_20_rank_all",
    "return_60_rank_all",
    "return_20_rank_category",
    "return_60_rank_category",
    "close_above_ma20",
    "ma20_above_ma60",
    "close_above_ma60",
    "ma60_slope_20",
    "weekly_close_above_ma10",
    "weekly_close_above_ma30",
    "avg_amount_5",
    "avg_amount_20",
    "amount_ratio_5_20",
    "distance_ma20_pct",
    "distance_ma20_atr",
    "is_60d_close_breakout",
    "missing_feature_names",
]

REQUIRED_FEATURES = (
    "return_20",
    "return_60",
    "ma20",
    "ma60",
    "atr20",
    "avg_amount_20",
    "amount_ratio_5_20",
    "weekly_ma10",
    "weekly_ma30",
)


def build_etf_atomic_indicator_snapshot(
    master: pd.DataFrame,
    parquet_store: Any,
    *,
    today: pd.Timestamp | None = None,
    min_history_rows: int = 252,
) -> pd.DataFrame:
    """Build one diagnostic atomic-indicator row per tradable ETF."""

    normalized_master = _normalize_master(master)
    if normalized_master.empty:
        return pd.DataFrame(columns=ATOMIC_INDICATOR_COLUMNS)

    expected = expected_latest_trade_date(today)
    rows = [
        _build_row(item, parquet_store, expected=expected, min_history_rows=min_history_rows)
        for item in normalized_master.to_dict("records")
        if _is_exchange_traded(item.get("tradability_status"))
    ]
    frame = pd.DataFrame(rows, columns=ATOMIC_INDICATOR_COLUMNS)
    if frame.empty:
        return frame
    return _add_return_ranks(frame)


def _build_row(item: dict[str, object], parquet_store: Any, *, expected: pd.Timestamp, min_history_rows: int) -> dict[str, object]:
    code = str(item["etf_code"])
    row = _base_row(item, expected.strftime("%Y-%m-%d"))
    try:
        prices = parquet_store.read_prices(code)
    except Exception:  # noqa: BLE001 - diagnostics must keep one bad file from breaking the table
        row.update({"history_status": "read_failed", "feature_status": "missing_features", "missing_feature_names": "read_failed"})
        return row

    if prices.empty:
        row.update({"history_status": "missing_history", "feature_status": "missing_features", "missing_feature_names": "missing_history"})
        return row

    prepared = prices.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce")
    prepared = prepared.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    if prepared.empty:
        row.update({"history_status": "read_failed", "feature_status": "missing_features", "missing_feature_names": "invalid_trade_date"})
        return row

    latest = pd.Timestamp(prepared["trade_date"].max()).normalize()
    history_rows = int(len(prepared))
    row.update(
        {
            "trade_date": latest.strftime("%Y-%m-%d"),
            "latest_trade_date": latest.strftime("%Y-%m-%d"),
            "history_rows": history_rows,
            "history_status": _history_status(history_rows, latest, expected, min_history_rows),
        }
    )

    try:
        featured = add_weekly_trend_features(add_technical_features(prepared))
    except Exception:  # noqa: BLE001 - one malformed price frame should stay diagnostic
        row.update({"feature_status": "missing_features", "missing_feature_names": "feature_calculation_failed"})
        return row

    last = featured.iloc[-1]
    missing = [name for name in REQUIRED_FEATURES if _is_missing(last.get(name))]
    row.update(
        {
            "feature_status": "complete" if not missing else "missing_features",
            "return_20": _value_or_na(last.get("return_20")),
            "return_60": _value_or_na(last.get("return_60")),
            "close_above_ma20": _compare(last.get("close"), last.get("ma20"), ">"),
            "ma20_above_ma60": _compare(last.get("ma20"), last.get("ma60"), ">"),
            "close_above_ma60": _compare(last.get("close"), last.get("ma60"), ">"),
            "ma60_slope_20": _value_or_na(last.get("ma60_slope_20")),
            "weekly_close_above_ma10": _value_or_na(last.get("weekly_close_above_ma10")) if "weekly_ma10" not in missing else pd.NA,
            "weekly_close_above_ma30": _value_or_na(last.get("weekly_close_above_ma30")) if "weekly_ma30" not in missing else pd.NA,
            "avg_amount_5": _value_or_na(last.get("avg_amount_5")),
            "avg_amount_20": _value_or_na(last.get("avg_amount_20")),
            "amount_ratio_5_20": _value_or_na(last.get("amount_ratio_5_20")),
            "distance_ma20_pct": _value_or_na(last.get("distance_ma20_pct")),
            "distance_ma20_atr": _value_or_na(last.get("distance_ma20_atr")),
            "is_60d_close_breakout": _value_or_na(last.get("is_60d_close_breakout")) if not _is_missing(last.get("rolling_high_close_60")) else pd.NA,
            "missing_feature_names": ",".join(missing),
        }
    )
    return row


def _normalize_master(master: pd.DataFrame) -> pd.DataFrame:
    if master.empty:
        return pd.DataFrame(columns=["etf_code", "name", "category", "exchange", "tradability_status"])

    frame = master.copy()
    column_map = {
        "ETF代码": "etf_code",
        "ETF名称": "name",
        "分类": "category",
        "交易所": "exchange",
    }
    frame = frame.rename(columns={source: target for source, target in column_map.items() if source in frame.columns and target not in frame.columns})
    for column in ["etf_code", "name", "category", "exchange", "tradability_status"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["etf_code"] = frame["etf_code"].map(_format_code)
    frame = frame[frame["etf_code"] != ""].copy()
    frame["name"] = frame["name"].fillna("").astype(str)
    frame["category"] = frame["category"].fillna("").astype(str)
    frame["exchange"] = frame["exchange"].fillna("").astype(str)
    frame["tradability_status"] = frame["tradability_status"].fillna("").astype(str)
    return frame[["etf_code", "name", "category", "exchange", "tradability_status"]]


def _base_row(item: dict[str, object], expected_date: str) -> dict[str, object]:
    row = {column: pd.NA for column in ATOMIC_INDICATOR_COLUMNS}
    row.update(
        {
            "trade_date": expected_date,
            "etf_code": item["etf_code"],
            "name": item["name"],
            "category": item["category"],
            "exchange": item["exchange"],
            "tradability_status": str(item.get("tradability_status") or "exchange_traded"),
            "history_status": "missing_history",
            "feature_status": "missing_features",
            "latest_trade_date": "",
            "history_rows": 0,
            "missing_feature_names": "missing_history",
        }
    )
    return row


def _history_status(history_rows: int, latest: pd.Timestamp, expected: pd.Timestamp, min_history_rows: int) -> str:
    if history_rows < min_history_rows:
        return "short_history"
    if latest < expected:
        return "stale"
    return "complete"


def _add_return_ranks(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column, rank_column in (("return_20", "return_20_rank_all"), ("return_60", "return_60_rank_all")):
        result[column] = pd.to_numeric(result[column], errors="coerce")
        result[rank_column] = result[column].rank(ascending=False, method="min")

    for column, rank_column in (("return_20", "return_20_rank_category"), ("return_60", "return_60_rank_category")):
        result[rank_column] = result.groupby("category", dropna=False)[column].rank(ascending=False, method="min")
    return result[ATOMIC_INDICATOR_COLUMNS]


def _compare(left: object, right: object, operator: str) -> object:
    if _is_missing(left) or _is_missing(right):
        return pd.NA
    if operator == ">":
        return bool(float(left) > float(right))
    raise ValueError(f"unsupported comparison operator: {operator}")


def _is_exchange_traded(status: object) -> bool:
    text = "" if status is None else str(status).strip()
    return text in {"", "exchange_traded"}


def _value_or_na(value: object) -> object:
    return pd.NA if _is_missing(value) else value


def _is_missing(value: object) -> bool:
    return bool(pd.isna(value))


def _format_code(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text
