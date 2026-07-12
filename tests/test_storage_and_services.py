from datetime import date

import pandas as pd

from etf_trading.data.index_catalog import BaselineSource, IndexCatalogEntry, SourceKind
from etf_trading.data.initialization import InitializationService
from etf_trading.data.provider import DataProvider
from etf_trading.data.storage import ParquetStore, SQLiteStore


class _FakeEtfBatchProvider(DataProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []

    def fetch_etf_list(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"etf_code": "510300", "name": "Fresh ETF", "exchange": "SSE", "category": "core", "is_active": 1},
                {"etf_code": "512880", "name": "Missing ETF", "exchange": "SSE", "category": "sector", "is_active": 1},
                {"etf_code": "159915", "name": "Failing ETF", "exchange": "SZSE", "category": "growth", "is_active": 1},
            ]
        )

    def fetch_etf_daily(self, code, start_date, end_date, adjust="qfq") -> pd.DataFrame:
        self.calls.append((code, start_date, end_date))
        if code == "159915":
            raise RuntimeError("provider down")
        return pd.DataFrame(
            {
                "etf_code": [code, code],
                "trade_date": pd.to_datetime(["2026-07-09", "2026-07-10"]),
                "open": [1.0, 1.1],
                "high": [1.2, 1.3],
                "low": [0.9, 1.0],
                "close": [1.1, 1.2],
                "volume": [1000, 1100],
                "amount": [10000, 12000],
            }
        )

    def fetch_etf_nav(self, code, start_date, end_date) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_index_daily(self, code, start_date, end_date) -> pd.DataFrame:
        raise NotImplementedError

    def fetch_trade_calendar(self, market, start_date, end_date) -> pd.DataFrame:
        raise NotImplementedError


class _FailingMasterRefreshProvider(_FakeEtfBatchProvider):
    def fetch_etf_list(self) -> pd.DataFrame:
        raise RuntimeError("master unavailable")


class _EmptyIndexProvider(_FakeEtfBatchProvider):
    def fetch_index_daily(self, code, start_date, end_date) -> pd.DataFrame:
        return pd.DataFrame(columns=["index_code", "trade_date", "open", "high", "low", "close", "volume", "amount"])


class _FakeProvider(_FakeEtfBatchProvider):
    def __init__(self, index_frame: pd.DataFrame) -> None:
        super().__init__()
        self.index_frame = index_frame

    def fetch_index_daily(self, code, start_date, end_date) -> pd.DataFrame:
        return self.index_frame.copy()


class _IndexProvider(_FakeEtfBatchProvider):
    def fetch_index_daily(self, code, start_date, end_date) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "index_code": [code],
                "trade_date": pd.to_datetime(["2026-07-10"]),
                "open": [1.0],
                "high": [1.1],
                "low": [0.9],
                "close": [1.05],
                "volume": [1000],
                "amount": [10000],
            }
        )


def _index_prices_through(code: str, end_date: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": [code],
            "trade_date": pd.to_datetime([end_date]),
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.05],
            "volume": [1000],
            "amount": [10000],
        }
    )


def _prices(code: str, *, start: str, end: str) -> pd.DataFrame:
    dates = pd.to_datetime([start, end])
    return pd.DataFrame(
        {
            "index_code": [code] * len(dates),
            "trade_date": dates,
            "open": [1.0] * len(dates),
            "high": [1.1] * len(dates),
            "low": [0.9] * len(dates),
            "close": [1.05] * len(dates),
            "volume": [1000] * len(dates),
            "amount": [10000] * len(dates),
        }
    )


def _catalog_entry(
    index_code: str,
    *,
    source_kind: SourceKind = "csi",
    index_base_date: date | None = date(2005, 1, 4),
    baseline_source: BaselineSource = "official_methodology",
) -> IndexCatalogEntry:
    return IndexCatalogEntry(
        index_code=index_code,
        name=index_code,
        market="港股" if source_kind == "hk" else "A股",
        category_level_1="测试",
        category_level_2="测试",
        index_type="测试",
        pool="core",
        index_base_date=index_base_date,
        baseline_source=baseline_source,
        source_kind=source_kind,
        provider_symbol=index_code,
    )


