"""Data maintenance page."""

from __future__ import annotations

from etf_trading.data.initialization import InitializationService
from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    service: InitializationService,
    view: str,
    status: dict[str, object],
    render_data_overview,
    render_gap_detail,
    render_repair_tasks,
    render_settings,
) -> None:
    if view == "数据总览":
        render_data_overview(store, parquet_store, status)
    elif view == "缺口明细":
        render_gap_detail(store, parquet_store, status)
    elif view == "补齐任务":
        render_repair_tasks(store, parquet_store)
    else:
        render_settings(store, service)
