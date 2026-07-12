from datetime import datetime
import json
from pathlib import Path

import pandas as pd
import pytest

from etf_trading.data.index_catalog import IndexCatalogEntry
from etf_trading.data.indexes import IndexDefinition
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.nicegui_app import state
from etf_trading.nicegui_app.view_models import PlatformSnapshot
from etf_trading.research.index_health_snapshot import INDEX_ATOMIC_DETAIL_COLUMNS, INDEX_ATOMIC_SUMMARY_COLUMNS


class FakeStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)


class FakeParquetStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root)


def _snapshot(label: str) -> PlatformSnapshot:
    return PlatformSnapshot(
        master=pd.DataFrame({"label": [label]}),
        watchlist=pd.DataFrame(),
        index_summary=pd.DataFrame(),
        universe=pd.DataFrame(),
        gaps=pd.DataFrame(),
        coverage=pd.DataFrame(),
        generated_at=datetime(2026, 7, 5, 12, 0, 0),
    )


def _atomic_master() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "etf_code": ["510300"],
            "name": ["沪深300ETF"],
            "category": ["A股宽基"],
            "exchange": ["SSE"],
            "tradability_status": ["exchange_traded"],
        }
    )


def _definition(index_code: str, *, pool: str = "core") -> IndexDefinition:
    return IndexDefinition(
        index_code=index_code,
        name=f"Index {index_code}",
        market="A股",
        category="宽基",
        provider_symbol=index_code,
        pool=pool,
        baseline_source="unverified",
    )


def _parquet_store(tmp_path: Path) -> ParquetStore:
    return ParquetStore(tmp_path / "parquet")


def _summary(index_code: str) -> pd.DataFrame:
    row = {column: pd.NA for column in INDEX_ATOMIC_SUMMARY_COLUMNS}
    row.update(
        {
            "index_code": index_code,
            "index_name": f"Index {index_code}",
            "snapshot_status": "ready",
            "history_status": "complete",
            "latest_date": "2026-07-11",
        }
    )
    return pd.DataFrame([row], columns=INDEX_ATOMIC_SUMMARY_COLUMNS)


def _details(index_code: str) -> pd.DataFrame:
    row = {column: pd.NA for column in INDEX_ATOMIC_DETAIL_COLUMNS}
    row.update({"index_code": index_code, "metric_key": "close", "status": "ready"})
    return pd.DataFrame([row], columns=INDEX_ATOMIC_DETAIL_COLUMNS)


def _coverage(index_code: str, latest_trade_date: str = "2026-07-12") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": [index_code],
            "latest_trade_date": [latest_trade_date],
            "history_rows": [1000],
            "completeness_status": ["complete"],
        }
    )


def _read_index_atomic_meta(parquet_store: ParquetStore) -> dict[str, object]:
    return json.loads((parquet_store.root / "cache" / "index_atomic_snapshot.meta.json").read_text(encoding="utf-8"))


def _write_atomic_cache(root: Path, signature: str, schema_version: int | None = None) -> None:
    cache_dir = root / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "etf_code": ["510300"],
            "name": ["沪深300ETF"],
            "category": ["A股宽基"],
            "history_status": ["complete"],
            "feature_status": ["complete"],
        }
    ).to_parquet(cache_dir / "atomic_indicators.parquet", index=False)
    (cache_dir / "atomic_indicators.meta.json").write_text(
        json.dumps(
            {
                "schema_version": state.ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION if schema_version is None else schema_version,
                "source_signature": signature,
                "generated_at": "2026-07-05T12:00:00",
                "rows": 1,
            }
        ),
        encoding="utf-8",
    )


def test_read_atomic_snapshot_disk_cache_rejects_legacy_schema(tmp_path):
    root = tmp_path / "parquet"
    _write_atomic_cache(root, "legacy-signature", schema_version=1)

    assert state._read_atomic_snapshot_disk_cache(FakeParquetStore(str(root))) is None