def _service_with_catalog(
    tmp_path,
    provider: DataProvider,
    entries: list[IndexCatalogEntry],
) -> tuple[InitializationService, SQLiteStore]:
    store = SQLiteStore(tmp_path / "etf.sqlite")
    service = InitializationService(store, provider=provider, parquet_store=ParquetStore(tmp_path / "parquet"))
    service.sync_index_catalog(entries)
    return service, store


def _fresh_etf_history(code: str) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "etf_code": [code],
            "trade_date": pd.to_datetime(["2026-07-10"]),
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.05],
            "volume": [1000],
            "amount": [10000],
        }
    )
    for column in [
        "ma20",
        "ma60",
        "return_20",
        "return_60",
        "avg_amount_5",
        "avg_amount_20",
        "amount_ratio_5_20",
        "atr20",
        "distance_ma20_atr",
        "distance_ma20_pct",
        "rolling_high_close_60",
    ]:
        frame[column] = 1.0
    frame["is_60d_close_breakout"] = False
    return frame


def test_sqlite_store_persists_etf_master_and_watchlist(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    master = pd.DataFrame(
        [
            {"etf_code": "510300", "name": "沪深300ETF", "exchange": "SSE", "category": "A股宽基", "is_active": 1},
            {"etf_code": "513130", "name": "恒生科技ETF", "exchange": "SSE", "category": "港股科技", "is_active": 1},
        ]
    )

    store.upsert_etf_master(master)
    store.set_watchlist("513130", enabled=True, allow_buy=True, category="港股科技")

    assert store.list_etf_master()["etf_code"].tolist() == ["510300", "513130"]
    watchlist = store.list_watchlist()
    assert watchlist.iloc[0]["etf_code"] == "513130"
    assert watchlist.iloc[0]["allow_buy"] == 1


def test_maintenance_task_run_persists_progress_result_and_interruption(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()

    created = store.create_maintenance_task_run("index_history_batch", progress_total=49)
    store.update_maintenance_task_run(
        created.task_id,
        progress_done=12,
        progress_detail="930633 STALE",
        state="running",
    )
    running = store.get_running_maintenance_task_run("index_history_batch")

    assert running is not None
    assert running.progress_done == 12
    assert running.progress_detail == "930633 STALE"

    store.mark_maintenance_task_interrupted(created.task_id, "服务器已重启")
    interrupted = store.get_maintenance_task_run(created.task_id)

    assert interrupted is not None
    assert interrupted.state == "interrupted"
    assert interrupted.error_message == "服务器已重启"


def test_initialization_service_selects_one_sample_per_required_category(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.upsert_etf_master(
        pd.DataFrame(
            [
                {"etf_code": "510300", "name": "沪深300ETF", "exchange": "SSE", "category": "A股宽基", "is_active": 1, "amount": 900},
                {"etf_code": "512010", "name": "医药ETF", "exchange": "SSE", "category": "A股行业", "is_active": 1, "amount": 800},
                {"etf_code": "159920", "name": "恒生ETF", "exchange": "SZSE", "category": "港股宽基", "is_active": 1, "amount": 700},
                {"etf_code": "513130", "name": "恒生科技ETF", "exchange": "SSE", "category": "港股科技", "is_active": 1, "amount": 1000},
                {"etf_code": "513060", "name": "恒生医疗ETF", "exchange": "SSE", "category": "港股医药", "is_active": 1, "amount": 600},
            ]
        )
    )

    service = InitializationService(store)
    samples = service.select_sample_etfs(["A股宽基", "A股行业", "港股宽基", "港股科技", "港股医药"])

    assert samples["category"].tolist() == ["A股宽基", "A股行业", "港股宽基", "港股科技", "港股医药"]
    assert samples[samples["category"] == "港股科技"].iloc[0]["etf_code"] == "513130"


def test_initialization_service_creates_history_jobs_for_all_master_etfs(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.upsert_etf_master(
        pd.DataFrame(
            [
                {"etf_code": "510300", "name": "沪深300ETF", "exchange": "SSE", "category": "A股宽基", "is_active": 1},
                {"etf_code": "512880", "name": "证券ETF", "exchange": "SSE", "category": "A股行业", "is_active": 1},
            ]
        )
    )

    count = InitializationService(store).create_history_jobs_for_all_master("2021-01-01", "2026-07-03")

    assert count == 2
    with store.connect() as conn:
        jobs = pd.read_sql_query("SELECT job_type, asset_code, start_date, end_date FROM data_fetch_job ORDER BY asset_code", conn)
    assert jobs["asset_code"].tolist() == ["510300", "512880"]
    assert jobs["job_type"].tolist() == ["history", "history"]


def test_ensure_index_history_marks_existing_history_stale_when_provider_returns_no_new_dates(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    parquet = ParquetStore(tmp_path / "parquet")
    store.initialize_schema()
    parquet.write_index_prices("000300", _index_prices_through("000300", "2026-07-01"))
    service = InitializationService(store, provider=_EmptyIndexProvider(), parquet_store=parquet)

    result = service.ensure_index_history("000300", "2026-07-10")

    assert result.status == "STALE"
    with store.connect() as conn:
        state = pd.read_sql_query(
            "SELECT status, error_message FROM data_update_state WHERE dataset='index_daily_price' AND asset_code='000300'",
            conn,
        ).iloc[0]
    assert state["status"] == "STALE"
    assert "2026-07-01" in state["error_message"]
    assert "2026-07-10" in state["error_message"]


def test_ensure_index_history_records_exact_missing_latest_trade_date(tmp_path):
    service, store = _service_with_catalog(
        tmp_path,
        _FakeProvider(index_frame=_prices("000300", start="2005-01-04", end="2026-07-09")),
        [_catalog_entry("000300", index_base_date=date(2005, 1, 4))],
    )

    result = service.ensure_index_history("000300", "2026-07-10")

    assert result.status == "STALE"
    assert result.error_message == "已更新至 2026-07-09，缺少 2026-07-10 行情。"
    with store.connect() as conn:
        state = pd.read_sql_query("SELECT error_message FROM data_update_state", conn).iloc[0]
    assert state["error_message"] == result.error_message


def test_ensure_index_history_records_empty_provider_response_with_source(tmp_path):
    service, store = _service_with_catalog(
        tmp_path,
        _FakeProvider(index_frame=pd.DataFrame()),
        [_catalog_entry("H30533", source_kind="hk", index_base_date=None, baseline_source="unverified")],
    )

    result = service.ensure_index_history("H30533", "2026-07-10")

    assert result.status == "EMPTY"
    assert result.error_message == "港股数据源未返回 H30533 的历史行情。"
    assert result.completeness_message == result.error_message
    with store.connect() as conn:
        state = pd.read_sql_query("SELECT error_message FROM data_update_state", conn).iloc[0]
    assert state["error_message"] == result.error_message


def test_ensure_all_index_history_reports_each_index_progress(tmp_path):
    progress = []
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    service = InitializationService(
        store,
        provider=_IndexProvider(),
        parquet_store=ParquetStore(tmp_path / "parquet"),
    )

    result = service.ensure_all_index_history(
        "2026-07-10",
        index_codes=["000300", "000905"],
        on_progress=progress.append,
    )

    assert result["index_code"].tolist() == ["000300", "000905"]
    assert [(item.done, item.total, item.index_code) for item in progress] == [
        (1, 2, "000300"),
        (2, 2, "000905"),
    ]


def test_ensure_all_etf_history_skips_fresh_fetches_missing_and_reports_progress(tmp_path):
    provider = _FakeEtfBatchProvider()
    sqlite_store = SQLiteStore(tmp_path / "etf.sqlite")
    parquet_store = ParquetStore(tmp_path / "parquet")
    sqlite_store.initialize_schema()
    sqlite_store.upsert_etf_master(provider.fetch_etf_list())
    parquet_store.write_prices("510300", _fresh_etf_history("510300"))
    service = InitializationService(sqlite_store, provider=provider, parquet_store=parquet_store)
    progress_events = []

    result = service.ensure_all_etf_history(
        start_date="2021-07-12",
        through="2026-07-11",
        sleep_seconds=0,
        on_progress=progress_events.append,
    )

    by_code = result.set_index("etf_code")
    assert by_code.loc["510300", "status"] == "SKIPPED"
    assert by_code.loc["510300", "fetched_rows"] == 0
    assert by_code.loc["512880", "status"] == "INITIALIZED"
    assert by_code.loc["512880", "fetched_rows"] == 2
    assert by_code.loc["159915", "status"] == "FAILED"
    assert "provider down" in by_code.loc["159915", "error_message"]
    assert provider.calls == [("159915", "2021-07-12", "2026-07-11"), ("512880", "2021-07-12", "2026-07-11")]

    assert [event.done for event in progress_events] == [1, 2, 3]
    assert [event.total for event in progress_events] == [3, 3, 3]
    assert {event.status for event in progress_events} == {"SKIPPED", "INITIALIZED", "FAILED"}

    stored = parquet_store.read_prices("512880")
    assert stored["trade_date"].dt.strftime("%Y-%m-%d").max() == "2026-07-10"
    with sqlite_store.connect() as conn:
        states = pd.read_sql_query("SELECT asset_code, status FROM data_update_state ORDER BY asset_code", conn)
    assert dict(zip(states["asset_code"], states["status"])) == {
        "159915": "FAILED",
        "510300": "SUCCESS",
        "512880": "SUCCESS",
    }


def test_ensure_all_etf_history_uses_local_master_when_refresh_fails(tmp_path):
    provider = _FailingMasterRefreshProvider()
    sqlite_store = SQLiteStore(tmp_path / "etf.sqlite")
    parquet_store = ParquetStore(tmp_path / "parquet")
    sqlite_store.initialize_schema()
    sqlite_store.upsert_etf_master(
        pd.DataFrame(
            [{"etf_code": "512880", "name": "Local ETF", "exchange": "SSE", "category": "sector", "is_active": 1}]
        )
    )
    service = InitializationService(sqlite_store, provider=provider, parquet_store=parquet_store)

    result = service.ensure_all_etf_history(
        start_date="2021-07-12",
        through="2026-07-11",
        refresh_master=True,
        sleep_seconds=0,
    )

    assert result["etf_code"].tolist() == ["512880"]
    assert result["status"].tolist() == ["INITIALIZED"]
    assert provider.calls == [("512880", "2021-07-12", "2026-07-11")]


def test_sqlite_store_persists_catalog_coverage_and_etf_mappings(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    entry = IndexCatalogEntry(
        index_code="801010",
        name="农林牧渔",
        market="A股",
        category_level_1="申万一级行业",
        category_level_2="一级行业",
        index_type="行业",
        pool="core",
        index_base_date=None,
        baseline_source="unverified",
        source_kind="shenwan",
        provider_symbol="801010",
    )

    store.upsert_index_catalog([entry])
    store.upsert_index_history_coverage(
        "801010",
        index_base_date=None,
        baseline_source="unverified",
        local_first_trade_date="1999-12-30",
        source_first_trade_date="1999-12-30",
        latest_trade_date="2026-07-10",
        history_rows=6408,
        completeness_status="BASELINE_UNVERIFIED",
        completeness_message="基日待核验",
    )
    store.replace_index_etf_mappings(
        pd.DataFrame(
            [
                {
                    "index_code": "801010",
                    "etf_code": "516300",
                    "mapping_source": "data_source",
                    "confidence": "high",
                    "is_tradable": 1,
                }
            ]
        )
    )

    catalog = store.list_index_catalog(pool="core")
    coverage = store.list_index_history_coverage()
    mappings = store.list_index_etf_mappings()

    assert catalog.iloc[0]["index_code"] == "801010"
    assert catalog.iloc[0]["baseline_source"] == "unverified"
    assert coverage.iloc[0]["completeness_status"] == "BASELINE_UNVERIFIED"
    assert mappings.iloc[0]["is_tradable"] == 1


class _PartialIndexHistoryProvider(_FakeEtfBatchProvider):
    def __init__(self) -> None:
        super().__init__()
        self.index_calls: list[tuple[object, object, object]] = []

    def fetch_index_daily(self, index, start_date, end_date) -> pd.DataFrame:
        self.index_calls.append((index, start_date, end_date))
        index_code = getattr(index, "index_code", str(index))
        return pd.DataFrame(
            {
                "index_code": [index_code, index_code],
                "trade_date": pd.to_datetime(["2005-01-04", "2026-07-10"]),
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.5, 101.5],
                "volume": [1000, 1100],
                "amount": [2000, 2100],
                "data_source": ["fake", "fake"],
            }
        )


def test_ensure_index_history_marks_incomplete_when_verified_base_date_is_not_covered(tmp_path):
    entry = IndexCatalogEntry(
        index_code="801010",
        name="农林牧渔",
        market="A股",
        category_level_1="申万一级行业",
        category_level_2="一级行业",
        index_type="行业",
        pool="research",
        index_base_date=date(1999, 12, 30),
        baseline_source="official_methodology",
        source_kind="shenwan",
        provider_symbol="801010",
    )
    store = SQLiteStore(tmp_path / "etf.sqlite")
    provider = _PartialIndexHistoryProvider()
    service = InitializationService(store, provider=provider, parquet_store=ParquetStore(tmp_path / "parquet"))

    service.sync_index_catalog([entry])
    result = service.ensure_index_history("801010", "2026-07-10")

    assert provider.index_calls == [(entry, date(1990, 1, 1), date(2026, 7, 10))]
    assert result.status == "INITIALIZED"
    assert result.completeness_status == "INCOMPLETE"
    coverage = store.list_index_history_coverage().iloc[0]
    assert coverage["local_first_trade_date"] == "2005-01-04"
    assert coverage["completeness_message"] == "应从 1999-12-30 开始，当前仅有 2005-01-04 起的数据。"


def test_validate_index_sources_uses_only_latest_ten_calendar_days_and_persists_result(tmp_path):
    entry = IndexCatalogEntry(
        index_code="801010",
        name="农林牧渔",
        market="A股",
        category_level_1="申万一级行业",
        category_level_2="一级行业",
        index_type="行业",
        pool="research",
        index_base_date=date(1999, 12, 30),
        baseline_source="official_methodology",
        source_kind="shenwan",
        provider_symbol="801010",
    )
    store = SQLiteStore(tmp_path / "etf.sqlite")
    provider = _PartialIndexHistoryProvider()
    service = InitializationService(store, provider=provider, parquet_store=ParquetStore(tmp_path / "parquet"))

    result = service.validate_index_sources("2026-07-10", [entry])

    assert [(call[0].index_code, call[1], call[2]) for call in provider.index_calls] == [
        ("801010", date(2026, 7, 1), date(2026, 7, 10))
    ]
    assert result.iloc[0]["status"] == "SUCCESS"
    with store.connect() as conn:
        state = pd.read_sql_query(
            "SELECT status, last_success_trade_date FROM data_update_state "
            "WHERE dataset='index_source_validation' AND asset_code='801010'",
            conn,
        ).iloc[0]
    assert state["status"] == "SUCCESS"
    assert state["last_success_trade_date"] == "2026-07-10"
