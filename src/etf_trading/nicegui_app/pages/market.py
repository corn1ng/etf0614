"""Market map page."""

from __future__ import annotations

import pandas as pd
from nicegui import ui

from etf_trading.data.indexes import IndexDefinition
from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.charts import render_ranged_lightweight_chart
from etf_trading.nicegui_app.components.tables import render_table
from etf_trading.nicegui_app.state import (
    index_chart_payload,
    invalidate_index_health_snapshot_cache,
    load_index_health_snapshot_cached,
)
from etf_trading.nicegui_app.view_models import (
    IndexHealthFilters,
    PlatformSnapshot,
    code_from_option,
    current_ui_audit_findings,
    index_choice_options,
    index_health_detail_options,
    index_health_detail_rows,
    index_health_filter_options,
    index_health_rows,
    index_health_summary,
    index_data_status_notice,
    market_overview,
)


def render(snapshot: PlatformSnapshot, section: str, parquet_store=None) -> None:
    if section == "市场总览":
        _render_overview(snapshot)
    elif section == "指数体检":
        _render_index_health(snapshot, parquet_store)
    elif section == "指数买卖参考":
        _render_index_reference(snapshot)
    else:
        _render_index_chart(snapshot, parquet_store)


def _render_overview(snapshot: PlatformSnapshot) -> None:
    overview = market_overview(snapshot)
    with ui.row().classes("w-full gap-2"):
        _metric("指数总数", overview["total_indexes"], "全市场观察池")
        _metric("核心池", overview["core_indexes"], "可进入策略前置核验")
        _metric("研究池", overview["research_indexes"], "仅供观察研究")
        _metric("历史待补/待核验", overview["incomplete_history_indexes"], "不作为买卖依据")
        _metric("可参与指数", overview["allowed_indexes"], "趋势允许")
        _metric("覆盖分类", len(overview["categories"]), "市场分组")

    rows = overview["categories"]
    if rows:
        render_table(rows, row_key="category", ui_module=ui).classes("workbench-data-table w-full")
    else:
        empty_state("暂无指数状态", "到数据维护补齐指数历史后再查看市场总览。")
    _render_audit("market")


def _render_index_reference(snapshot: PlatformSnapshot) -> None:
    frame = snapshot.index_summary.copy()
    if not frame.empty:
        ui.label(index_data_status_notice(snapshot)).classes("workbench-chart-note")
        ui.label("核心池同时满足历史完整、数据新鲜和趋势条件时，才允许新开仓；研究池只供观察。").classes("workbench-chart-note")

        def render_pool(pool: str) -> None:
            table_area.clear()
            data = frame.copy()
            if "pool" in data:
                data = data[data["pool"].fillna("").astype(str) == pool]
            if pool == "research" and "allows_new_position" in data:
                data["allows_new_position"] = False
            rows = data.fillna("").to_dict("records")
            with table_area:
                if rows:
                    render_table(rows, row_key="index_code", compact=True, ui_module=ui).classes("workbench-data-table workbench-data-table--compact")
                else:
                    empty_state("当前池没有指数", "请先在数据维护页同步目录并完成相应数据任务。")

        if "pool" in frame:
            toggle = ui.toggle({"core": "核心交易池", "research": "研究池"}, value="core").props("dense")
            toggle.on_value_change(lambda event: render_pool(str(event.value)))
        table_area = ui.column().classes("w-full")
        render_pool("core")
    else:
        empty_state("暂无指数买卖参考", "先补齐指数历史。")
    _render_audit("market")


