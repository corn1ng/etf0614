import pandas as pd

from etf_trading.data.index_valuations import (
    CORE_VALUATION_METRICS,
    INDEX_VALUATION_COLUMNS,
    MACRO_SERIES_COLUMNS,
    OFFICIAL_INDEX_VALUATION_TS_CODES,
    finalize_index_valuation_frame,
    normalize_macro_series,
)
from etf_trading.data.storage import ParquetStore


def test_finalize_index_valuation_frame_derives_yields_and_orders_columns():
    raw = pd.DataFrame(
        {
            "trade_date": ["2026-07-03", "2026-07-02"],
            "pe_ttm": [12.5, 10.0],
            "pb": [1.4, 1.3],
            "dividend_yield": [0.025, 0.024],
            "bond_yield_10y": [0.018, 0.019],
        }
    )

    result = finalize_index_valuation_frame(raw, "000300", "unit", "primary")

    assert result.columns.tolist() == INDEX_VALUATION_COLUMNS
    assert CORE_VALUATION_METRICS == ("pe_ttm", "pb", "erp")
    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-02", "2026-07-03"]
    latest = result.iloc[-1]
    assert latest["index_code"] == "000300"
    assert round(float(latest["earnings_yield"]), 4) == 0.08
    assert round(float(latest["erp"]), 4) == 0.062
    assert latest["data_source"] == "unit"
    assert latest["source_quality"] == "primary"


def test_finalize_index_valuation_frame_keeps_invalid_pe_from_yield_derivation():
    raw = pd.DataFrame({"trade_date": ["2026-07-03"], "pe_ttm": [0], "bond_yield_10y": [0.018]})

    result = finalize_index_valuation_frame(raw, "000300", "unit", "primary")

    assert pd.isna(result.iloc[0]["earnings_yield"])
    assert pd.isna(result.iloc[0]["erp"])


def test_index_valuation_schema_includes_official_dailybasic_fields():
    assert OFFICIAL_INDEX_VALUATION_TS_CODES == {
        "000001": "000001.SH",
        "000016": "000016.SH",
        "000300": "000300.SH",
        "000905": "000905.SH",
        "399001": "399001.SZ",
        "399006": "399006.SZ",
    }
    assert INDEX_VALUATION_COLUMNS[13:20] == [
        "total_mv",
        "float_mv",
        "total_share",
        "float_share",
        "free_share",
        "turnover_rate",
        "turnover_rate_f",
    ]


def test_normalize_macro_series_uses_standard_schema():
    raw = pd.DataFrame({"trade_date": ["2026-07-03"], "value": [0.018]})

    result = normalize_macro_series(raw, "10y_bond_yield", "unit")

    assert result.columns.tolist() == MACRO_SERIES_COLUMNS
    assert result.iloc[0]["series_name"] == "10y_bond_yield"
    assert result.iloc[0]["data_source"] == "unit"


def test_parquet_store_reads_and_writes_index_valuations_and_macro(tmp_path):
    store = ParquetStore(tmp_path)
    valuations = finalize_index_valuation_frame(
        pd.DataFrame({"trade_date": ["2026-07-03"], "pe_ttm": [12.5], "pb": [1.4]}),
        "000300",
        "unit",
        "primary",
    )
    macro = normalize_macro_series(
        pd.DataFrame({"trade_date": ["2026-07-03"], "value": [0.018]}),
        "10y_bond_yield",
        "unit",
    )

    valuation_path = store.write_index_valuations("000300", valuations)
    macro_path = store.write_macro_series("10y_bond_yield", macro)

    assert valuation_path.name == "000300.parquet"
    assert macro_path.name == "10y_bond_yield.parquet"
    assert store.read_index_valuations("000300")["index_code"].tolist() == ["000300"]
    assert store.read_macro_series("10y_bond_yield")["series_name"].tolist() == ["10y_bond_yield"]
    assert store.read_index_valuations("missing").empty
    assert store.read_macro_series("missing").empty