def test_load_snapshot_cached_reuses_snapshot_within_ttl(monkeypatch):
    calls: list[str] = []

    def fake_load_snapshot(store, parquet_store):
        calls.append("called")
        return _snapshot(f"snapshot-{len(calls)}")

    monkeypatch.setattr(state, "load_snapshot", fake_load_snapshot)
    state.invalidate_snapshot_cache()

    store = FakeStore("database/cache-test.sqlite")
    parquet_store = FakeParquetStore("data/cache-test")
    first = state.load_snapshot_cached(store, parquet_store, now=100.0, ttl_seconds=60)
    second = state.load_snapshot_cached(store, parquet_store, now=120.0, ttl_seconds=60)

    assert first is second
    assert calls == ["called"]


def test_load_snapshot_cached_refreshes_after_invalidate(monkeypatch):
    calls: list[str] = []

    def fake_load_snapshot(store, parquet_store):
        calls.append("called")
        return _snapshot(f"snapshot-{len(calls)}")

    monkeypatch.setattr(state, "load_snapshot", fake_load_snapshot)
    state.invalidate_snapshot_cache()

    store = FakeStore("database/cache-test.sqlite")
    parquet_store = FakeParquetStore("data/cache-test")
    first = state.load_snapshot_cached(store, parquet_store, now=100.0, ttl_seconds=60)
    state.invalidate_snapshot_cache(store, parquet_store)
    second = state.load_snapshot_cached(store, parquet_store, now=101.0, ttl_seconds=60)

    assert first is not second
    assert calls == ["called", "called"]


def test_load_atomic_snapshot_cached_uses_fresh_disk_cache_without_building(tmp_path, monkeypatch):
    root = tmp_path / "parquet"
    _write_atomic_cache(root, "current-signature")
    scheduled: list[str] = []
    monkeypatch.setattr(state, "_atomic_snapshot_source_signature", lambda master, parquet_store: "current-signature", raising=False)
    monkeypatch.setattr(state, "_start_atomic_snapshot_build", lambda *args, **kwargs: scheduled.append("build"), raising=False)
    state.invalidate_atomic_snapshot_cache()

    result = state.load_atomic_snapshot_cached(_atomic_master(), FakeParquetStore(str(root)))

    assert result.status == "ready"
    assert result.frame["etf_code"].tolist() == ["510300"]
    assert scheduled == []


def test_load_atomic_snapshot_cached_serves_stale_cache_while_scheduling_refresh(tmp_path, monkeypatch):
    root = tmp_path / "parquet"
    _write_atomic_cache(root, "old-signature")
    scheduled: list[str] = []
    monkeypatch.setattr(state, "_atomic_snapshot_source_signature", lambda master, parquet_store: "current-signature", raising=False)
    monkeypatch.setattr(state, "_start_atomic_snapshot_build", lambda *args, **kwargs: scheduled.append("build"), raising=False)
    state.invalidate_atomic_snapshot_cache()

    result = state.load_atomic_snapshot_cached(_atomic_master(), FakeParquetStore(str(root)))

    assert result.status == "stale"
    assert result.frame["etf_code"].tolist() == ["510300"]
    assert scheduled == ["build"]


def test_load_atomic_snapshot_cached_returns_building_without_cache(tmp_path, monkeypatch):
    root = tmp_path / "parquet"
    scheduled: list[str] = []
    monkeypatch.setattr(state, "_atomic_snapshot_source_signature", lambda master, parquet_store: "current-signature", raising=False)
    monkeypatch.setattr(state, "_start_atomic_snapshot_build", lambda *args, **kwargs: scheduled.append("build"), raising=False)
    state.invalidate_atomic_snapshot_cache()

    result = state.load_atomic_snapshot_cached(_atomic_master(), FakeParquetStore(str(root)))

    assert result.status == "building"
    assert result.frame.empty
    assert scheduled == ["build"]


def test_load_snapshot_cached_refreshes_after_ttl(monkeypatch):
    calls: list[str] = []

    def fake_load_snapshot(store, parquet_store):
        calls.append("called")
        return _snapshot(f"snapshot-{len(calls)}")

    monkeypatch.setattr(state, "load_snapshot", fake_load_snapshot)
    state.invalidate_snapshot_cache()

    store = FakeStore("database/cache-test.sqlite")
    parquet_store = FakeParquetStore("data/cache-test")
    first = state.load_snapshot_cached(store, parquet_store, now=100.0, ttl_seconds=10)
    second = state.load_snapshot_cached(store, parquet_store, now=111.0, ttl_seconds=10)

    assert first is not second
    assert calls == ["called", "called"]