def _render_index_health(snapshot: PlatformSnapshot, parquet_store) -> None:
    if parquet_store is None:
        empty_state("暂无指数体检", "当前页面没有可用历史数据存储。")
        _render_audit("market")
        return

    try:
        definitions, coverage = _index_health_inputs(snapshot)
        cache_result = load_index_health_snapshot_cached(parquet_store, definitions, coverage=coverage)
        holder = {"summary": cache_result.summary, "details": cache_result.details, "result": cache_result}
    except Exception as exc:  # noqa: BLE001 - diagnostics should surface snapshot failures
        empty_state("指数体检快照生成失败", str(exc))
        _render_audit("market")
        return

    ui.label(index_data_status_notice(snapshot)).classes("workbench-chart-note")
    status_area = ui.row().classes("w-full")
    metric_area = ui.row().classes("w-full gap-2")
    table_area = ui.column().classes("w-full")
    detail_area = ui.column().classes("w-full gap-2")
    filter_maps = {
        "categories": index_health_filter_options(holder["summary"], "category", "全部分类"),
        "trend": index_health_filter_options(holder["summary"], "trend_health_status", "全部趋势体检"),
        "valuation": index_health_filter_options(holder["summary"], "valuation_health_status", "全部估值体检"),
    }

    with ui.row().classes("workbench-toolbar w-full"):
        query = ui.input("代码 / 名称 / 分类").props("dense outlined clearable debounce=250").classes("w-72")
        category = ui.select(filter_maps["categories"], value=filter_maps["categories"][0], label="分类").props("dense outlined").classes("w-40")
        trend_status = ui.select(filter_maps["trend"], value=filter_maps["trend"][0], label="趋势体检").props("dense outlined").classes("w-40")
        valuation_status = ui.select(filter_maps["valuation"], value=filter_maps["valuation"][0], label="估值体检").props("dense outlined").classes("w-40")
        detail_select = ui.select([], value=None, label="查看指数").props("dense outlined").classes("w-72")
        ui.button("刷新快照", icon="refresh", on_click=lambda: reload_snapshot()).props("dense outline")

    selected_holder = {"code": ""}

    def render_cache_status() -> None:
        status_area.clear()
        result = holder["result"]
        if result.status == "ready":
            return
        with status_area:
            if result.status == "stale":
                ui.label(f"指数体检快照刷新失败，当前展示上一版缓存：{result.message}").classes("text-xs text-amber-700")
            elif result.status == "building":
                ui.label("指数体检快照正在生成，稍后刷新即可查看。").classes("text-xs text-blue-700")
            elif result.status == "failed":
                ui.label(f"指数体检快照生成失败：{result.message}").classes("text-xs text-red-700")

    def render_metrics() -> None:
        metric_area.clear()
        with metric_area:
            for metric in index_health_summary(holder["summary"]):
                _metric(metric.label, metric.value, metric.detail)

    def current_filters() -> IndexHealthFilters:
        return IndexHealthFilters(
            query=str(query.value or ""),
            category=str(category.value or "全部分类"),
            trend_status=str(trend_status.value or "全部趋势体检"),
            valuation_status=str(valuation_status.value or "全部估值体检"),
        )

    def refresh_filter_options() -> None:
        def sync(select_control, key: str, column: str, all_label: str) -> None:
            options = index_health_filter_options(holder["summary"], column, all_label)
            filter_maps[key] = options
            current = str(select_control.value or all_label)
            select_control.options = options
            select_control.value = current if current in options else options[0]
            select_control.update()

        sync(category, "categories", "category", "全部分类")
        sync(trend_status, "trend", "trend_health_status", "全部趋势体检")
        sync(valuation_status, "valuation", "valuation_health_status", "全部估值体检")

    def select_detail(index_code: str) -> None:
        if not index_code:
            return
        selected_holder["code"] = index_code
        for option in detail_select.options:
            if code_from_option(option) == index_code:
                detail_select.value = option
                detail_select.update()
                break
        render_details()

    def refresh_table() -> None:
        filters = current_filters()
        rows = index_health_rows(holder["summary"], filters)
        options = index_health_detail_options(holder["summary"], filters)
        option_by_code = {code_from_option(option): option for option in options}
        current_code = selected_holder["code"]
        if not current_code or current_code not in option_by_code:
            current_code = code_from_option(options[0]) if options else ""
            selected_holder["code"] = current_code
        detail_select.options = options
        detail_select.value = option_by_code.get(current_code)
        detail_select.update()

        table_area.clear()
        with table_area:
            if rows:
                render_table(rows, row_key="index_code", pagination=15, compact=True, ui_module=ui).classes("workbench-data-table w-full").on(
                    "rowClick",
                    lambda event: select_detail(_event_row_code(event, "index_code")),
                )
            else:
                empty_state("没有匹配指数体检", "换一个筛选条件，或先到数据维护补齐指数历史与估值缓存。")
        render_details()

    def render_details() -> None:
        detail_area.clear()
        index_code = selected_holder["code"]
        with detail_area:
            if not index_code:
                empty_state("暂无指数体检详情", "请选择一个指数查看原子指标。")
                return
            trend_rows = index_health_detail_rows(holder["details"], index_code, "trend")
            valuation_rows = index_health_detail_rows(holder["details"], index_code, "valuation")
            ui.label(f"趋势原子指标：{index_code}").classes("text-sm font-semibold text-slate-700")
            if trend_rows:
                render_table(trend_rows, pagination=12, compact=True, ui_module=ui).classes("workbench-data-table w-full")
            else:
                empty_state("暂无趋势原子指标", "当前快照中没有这个指数的趋势明细。")
            ui.label(f"估值原子指标：{index_code}").classes("text-sm font-semibold text-slate-700")
            if valuation_rows:
                render_table(valuation_rows, pagination=12, compact=True, ui_module=ui).classes("workbench-data-table w-full")
            else:
                empty_state("暂无估值原子指标", "当前快照中没有这个指数的估值明细。")

    def reload_snapshot() -> None:
        try:
            should_force_refresh = holder["result"].status == "ready"
            if should_force_refresh:
                invalidate_index_health_snapshot_cache(parquet_store)
            cache_result = load_index_health_snapshot_cached(
                parquet_store,
                definitions,
                coverage=coverage,
                force_refresh=should_force_refresh,
            )
            holder["summary"] = cache_result.summary
            holder["details"] = cache_result.details
            holder["result"] = cache_result
        except Exception as exc:  # noqa: BLE001 - keep current page usable after refresh failures
            ui.notify(f"刷新指数体检失败：{exc}", type="negative")
            return
        refresh_filter_options()
        render_cache_status()
        render_metrics()
        refresh_table()
        if cache_result.status == "failed":
            ui.notify("指数体检快照生成失败，请查看页面提示", type="negative")
        elif cache_result.status == "stale":
            ui.notify("指数体检快照刷新失败，已保留上一版缓存", type="warning")
        else:
            ui.notify("指数体检快照已刷新", type="positive")

    query.on_value_change(lambda event: refresh_table())
    category.on_value_change(lambda event: refresh_table())
    trend_status.on_value_change(lambda event: refresh_table())
    valuation_status.on_value_change(lambda event: refresh_table())
    detail_select.on_value_change(lambda event: select_detail(code_from_option(str(detail_select.value or ""))))
    render_cache_status()
    render_metrics()
    refresh_table()
    _render_audit("market")


