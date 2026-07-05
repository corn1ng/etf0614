"""Market map page."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, market_overview


def render(snapshot: PlatformSnapshot, section: str, parquet_store=None) -> None:
    if section == "市场总览":
        _render_overview(snapshot)
    elif section == "指数买卖参考":
        _render_index_reference(snapshot)
    else:
        _render_index_chart_placeholder(snapshot)


def _render_overview(snapshot: PlatformSnapshot) -> None:
    overview = market_overview(snapshot)
    with ui.row().classes("w-full gap-2"):
        _metric("指数总数", overview["total_indexes"], "全市场观察池")
        _metric("可参与指数", overview["allowed_indexes"], "趋势允许")
        _metric("覆盖分类", len(overview["categories"]), "市场分组")

    rows = overview["categories"]
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, row_key="category").classes("workbench-data-table w-full")
    else:
        empty_state("暂无指数状态", "到数据维护补齐指数历史后再查看市场总览。")
    _render_audit("market")


def _render_index_reference(snapshot: PlatformSnapshot) -> None:
    rows = snapshot.index_summary.fillna("").to_dict("records") if not snapshot.index_summary.empty else []
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, row_key="index_code").classes("workbench-data-table w-full")
    else:
        empty_state("暂无指数买卖参考", "先补齐指数历史。")
    _render_audit("market")


def _render_index_chart_placeholder(snapshot: PlatformSnapshot) -> None:
    if snapshot.index_summary.empty:
        empty_state("暂无指数K线", "先补齐指数历史。")
        return
    with ui.column().classes("workbench-chart-panel w-full items-center justify-center gap-2"):
        ui.icon("show_chart").classes("text-4xl text-blue-600")
        ui.label("指数K线图将在接入历史行情后显示").classes("text-sm font-semibold text-slate-700")
        ui.label("筛选、区间和图表会在同一工具区内完成，避免K线被控件挤到首屏下方。").classes("text-xs text-slate-500")
    _render_audit("market")


def _metric(label: str, value: object, detail: str) -> None:
    with ui.column().classes("workbench-metric"):
        ui.label(label).classes("workbench-metric-label")
        ui.label(str(value)).classes("workbench-metric-value")
        ui.label(detail).classes("text-xs text-slate-400")


def _render_audit(page_slug: str) -> None:
    findings = [item for item in current_ui_audit_findings() if item.page_slug == page_slug]
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in findings:
            ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
