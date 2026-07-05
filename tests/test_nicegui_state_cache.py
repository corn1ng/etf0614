from datetime import datetime
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
