"""Data maintenance page."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from nicegui import ui

from etf_trading.data.indexes import index_options
from etf_trading.data.initialization import InitializationService
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.state import invalidate_snapshot_cache
from etf_trading.nicegui_app.view_models import (
    PlatformSnapshot,
    code_from_option,
    current_ui_audit_findings,
    etf_choice_options,
    etf_overview_rows,
    maintenance_rows,
)

SAMPLE_CATEGORIES = ["A股宽基", "A股行业", "港股宽基", "港股科技", "港股医药", "商品", "债券"]


def render(snapshot: PlatformSnapshot, section: str, store=None, parquet_store=None) -> None:
    if section == "数据总览":
        _render_data_overview(snapshot)
    elif section == "缺口明细":
        _render_gap_detail(snapshot)
    elif section == "补齐任务":
        _render_tasks(snapshot, store, parquet_store)
    else:
        _render_logs_and_settings(store)
    _render_audit()


def _render_data_overview(snapshot: PlatformSnapshot) -> None:
    with ui.row().classes("w-full gap-2"):
        _metric("覆盖项", len(snapshot.coverage), "数据集维度")
        _metric("缺口数", len(snapshot.gaps), "待处理项")
        _metric("ETF主列表", len(snapshot.master), "资产数量")
        _metric("计算池", len(snapshot.watchlist), "每日跟踪")
    rows = snapshot.coverage.fillna("").to_dict("records") if not snapshot.coverage.empty else []
    _render_rows(rows, "暂无数据健康摘要", "当前没有覆盖率数据。")


def _render_gap_detail(snapshot: PlatformSnapshot) -> None:
    rows = maintenance_rows(snapshot)
    if not rows:
        empty_state("暂无缺口明细", "当前没有检测到需要处理的数据缺口。")
        return

    data_types = ["全部类型", *sorted({str(row.get("数据类型", "")) for row in rows if row.get("数据类型")})]
    statuses = ["全部状态", *sorted({str(row.get("状态", "")) for row in rows if row.get("状态")})]
    with ui.row().classes("workbench-toolbar w-full"):
        data_type = ui.select(data_types, value=data_types[0], label="数据类型").props("dense outlined").classes("w-44")
        status = ui.select(statuses, value=statuses[0], label="状态").props("dense outlined").classes("w-44")
        query = ui.input("代码 / 名称").props("dense outlined clearable debounce=250").classes("w-64")
    result_area = ui.column().classes("w-full")

    def refresh() -> None:
        filtered = _filter_gap_rows(rows, str(data_type.value or ""), str(status.value or ""), str(query.value or ""))
        result_area.clear()
        with result_area:
            _render_rows(filtered, "没有匹配缺口", "换一个类型、状态或关键字再试。")

    data_type.on_value_change(lambda event: refresh())
    status.on_value_change(lambda event: refresh())
    query.on_value_change(lambda event: refresh())
    refresh()


def _render_tasks(snapshot: PlatformSnapshot, store, parquet_store) -> None:
    result_area = ui.column().classes("w-full gap-2")
    _render_master_tasks(store, parquet_store, result_area)
    _render_etf_history_tasks(snapshot, store, parquet_store, result_area)
    _render_index_history_tasks(store, parquet_store, result_area)
    _render_batch_tasks(store, parquet_store, result_area)
    ui.label("补齐任务只在点击后执行，避免打开页面自动触发耗时操作。").classes("text-xs text-slate-500")


def _render_master_tasks(store, parquet_store, result_area) -> None:
    with ui.expansion("主列表", icon="database").classes("workbench-task-panel w-full"):
        with ui.row().classes("workbench-toolbar w-full"):
            master_button = ui.button(
                "轻量初始化：拉取全量 A 股 ETF 列表",
                icon="database",
                on_click=lambda: _run_task(
                    master_button,
                    result_area,
                    "初始化ETF主列表",
                    lambda: _service_with_provider(store, parquet_store).initialize_master(),
                    lambda result: f"已写入 {len(result)} 只 ETF",
                ),
            ).props("dense outline")
            sample_button = ui.button(
                "选择样本 ETF",
                icon="fact_check",
                on_click=lambda: _run_task(
                    sample_button,
                    result_area,
                    "选择样本ETF",
                    lambda: _service(store, parquet_store).select_sample_etfs(SAMPLE_CATEGORIES),
                    lambda result: f"已筛选 {len(result)} 只样本 ETF",
                ),
            ).props("dense outline")


def _render_etf_history_tasks(snapshot: PlatformSnapshot, store, parquet_store, result_area) -> None:
    options = etf_choice_options(etf_overview_rows(snapshot))
    start = (date.today() - timedelta(days=365 * 5)).isoformat()
    end = date.today().isoformat()
    with ui.expansion("ETF历史", icon="history").classes("workbench-task-panel w-full"):
        if not options:
            empty_state("暂无ETF主列表", "请先初始化 ETF 主列表。")
            return
        with ui.row().classes("workbench-toolbar w-full"):
            selected = ui.select(options, value=options[0], label="ETF").props("dense outlined").classes("w-96")
            start_input = ui.input("开始日期", value=start).props("dense outlined type=date").classes("w-44")
            end_input = ui.input("结束日期", value=end).props("dense outlined type=date").classes("w-44")
            fetch_button = ui.button(
                "拉取并保存历史行情",
                icon="download",
                on_click=lambda: _run_task(
                    fetch_button,
                    result_area,
                    "拉取ETF历史行情",
                    lambda: _service_with_provider(store, parquet_store).fetch_and_store_history(
                        code_from_option(selected.value),
                        str(start_input.value or start),
                        str(end_input.value or end),
                    ),
                    lambda result: f"保存 {len(result)} 行历史行情",
                ),
            ).props("dense outline")


def _render_index_history_tasks(store, parquet_store, result_area) -> None:
    options = index_options()
    end = date.today().isoformat()
    with ui.expansion("指数历史", icon="stacked_line_chart").classes("workbench-task-panel w-full"):
        with ui.row().classes("workbench-toolbar w-full"):
            selected = ui.select(options, value=options[0], label="指数").props("dense outlined").classes("w-80")
            end_input = ui.input("指数结束日期", value=end).props("dense outlined type=date").classes("w-44")
            fetch_one_button = ui.button(
                "拉取并保存指数历史",
                icon="download",
                on_click=lambda: _run_task(
                    fetch_one_button,
                    result_area,
                    "拉取指数历史",
                    lambda: pd.DataFrame([_service_with_provider(store, parquet_store).ensure_index_history(code_from_option(selected.value), str(end_input.value or end)).__dict__]),
                    lambda result: f"已检查 {len(result)} 个指数",
                ),
            ).props("dense outline")
            fetch_all_button = ui.button(
                "一键初始化/补齐全部指数",
                icon="sync",
                on_click=lambda: _run_task(
                    fetch_all_button,
                    result_area,
                    "补齐全部指数历史",
                    lambda: _service_with_provider(store, parquet_store).ensure_all_index_history(str(end_input.value or end)),
                    lambda result: f"已检查 {len(result)} 个指数",
                ),
            ).props("dense outline")
        ui.label("单个指数失败不会中断全部指数补齐。").classes("text-xs text-slate-500")


def _render_batch_tasks(store, parquet_store, result_area) -> None:
    with ui.expansion("批量任务", icon="queue").classes("workbench-task-panel w-full"):
        with ui.row().classes("workbench-toolbar w-full"):
            jobs_button = ui.button(
                "为每日计算池创建历史初始化任务",
                icon="playlist_add",
                on_click=lambda: _run_task(
                    jobs_button,
                    result_area,
                    "生成ETF历史任务",
                    lambda: _service(store, parquet_store).create_history_jobs_for_watchlist(),
                    lambda result: f"已创建 {result} 个历史任务",
                ),
            ).props("dense outline")


def _render_logs_and_settings(store) -> None:
    if store is None:
        empty_state("暂无日志", "当前页面没有可用数据库连接。")
        return
    with store.connect() as conn:
        state = pd.read_sql_query("SELECT * FROM data_update_state ORDER BY updated_at DESC LIMIT 100", conn)
        jobs = pd.read_sql_query("SELECT * FROM data_fetch_job ORDER BY job_id DESC LIMIT 100", conn)
        quality = pd.read_sql_query("SELECT * FROM data_quality_log ORDER BY log_id DESC LIMIT 100", conn)
    options = {
        "更新状态": state,
        "任务日志": jobs,
        "数据质量日志": quality,
    }
    with ui.row().classes("workbench-toolbar w-full"):
        selected = ui.select(list(options), value="更新状态", label="日志视图").props("dense outlined").classes("w-52")
        ui.label("港股跨境 ETF 关键词和仓位上限由配置文件控制：configs/strategy.yaml、configs/risk.yaml。").classes("text-xs text-slate-500")
    result_area = ui.column().classes("w-full")

    def refresh() -> None:
        result_area.clear()
        with result_area:
            rows = options[str(selected.value)].fillna("").to_dict("records")
            _render_rows(rows, "暂无日志", "当前日志表为空。")

    selected.on_value_change(lambda event: refresh())
    refresh()


def _filter_gap_rows(rows: list[dict[str, object]], data_type: str, status: str, query: str) -> list[dict[str, object]]:
    normalized_query = query.strip().lower()
    filtered = []
    for row in rows:
        if data_type not in {"", "全部类型"} and str(row.get("数据类型", "")) != data_type:
            continue
        if status not in {"", "全部状态"} and str(row.get("状态", "")) != status:
            continue
        searchable = " ".join(str(value) for value in row.values()).lower()
        if normalized_query and normalized_query not in searchable:
            continue
        filtered.append(row)
    return filtered


def _run_task(button, result_area, title: str, action, success_message) -> None:
    if button is not None:
        button.disable()
    result_area.clear()
    try:
        result = action()
    except Exception as exc:  # noqa: BLE001 - UI should surface provider/storage errors clearly
        ui.notify(f"{title}失败：{exc}", type="negative")
        with result_area:
            empty_state(f"{title}失败", str(exc))
    else:
        invalidate_snapshot_cache()
        message = success_message(result)
        ui.notify(message, type="positive")
        with result_area:
            ui.label(message).classes("text-sm font-semibold text-slate-700")
            _render_task_result(result)
    finally:
        if button is not None:
            button.enable()


def _render_task_result(result) -> None:
    if isinstance(result, pd.DataFrame):
        rows = result.fillna("").to_dict("records") if not result.empty else []
    elif isinstance(result, list):
        rows = result
    else:
        rows = [{"结果": result}]
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, pagination=10).classes("workbench-data-table w-full")


def _render_rows(rows: list[dict[str, object]], empty_title: str, empty_detail: str) -> None:
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, pagination=12).classes("workbench-data-table w-full")
    else:
        empty_state(empty_title, empty_detail)


def _metric(label: str, value: object, detail: str) -> None:
    with ui.column().classes("workbench-metric"):
        ui.label(label).classes("workbench-metric-label")
        ui.label(str(value)).classes("workbench-metric-value")
        ui.label(detail).classes("text-xs text-slate-400")


def _service(store, parquet_store) -> InitializationService:
    if store is None:
        raise ValueError("当前页面没有可用数据库连接")
    return InitializationService(store=store, parquet_store=parquet_store)


def _service_with_provider(store, parquet_store) -> InitializationService:
    if store is None:
        raise ValueError("当前页面没有可用数据库连接")
    return InitializationService(store=store, provider=AkShareProvider(), parquet_store=parquet_store)


def _render_audit() -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "maintenance":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
