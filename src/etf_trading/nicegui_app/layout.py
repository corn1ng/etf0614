"""Application shell for the NiceGUI workbench."""

from __future__ import annotations

from urllib.parse import quote

from nicegui import ui

from .navigation import NICEGUI_PAGES, NicePageSpec, get_page_by_slug, resolve_section
from .theme import apply_theme
from .view_models import PlatformSnapshot, platform_data_status_summary


def render_shell(page_slug: str | None = None, section: str | None = None) -> None:
    from .state import create_parquet_store, create_store, load_snapshot_cached

    apply_theme()
    page = get_page_by_slug(page_slug)
    active_section = resolve_section(page, section)
    store = create_store()
    parquet_store = create_parquet_store()
    snapshot = load_snapshot_cached(store, parquet_store)

    with ui.row().classes("workbench-shell w-full no-wrap"):
        _render_sidebar(page.slug)
        with ui.column().classes("workbench-main flex-1 no-wrap"):
            _render_topbar(snapshot)
            with ui.column().classes("workbench-page w-full"):
                _render_page_header(page, active_section)
                _render_page(page.slug, active_section, snapshot, store=store, parquet_store=parquet_store)


def _render_sidebar(active_slug: str) -> None:
    with ui.column().classes("workbench-sidebar min-h-screen gap-1 p-2"):
        ui.label("ETF 工作台").classes("workbench-brand")
        for page in NICEGUI_PAGES:
            classes = "workbench-nav-item"
            if page.slug == active_slug:
                classes += " is-active"
            ui.link(page.label, f"/page/{page.slug}").props(
                f'aria-label="{page.label}" title="{page.label}" data-short="{page.label[:1]}"'
            ).classes(classes)


def _render_topbar(snapshot: PlatformSnapshot) -> None:
    status = platform_data_status_summary(snapshot)
    data_health_target = f"/page/maintenance/{quote('数据体检', safe='')}"
    with ui.row().classes("workbench-topbar w-full items-center justify-between px-4"):
        ui.label("本地量化工作台").classes("text-sm font-semibold text-slate-700")
        with ui.row().classes("items-center gap-2"):
            ui.icon("radio_button_checked").classes("text-xs text-emerald-500")
            ui.link(status.etf_label, data_health_target).classes("text-xs text-slate-500")
            ui.link(status.index_label, data_health_target).classes("text-xs text-slate-500")
            if status.latest_trade_date:
                ui.label(f"行情有效至 {status.latest_trade_date}").classes("text-xs text-slate-500")
            ui.label(status.generated_label).classes("text-xs text-slate-500")


def _render_page_header(page: NicePageSpec, active_section: str) -> None:
    with ui.column().classes("workbench-page-header w-full gap-2"):
        with ui.column().classes("gap-0"):
            ui.label(page.label).classes("workbench-page-title")
            ui.label(page.caption).classes("workbench-page-caption")
        with ui.row().classes("workbench-section-tabs w-full justify-start"):
            for item in page.sections:
                classes = "workbench-section-tab"
                if item == active_section:
                    classes += " is-active"
                ui.link(item, f"/page/{page.slug}/{quote(item, safe='')}").classes(classes)


def _render_page(page_slug: str, section: str, snapshot: PlatformSnapshot, *, store, parquet_store) -> None:
    from .pages import action, etf_data, maintenance, market, research

    if page_slug == "action":
        action.render(snapshot, section, store=store, parquet_store=parquet_store)
        return
    if page_slug == "market":
        market.render(snapshot, section, parquet_store=parquet_store)
        return
    if page_slug == "etf-data":
        etf_data.render(snapshot, section, parquet_store=parquet_store, store=store)
        return
    if page_slug == "maintenance":
        maintenance.render(snapshot, section, store=store, parquet_store=parquet_store)
        return
    if page_slug == "research":
        research.render(snapshot, section, store=store, parquet_store=parquet_store)
        return

    action.render(snapshot, "行动摘要")