def _index_health_inputs(snapshot: PlatformSnapshot) -> tuple[tuple[IndexDefinition, ...], pd.DataFrame]:
    summary = snapshot.index_summary.copy()
    if summary.empty or "index_code" not in summary:
        return (), pd.DataFrame()
    definitions: list[IndexDefinition] = []
    for row in summary.fillna("").to_dict("records"):
        code = str(row.get("index_code") or "").strip()
        if not code:
            continue
        base_date = pd.to_datetime(row.get("index_base_date"), errors="coerce")
        definitions.append(
            IndexDefinition(
                code,
                str(row.get("index_name") or code),
                str(row.get("market") or ""),
                str(row.get("category") or ""),
                code,
                pool=str(row.get("pool") or "core"),
                index_base_date=None if pd.isna(base_date) else pd.Timestamp(base_date).date(),
            )
        )
    coverage_columns = [
        column
        for column in (
            "index_code",
            "index_base_date",
            "history_completeness_status",
            "history_completeness_message",
        )
        if column in summary
    ]
    coverage = summary[coverage_columns].rename(
        columns={
            "history_completeness_status": "completeness_status",
            "history_completeness_message": "completeness_message",
        }
    )
    return tuple(definitions), coverage


def _render_index_chart(snapshot: PlatformSnapshot, parquet_store) -> None:
    options = index_choice_options(snapshot.index_summary)
    if not options or parquet_store is None:
        empty_state("暂无指数K线", "先补齐指数历史。")
        _render_audit("market")
        return

    def draw_chart(option: str | None) -> None:
        selected = code_from_option(option)
        chart_area.clear()
        with chart_area:
            if not selected:
                empty_state("暂无指数K线", "请选择一个指数。")
                return

            payload = index_chart_payload(parquet_store, selected)
            if not payload[0]["series"]:
                empty_state("暂无指数K线", "先补齐该指数历史。")
                return

            render_ranged_lightweight_chart(payload, element_id=f"index-chart-{selected}", title=f"指数：{selected}")

    with ui.row().classes("workbench-chart-selector w-full"):
        ui.select(
            options,
            value=options[0],
            label="选择指数",
            on_change=lambda event: draw_chart(event.value),
        ).props("dense outlined").classes("w-96")
        ui.label("指数只做市场状态判断，ETF 交易载体在 ETF 数据页处理。").classes("workbench-chart-note")
    chart_area = ui.column().classes("w-full gap-2")
    draw_chart(options[0])
    _render_audit("market")


def _metric(label: str, value: object, detail: str) -> None:
    with ui.column().classes("workbench-metric"):
        ui.label(label).classes("workbench-metric-label")
        ui.label(str(value)).classes("workbench-metric-value")
        ui.label(detail).classes("text-xs text-slate-400")


def _event_row_code(event, key: str) -> str:
    args = getattr(event, "args", None)
    if isinstance(args, dict):
        row = args.get("row", args)
    elif isinstance(args, list) and len(args) >= 2 and isinstance(args[1], dict):
        row = args[1]
    else:
        row = {}
    value = row.get(key, "") if isinstance(row, dict) else ""
    return str(value).strip()


def _render_audit(page_slug: str) -> None:
    findings = [item for item in current_ui_audit_findings() if item.page_slug == page_slug]
    expansion = getattr(ui, "expansion", None)
    if not callable(expansion):
        return
    with expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in findings:
            ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
