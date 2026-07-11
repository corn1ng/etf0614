"""Market map page."""

from __future__ import annotations

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    index_summary,
    render_market_overview,
    render_index_filter_explorer,
    render_index_watch,
) -> None:
    if view == "指数买卖参考":
        render_index_filter_explorer(index_summary, parquet_store)
        return
    if view == "指数K线":
        render_index_watch(parquet_store)
        return
    render_market_overview(index_summary)
