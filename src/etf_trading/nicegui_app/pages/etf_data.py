"""ETF data page."""

from __future__ import annotations

from urllib.parse import quote

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.charts import render_ranged_lightweight_chart
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.state import etf_chart_payload, invalidate_snapshot_cache
from etf_trading.nicegui_app.view_models import (
    AtomicIndicatorFilters,
    PlatformSnapshot,
    atomic_indicator_rows,
    atomic_indicator_summary,
    build_atomic_indicator_snapshot,
    category_options,
    code_from_option,
    current_ui_audit_findings,
    etf_category_for_code,
    etf_choice_options,
    etf_overview_rows,
    filter_etf_rows,
)
from etf_trading.universe.classification import CATEGORIES


def render(snapshot: PlatformSnapshot, section: str, parquet_store=None, store=None) -> None:
    if section == "ETF总览":
        _render_rows(etf_overview_rows(snapshot), empty_title="暂无ETF数据")
    elif section == "原子指标":
        _render_atomic_indicators(snapshot, parquet_store)
    elif section == "每日计算池":
        rows = snapshot.watchlist.fillna("").to_dict("records") if not snapshot.watchlist.empty else []
        _render_rows(rows, empty_title="每日计算池为空")
    elif section == "指数样本池":
        rows = snapshot.universe.fillna("").to_dict("records") if not snapshot.universe.empty else []
        _render_rows(rows, empty_title="暂无指数样本池")
    elif section == "搜索加入":
        _render_search(snapshot, store)
    else:
        _render_etf_chart(snapshot, parquet_store)
    _render_audit("etf-data")


def _render_rows(rows: list[dict[str, object]], empty_title: str) -> None:
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, pagination=12).classes("workbench-data-table w-full")
    else:
        empty_state(empty_title, "先到数据维护初始化主列表或补齐历史。")


def _render_atomic_indicators(snapshot: PlatformSnapshot, parquet_store) -> None:
    if parquet_store is None:
        empty_state("暂无原子指标", "当前页面没有可用历史数据存储。")
        return

    try:
        frame_holder = {"frame": build_atomic_indicator_snapshot(snapshot, parquet_store)}
    except Exception as exc:  # noqa: BLE001 - diagnostics should surface snapshot failures
        empty_state("原子指标生成失败", str(exc))
        return

    metric_area = ui.row().classes("w-full gap-2")
    categories = _atomic_filter_options(frame_holder["frame"], "category", "全部分类")
    history_statuses = _atomic_filter_options(frame_holder["frame"], "history_status", "全部历史状态")
    feature_statuses = _atomic_filter_options(frame_holder["frame"], "feature_status", "全部特征状态")

    with ui.row().classes("workbench-toolbar w-full"):
        query = ui.input("代码 / 名称 / 分类").props("dense outlined clearable debounce=250").classes("w-72")
        category = ui.select(categories, value=categories[0], label="分类").props("dense outlined").classes("w-40")
        history_status = ui.select(history_statuses, value=history_statuses[0], label="历史状态").props("dense outlined").classes("w-40")
        feature_status = ui.select(feature_statuses, value=feature_statuses[0], label="特征状态").props("dense outlined").classes("w-40")
        min_amount = ui.number("最低20日成交额", value=None, format="%.0f").props("dense outlined clearable").classes("w-40")
        breakout = ui.checkbox("60日突破", value=False)
        weekly_ma10 = ui.checkbox("周线>10周", value=False)
        ui.button("刷新快照", icon="refresh", on_click=lambda: reload_snapshot()).props("dense outline")
        ui.link("去补齐任务", f"/page/maintenance/{quote('补齐任务', safe='')}").classes("workbench-section-tab")

    result_area = ui.column().classes("w-full gap-2")

    def render_metrics() -> None:
        metric_area.clear()
        with metric_area:
            for metric in atomic_indicator_summary(frame_holder["frame"]):
                _metric_tile(metric.label, metric.value, metric.detail, metric.tone)

    def current_filters() -> AtomicIndicatorFilters:
        amount_value = None if min_amount.value in {None, ""} else float(min_amount.value)
        return AtomicIndicatorFilters(
            query=str(query.value or ""),
            category=str(category.value or "全部分类"),
            history_status=str(history_status.value or "全部历史状态"),
            feature_status=str(feature_status.value or "全部特征状态"),
            min_avg_amount_20=amount_value,
            only_breakout=bool(breakout.value),
            only_weekly_ma10=bool(weekly_ma10.value),
        )

    def refresh_table() -> None:
        rows = atomic_indicator_rows(frame_holder["frame"], current_filters())
        result_area.clear()
        with result_area:
            if rows:
                ui.table(columns=table_columns(rows), rows=rows, pagination=15).classes("workbench-data-table w-full")
            else:
                empty_state("没有匹配原子指标", "换一个筛选条件，或到数据维护补齐历史。")

    def reload_snapshot() -> None:
        try:
            frame_holder["frame"] = build_atomic_indicator_snapshot(snapshot, parquet_store)
        except Exception as exc:  # noqa: BLE001 - keep the page usable after a failed refresh
            ui.notify(f"刷新原子指标失败：{exc}", type="negative")
            return
        render_metrics()
        refresh_table()
        ui.notify("原子指标快照已刷新", type="positive")

    query.on_value_change(lambda event: refresh_table())
    category.on_value_change(lambda event: refresh_table())
    history_status.on_value_change(lambda event: refresh_table())
    feature_status.on_value_change(lambda event: refresh_table())
    min_amount.on_value_change(lambda event: refresh_table())
    breakout.on_value_change(lambda event: refresh_table())
    weekly_ma10.on_value_change(lambda event: refresh_table())
    render_metrics()
    refresh_table()