def test_load_snapshot_limits_tradeable_universe_and_mapping_to_sqlite_core_catalog(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    parquet_store = ParquetStore(tmp_path / "parquet")
    store.initialize_schema()
    entries = (
        IndexCatalogEntry(
            index_code="000300", name="沪深300", market="A股", category_level_1="宽基", category_level_2="核心宽基",
            index_type="宽基", pool="core", index_base_date=None, baseline_source="unverified",
            source_kind="csi", provider_symbol="000300",
        ),
        IndexCatalogEntry(
            index_code="801010", name="农林牧渔", market="A股", category_level_1="申万一级行业", category_level_2="一级行业",
            index_type="行业", pool="research", index_base_date=None, baseline_source="unverified",
            source_kind="shenwan", provider_symbol="801010",
        ),
    )
    store.upsert_index_catalog(entries)
    store.upsert_etf_master(
        pd.DataFrame(
            [
                {"etf_code": "510300", "name": "沪深300ETF", "tracking_index": "000300", "is_active": 1, "amount": 100},
                {"etf_code": "516300", "name": "农林牧渔ETF", "tracking_index": "801010", "is_active": 1, "amount": 90},
            ]
        )
    )
    prices = pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-01", periods=300, freq="D"),
            "open": [1.0] * 300,
            "high": [1.1] * 300,
            "low": [0.9] * 300,
            "close": [1.0] * 300,
            "volume": [1000] * 300,
            "amount": [1000] * 300,
        }
    )
    parquet_store.write_prices("510300", prices.assign(etf_code="510300"))
    parquet_store.write_prices("516300", prices.assign(etf_code="516300"))
    monkeypatch.setattr(state, "build_index_trend_summary", lambda *args, **kwargs: pd.DataFrame())

    snapshot = state.load_snapshot(store, parquet_store)

    assert snapshot.universe["index_code"].tolist() == ["000300"]
    assert store.list_index_etf_mappings()["index_code"].tolist() == ["000300"]


def test_readonly_loader_never_calls_builder_when_snapshot_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        state,
        "build_index_atomic_snapshot",
        lambda *args, **kwargs: pytest.fail("page must not build"),
    )

    result = state.load_index_atomic_snapshot_readonly(_parquet_store(tmp_path), (_definition("000300"),))

    assert result.status == "missing"
    assert result.summary.empty
    assert list(result.summary.columns) == INDEX_ATOMIC_SUMMARY_COLUMNS
    assert list(result.details.columns) == INDEX_ATOMIC_DETAIL_COLUMNS


def test_readonly_loader_marks_signature_mismatch_stale_and_keeps_previous_rows(tmp_path):
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    coverage = _coverage("000300", "2026-07-13")
    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        "old-signature",
        datetime(2026, 7, 12, 9, 0),
        parquet_store,
        definitions=definitions,
        coverage=coverage,
    )

    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions, coverage=coverage)

    assert result.status == "stale"
    assert result.summary["index_code"].tolist() == ["000300"]
    assert result.generated_at == datetime(2026, 7, 12, 9, 0)
    assert result.current_latest_date == "2026-07-13"


def test_atomic_snapshot_meta_records_schema_catalog_source_and_task_result(tmp_path):
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    coverage = _coverage("000300")
    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        "source-signature",
        datetime(2026, 7, 12, 9, 0),
        parquet_store,
        definitions=definitions,
        coverage=coverage,
        task_result_id=17,
    )

    meta = _read_index_atomic_meta(parquet_store)

    assert meta["schema_version"] == state.INDEX_ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION
    assert meta["catalog_signature"] == state._index_atomic_snapshot_catalog_signature(definitions)
    assert meta["source_signature"] == "source-signature"
    assert meta["generated_at"] == "2026-07-12T09:00:00"
    assert meta["task_result_id"] == 17
    assert meta["data_status_counts"] == {"ready": 1}
    assert meta["coverage_signature"] == state._index_atomic_snapshot_coverage_signature(coverage)


