"""Market map page."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

import pandas as pd
from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.charts import render_ranged_lightweight_chart
from etf_trading.nicegui_app.components.tables import render_table
from etf_trading.nicegui_app.state import (
    create_store,
    index_atomic_snapshot_inputs,
    index_chart_payload,
    load_index_atomic_snapshot_readonly,
)
from etf_trading.nicegui_app.view_models import (
    IndexAtomicFilters,
    INDEX_ATOMIC_DATA_SOURCE_LABELS,
    PlatformSnapshot,
    build_index_atomic_rows,
    code_from_option,
    current_ui_audit_findings,
    index_atomic_detail_groups,
    index_choice_options,
    index_data_status_notice,
    market_overview,
)


_SNAPSHOT_STATUS_LABELS = {
    "ready": "已验证",
    "stale": "待重建",
    "missing": "不存在",
    "failed": "生成失败",
    "building": "生成中",
    "computed": "已计算",
    "insufficient_history": "历史不足",
    "missing_input": "缺少输入字段",
    "read_failed": "读取失败",
    "calculation_failed": "计算失败",
    "COMPLETE": "历史完整",
    "INCOMPLETE": "历史不完整",
    "BASELINE_UNVERIFIED": "基日待核验",
    "SOURCE_LIMITED": "数据源历史不完整",
    "MISSING_HISTORY": "历史缺失",
    "NOT_VALIDATED": "待校验",
}
_KEY_METRICS = (
    ("close", "最新收盘"),
    ("ma_20", "MA20"),
    ("ma_60", "MA60"),
    ("close_vs_ma_20", "相对MA20"),
    ("close_vs_ma_60", "相对MA60"),
    ("range_20", "20日区间"),
    ("return_20", "20日收益"),
    ("data_status", "数据状态"),
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
                    render_table(rows, row_key="index_code", compact=True, ui_module=ui).classes(
                        "workbench-data-table workbench-data-table--compact"
                    )
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
    """Render stored index atoms only; maintenance owns every rebuild."""

    if parquet_store is None:
        empty_state("暂无指数体检", "当前页面没有可用历史数据存储。")
        _render_audit("market")
        return

    definitions, coverage = index_atomic_snapshot_inputs(create_store())
    holder = {"result": load_index_atomic_snapshot_readonly(parquet_store, definitions, coverage=coverage)}

    with ui.column().classes("index-atomic-workbench w-full gap-3"):
        with ui.column().classes("index-atomic-toolbar w-full gap-2"):
            status_area = ui.row().classes("index-atomic-status-bar w-full")
            with ui.row().classes("index-atomic-controls w-full items-center gap-2"):
                pool = ui.toggle({"core": "核心池", "research": "研究池"}, value="core").props("dense")
                query = ui.input("搜索指数").props("dense outlined clearable debounce=250").classes("index-atomic-search")
                ui.button("重新读取快照", icon="refresh", on_click=lambda: reload_snapshot()).props("dense outline")
                ui.link("前往数据维护", f"/page/maintenance/{quote('数据体检', safe='')}").classes("text-sm font-semibold")
        alert_area = ui.column().classes("w-full")
        table_area = ui.column().classes("index-atomic-table w-full")

    def render_status_bar() -> None:
        result = holder["result"]
        status_area.clear()
        generated_at = _datetime_text(result.generated_at)
        current_date = result.current_latest_date or "暂无"
        counts = _snapshot_status_counts(result.summary)
        with status_area:
            with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                ui.label(f"快照状态：{_SNAPSHOT_STATUS_LABELS.get(result.status, result.status)}").classes("index-atomic-status")
                ui.label(f"生成时间：{generated_at}").classes("index-atomic-status")
                ui.label(f"当前输入最新日期：{current_date}").classes("index-atomic-status")
                ui.label(f"指标状态计数：{counts}").classes("index-atomic-status")

    def render_alert() -> None:
        result = holder["result"]
        alert_area.clear()
        message = _snapshot_alert_message(result.status)
        if not message:
            return
        with alert_area:
            with ui.element("div").classes("index-atomic-alert w-full"):
                ui.label(message).classes("text-sm font-bold")
                ui.link("前往数据维护", f"/page/maintenance/{quote('数据体检', safe='')}").classes("text-sm font-semibold")

    def refresh_table() -> None:
        result = holder["result"]
        table_area.clear()
        if result.status in {"missing", "failed"}:
            return
        rows = build_index_atomic_rows(
            result.summary,
            IndexAtomicFilters(pool=str(pool.value or "core"), query=str(query.value or "")),
        )
        with table_area:
            if rows:
                render_table(rows, row_key="index_code", pagination=15, compact=True, ui_module=ui).classes(
                    "workbench-data-table workbench-data-table--compact w-full"
                ).on("rowClick", lambda event: _open_index_atomic_dialog(holder["result"], _event_row_code(event, "index_code")))
            else:
                empty_state("没有匹配的指数", "请调整核心/研究池或搜索条件。")

    def reload_snapshot() -> None:
        try:
            holder["result"] = load_index_atomic_snapshot_readonly(parquet_store, definitions, coverage=coverage)
        except Exception as exc:  # noqa: BLE001 - a read failure must keep the visible snapshot intact
            ui.notify(f"读取指数原子指标快照失败：{exc}", type="negative")
            return
        render_status_bar()
        render_alert()
        refresh_table()

    pool.on_value_change(lambda event: refresh_table())
    query.on_value_change(lambda event: refresh_table())
    render_status_bar()
    render_alert()
    refresh_table()
    _render_audit("market")


def _open_index_atomic_dialog(result, index_code: str) -> None:
    if not index_code:
        return
    groups = index_atomic_detail_groups(result.details, index_code)
    summary = _summary_row(result.summary, index_code)
    dialog = ui.dialog()
    with dialog:
        with ui.card().classes("index-atomic-dialog"):
            with ui.row().classes("w-full items-center justify-between gap-2"):
                ui.label(f"指数原子指标：{_summary_identity(summary, index_code)}").classes("text-lg font-bold")
                ui.button("关闭", icon="close", on_click=dialog.close).props("flat dense")
            with ui.tabs().classes("w-full") as tabs:
                key_tab = ui.tab("关键指标")
                all_tab = ui.tab("全部原子指标")
                quality_tab = ui.tab("数据质量")
            with ui.tab_panels(tabs, value=key_tab).classes("w-full"):
                with ui.tab_panel(key_tab):
                    _render_key_metrics(groups, summary)
                with ui.tab_panel(all_tab):
                    _render_all_atomic_groups(groups)
                with ui.tab_panel(quality_tab):
                    _render_snapshot_quality(result, summary)
    dialog.open()


def _render_key_metrics(groups, summary: dict[str, object]) -> None:
    _render_metric_grid(_key_metric_rows(groups, summary))


def _key_metric_rows(groups, summary: dict[str, object]) -> list[tuple[str, str, str]]:
    items_by_key = {item.metric_key: item for group in groups for item in group.items}
    rows: list[tuple[str, str, str]] = []
    for key, label in _KEY_METRICS:
        if key == "range_20":
            high = items_by_key.get("range_20_high")
            low = items_by_key.get("range_20_low")
            value = _range_20_text(high.value if high is not None else "", low.value if low is not None else "")
            status = high.status if high is not None else (low.status if low is not None else "")
        elif key == "data_status":
            value = _status_text(summary.get("snapshot_status"), "数据不足")
            status = ""
        else:
            item = items_by_key.get(key)
            value = item.value if item is not None else "数据不足"
            status = item.status if item is not None else ""
        rows.append((label, value, status))
    return rows


def _range_20_text(high: str, low: str) -> str:
    if high == "是":
        return "20日新高"
    if low == "是":
        return "20日新低"
    if high == "数据不足" or low == "数据不足":
        return "数据不足"
    return "区间内"


def _render_all_atomic_groups(groups) -> None:
    with ui.element("div").classes("index-atomic-detail-grid"):
        for group in groups:
            with ui.element("section").classes("index-atomic-detail-group"):
                ui.label(group.title).classes("index-atomic-detail-title")
                if group.items:
                    _render_metric_grid([(item.label, item.value, item.status) for item in group.items])
                else:
                    ui.label("该组没有存储指标。").classes("text-sm text-slate-500")


def _render_snapshot_quality(result, summary: dict[str, object]) -> None:
    coverage = " · ".join(
        part
        for part in (
            _status_text(summary.get("history_completeness_status"), ""),
            _text(summary.get("history_completeness_message"), ""),
        )
        if part
    ) or "暂无"
    _render_metric_grid(
        [
            ("快照生成时间", _datetime_text(result.generated_at), ""),
            ("快照状态", _SNAPSHOT_STATUS_LABELS.get(result.status, result.status), ""),
            ("原始历史状态", _status_text(summary.get("history_status"), "暂无"), ""),
            ("历史行数", _text(summary.get("history_rows"), "0"), ""),
            ("历史覆盖", coverage, ""),
            ("数据源", _data_source_text(summary.get("data_source")), ""),
            ("错误信息", _text(summary.get("error_text"), "无"), ""),
        ]
    )


def _render_metric_grid(rows: list[tuple[str, str, str]]) -> None:
    with ui.element("div").classes("index-atomic-detail-grid"):
        for label, value, status in rows:
            with ui.element("div").classes("index-atomic-detail-item"):
                ui.label(label).classes("index-atomic-detail-label")
                ui.label(value).classes("index-atomic-detail-value")
                if status:
                    ui.label(status).classes("index-atomic-detail-status")


def _summary_row(summary: pd.DataFrame, index_code: str) -> dict[str, object]:
    if summary.empty or "index_code" not in summary:
        return {}
    rows = summary[summary["index_code"].fillna("").astype(str) == index_code].to_dict("records")
    return rows[0] if rows else {}


def _summary_identity(summary: dict[str, object], index_code: str) -> str:
    name = _text(summary.get("index_name"), "")
    return f"{index_code} {name}".strip()


def _snapshot_alert_message(status: str) -> str:
    messages = {
        "stale": "原子指标快照待重建，当前展示的是上次成功生成的数据。",
        "missing": "尚未生成指数原子指标快照，不能展示计算指标。请前往数据维护执行“重建指数原子指标”。",
        "failed": "最近一次原子指标快照生成失败，不能把结果作为最新数据使用。请查看数据维护任务并重新执行。",
        "building": "指数原子指标快照正在生成，完成后请重新读取快照。",
    }
    return messages.get(status, "")


def _snapshot_status_counts(summary: pd.DataFrame) -> str:
    if summary.empty or "snapshot_status" not in summary:
        return "暂无"
    counts = summary["snapshot_status"].fillna("").astype(str).value_counts()
    if counts.empty:
        return "暂无"
    return "、".join(f"{_SNAPSHOT_STATUS_LABELS.get(key, key)} {count}" for key, count in counts.items())


def _datetime_text(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value is not None else "暂无"


def _text(value: object, fallback: str) -> str:
    if value is None or (not isinstance(value, (list, tuple, dict)) and pd.isna(value)):
        return fallback
    text = str(value).strip()
    return text or fallback


def _status_text(value: object, fallback: str) -> str:
    text = _text(value, fallback)
    return _SNAPSHOT_STATUS_LABELS.get(text, text)


def _data_source_text(value: object) -> str:
    text = _text(value, "暂无")
    return INDEX_ATOMIC_DATA_SOURCE_LABELS.get(text, text)


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
        ui.select(options, value=options[0], label="选择指数").props("dense outlined").classes("w-96").on_value_change(
            lambda event: draw_chart(event.value)
        )
        ui.label("指数只做市场状态判断，ETF交易载体在ETF数据页处理。").classes("workbench-chart-note")
    chart_area = ui.column().classes("w-full gap-2")
    draw_chart(options[0])
    _render_audit("market")


def _metric(label: str, value: object, detail: str) -> None:
    with ui.column().classes("workbench-metric"):
        ui.label(str(label)).classes("workbench-metric-label")
        ui.label(str(value)).classes("workbench-metric-value")
        ui.label(str(detail)).classes("workbench-metric-detail")


def _event_row_code(event, key: str) -> str:
    args = getattr(event, "args", event)
    if isinstance(args, dict):
        row = args.get("row", args)
    elif isinstance(args, (list, tuple)) and len(args) > 1 and isinstance(args[1], dict):
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
    with expansion("页面审计", icon="fact_check").classes("w-full"):
        for item in findings:
            ui.label(f"{item.problem} → {item.fix}").classes("text-xs text-slate-500")
