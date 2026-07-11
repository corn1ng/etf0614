from datetime import datetime
import json
from pathlib import Path

import pandas as pd

from etf_trading.nicegui_app import state
from etf_trading.nicegui_app.view_models import PlatformSnapshot


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


def test_load_index_health_snapshot_cached_writes_and_reuses_disk_cache(tmp_path, monkeypatch):
    summary = pd.DataFrame({"index_code": ["000300"], "valuation_health_status": ["complete"]})
    details = pd.DataFrame({"index_code": ["000300"], "detail_kind": ["valuation"], "metric_name": ["pe_ttm"]})
    calls: list[str] = []

    def fake_builder(parquet_store, definitions=None):
        calls.append("build")
        return summary, details

    monkeypatch.setattr(state, "build_index_health_snapshot", fake_builder, raising=False)
    monkeypatch.setattr(state, "_index_health_snapshot_source_signature", lambda parquet_store, definitions: "current", raising=False)
    state.invalidate_index_health_snapshot_cache()

    parquet_store = FakeParquetStore(str(tmp_path / "parquet"))
    first = state.load_index_health_snapshot_cached(parquet_store)
    second = state.load_index_health_snapshot_cached(parquet_store)

    assert first.status == "ready"
    assert second.status == "ready"
    assert second.summary["index_code"].tolist() == ["000300"]
    assert second.details["metric_name"].tolist() == ["pe_ttm"]
    assert calls == ["build"]


def test_load_index_health_snapshot_cached_persists_mixed_detail_values(tmp_path, monkeypatch):
    summary = pd.DataFrame({"index_code": ["000300"], "valuation_health_status": ["complete"]})
    details = pd.DataFrame(
        {
            "index_code": ["000300", "000300"],
            "detail_kind": ["trend", "valuation"],
            "metric_name": ["large_trend", "pe_ttm"],
            "metric_label": ["大趋势", "市盈率TTM"],
            "current_value": ["UP", 12.5],
            "status": ["normal", "computed"],
            "reason": ["大趋势向上", "已计算历史分位"],
            "historical_percentile": [pd.NA, 42.0],
        }
    )

    monkeypatch.setattr(state, "build_index_health_snapshot", lambda parquet_store, definitions=None: (summary, details), raising=False)
    monkeypatch.setattr(state, "_index_health_snapshot_source_signature", lambda parquet_store, definitions: "mixed-values", raising=False)
    state.invalidate_index_health_snapshot_cache()

    parquet_store = FakeParquetStore(str(tmp_path / "parquet"))
    first = state.load_index_health_snapshot_cached(parquet_store)
    state.invalidate_index_health_snapshot_cache(parquet_store)
    second = state.load_index_health_snapshot_cached(parquet_store)

    assert first.status == "ready"
    assert second.status == "ready"
    assert second.details["current_value"].tolist() == ["UP", "12.5"]
