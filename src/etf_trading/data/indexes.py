"""Index definitions and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from etf_trading.data.index_catalog import catalog_definitions, default_index_catalog


INDEX_HISTORY_AUTO_START = date(1990, 1, 1)


@dataclass(frozen=True)
class IndexDefinition:
    index_code: str
    name: str
    market: str
    category: str
    provider_symbol: str
    pool: str | None = None
    index_base_date: date | None = None
    baseline_source: str = "unverified"
    source_kind: str | None = None


DEFAULT_INDEXES: tuple[IndexDefinition, ...] = catalog_definitions(default_index_catalog())


def index_options() -> list[str]:
    return [f"{item.index_code} {item.name}" for item in DEFAULT_INDEXES]


def get_index_definition(index_code: str) -> IndexDefinition:
    for item in DEFAULT_INDEXES:
        if item.index_code == index_code:
            return item
    raise KeyError(f"Unknown index code: {index_code}")


def normalize_index_daily(raw: pd.DataFrame, index_code: str, source: str) -> pd.DataFrame:
    columns = ["index_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "data_source"]
    if raw.empty:
        return pd.DataFrame(columns=columns)

    frame = raw.rename(
        columns={
            "date": "trade_date",
            "日期": "trade_date",
            "交易日": "trade_date",
            "cal_date": "trade_date",
            "calendar_date": "trade_date",
            "open": "open",
            "开盘": "open",
            "開盤": "open",
            "high": "high",
            "最高": "high",
            "low": "low",
            "最低": "low",
            "close": "close",
            "收盘": "close",
            "收盤": "close",
            "volume": "volume",
            "成交量": "volume",
            "amount": "amount",
            "成交金额": "amount",
            "成交額": "amount",
            "成交额": "amount",
        }
    ).copy()

    date_column = _find_trade_date_column(frame)
    if date_column is None:
        return pd.DataFrame(columns=columns)
    if date_column != "trade_date":
        frame = frame.rename(columns={date_column: "trade_date"})

    frame["index_code"] = index_code
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        if col not in frame.columns:
            frame[col] = 0
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["data_source"] = source
    return frame[columns].sort_values("trade_date").reset_index(drop=True)


def _find_trade_date_column(frame: pd.DataFrame) -> str | None:
    if "trade_date" in frame.columns:
        return "trade_date"

    exact_candidates = ("date", "日期", "交易日", "cal_date", "calendar_date")
    for candidate in exact_candidates:
        if candidate in frame.columns:
            return candidate

    lower_map = {str(col).lower().strip(): col for col in frame.columns}
    for key in ("date", "time", "datetime", "trade"):
        if key in lower_map:
            return lower_map[key]
    for col_lower, original in lower_map.items():
        if "date" in col_lower or "time" in col_lower or "交易" in col_lower or "时间" in col_lower:
            return original

    for col in frame.columns:
        parsed = pd.to_datetime(frame[col], errors="coerce")
        if parsed.notna().mean() >= 0.95:
            return col
    return None
