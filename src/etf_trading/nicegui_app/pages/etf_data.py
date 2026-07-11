"""ETF data page."""

from __future__ import annotations

from urllib.parse import quote

import pandas as pd
from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.charts import render_ranged_lightweight_chart
from etf_trading.nicegui_app.components.tables import VALUE_LABELS, render_table
from etf_trading.nicegui_app.state import etf_chart_payload, invalidate_snapshot_cache, load_atomic_snapshot_cached
from etf_trading.nicegui_app.view_models import (
    ATOMIC_VIEW_MODES,
    AtomicIndicatorFilters,
    AtomicDataHealthItem,
    PlatformSnapshot,
    atomic_indicator_detail_groups,
    atomic_indicator_detail_options,
    atomic_indicator_rows,
    atomic_indicator_summary,
    atomic_data_health_summary,
    category_options,
    code_from_option,
    ATOMIC_FEATURE_STATUS_LABELS,
    ATOMIC_HISTORY_STATUS_LABELS,
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
        render_table(rows, pagination=12, ui_module=ui).classes("workbench-data-table w-full")
    else:
        empty_state(empty_title, "先到数据维护初始化主列表或补齐历史。")


def _render_atomic_indicators(snapshot: PlatformSnapshot, parquet_store) -> None:
    if parquet_store is None:
        empty_state("暂无原子指标", "当前页面没有可用历史数据存储。")
        return

    try:
        cache_result = load_atomic_snapshot_cached(snapshot.master, parquet_store)
        frame_holder = {"frame": cache_result.frame, "result": cache_result}
    except Exception as exc:  # noqa: BLE001 - diagnostics should surface snapshot failures
        empty_state("原子指标生成失败", str(exc))
        return

    status_area = ui.row().classes("w-full")
    metric_area = ui.row().classes("atomic-metric-strip w-full")
    health_area = ui.column().classes("w-full")
    categories = _atomic_filter_options(frame_holder["frame"], "category", "全部分类")
    history_statuses = _atomic_filter_options(frame_holder["frame"], "history_status", "全部历史状态")
    feature_statuses = _atomic_filter_options(frame_holder["frame"], "feature_status", "全部特征状态")
    selected_holder = {"code": ""}

    with ui.column().classes("atomic-workbench w-full gap-2"):
        with ui.row().classes("atomic-workbench-head w-full"):
            with ui.column().classes("atomic-mode-block gap-1"):
                ui.label("列表视图").classes("atomic-control-label")
                view_mode = (
                    ui.toggle(list(ATOMIC_VIEW_MODES), value=ATOMIC_VIEW_MODES[0])
                    .props("dense unelevated toggle-color=primary")
                    .classes("workbench-range-toggle")
                )
            with ui.row().classes("atomic-actions"):
                detail_select = ui.select([], value=None, label="查看详情").props("dense outlined").classes("atomic-detail-select")
                ui.button("刷新快照", icon="refresh", on_click=lambda: reload_snapshot()).props("dense outline")
                ui.link("去补齐任务", f"/page/maintenance/{quote(chr(34917) + chr(40784) + chr(20219) + chr(21153), safe='')}").classes("workbench-section-tab")

        with ui.row().classes("atomic-filter-bar w-full"):
            query = ui.input("代码 / 名称 / 分类").props("dense outlined clearable debounce=250").classes("atomic-query-input")
            category = ui.select(list(categories), value=next(iter(categories)), label="分类").props("dense outlined").classes("atomic-filter-select")
            history_status = ui.select(list(history_statuses), value=next(iter(history_statuses)), label="历史状态").props("dense outlined").classes("atomic-filter-select")
            feature_status = ui.select(list(feature_statuses), value=next(iter(feature_statuses)), label="特征状态").props("dense outlined").classes("atomic-filter-select")
            min_amount = ui.number("最低20日成交额", value=None, format="%.0f").props("dense outlined clearable").classes("atomic-filter-number")
            breakout = ui.checkbox("60日突破", value=False).classes("atomic-filter-check")
            weekly_ma10 = ui.checkbox("周线>10周", value=False).classes("atomic-filter-check")

        grid_factory = getattr(ui, "element", None)
        workbench_grid = grid_factory("div") if callable(grid_factory) else ui.row()
        with workbench_grid.classes("atomic-workbench-grid w-full"):
            result_area = ui.column().classes("atomic-table-pane gap-2")
            detail_area = ui.column().classes("atomic-inspector gap-2")

    def render_metrics() -> None:
        metric_area.clear()
        with metric_area:
            for metric in atomic_indicator_summary(frame_holder["frame"]):
                _metric_tile(metric.label, metric.value, metric.detail, metric.tone)

    def render_cache_status() -> None:
        status_area.clear()
        result = frame_holder["result"]
        if result.status == "ready":
            return
        with status_area:
            if result.status == "stale":
                ui.label("原子指标快照正在后台刷新，当前先展示上一次缓存。").classes("text-xs text-amber-700")
            elif result.status == "building":
                ui.label("原子指标快照正在后台生成，稍后点刷新快照即可查看。").classes("text-xs text-blue-700")
            elif result.status == "failed":
                ui.label(f"原子指标后台生成失败：{result.message}").classes("text-xs text-red-700")

    def current_filters() -> AtomicIndicatorFilters:
        amount_value = None if min_amount.value in {None, ""} else float(min_amount.value)
        return AtomicIndicatorFilters(
            query=str(query.value or ""),
            category=_atomic_filter_value(categories, str(category.value or "全部分类")),
            history_status=_atomic_filter_value(history_statuses, str(history_status.value or "全部历史状态")),
            feature_status=_atomic_filter_value(feature_statuses, str(feature_status.value or "全部特征状态")),
            min_avg_amount_20=amount_value,
            only_breakout=bool(breakout.value),
            only_weekly_ma10=bool(weekly_ma10.value),
        )

    def refresh_filter_options() -> None:
        def sync_filter(select_control, option_map: dict[str, str], column: str, all_label: str) -> None:
            updated_options = _atomic_filter_options(frame_holder["frame"], column, all_label)
            current_label = str(select_control.value or all_label)
            option_map.clear()
            option_map.update(updated_options)
            select_control.options = list(updated_options)
            select_control.value = current_label if current_label in updated_options else next(iter(updated_options))
            select_control.update()

        sync_filter(category, categories, "category", "全部分类")
        sync_filter(history_status, history_statuses, "history_status", "全部历史状态")
        sync_filter(feature_status, feature_statuses, "feature_status", "全部特征状态")

    def apply_health_filter(item: AtomicDataHealthItem) -> None:
        if item.count <= 0:
            return
        if view_mode.value != "体检特征":
            view_mode.value = "体检特征"
            view_mode.update()
        if item.filter_type == "history_status":
            label = _atomic_filter_label(history_statuses, item.filter_value)
            if label:
                history_status.value = label
                history_status.update()
                feature_status.value = "全部特征状态"
                feature_status.update()
        elif item.filter_type == "feature_status":
            label = _atomic_filter_label(feature_statuses, item.filter_value)
            if label:
                feature_status.value = label
                feature_status.update()
                history_status.value = "全部历史状态"
                history_status.update()
        refresh_table()

    def render_data_health() -> None:
        health_area.clear()
        health_summary = atomic_data_health_summary(frame_holder["frame"])
        items = health_summary.items
        issue_total = health_summary.issue_count
        with health_area:
            with ui.column().classes("atomic-data-health w-full"):
                with ui.row().classes("atomic-data-health-header w-full"):
                    ui.icon("monitoring").classes("tone-info")
                    ui.label("数据更新体检").classes("text-sm font-semibold text-slate-700")
                    ui.badge("数据就绪" if issue_total == 0 else f"{issue_total} 只ETF需关注").classes(
                        "atomic-data-health-status is-ready" if issue_total == 0 else "atomic-data-health-status is-warning"
                    )
                    if issue_total:
                        ui.link(
                            "前往数据体检",
                            f"/page/maintenance/{quote('数据体检', safe='')}",
                        ).classes("workbench-section-tab")
                ui.label("主状态互斥统计每只 ETF 一次；特征缺失是附加诊断。行情滞后或历史不足的数据不会进入机会排名。").classes("atomic-data-health-note")
                with ui.row().classes("atomic-data-health-items"):
                    for item in items:
                        if item.count > 0:
                            ui.button(
                                f"{item.label} {item.count}",
                                icon=_atomic_health_icon(item),
                                on_click=lambda item=item: apply_health_filter(item),
                            ).props("dense flat").classes(f"atomic-data-health-item tone-{item.tone}")
                        else:
                            with ui.row().classes("atomic-data-health-item is-empty"):
                                ui.icon(_atomic_health_icon(item))
                                ui.label(f"{item.label} 0")
                        ui.label(item.detail).classes("atomic-data-health-detail")

    def select_detail(etf_code: str) -> None:
        if not etf_code:
            return
        selected_holder["code"] = etf_code
        for option in detail_select.options:
            if code_from_option(option) == etf_code:
                detail_select.value = option
                detail_select.update()
                break
        render_details()

    def render_details() -> None:
        detail_area.clear()
        etf_code = selected_holder["code"]
        with detail_area:
            if not etf_code:
                empty_state("暂无原子指标详情", "请选择一只 ETF 查看完整原子指标。")
                return
            groups = atomic_indicator_detail_groups(frame_holder["frame"], etf_code)
            if not groups:
                empty_state("暂无原子指标详情", "当前快照中没有这只 ETF。")
                return
            ui.label("ETF检查器").classes("atomic-inspector-kicker")
            ui.label(f"原子指标详情：{etf_code}").classes("atomic-inspector-title")
            detail_grid_factory = getattr(ui, "element", None)
            detail_grid = detail_grid_factory("div") if callable(detail_grid_factory) else ui.column()
            with detail_grid.classes("atomic-detail-grid"):
                for group in groups:
                    with ui.column().classes("atomic-detail-group gap-1"):
                        ui.label(group.title).classes("atomic-detail-group-title")
                        for row in group.rows:
                            metric = str(row.get("指标", ""))
                            value = str(row.get("数值", ""))
                            with ui.row().classes("atomic-detail-row"):
                                ui.label(metric).classes("atomic-detail-label")
                                ui.label(value).classes(f"atomic-detail-value {_atomic_detail_value_tone(metric, value)}")

    def refresh_table() -> None:
        filters = current_filters()
        rows = atomic_indicator_rows(
            frame_holder["frame"],
            filters,
            view_mode=str(view_mode.value or ATOMIC_VIEW_MODES[0]),
        )
        options = atomic_indicator_detail_options(
            frame_holder["frame"],
            filters,
            opportunity_only=str(view_mode.value or ATOMIC_VIEW_MODES[0]) == "机会特征",
        )
        current_code = selected_holder["code"]
        option_by_code = {code_from_option(option): option for option in options}
        if not current_code or current_code not in option_by_code:
            current_code = code_from_option(options[0]) if options else current_code
            selected_holder["code"] = current_code
        detail_select.options = options
        detail_select.value = option_by_code.get(current_code)
        detail_select.update()

        result_area.clear()
        with result_area:
            if rows:
                render_table(
                    rows,
                    row_key="ETF代码",
                    pagination=15,
                    compact=True,
                    ui_module=ui,
                ).classes("workbench-data-table w-full").on("rowClick", lambda event: select_detail(_event_row_code(event)))
            else:
                empty_state("没有匹配原子指标", "换一个筛选条件，或到数据维护补齐历史。")
        render_details()

    def reload_snapshot() -> None:
        try:
            should_force_refresh = frame_holder["result"].status == "ready"
            cache_result = load_atomic_snapshot_cached(snapshot.master, parquet_store, force_refresh=should_force_refresh)
            frame_holder["frame"] = cache_result.frame
            frame_holder["result"] = cache_result
        except Exception as exc:  # noqa: BLE001 - keep the page usable after a failed refresh
            ui.notify(f"刷新原子指标失败：{exc}", type="negative")
            return
        refresh_filter_options()
        render_cache_status()
        render_metrics()
        render_data_health()
        refresh_table()
        if cache_result.status in {"building", "stale"}:
            ui.notify("原子指标快照已转入后台刷新，页面会继续保持可用", type="info")
        elif cache_result.status == "failed":
            ui.notify("原子指标快照生成失败，请查看页面提示", type="negative")
        else:
            ui.notify("原子指标快照已刷新", type="positive")

    query.on_value_change(lambda event: refresh_table())
    category.on_value_change(lambda event: refresh_table())
    history_status.on_value_change(lambda event: refresh_table())
    feature_status.on_value_change(lambda event: refresh_table())
    min_amount.on_value_change(lambda event: refresh_table())
    breakout.on_value_change(lambda event: refresh_table())
    weekly_ma10.on_value_change(lambda event: refresh_table())
    view_mode.on_value_change(lambda event: refresh_table())
    detail_select.on_value_change(lambda event: select_detail(code_from_option(str(detail_select.value or ""))))
    render_cache_status()
    render_metrics()
    render_data_health()
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
                render_table(filtered, pagination=10, ui_module=ui).classes("workbench-data-table w-full")
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

    with ui.row().classes("workbench-chart-selector w-full"):
        ui.select(
            options,
            value=options[0],
            label="选择ETF",
            on_change=lambda event: draw_chart(event.value),
        ).props("dense outlined").classes("w-96")
        ui.label("这里只看 ETF 交易载体行情，指数状态在市场地图查看。").classes("workbench-chart-note")
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


def _atomic_filter_options(frame, column: str, all_label: str) -> dict[str, str]:
    if getattr(frame, "empty", False) or column not in frame:
        return {all_label: all_label}

    series = frame[column] if hasattr(frame, "__getitem__") else []
    values = sorted({str(value) for value in pd.Series(series).dropna().tolist() if str(value).strip()})
    options = {all_label: all_label}
    for value in values:
        label = _atomic_filter_label_for(column, value)
        options[label] = value
    return options


def _atomic_filter_label_for(column: str, value: str) -> str:
    if column == "history_status":
        return ATOMIC_HISTORY_STATUS_LABELS.get(value, VALUE_LABELS.get(value, value))
    if column == "feature_status":
        return ATOMIC_FEATURE_STATUS_LABELS.get(value, VALUE_LABELS.get(value, value))
    return VALUE_LABELS.get(value, value)


def _atomic_filter_value(options: dict[str, str], label: str) -> str:
    return options.get(label, label)


def _atomic_filter_label(options: dict[str, str], value: str) -> str:
    for label, option_value in options.items():
        if option_value == value:
            return label
    return ""


def _atomic_health_icon(item: AtomicDataHealthItem) -> str:
    return {
        "stale": "update",
        "short_history": "hourglass_empty",
        "missing_history": "folder_off",
        "read_failed": "error_outline",
        "missing_features": "analytics",
    }.get(item.key, "info")


def _event_row_code(event) -> str:
    args = getattr(event, "args", None)
    row = None
    if isinstance(args, dict):
        row = args.get("row") if isinstance(args.get("row"), dict) else args
    elif isinstance(args, (list, tuple)) and len(args) >= 2 and isinstance(args[1], dict):
        row = args[1]
    if not isinstance(row, dict):
        return ""
    return str(row.get("ETF代码") or row.get("etf_code") or "").strip()


def _atomic_detail_value_tone(metric: str, value: str) -> str:
    if value in {"完整", "数据可用", "是"}:
        return "tone-success"
    if value == "否":
        return "tone-neutral"
    if "缺失" in value or value in {"历史不足", "特征计算失败"}:
        return "tone-warning"
    if metric in {"20日收益", "60日收益", "距20日线"} and value.startswith("-"):
        return "tone-danger"
    if metric in {"20日收益", "60日收益", "60日突破", "周线>10周", "周线>30周"}:
        return "tone-info"
    return "tone-neutral"


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
