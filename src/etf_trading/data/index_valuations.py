"""Normalized schemas and helpers for index valuation histories."""

from __future__ import annotations

import pandas as pd


OFFICIAL_INDEX_VALUATION_TS_CODES = {
    "000001": "000001.SH",
    "000016": "000016.SH",
    "000300": "000300.SH",
    "000905": "000905.SH",
    "399001": "399001.SZ",
    "399006": "399006.SZ",
}


INDEX_VALUATION_COLUMNS = [
    "index_code",
    "trade_date",
    "pe_ttm",
    "pe_static",
    "pb",
    "ps",
    "dividend_yield",
    "earnings_yield",
    "bond_yield_10y",
    "erp",
    "roe",
    "payout_ratio",
    "forward_pe",
    "total_mv",
    "float_mv",
    "total_share",
    "float_share",
    "free_share",
    "turnover_rate",
    "turnover_rate_f",
    "data_source",
    "source_quality",
    "source_updated_at",
]

MACRO_SERIES_COLUMNS = [
    "series_name",
    "trade_date",
    "value",
    "data_source",
    "source_updated_at",
]

NUMERIC_VALUATION_COLUMNS = [
    "pe_ttm",
    "pe_static",
    "pb",
    "ps",
    "dividend_yield",
    "earnings_yield",
    "bond_yield_10y",
    "erp",
    "roe",
    "payout_ratio",
    "forward_pe",
    "total_mv",
    "float_mv",
    "total_share",
    "float_share",
    "free_share",
    "turnover_rate",
    "turnover_rate_f",
]

CORE_VALUATION_METRICS = ("pe_ttm", "pb", "erp")

_VALUATION_RENAME_MAP = {
    "pb_lf": "pb",
    "市盈率": "pe_ttm",
    "滚动市盈率": "pe_ttm",
    "市净率": "pb",
    "股息率": "dividend_yield",
    "日期": "trade_date",
    "交易日期": "trade_date",
    "date": "trade_date",
}


def finalize_index_valuation_frame(
    frame: pd.DataFrame,
    index_code: str,
    data_source: str,
    source_quality: str,
) -> pd.DataFrame:
    """Return a canonical valuation history for one index."""

    result = frame.rename(columns={key: value for key, value in _VALUATION_RENAME_MAP.items() if key in frame.columns}).copy()
    if result.empty:
        return pd.DataFrame(columns=INDEX_VALUATION_COLUMNS)
    if "trade_date" not in result.columns:
        raise ValueError("valuation frame missing trade_date")

    result["index_code"] = str(index_code)
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    for column in NUMERIC_VALUATION_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
        result[column] = pd.to_numeric(result[column], errors="coerce")

    pe = result["pe_ttm"].where(result["pe_ttm"] > 0)
    missing_earnings = result["earnings_yield"].isna()
    result.loc[missing_earnings, "earnings_yield"] = 1.0 / pe.loc[missing_earnings]

    missing_erp = result["erp"].isna()
    result.loc[missing_erp, "erp"] = result.loc[missing_erp, "earnings_yield"] - result.loc[missing_erp, "bond_yield_10y"]

    result["data_source"] = data_source
    result["source_quality"] = source_quality
    result["source_updated_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    result = result.drop_duplicates(subset=["index_code", "trade_date"], keep="last")
    return result[INDEX_VALUATION_COLUMNS].sort_values("trade_date").reset_index(drop=True)


def normalize_macro_series(frame: pd.DataFrame, series_name: str, data_source: str) -> pd.DataFrame:
    """Return a canonical macro time series used by valuation diagnostics."""

    result = frame.rename(columns={"date": "trade_date", "日期": "trade_date"}).copy()
    if result.empty:
        return pd.DataFrame(columns=MACRO_SERIES_COLUMNS)
    if "trade_date" not in result.columns or "value" not in result.columns:
        raise ValueError("macro series frame must contain trade_date and value")

    result["series_name"] = str(series_name)
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result["data_source"] = data_source
    result["source_updated_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    result = result.drop_duplicates(subset=["series_name", "trade_date"], keep="last")
    return result[MACRO_SERIES_COLUMNS].sort_values("trade_date").reset_index(drop=True)
