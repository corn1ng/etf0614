"""ETF pool page."""

from __future__ import annotations

import streamlit as st

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    render_data_overview,
    render_etf_chart,
    render_index_etf_pool,
    render_search_and_add,
    watchlist_status_frame,
) -> None:
    watchlist = store.list_watchlist()

    if view == "ETF总览":
        render_data_overview(store, parquet_store)
        return

    if view == "ETF行情":
        render_etf_chart(store, parquet_store)
        return

    if view == "指数样本池":
        render_index_etf_pool(store, parquet_store)
        return

    if view == "搜索加入":
        render_search_and_add(store)
        st.markdown("### 每日计算池")
        if watchlist.empty:
            st.info("每日计算池为空。请先在上方搜索 ETF 并保存。")
        else:
            st.dataframe(watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=320)
        return

    st.markdown("### 每日计算池")
    if watchlist.empty:
        st.info("每日计算池为空。请先在“搜索加入”中保存 ETF。")
    else:
        st.dataframe(watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=520)
