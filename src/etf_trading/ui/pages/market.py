"""Market map page."""

from __future__ import annotations

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    index_summary,
    render_index_filter_explorer,
    render_etf_chart,
    render_index_watch,
) -> None:
    if view == "ETF行情":
        render_etf_chart(store, parquet_store)
    else:
        render_index_watch(parquet_store)
