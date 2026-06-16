from __future__ import annotations

from datetime import date

import pandas as pd

from etf_trading.data.indexes import INDEX_HISTORY_AUTO_START
from etf_trading.data.initialization import InitializationService
from etf_trading.data.provider import DataProvider
from etf_trading.data.storage import ParquetStore, SQLiteStore


class _FakeIndexProvider(DataProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, date | str, date | str]] = []

    def fetch_etf_list(self) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_etf_daily(self, code: str, start_date: date | str, end_date: date | str, adjust: str = "qfq") -> pd.DataFrame:
        raise NotImplementedError

    def fetch_etf_nav(self, code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_index_daily(self, code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        self.calls.append((code, start_date, end_date))
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        rows = []
        for trade_date in pd.date_range(start, end, freq="B"):
            rows.append(
                {
                    "index_code": code,
                    "trade_date": trade_date,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0 + len(rows),
                    "volume": 1000,
                    "amount": 2000,
                    "data_source": "fake",
                }
            )
        return pd.DataFrame(rows)

    def fetch_trade_calendar(self, market: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        raise NotImplementedError


def test_ensure_index_history_fetches_full_history_when_missing(tmp_path):
    provider = _FakeIndexProvider()
    service = InitializationService(
        store=SQLiteStore(tmp_path / "etf.sqlite"),
        provider=provider,
        parquet_store=ParquetStore(tmp_path / "parquet"),
    )
    service.store.initialize_schema()

    result = service.ensure_index_history("000905", through=date(2024, 1, 3))

    assert provider.calls == [("000905", INDEX_HISTORY_AUTO_START, date(2024, 1, 3))]
    assert result.status == "INITIALIZED"
    assert result.fetched_rows > 0
    stored = service.parquet_store.read_index_prices("000905")
    assert len(stored) == result.total_rows
    assert stored["trade_date"].min() == pd.Timestamp(INDEX_HISTORY_AUTO_START)


def test_ensure_index_history_catches_up_from_last_local_date(tmp_path):
    provider = _FakeIndexProvider()
    parquet_store = ParquetStore(tmp_path / "parquet")
    existing = pd.DataFrame(
        {
            "index_code": ["000905", "000905"],
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
            "volume": [1000, 1000],
            "amount": [2000, 2000],
            "data_source": ["seed", "seed"],
        }
    )
    parquet_store.write_index_prices("000905", existing)
    service = InitializationService(
        store=SQLiteStore(tmp_path / "etf.sqlite"),
        provider=provider,
        parquet_store=parquet_store,
    )
    service.store.initialize_schema()

    result = service.ensure_index_history("000905", through=date(2024, 1, 5))

    assert provider.calls == [("000905", date(2024, 1, 4), date(2024, 1, 5))]
    assert result.status == "UPDATED"
    assert result.fetched_rows == 2
    stored = service.parquet_store.read_index_prices("000905")
    assert stored["trade_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
    ]


def test_ensure_index_history_skips_when_already_current(tmp_path):
    provider = _FakeIndexProvider()
    parquet_store = ParquetStore(tmp_path / "parquet")
    parquet_store.write_index_prices(
        "000905",
        pd.DataFrame(
            {
                "index_code": ["000905"],
                "trade_date": pd.to_datetime(["2024-01-05"]),
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000],
                "amount": [2000],
                "data_source": ["seed"],
            }
        ),
    )
    service = InitializationService(
        store=SQLiteStore(tmp_path / "etf.sqlite"),
        provider=provider,
        parquet_store=parquet_store,
    )
    service.store.initialize_schema()

    result = service.ensure_index_history("000905", through=date(2024, 1, 5))

    assert provider.calls == []
    assert result.status == "SKIPPED"
    assert result.fetched_rows == 0
