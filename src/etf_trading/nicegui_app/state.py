"""State loading for the NiceGUI workbench."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import RLock
import time

import pandas as pd

from etf_trading.data.indexes import DEFAULT_INDEXES, IndexDefinition
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.research.index_etf_universe import build_index_etf_universe
from etf_trading.research.regime import TrendRegimeClassifier, add_trend_regime_features
from etf_trading.strategy.features import add_technical_features
from etf_trading.ui.chart_renderer import build_lightweight_chart_payload
from etf_trading.ui.data_coverage import (
    build_data_coverage_summary,
    build_data_gap_detail,
    build_etf_data_overview,
)

from .view_models import PlatformSnapshot

SNAPSHOT_CACHE_TTL_SECONDS = 60.0
_SNAPSHOT_CACHE: dict[tuple[str, str], tuple[float, PlatformSnapshot]] = {}
_SNAPSHOT_CACHE_LOCK = RLock()


def create_store(db_path: str | Path | None = None) -> SQLiteStore:
    return SQLiteStore() if db_path is None else SQLiteStore(db_path)


def create_parquet_store(root: str | Path | None = None) -> ParquetStore:
    return ParquetStore() if root is None else ParquetStore(root)


def load_snapshot(store: SQLiteStore, parquet_store: ParquetStore) -> PlatformSnapshot:
    store.initialize_schema()
    raw_master = store.list_etf_master()
    watchlist = store.list_watchlist()
    index_summary = build_index_trend_summary(parquet_store)
    universe = build_index_etf_universe(raw_master, parquet_store)
    etf_overview = build_etf_data_overview(raw_master, watchlist, parquet_store, universe)
    gaps = build_data_gap_detail(raw_master, watchlist, index_summary, universe, parquet_store)
    coverage = build_data_coverage_summary(gaps, raw_master, watchlist, index_summary, universe)
    return PlatformSnapshot(
        master=etf_overview,
        watchlist=watchlist,
        index_summary=index_summary,
        universe=universe,
        gaps=gaps,
        coverage=coverage,
        generated_at=datetime.now(),
    )


def load_snapshot_cached(
    store: SQLiteStore,
    parquet_store: ParquetStore,
    *,
    now: float | None = None,
    ttl_seconds: float = SNAPSHOT_CACHE_TTL_SECONDS,
) -> PlatformSnapshot:
    cache_key = _snapshot_cache_key(store, parquet_store)
    timestamp = time.monotonic() if now is None else now
    with _SNAPSHOT_CACHE_LOCK:
        cached = _SNAPSHOT_CACHE.get(cache_key)
        if cached is not None:
            cached_at, snapshot = cached
            if timestamp - cached_at <= ttl_seconds:
                return snapshot

    snapshot = load_snapshot(store, parquet_store)
    with _SNAPSHOT_CACHE_LOCK:
        _SNAPSHOT_CACHE[cache_key] = (timestamp, snapshot)
    return snapshot


def invalidate_snapshot_cache(store: SQLiteStore | None = None, parquet_store: ParquetStore | None = None) -> None:
    with _SNAPSHOT_CACHE_LOCK:
        if store is None or parquet_store is None:
            _SNAPSHOT_CACHE.clear()
            return
        _SNAPSHOT_CACHE.pop(_snapshot_cache_key(store, parquet_store), None)


def _snapshot_cache_key(store: SQLiteStore, parquet_store: ParquetStore) -> tuple[str, str]:
    db_path = Path(getattr(store, "db_path", "")).resolve()
    parquet_root = Path(getattr(parquet_store, "root", "")).resolve()
    return (str(db_path), str(parquet_root))


def build_index_trend_summary(
    parquet_store: ParquetStore,
    definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES,
) -> pd.DataFrame:
    classifier = TrendRegimeClassifier()
    rows: list[dict[str, object]] = []
    for definition in definitions:
        row = {
            "index_code": definition.index_code,
            "index_name": definition.name,
            "market": definition.market,
            "category": definition.category,
            "large_trend": "UNKNOWN",
            "medium_trend": "UNKNOWN",
            "small_trend": "UNKNOWN",
            "allows_new_position": False,
            "latest_date": "",
            "history_rows": 0,
        }
        prices = parquet_store.read_index_prices(definition.index_code)
        if prices.empty:
            rows.append(row)
            continue

        featured = add_trend_regime_features(prices)
        if featured.empty:
            rows.append(row)
            continue

        last = featured.iloc[-1]
        regime = classifier.classify(last)
        row.update(
            {
                "large_trend": regime.large_trend,
                "medium_trend": regime.medium_trend,
                "small_trend": regime.small_trend,
                "allows_new_position": bool(regime.allows_new_position),
                "latest_date": pd.Timestamp(last["trade_date"]).strftime("%Y-%m-%d"),
                "history_rows": int(len(featured)),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def index_chart_payload(parquet_store: ParquetStore, index_code: str) -> list[dict]:
    prices = parquet_store.read_index_prices(index_code)
    if prices.empty:
        return build_lightweight_chart_payload(prices)
    featured = add_technical_features(prices.rename(columns={"index_code": "etf_code"}))
    return build_lightweight_chart_payload(featured, chart_type="candlestick", price_scale_mode="normal")


def etf_chart_payload(parquet_store: ParquetStore, etf_code: str) -> list[dict]:
    prices = parquet_store.read_prices(etf_code)
    if prices.empty:
        return build_lightweight_chart_payload(prices)
    featured = add_technical_features(prices)
    return build_lightweight_chart_payload(featured, chart_type="candlestick", price_scale_mode="normal")
