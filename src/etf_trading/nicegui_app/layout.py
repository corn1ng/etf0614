"""Application shell for the NiceGUI workbench."""

from __future__ import annotations

from urllib.parse import quote

from nicegui import ui

from .navigation import NICEGUI_PAGES, NicePageSpec, get_page_by_slug, resolve_section
from .theme import apply_theme


def render_shell(page_slug: str | None = None, section: str | None = None) -> None:
    apply_theme()
    page = get_page_by_slug(page_slug)
    active_section = resolve_section(page, section)

    with ui.row().classes("workbench-shell w-full no-wrap"):
        _render_sidebar(page.slug)
        with ui.column().classes("workbench-main flex-1 no-wrap"):
            _render_topbar()
            with ui.column().classes("workbench-page w-full"):
                _render_page_header(page, active_section)
                _render_page(page.slug, active_section)


def _render_sidebar(active_slug: str) -> None:
    with ui.column().classes("workbench-sidebar min-h-screen gap-1 p-2"):
        ui.label("ETF 工作台").classes("workbench-brand")
        for page in NICEGUI_PAGES:
            classes = "workbench-nav-item"
            if page.slug == active_slug:
                classes += " is-active"
            ui.link(page.label, f"/page/{page.slug}").classes(classes)


def _render_topbar() -> None:
    with ui.row().classes("workbench-topbar w-full items-center justify-between px-4"):
        ui.label("本地量化工作台").classes("text-sm font-semibold text-slate-700")
        with ui.row().classes("items-center gap-2"):
            ui.icon("radio_button_checked").classes("text-xs text-emerald-500")
            ui.label("NiceGUI").classes("text-xs text-slate-500")


def _render_page_header(page: NicePageSpec, active_section: str) -> None:
    with ui.row().classes("w-full items-end justify-between gap-3"):
        with ui.column().classes("gap-0"):
            ui.label(page.label).classes("workbench-page-title")
            ui.label(page.caption).classes("workbench-page-caption")
        with ui.row().classes("workbench-toolbar"):
            for item in page.sections:
                classes = "workbench-section-tab"
                if item == active_section:
                    classes += " is-active"
                ui.link(item, f"/page/{page.slug}/{quote(item, safe='')}").classes(classes)


def _render_page(page_slug: str, section: str) -> None:
    ui.label(f"{page_slug} / {section} 页面迁移中").classes("text-sm text-slate-500")
