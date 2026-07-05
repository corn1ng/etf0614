"""Data maintenance page."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, maintenance_rows


def render(snapshot: PlatformSnapshot, section: str) -> None:
    if section == "数据健康":
        rows = snapshot.coverage.fillna("").to_dict("records") if not snapshot.coverage.empty else []
        _render_rows(rows, "暂无数据健康摘要")
    elif section == "补齐任务":
        _render_tasks()
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


def _render_tasks() -> None:
    with ui.row().classes("workbench-toolbar w-full"):
        ui.button("初始化ETF主列表", icon="database").props("dense outline")
        ui.button("补齐ETF历史", icon="history").props("dense outline")
        ui.button("补齐指数历史", icon="stacked_line_chart").props("dense outline")
    ui.label("补齐任务只在点击后执行，避免打开页面自动触发耗时操作。").classes("text-xs text-slate-500")


def _render_audit() -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "maintenance":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
