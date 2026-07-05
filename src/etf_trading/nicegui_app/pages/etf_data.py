"""ETF data page."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.charts import render_lightweight_chart
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.state import etf_chart_payload
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, etf_overview_rows


def render(snapshot: PlatformSnapshot, section: str, parquet_store=None) -> None:
    if section == "ETF总览":
        _render_rows(etf_overview_rows(snapshot), empty_title="暂无ETF数据")
    elif section == "每日计算池":
        rows = snapshot.watchlist.fillna("").to_dict("records") if not snapshot.watchlist.empty else []
        _render_rows(rows, empty_title="每日计算池为空")
    elif section == "指数样本池":
        rows = snapshot.universe.fillna("").to_dict("records") if not snapshot.universe.empty else []
        _render_rows(rows, empty_title="暂无指数样本池")
    elif section == "搜索加入":
        _render_search()
    else:
        _render_etf_chart(snapshot, parquet_store)
    _render_audit("etf-data")


def _render_rows(rows: list[dict[str, object]], empty_title: str) -> None:
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, pagination=12).classes("workbench-data-table w-full")
    else:
        empty_state(empty_title, "先到数据维护初始化主列表或补齐历史。")


def _render_search() -> None:
    with ui.row().classes("workbench-toolbar w-full"):
        ui.input("代码 / 名称 / 分类").props("dense outlined clearable").classes("w-80")
        ui.select(["全部分类"], value="全部分类", label="分类").props("dense outlined").classes("w-40")
        ui.button("加入计算池", icon="add").props("dense unelevated color=primary")
    ui.label("搜索结果会贴近计算池操作区，避免先滚动再保存。").classes("text-xs text-slate-500")


def _render_etf_chart(snapshot: PlatformSnapshot, parquet_store) -> None:
    rows = etf_overview_rows(snapshot)
    if not rows or parquet_store is None:
        empty_state("暂无ETF K线", "先初始化ETF主列表并补齐历史。")
        return

    selected = str(rows[0].get("ETF代码") or rows[0].get("etf_code") or "")
    if not selected:
        empty_state("暂无ETF K线", "ETF主列表缺少代码字段。")
        return

    payload = etf_chart_payload(parquet_store, selected)
    if not payload[0]["series"]:
        empty_state("暂无ETF K线", "先到数据维护补齐该ETF历史。")
        return

    with ui.row().classes("workbench-toolbar w-full justify-between"):
        ui.label(f"ETF：{selected}").classes("text-sm font-semibold text-slate-700")
        ui.label("近500条记录").classes("text-xs text-slate-500")
    render_lightweight_chart(payload, element_id=f"etf-chart-{selected}")


def _render_audit(page_slug: str) -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == page_slug:
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
