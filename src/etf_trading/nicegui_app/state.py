"""State loading for the NiceGUI workbench."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from etf_trading.data.indexes import DEFAULT_INDEXES, IndexDefinition
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.research.index_etf_universe import build_index_etf_universe
from etf_trading.research.regime import TrendRegimeClassifier, add_trend_regime_features
from etf_trading.ui.data_coverage import (
    build_data_coverage_summary,
    build_data_gap_detail,
    build_etf_data_overview,
)

from .view_models import PlatformSnapshot


def create_store(db_path: str | Path | None = None) -> SQLiteStore:
    return SQLiteStore() if db_path is None else SQLiteStore(db_path)


def create_parquet_store(root: str | Path | None = None) -> ParquetStore:
    return ParquetStore() if root is None else ParquetStore(root)


def load_snapshot(store: SQLiteStore, parquet_store: ParquetStore) -> PlatformSnapshot:
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
