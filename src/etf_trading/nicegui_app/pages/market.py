"""Market map page."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.charts import chart_record_label, render_lightweight_chart
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.state import index_chart_payload
from etf_trading.nicegui_app.view_models import (
    PlatformSnapshot,
    code_from_option,
    current_ui_audit_findings,
    index_choice_options,
    market_overview,
)


def render(snapshot: PlatformSnapshot, section: str, parquet_store=None) -> None:
    if section == "市场总览":
        _render_overview(snapshot)
    elif section == "指数买卖参考":
        _render_index_reference(snapshot)
    else:
        _render_index_chart(snapshot, parquet_store)


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


def _render_index_chart(snapshot: PlatformSnapshot, parquet_store) -> None:
    options = index_choice_options(snapshot.index_summary)
    if not options or parquet_store is None:
        empty_state("暂无指数K线", "先补齐指数历史。")
        _render_audit("market")
        return

    def draw_chart(option: str | None) -> None:
        selected = code_from_option(option)
        chart_area.clear()
        with chart_area:
            if not selected:
                empty_state("暂无指数K线", "请选择一个指数。")
                return

            payload = index_chart_payload(parquet_store, selected)
            if not payload[0]["series"]:
                empty_state("暂无指数K线", "先补齐该指数历史。")
                return

            with ui.row().classes("workbench-toolbar w-full justify-between"):
                ui.label(f"指数：{selected}").classes("text-sm font-semibold text-slate-700")
                ui.label(chart_record_label(payload)).classes("text-xs text-slate-500")
            render_lightweight_chart(payload, element_id=f"index-chart-{selected}")

    with ui.row().classes("workbench-toolbar w-full justify-between"):
        ui.select(
            options,
            value=options[0],
            label="选择指数",
            on_change=lambda event: draw_chart(event.value),
        ).props("dense outlined").classes("w-96")
        ui.label("指数只做市场状态判断，ETF 交易载体在 ETF 数据页处理。").classes("text-xs text-slate-500")
    chart_area = ui.column().classes("w-full gap-2")
    draw_chart(options[0])
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
