"""Application shell for the NiceGUI workbench."""

from __future__ import annotations

from urllib.parse import quote

from nicegui import ui

from .navigation import NICEGUI_PAGES, NicePageSpec, get_page_by_slug, resolve_section
from .theme import apply_theme
from .view_models import PlatformSnapshot, platform_data_status_summary

FULL_SNAPSHOT_MODE = "full"
MAINTENANCE_TASK_SNAPSHOT_MODE = "maintenance_tasks"
ATOMIC_INDEX_SNAPSHOT_MODE = "atomic_index"
SNAPSHOT_MODES = {FULL_SNAPSHOT_MODE, MAINTENANCE_TASK_SNAPSHOT_MODE, ATOMIC_INDEX_SNAPSHOT_MODE}
MAINTENANCE_TASK_SECTIONS = {"补齐任务", "日志与设置"}
LIGHTWEIGHT_ETF_SECTIONS = {"原子指标", "ETF行情", "搜索加入", "每日计算池"}


def render_shell(page_slug: str | None = None, section: str | None = None) -> None:
    from . import state

    apply_theme()
    page = get_page_by_slug(page_slug)
    active_section = active_section_for_route(page, section)
    store = state.create_store()
    parquet_store = state.create_parquet_store()
    snapshot = _load_snapshot_for_route(snapshot_mode_for_route(page.slug, active_section), store, parquet_store)

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
            ui.link(page.label, _page_link_target(page)).props(
                f'aria-label="{page.label}" title="{page.label}" data-short="{page.label[:1]}"'
            ).classes(classes)


def _page_link_target(page: NicePageSpec) -> str:
    if page.slug == "maintenance":
        return f"/page/{page.slug}/{quote('补齐任务', safe='')}"
    return f"/page/{page.slug}"


def active_section_for_route(page: NicePageSpec, section: str | None) -> str:
    if page.slug == "maintenance" and section is None:
        return "补齐任务"
    return resolve_section(page, section)


def snapshot_mode_for_route(page_slug: str | None, section: str | None) -> str:
    page = get_page_by_slug(page_slug)
    active_section = active_section_for_route(page, section)
    if page.slug == "maintenance" and active_section in MAINTENANCE_TASK_SECTIONS:
        return MAINTENANCE_TASK_SNAPSHOT_MODE
    if page.slug == "market" and active_section in {"指数体检", "指数估值"}:
        return ATOMIC_INDEX_SNAPSHOT_MODE
    if page.slug == "etf-data" and active_section in LIGHTWEIGHT_ETF_SECTIONS:
        return MAINTENANCE_TASK_SNAPSHOT_MODE
    return FULL_SNAPSHOT_MODE


def _load_snapshot_for_route(mode: str, store, parquet_store) -> PlatformSnapshot:
    from . import state

    if mode == FULL_SNAPSHOT_MODE:
        return state.load_snapshot_cached(store, parquet_store)
    if mode in {MAINTENANCE_TASK_SNAPSHOT_MODE, ATOMIC_INDEX_SNAPSHOT_MODE}:
        return state.load_maintenance_task_snapshot(store)
    raise ValueError(f"unknown snapshot mode: {mode}")


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
