"""ETF pool page."""

from __future__ import annotations

import streamlit as st

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    render_search_and_add,
    watchlist_status_frame,
) -> None:
    st.subheader("ETF池")
    st.caption("找 ETF、加入每日计算池，并检查买入许可和历史行情状态。")
    watchlist = store.list_watchlist()

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
