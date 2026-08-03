import pandas as pd
import pytest

from etf_trading.data.index_valuation_service import OfficialIndexValuationSyncService
from etf_trading.data.index_valuations import finalize_index_valuation_frame
from etf_trading.data.provider_runtime import ProviderCallError
from etf_trading.data.storage import ParquetStore


def _valuation_rows(dates):
    return finalize_index_valuation_frame(
        pd.DataFrame(
            {
                "trade_date": dates,
                "pe_ttm": [11.6] * len(dates),
                "pe_static": [11.9] * len(dates),
                "pb": [1.24] * len(dates),
            }
        ),
        "000300",
        "tushare_index_dailybasic",
        "official",
    )


class FakeOfficialProvider:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def fetch_index_official_valuations(self, code, start, end):
        self.calls.append(
            (
                str(code),
                pd.Timestamp(start).strftime("%Y-%m-%d"),
                pd.Timestamp(end).strftime("%Y-%m-%d"),
            )
        )
        return self.frames.get(str(code), pd.DataFrame()).copy()


class FailingOfficialProvider:
    def __init__(self, message):
        self.message = message

    def fetch_index_official_valuations(self, code, start, end):
        raise ProviderCallError(self.message, category="permission")


class RecordingParquetStore:
    def __init__(self, store):
        self.store = store
        self.write_calls = []

    def read_index_valuations(self, index_code):
        return self.store.read_index_valuations(index_code)

    def write_index_valuations(self, index_code, frame):
        self.write_calls.append((index_code, frame.copy()))
        return self.store.write_index_valuations(index_code, frame)


def test_sync_all_initializes_then_increments_without_duplicates(tmp_path):
    provider = FakeOfficialProvider(
        {"000300": _valuation_rows(["2026-07-28", "2026-07-29"])}
    )
    store = ParquetStore(tmp_path / "parquet")
    service = OfficialIndexValuationSyncService(provider, store, index_codes=("000300",))

    first = service.sync_all("2026-07-29")
    second = service.sync_all("2026-07-29")

    assert first.loc[0, "status"] == "INITIALIZED"
    assert second.loc[0, "status"] == "CURRENT"
    assert store.read_index_valuations("000300")["trade_date"].nunique() == 2
    assert provider.calls == [("000300", "2004-01-01", "2026-07-29")]


def test_sync_failure_preserves_previous_successful_cache(tmp_path):
    store = ParquetStore(tmp_path / "parquet")
    existing = _valuation_rows(["2026-07-28"])
    store.write_index_valuations("000300", existing)
    service = OfficialIndexValuationSyncService(
        FailingOfficialProvider("permission denied token=secret"),
        store,
        index_codes=("000300",),
        secrets=("secret",),
    )

    result = service.sync_all("2026-07-29")

    assert result.loc[0, "status"] == "FAILED"
    assert "secret" not in result.loc[0, "message"]
    pd.testing.assert_frame_equal(store.read_index_valuations("000300"), existing)


def test_sync_all_fetches_only_dates_after_the_cached_latest_date(tmp_path):
    store = ParquetStore(tmp_path / "parquet")
    store.write_index_valuations("000300", _valuation_rows(["2026-07-28"]))
    provider = FakeOfficialProvider({"000300": _valuation_rows(["2026-07-29"])})
    service = OfficialIndexValuationSyncService(provider, store, index_codes=("000300",))

    result = service.sync_all("2026-07-29")

    assert result.loc[0, "status"] == "UPDATED"
    assert provider.calls == [("000300", "2026-07-29", "2026-07-29")]
    assert store.read_index_valuations("000300")["trade_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-07-28",
        "2026-07-29",
    ]


def test_sync_rejects_invalid_provider_frame_without_replacing_cache(tmp_path):
    store = ParquetStore(tmp_path / "parquet")
    existing = _valuation_rows(["2026-07-28"])
    store.write_index_valuations("000300", existing)
    provider = FakeOfficialProvider(
        {
            "000300": pd.DataFrame(
                {"index_code": ["000300"], "trade_date": ["2026-07-29"], "other": [1]}
            )
        }
    )
    service = OfficialIndexValuationSyncService(provider, store, index_codes=("000300",))

    result = service.sync_all("2026-07-29")

    assert result.loc[0, "status"] == "FAILED"
    assert "valuation metric" in result.loc[0, "message"]
    pd.testing.assert_frame_equal(store.read_index_valuations("000300"), existing)


@pytest.mark.parametrize("invalid_index_code", ["missing", None, "000905"])
def test_sync_rejects_missing_empty_or_mismatched_index_code_without_writing_cache(
    tmp_path, invalid_index_code
):
    backing_store = ParquetStore(tmp_path / "parquet")
    existing = _valuation_rows(["2026-07-28"])
    backing_store.write_index_valuations("000300", existing)
    fetched = _valuation_rows(["2026-07-29"])
    if invalid_index_code == "missing":
        fetched = fetched.drop(columns="index_code")
    else:
        fetched["index_code"] = invalid_index_code
    store = RecordingParquetStore(backing_store)
    provider = FakeOfficialProvider({"000300": fetched})
    service = OfficialIndexValuationSyncService(provider, store, index_codes=("000300",))

    result = service.sync_all("2026-07-29")

    assert result.loc[0, "status"] == "FAILED"
    assert "index_code" in result.loc[0, "message"]
    assert store.write_calls == []
    pd.testing.assert_frame_equal(backing_store.read_index_valuations("000300"), existing)
