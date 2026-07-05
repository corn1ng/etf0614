"""Data maintenance page."""

from __future__ import annotations

from datetime import date

import pandas as pd
from nicegui import ui

from etf_trading.data.initialization import InitializationService
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, maintenance_rows

SAMPLE_CATEGORIES = ["A股宽基", "A股行业", "港股宽基", "港股科技", "港股医药", "商品", "债券"]


def render(snapshot: PlatformSnapshot, section: str, store=None, parquet_store=None) -> None:
    if section == "数据健康":
        rows = snapshot.coverage.fillna("").to_dict("records") if not snapshot.coverage.empty else []
        _render_rows(rows, "暂无数据健康摘要")
    elif section == "补齐任务":
        _render_tasks(store, parquet_store)
    elif section == "任务日志":
        _render_rows(maintenance_rows(snapshot), "暂无任务日志")
    else:
        _render_rows(
            [
                {"设置项": "自动运行耗时任务", "当前值": "关闭"},
                {"设置项": "Streamlit回退入口", "当前值": "保留"},
            ],
            "暂无设置",
        )
    _render_audit()


def _render_rows(rows: list[dict[str, object]], empty_title: str) -> None:
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, pagination=12).classes("workbench-data-table w-full")
    else:
        empty_state(empty_title, "当前没有检测到需要处理的数据。")


def _render_tasks(store, parquet_store) -> None:
    result_area = ui.column().classes("w-full gap-2")

    with ui.row().classes("workbench-toolbar w-full"):
        master_button = ui.button(
            "初始化ETF主列表",
            icon="database",
            on_click=lambda: _run_task(
                master_button,
                result_area,
                "初始化ETF主列表",
                lambda: _service_with_provider(store, parquet_store).initialize_master(),
                lambda result: f"已写入 {len(result)} 只 ETF",
            ),
        ).props("dense outline")
        sample_button = ui.button(
            "选择样本ETF",
            icon="fact_check",
            on_click=lambda: _run_task(
                sample_button,
                result_area,
                "选择样本ETF",
                lambda: _service(store, parquet_store).select_sample_etfs(SAMPLE_CATEGORIES),
                lambda result: f"已筛选 {len(result)} 只样本 ETF",
            ),
        ).props("dense outline")
        jobs_button = ui.button(
            "生成ETF历史任务",
            icon="history",
            on_click=lambda: _run_task(
                jobs_button,
                result_area,
                "生成ETF历史任务",
                lambda: _service(store, parquet_store).create_history_jobs_for_watchlist(),
                lambda result: f"已创建 {result} 个历史任务",
            ),
        ).props("dense outline")
        index_button = ui.button(
            "补齐指数历史",
            icon="stacked_line_chart",
            on_click=lambda: _run_task(
                index_button,
                result_area,
                "补齐指数历史",
                lambda: _service_with_provider(store, parquet_store).ensure_all_index_history(date.today()),
                lambda result: f"已检查 {len(result)} 个指数",
            ),
        ).props("dense outline")
    ui.label("补齐任务只在点击后执行，避免打开页面自动触发耗时操作。").classes("text-xs text-slate-500")


def _run_task(button, result_area, title: str, action, success_message) -> None:
    if button is not None:
        button.disable()
    result_area.clear()
    try:
        result = action()
    except Exception as exc:  # noqa: BLE001 - UI should surface provider/storage errors clearly
        ui.notify(f"{title}失败：{exc}", type="negative")
        with result_area:
            empty_state(f"{title}失败", str(exc))
    else:
        message = success_message(result)
        ui.notify(message, type="positive")
        with result_area:
            ui.label(message).classes("text-sm font-semibold text-slate-700")
            _render_task_result(result)
    finally:
        if button is not None:
            button.enable()


def _render_task_result(result) -> None:
    if isinstance(result, pd.DataFrame):
        rows = result.fillna("").to_dict("records") if not result.empty else []
    elif isinstance(result, list):
        rows = result
    else:
        rows = [{"结果": result}]
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, pagination=10).classes("workbench-data-table w-full")


def _service(store, parquet_store) -> InitializationService:
    if store is None:
        raise ValueError("当前页面没有可用数据库连接")
    return InitializationService(store=store, parquet_store=parquet_store)


def _service_with_provider(store, parquet_store) -> InitializationService:
    if store is None:
        raise ValueError("当前页面没有可用数据库连接")
    return InitializationService(store=store, provider=AkShareProvider(), parquet_store=parquet_store)


def _render_audit() -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "maintenance":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
