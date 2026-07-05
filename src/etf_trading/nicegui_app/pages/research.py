"""Minimal research page for the first NiceGUI migration."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings


def render(snapshot: PlatformSnapshot, section: str) -> None:
    with ui.column().classes("w-full gap-2"):
        ui.label("策略实验室第一版先保留研究状态和结果入口，复杂回测表单后续迁移。").classes("text-sm text-slate-600")
        with ui.row().classes("workbench-toolbar"):
            ui.button("查看已有结果", icon="analytics").props("dense outline")
            ui.button("返回Streamlit研究页", icon="open_in_new").props("dense outline")
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "research":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