def _render_search(snapshot: PlatformSnapshot, store) -> None:
    rows = etf_overview_rows(snapshot)
    if not rows:
        empty_state("暂无ETF主列表", "请先到数据维护初始化 ETF 主列表。")
        return

    categories = category_options(rows)
    correction_categories = list(CATEGORIES)
    for item in categories[1:]:
        if item not in correction_categories:
            correction_categories.append(item)

    with ui.row().classes("workbench-toolbar w-full"):
        query = ui.input("代码 / 名称 / 分类").props("dense outlined clearable debounce=250").classes("w-80")
        category = ui.select(categories, value=categories[0], label="分类").props("dense outlined").classes("w-44")

    with ui.row().classes("w-full gap-3 items-start"):
        result_area = ui.column().classes("flex-1 min-w-0 gap-2")
        with ui.column().classes("workbench-action-panel gap-2"):
            ui.label("加入每日计算池").classes("text-sm font-semibold text-slate-700")
            selected = ui.select([], label="ETF").props("dense outlined").classes("w-80")
            selected_category = ui.select(correction_categories, value=correction_categories[0], label="分类修正").props("dense outlined").classes("w-80")
            with ui.row().classes("gap-3"):
                allow_buy = ui.checkbox("允许买入", value=True)
                enabled = ui.checkbox("纳入每日计算", value=True)
            ui.button(
                "保存到计算池",
                icon="save",
                on_click=lambda: _save_watchlist(
                    store,
                    code_from_option(selected.value),
                    bool(enabled.value),
                    bool(allow_buy.value),
                    str(selected_category.value or ""),
                ),
            ).props("dense unelevated color=primary").classes("w-full")

    def sync_selected_category() -> None:
        etf_code = code_from_option(selected.value)
        row_category = etf_category_for_code(rows, etf_code, default=correction_categories[0])
        if row_category not in correction_categories:
            selected_category.options = [*correction_categories, row_category]
        selected_category.value = row_category
        selected_category.update()

    def refresh_results() -> None:
        filtered = filter_etf_rows(rows, query=str(query.value or ""), category=str(category.value or "全部分类"), limit=80)
        options = etf_choice_options(filtered)
        selected.options = options
        selected.value = options[0] if options else None
        selected.update()
        sync_selected_category()

        result_area.clear()
        with result_area:
            if filtered:
                ui.table(columns=table_columns(filtered), rows=filtered, pagination=10).classes("workbench-data-table w-full")
            else:
                empty_state("没有匹配 ETF", "换一个代码、名称或分类再试。")

    query.on_value_change(lambda event: refresh_results())
    category.on_value_change(lambda event: refresh_results())
    selected.on_value_change(lambda event: sync_selected_category())
    refresh_results()


def _render_etf_chart(snapshot: PlatformSnapshot, parquet_store) -> None:
    rows = etf_overview_rows(snapshot)
    options = etf_choice_options(rows)
    if not options or parquet_store is None:
        empty_state("暂无ETF K线", "先初始化ETF主列表并补齐历史。")
        return

    def draw_chart(option: str | None) -> None:
        selected = code_from_option(option)
        chart_area.clear()
        with chart_area:
            if not selected:
                empty_state("暂无ETF K线", "请选择一个 ETF。")
                return

            payload = etf_chart_payload(parquet_store, selected)
            if not payload[0]["series"]:
                empty_state("暂无ETF K线", "先到数据维护补齐该ETF历史。")
                return

            render_ranged_lightweight_chart(payload, element_id=f"etf-chart-{selected}", title=f"ETF：{selected}")

    with ui.row().classes("workbench-toolbar w-full justify-between"):
        ui.select(
            options,
            value=options[0],
            label="选择ETF",
            on_change=lambda event: draw_chart(event.value),
        ).props("dense outlined").classes("w-96")
        ui.label("这里只看 ETF 交易载体行情，指数状态在市场地图查看。").classes("text-xs text-slate-500")
    chart_area = ui.column().classes("w-full gap-2")
    draw_chart(options[0])


def _save_watchlist(store, etf_code: str, enabled: bool, allow_buy: bool, category: str) -> None:
    if store is None:
        ui.notify("当前页面没有可用数据库连接", type="negative")
        return
    if not etf_code:
        ui.notify("请先选择 ETF", type="warning")
        return
    store.set_watchlist(etf_code, enabled=enabled, allow_buy=allow_buy, category=category)
    invalidate_snapshot_cache()
    ui.notify(f"{etf_code} 已保存到每日计算池", type="positive")


def _atomic_filter_options(frame, column: str, all_label: str) -> list[str]:
    if frame.empty or column not in frame:
        return [all_label]
    values = sorted({str(value) for value in frame[column].dropna().tolist() if str(value).strip()})
    return [all_label, *values]


def _metric_tile(label: str, value: object, detail: str, tone: str) -> None:
    with ui.column().classes("workbench-metric"):
        ui.label(label).classes("workbench-metric-label")
        ui.label(str(value)).classes(f"workbench-metric-value tone-{tone}")
        ui.label(detail).classes("text-xs text-slate-400")


def _render_audit(page_slug: str) -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == page_slug:
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
