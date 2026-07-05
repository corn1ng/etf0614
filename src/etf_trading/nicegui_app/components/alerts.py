"""Compact alert and empty-state helpers."""

from __future__ import annotations

from nicegui import ui


def empty_state(title: str, detail: str) -> None:
    with ui.column().classes("workbench-alert w-full items-center justify-center gap-1 py-6 text-slate-500"):
        ui.icon("info").classes("text-2xl text-blue-600")
        ui.label(title).classes("text-sm font-semibold text-slate-700")
        ui.label(detail).classes("text-xs text-slate-500")