def test_index_atomic_snapshot_inputs_excludes_reserve_catalog_entries(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.upsert_index_catalog(
        (
            IndexCatalogEntry(
                index_code="000300", name="沪深300", market="A股", category_level_1="宽基", category_level_2="宽基",
                index_type="宽基", pool="core", index_base_date=None, baseline_source="unverified",
                source_kind="csi", provider_symbol="000300",
            ),
            IndexCatalogEntry(
                index_code="801010", name="农林牧渔", market="A股", category_level_1="行业", category_level_2="行业",
                index_type="行业", pool="research", index_base_date=None, baseline_source="unverified",
                source_kind="shenwan", provider_symbol="801010",
            ),
            IndexCatalogEntry(
                index_code="000001", name="上证指数", market="A股", category_level_1="宽基", category_level_2="宽基",
                index_type="宽基", pool="reserve", index_base_date=None, baseline_source="unverified",
                source_kind="csi", provider_symbol="000001",
            ),
        )
    )
    store.upsert_index_history_coverage(
        "000300",
        index_base_date=None,
        baseline_source="unverified",
        local_first_trade_date="2020-01-01",
        source_first_trade_date=None,
        latest_trade_date="2026-07-11",
        history_rows=1000,
        completeness_status="complete",
        completeness_message="完整",
    )

    definitions, coverage = state.index_atomic_snapshot_inputs(store)

    assert [definition.index_code for definition in definitions] == ["000300", "801010"]
    assert coverage["index_code"].tolist() == ["000300"]


def test_readonly_loader_returns_failed_for_corrupt_snapshot_files(tmp_path):
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        "source-signature",
        datetime(2026, 7, 12, 9, 0),
        parquet_store,
        definitions=definitions,
    )
    (parquet_store.root / "cache" / "index_atomic_snapshot.meta.json").write_text("{broken", encoding="utf-8")

    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions)

    assert result.status == "failed"
    assert result.summary.empty
    assert "读取指数原子快照失败" in result.message


def test_failed_atomic_snapshot_write_keeps_last_successful_snapshot(tmp_path, monkeypatch):
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        "old-signature",
        datetime(2026, 7, 12, 9, 0),
        parquet_store,
        definitions=definitions,
    )
    original_to_parquet = pd.DataFrame.to_parquet
    writes = 0

    def fail_second_temp_write(frame, path, *args, **kwargs):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("disk full")
        return original_to_parquet(frame, path, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_second_temp_write)
    with pytest.raises(OSError, match="disk full"):
        state.write_index_atomic_snapshot(
            _summary("000300"),
            _details("000300"),
            "new-signature",
            datetime(2026, 7, 12, 10, 0),
            parquet_store,
            definitions=definitions,
        )

    monkeypatch.setattr(
        state,
        "_index_atomic_snapshot_source_signature",
        lambda parquet_store, definitions, coverage=None: "old-signature",
    )
    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions)

    assert result.status == "ready"
    assert result.generated_at == datetime(2026, 7, 12, 9, 0)


def test_final_atomic_snapshot_publish_failure_restores_all_previous_files(tmp_path, monkeypatch):
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        "old-signature",
        datetime(2026, 7, 12, 9, 0),
        parquet_store,
        definitions=definitions,
    )
    _, _, meta_file = state._index_atomic_snapshot_cache_paths(parquet_store)
    original_replace = Path.replace
    failed = False

    def fail_final_meta_publish(path, target):
        nonlocal failed
        if not failed and Path(target) == meta_file and ".tmp" in path.name:
            failed = True
            raise OSError("final publish failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_final_meta_publish)
    with pytest.raises(OSError, match="final publish failed"):
        state.write_index_atomic_snapshot(
            _summary("000905"),
            _details("000905"),
            "new-signature",
            datetime(2026, 7, 12, 10, 0),
            parquet_store,
            definitions=definitions,
        )

    monkeypatch.setattr(
        state,
        "_index_atomic_snapshot_source_signature",
        lambda parquet_store, definitions, coverage=None: "old-signature",
    )
    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions)

    assert result.status == "ready"
    assert result.summary["index_code"].tolist() == ["000300"]
    assert result.details["index_code"].tolist() == ["000300"]
    assert result.generated_at == datetime(2026, 7, 12, 9, 0)


