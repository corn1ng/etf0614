"""Compact controls."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui


def refresh_button(on_click: Callable[[], None] | None = None) -> None:
    ui.button("刷新", icon="refresh", on_click=on_click).props("dense outline").classes("h-8")
