"""Market map page."""

from __future__ import annotations

import streamlit as st

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    build_index_trend_summary,
    render_index_filter_explorer,
    render_etf_chart,
    render_index_watch,
) -> None:
    st.subheader("市场地图")
    st.caption("先看指数过滤和趋势结构，再下钻到 ETF 行情。")
    index_summary = build_index_trend_summary(parquet_store)

    if view == "指数买卖参考":
        render_index_filter_explorer(index_summary, parquet_store)
    elif view == "ETF行情":
        render_etf_chart(store, parquet_store)
    else:
        render_index_watch(parquet_store)
