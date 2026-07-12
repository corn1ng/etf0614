import numpy as np
import pandas as pd
from datetime import date

from etf_trading.data.indexes import IndexDefinition
from etf_trading.data.index_valuations import finalize_index_valuation_frame
from etf_trading.nicegui_app.state import build_index_trend_summary
from etf_trading.data.storage import ParquetStore
from etf_trading.research.index_health_snapshot import build_index_health_snapshot


def _prices(index_code: str, rows: int = 900) -> pd.DataFrame:
    dates = pd.date_range("2022-01-03", periods=rows, freq="B")
    close = np.linspace(100.0, 220.0, rows)
    return pd.DataFrame(
        {
            "index_code": index_code,
            "trade_date": dates,
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": np.arange(rows) + 1000,
            "amount": (np.arange(rows) + 1000) * 10000,
            "data_source": "unit",
        }
    )


def _valuations(index_code: str, rows: int = 800) -> pd.DataFrame:
    dates = pd.date_range("2023-01-03", periods=rows, freq="B")
    raw = pd.DataFrame(
        {
            "trade_date": dates,
            "pe_ttm": np.linspace(10.0, 20.0, rows),
            "pb": np.linspace(1.0, 2.0, rows),
            "bond_yield_10y": 0.02,
        }
    )
    return finalize_index_valuation_frame(raw, index_code, "unit", "primary")


def test_index_health_snapshot_builds_trend_and_valuation_atomic_rows(tmp_path):
    store = ParquetStore(tmp_path)
    store.write_index_prices("000300", _prices("000300"))
    store.write_index_valuations("000300", _valuations("000300"))
    definitions = (IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),)

    summary, details = build_index_health_snapshot(store, definitions=definitions, min_valuation_history_rows=756)

    assert summary.iloc[0]["index_code"] == "000300"
    assert summary.iloc[0]["trend_health_status"] == "normal"
    assert summary.iloc[0]["valuation_health_status"] == "complete"
    assert summary.iloc[0]["valuation_overview_label"] in {"low_percentile", "mid_percentile", "high_percentile"}
    assert set(details["detail_kind"]) == {"trend", "valuation"}
    valuation_rows = details[(details["detail_kind"] == "valuation") & (details["index_code"] == "000300")]
    assert set(valuation_rows["metric_name"]) == {"pe_ttm", "pb", "erp"}
    assert set(valuation_rows["status"]) == {"computed"}
    assert valuation_rows["historical_percentile"].between(0, 100).all()
    forbidden = {"score", "target_weight", "advice", "action"}
    assert forbidden.isdisjoint(summary.columns)
    assert forbidden.isdisjoint(details.columns)


def test_index_health_snapshot_keeps_missing_valuation_explicit(tmp_path):
    store = ParquetStore(tmp_path)
    store.write_index_prices("000905", _prices("000905", rows=320))
    definitions = (IndexDefinition("000905", "中证500", "A股", "A股宽基", "000905"),)

    summary, details = build_index_health_snapshot(store, definitions=definitions, min_valuation_history_rows=756)

    assert summary.iloc[0]["valuation_health_status"] == "missing_valuation"
    assert summary.iloc[0]["valuation_overview_label"] == "missing"
    valuation_rows = details[details["detail_kind"] == "valuation"]
    assert set(valuation_rows["metric_name"]) == {"pe_ttm", "pb", "erp"}
    assert set(valuation_rows["status"]) == {"missing_valuation"}
    assert all("没有本地估值历史" in str(reason) for reason in valuation_rows["reason"])


def test_index_trend_summary_includes_catalog_pool_and_history_completeness(tmp_path):
    store = ParquetStore(tmp_path)
    store.write_index_prices("801010", _prices("801010", rows=320))
    definitions = (
        IndexDefinition(
            "801010",
            "农林牧渔",
            "A股",
            "申万一级行业",
            "801010",
            pool="research",
            index_base_date=date(1999, 12, 30),
            baseline_source="official_methodology",
        ),
    )
    coverage = pd.DataFrame(
        [
            {
                "index_code": "801010",
                "completeness_status": "INCOMPLETE",
                "completeness_message": "应从 1999-12-30 开始，本地仅从 2005-01-04 开始",
            }
        ]
    )

    summary = build_index_trend_summary(store, definitions=definitions, coverage=coverage)

    assert summary.iloc[0]["pool"] == "research"
    assert summary.iloc[0]["history_completeness_status"] == "INCOMPLETE"
    assert bool(summary.iloc[0]["allows_new_position"]) is False


def test_index_health_snapshot_propagates_catalog_coverage_and_blocks_research_pool(tmp_path):
    store = ParquetStore(tmp_path)
    store.write_index_prices("801010", _prices("801010", rows=320))
    definitions = (
        IndexDefinition(
            "801010",
            "农林牧渔",
            "A股",
            "申万一级行业",
            "801010",
            pool="research",
            index_base_date=date(1999, 12, 30),
            baseline_source="official_methodology",
        ),
    )
    coverage = pd.DataFrame(
        [{"index_code": "801010", "completeness_status": "INCOMPLETE", "completeness_message": "历史不完整"}]
    )

    summary, _ = build_index_health_snapshot(store, definitions=definitions, coverage=coverage)

    assert summary.iloc[0]["pool"] == "research"
    assert summary.iloc[0]["history_completeness_status"] == "INCOMPLETE"
    assert bool(summary.iloc[0]["allows_new_position"]) is False