def test_atomic_snapshot_temp_validation_failure_preserves_previous_files(tmp_path, monkeypatch):
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        "old-signature",
        datetime(2026, 7, 12, 9, 0),
        parquet_store,
        definitions=definitions,
    )
    original_read_parquet = pd.read_parquet

    def fail_temp_validation(path, *args, **kwargs):
        if ".tmp" in Path(path).name:
            raise OSError("temporary snapshot validation failed")
        return original_read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", fail_temp_validation)
    with pytest.raises(OSError, match="temporary snapshot validation failed"):
        state.write_index_atomic_snapshot(
            _summary("000905"),
            _details("000905"),
            "new-signature",
            datetime(2026, 7, 12, 10, 0),
            parquet_store,
            definitions=definitions,
        )

    monkeypatch.setattr(
        state,
        "_index_atomic_snapshot_source_signature",
        lambda parquet_store, definitions, coverage=None: "old-signature",
    )
    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions)

    assert result.status == "ready"
    assert result.summary["index_code"].tolist() == ["000300"]


@pytest.mark.parametrize("invalid_value", [None, 17])
def test_readonly_loader_fails_for_missing_or_invalid_coverage_signature(tmp_path, invalid_value):
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    coverage = _coverage("000300")
    source_signature = state._index_atomic_snapshot_source_signature(parquet_store, definitions, coverage)
    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        source_signature,
        datetime(2026, 7, 12, 9, 0),
        parquet_store,
        definitions=definitions,
        coverage=coverage,
    )
    _, _, meta_file = state._index_atomic_snapshot_cache_paths(parquet_store)
    meta = _read_index_atomic_meta(parquet_store)
    if invalid_value is None:
        del meta["coverage_signature"]
    else:
        meta["coverage_signature"] = invalid_value
    meta_file.write_text(json.dumps(meta), encoding="utf-8")

    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions, coverage=coverage)

    assert result.status == "failed"
    assert result.summary.empty


def test_readonly_loader_marks_coverage_signature_mismatch_stale(tmp_path):
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    coverage = _coverage("000300", "2026-07-14")
    source_signature = state._index_atomic_snapshot_source_signature(parquet_store, definitions, coverage)
    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        source_signature,
        datetime(2026, 7, 12, 9, 0),
        parquet_store,
        definitions=definitions,
        coverage=coverage,
    )
    _, _, meta_file = state._index_atomic_snapshot_cache_paths(parquet_store)
    meta = _read_index_atomic_meta(parquet_store)
    meta["coverage_signature"] = "mismatch"
    meta_file.write_text(json.dumps(meta), encoding="utf-8")

    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions, coverage=coverage)

    assert result.status == "stale"
    assert result.current_latest_date == "2026-07-14"
    assert result.summary["index_code"].tolist() == ["000300"]


def test_index_atomic_snapshot_read_and_write_share_module_lock(tmp_path, monkeypatch):
    class RecordingLock:
        def __init__(self) -> None:
            self.entries = 0

        def __enter__(self):
            self.entries += 1
            return self

        def __exit__(self, *args):
            return False

    lock = RecordingLock()
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    monkeypatch.setattr(state, "_INDEX_ATOMIC_SNAPSHOT_LOCK", lock, raising=False)
    monkeypatch.setattr(
        state,
        "_index_atomic_snapshot_source_signature",
        lambda parquet_store, definitions, coverage=None: "current-signature",
    )

    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        "current-signature",
        datetime(2026, 7, 12, 9, 0),
        parquet_store,
        definitions=definitions,
    )
    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions)

    assert result.status == "ready"
    assert lock.entries == 2
