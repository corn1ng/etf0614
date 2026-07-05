"""Daily action page."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.status import metric_strip
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, status_metrics


def render(snapshot: PlatformSnapshot, section: str) -> None:
    metric_strip(status_metrics(snapshot))
    if section == "计算池明细":
        rows = snapshot.watchlist.fillna("").to_dict("records") if not snapshot.watchlist.empty else []
    elif section == "每日建议":
        rows = snapshot.index_summary.fillna("").to_dict("records") if not snapshot.index_summary.empty else []
    else:
        rows = snapshot.gaps.fillna("").to_dict("records") if not snapshot.gaps.empty else []

    if rows:
        ui.table(columns=table_columns(rows), rows=rows, pagination=10).classes("workbench-data-table w-full")
    else:
        empty_state("当前无待处理事项", "系统状态可用时，这里会保持轻量。")
    _render_audit()


def _render_audit() -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "action":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
