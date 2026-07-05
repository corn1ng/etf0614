import pandas as pd

from etf_trading.data.indexes import IndexDefinition
from etf_trading.data.storage import ParquetStore
from etf_trading.research.index_etf_universe import build_index_etf_universe, selected_etf_codes


def _price_frame(days: int) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "etf_code": ["510300"] * days,
            "trade_date": dates,
            "open": [1.0] * days,
            "high": [1.1] * days,
            "low": [0.9] * days,
            "close": [1.0] * days,
            "volume": [1000] * days,
            "amount": [1_000_000] * days,
        }
    )


def test_build_index_etf_universe_maps_by_tracking_index_first(tmp_path):
    parquet_store = ParquetStore(tmp_path)
    parquet_store.write_prices("510300", _price_frame(300))
    master = pd.DataFrame(
        {
            "etf_code": ["510300"],
            "name": ["沪深300ETF华泰柏瑞"],
            "tracking_index": ["000300"],
            "amount": [100_000_000],
            "volume": [1_000_000],
            "is_active": [1],
        }
    )

    universe = build_index_etf_universe(
        master,
        parquet_store,
        definitions=(IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),),
    )

    assert universe.iloc[0]["etf_code"] == "510300"
    assert universe.iloc[0]["index_code"] == "000300"
    assert universe.iloc[0]["index_name"] == "沪深300"
    assert universe.iloc[0]["mapping_source"] == "data_source"
    assert universe.iloc[0]["confidence"] == "high"
    assert bool(universe.iloc[0]["is_top_sample"]) is True


def test_build_index_etf_universe_infers_by_name_and_limits_to_top_10(tmp_path):
    parquet_store = ParquetStore(tmp_path)
    codes = [f"5103{i:02d}" for i in range(12)]
    for code in codes:
        frame = _price_frame(300).assign(etf_code=code)
        parquet_store.write_prices(code, frame)
    master = pd.DataFrame(
        {
            "etf_code": codes,
            "name": [f"沪深300ETF测试{i}" for i in range(12)],
            "tracking_index": [None] * 12,
            "amount": list(range(12)),
            "volume": [1_000] * 12,
            "is_active": [1] * 12,
        }
    )

    universe = build_index_etf_universe(
        master,
        parquet_store,
        definitions=(IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),),
    )
    selected = universe[universe["is_top_sample"]]

    assert len(selected) == 10
    assert selected["amount"].tolist() == sorted(selected["amount"].tolist(), reverse=True)
    assert selected.iloc[0]["mapping_source"] == "name_inferred"
    assert selected.iloc[0]["confidence"] == "medium"


def test_build_index_etf_universe_skips_short_history_and_inactive_etfs(tmp_path):
    parquet_store = ParquetStore(tmp_path)
    parquet_store.write_prices("510300", _price_frame(100))
    parquet_store.write_prices("510310", _price_frame(300).assign(etf_code="510310"))
    master = pd.DataFrame(
        {
            "etf_code": ["510300", "510310", "159919"],
            "name": ["沪深300ETF短历史", "沪深300ETF正常", "沪深300ETF停用"],
            "tracking_index": ["000300", "000300", "000300"],
            "amount": [300, 200, 500],
            "volume": [1_000, 1_000, 1_000],
            "is_active": [1, 1, 0],
        }
    )

    universe = build_index_etf_universe(
        master,
        parquet_store,
        definitions=(IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),),
    )

    assert universe["etf_code"].tolist() == ["510310"]


def test_selected_etf_codes_returns_deduplicated_top_samples():
    universe = pd.DataFrame(
        {
            "index_code": ["000300", "000300", "000905"],
            "etf_code": ["510300", "510300", "510500"],
            "is_top_sample": [True, True, False],
        }
    )

    assert selected_etf_codes(universe, ["000300", "000905"]) == ["510300"]
