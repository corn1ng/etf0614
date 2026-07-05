"""Status metric components."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.theme import tone_class
from etf_trading.nicegui_app.view_models import MetricTile


def metric_strip(metrics: list[MetricTile]) -> None:
    with ui.row().classes("w-full gap-2"):
        for metric in metrics:
            with ui.column().classes("workbench-metric gap-0"):
                ui.label(metric.label).classes("workbench-metric-label")
                ui.label(metric.value).classes(f"workbench-metric-value {tone_class(metric.tone)}")
                if metric.detail:
                    ui.label(metric.detail).classes("text-xs text-slate-400")
