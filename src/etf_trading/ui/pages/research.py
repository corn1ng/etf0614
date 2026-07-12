"""Research replay page."""

from __future__ import annotations

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(*, store: SQLiteStore, parquet_store: ParquetStore, view: str, legacy_render) -> None:
    legacy_render(store, parquet_store, research_view=view)
