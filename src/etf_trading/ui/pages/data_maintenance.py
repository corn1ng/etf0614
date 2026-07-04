"""Data maintenance page."""

from __future__ import annotations

import streamlit as st

from etf_trading.data.initialization import InitializationService
from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    service: InitializationService,
    view: str,
    platform_status,
    render_data_health,
    render_index_quick_sync,
    render_data_center,
    render_settings,
) -> None:
    st.subheader("数据维护")
    st.caption("低频维护入口：先看数据健康，再初始化数据、补齐指数历史、查看任务日志。")
    status = platform_status(store, parquet_store)

    if view == "数据健康":
        render_data_health(status)
        render_index_quick_sync(store, parquet_store)
    elif view == "数据中心":
        render_data_health(status)
        render_index_quick_sync(store, parquet_store)
        render_data_center(store, parquet_store)
    else:
        render_data_health(status)
        render_settings(store, service)
