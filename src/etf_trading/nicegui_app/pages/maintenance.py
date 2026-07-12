"""Data maintenance page."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
from nicegui import run, ui

from etf_trading.data.indexes import index_options
from etf_trading.data.initialization import EtfHistoryProgress, InitializationService
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.data.storage import MaintenanceTaskRun
from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.tables import VALUE_LABELS, render_table
from etf_trading.nicegui_app.maintenance_tasks import (
    INDEX_ATOMIC_SNAPSHOT_REBUILD_TASK_TYPE,
    INDEX_MAINTENANCE_TASK_TYPES,
    IndexAtomicSnapshotMaintenanceRunner,
    IndexCatalogMaintenanceRunner,
    IndexHistoryBatchRunner,
)
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
EtfHistoryProgressView = EtfHistoryProgress
INDEX_HISTORY_BATCH_TASK_TITLE = "补齐全部指数历史"
INDEX_TASK_TITLES = {
    "index_history_batch": INDEX_HISTORY_BATCH_TASK_TITLE,
    INDEX_ATOMIC_SNAPSHOT_REBUILD_TASK_TYPE: "重建指数原子指标",
    **INDEX_MAINTENANCE_TASK_TYPES,
}


@dataclass
class MaintenanceTaskStatus:
    title: str = ""
    state: str = "idle"
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: object | None = None
    error: str = ""
    progress_done: int = 0
    progress_total: int = 0
    progress_detail: str = ""


def _task_state_label(state: str) -> str:
    return {
        "idle": "空闲",
        "running": "运行中",
        "success": "成功",
        "failed": "失败",
        "interrupted": "已中断",
        "cancelled": "取消",
    }.get(state, "空闲")


def _task_state_tone(state: str) -> str:
    return {
        "idle": "neutral",
        "running": "info",
        "success": "success",
        "failed": "danger",
        "interrupted": "warning",
        "cancelled": "warning",
    }.get(state, "neutral")


def _format_task_time(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else ""


def _task_status_from_run(run: MaintenanceTaskRun) -> MaintenanceTaskStatus:
    result = json.loads(run.result_json) if run.result_json else None
    title = INDEX_TASK_TITLES.get(run.task_type, run.task_type)
    if run.state == "success":
        message = _catalog_task_message(run.task_type, result or [])
        error = ""
    elif run.state == "running":
        message = f"{title}正在执行，请稍候..."
        error = ""
    else:
        message = run.error_message or "任务没有返回结果，请稍后重试。"
        error = run.error_message or ""
    return MaintenanceTaskStatus(
        title=title,
        state=run.state,
        message=message,
        started_at=_parse_task_time(run.started_at),
        finished_at=_parse_task_time(run.finished_at),
        result=result,
        error=error,
        progress_done=run.progress_done,
        progress_total=run.progress_total,
        progress_detail=_task_progress_detail_label(run.progress_detail),
    )


def _parse_task_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _task_progress_detail_label(detail: str) -> str:
    code, separator, status = detail.rpartition(" ")
    if not separator:
        return detail
    return f"{code} {VALUE_LABELS.get(status, status)}"


def _index_history_batch_message(rows: list[dict[str, object]]) -> str:
    statuses = pd.Series([str(row.get("status", "")) for row in rows], dtype=str)
    completed = int(statuses.isin(["INITIALIZED", "UPDATED", "REPAIRED"]).sum())
    skipped = int((statuses == "SKIPPED").sum())
    stale = int((statuses == "STALE").sum())
    failed_or_empty = int(statuses.isin(["FAILED", "EMPTY"]).sum())
    return (
        f"已检查 {len(rows)} 个指数：补齐 {completed}，跳过 {skipped}，"
        f"行情仍滞后 {stale}，失败/无数据 {failed_or_empty}"
    )


def _catalog_task_message(task_type: str, rows: object) -> str:
    if task_type == INDEX_ATOMIC_SNAPSHOT_REBUILD_TASK_TYPE:
        result = rows if isinstance(rows, dict) else {}
        total = int(result.get("total_count", 0))
        calculated = int(result.get("successfully_calculated_count", 0))
        status_counts = result.get("data_status_counts", {})
        status_text = "、".join(f"{status} {count}" for status, count in status_counts.items()) if isinstance(status_counts, dict) else ""
        suffix = f"；状态：{status_text}" if status_text else ""
        return f"已重建 {calculated}/{total} 个指数的原子指标{suffix}"
    if not isinstance(rows, list):
        rows = []
    if task_type == "index_catalog_sync":
        pools = pd.Series([str(row.get("pool", "")) for row in rows], dtype=str)
        formal = int(pools.isin(["core", "research"]).sum())
        return (
            f"目录已同步：候选 {len(rows)}，正式 {formal}，核心 {int((pools == 'core').sum())}，"
            f"研究 {int((pools == 'research').sum())}，候补 {int((pools == 'reserve').sum())}"
        )
    if task_type == "index_source_validation":
        statuses = pd.Series([str(row.get("status", "")) for row in rows], dtype=str)
        return f"已验证 {len(rows)} 个指数：可用 {int((statuses == 'SUCCESS').sum())}，异常 {int((statuses != 'SUCCESS').sum())}"
    if task_type == "index_history_repair":
        completeness = pd.Series([str(row.get("completeness_status", "")) for row in rows], dtype=str)
        return f"已检查 {len(rows)} 个指数：历史不完整 {int((completeness == 'INCOMPLETE').sum())}"
    return _index_history_batch_message(rows)


def _render_task_center(container, status: MaintenanceTaskStatus) -> None:
    container.clear()
    tone = _task_state_tone(status.state)
    with container:
        with ui.column().classes("workbench-task-center w-full"):
            with ui.row().classes("workbench-task-center-header w-full"):
                ui.icon("task_alt").classes(f"tone-{tone}")
                ui.label("任务中心").classes("text-sm font-semibold text-slate-700")
                ui.badge(_task_state_label(status.state)).classes(f"workbench-task-center-status is-{status.state}")
            if status.state == "idle":
                ui.label("暂无任务").classes("text-sm font-semibold text-slate-600")
                ui.label("点击下方补齐按钮后，这里会显示运行状态和最近结果。").classes("text-xs text-slate-500")
                return

            ui.label(status.title).classes("text-sm font-semibold text-slate-700")
            if status.message:
                ui.label(status.message).classes(f"text-sm font-semibold tone-{tone}")

            meta_parts = []
            if status.started_at is not None:
                meta_parts.append(f"开始 {_format_task_time(status.started_at)}")
            if status.finished_at is not None:
                meta_parts.append(f"结束 {_format_task_time(status.finished_at)}")
            if meta_parts:
                ui.label(" · ".join(meta_parts)).classes("workbench-task-center-meta")

            if status.progress_total > 0:
                progress_value = max(0.0, min(1.0, status.progress_done / status.progress_total))
                ui.linear_progress(value=progress_value).props("instant-feedback").classes("w-full")
                detail = status.progress_detail or status.title
                ui.label(f"{status.progress_done}/{status.progress_total} · {detail}").classes("text-xs text-slate-500")

            if status.state == "success" and status.result is not None:
                with ui.column().classes("workbench-task-center-result w-full"):
                    _render_task_result(status.result)
            elif status.state in {"failed", "interrupted"} and status.error:
                ui.label(status.error).classes("text-xs text-red-700")
            elif status.state == "cancelled":
                ui.label("任务没有返回结果，请稍后重试。").classes("text-xs text-amber-700")


def render(snapshot: PlatformSnapshot, section: str, store=None, parquet_store=None) -> None:
    if section in {"数据体检", "数据总览"}:
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
    index_runner = IndexHistoryBatchRunner(store, parquet_store)
    catalog_runner = IndexCatalogMaintenanceRunner(store, parquet_store) if hasattr(store, "list_index_catalog") else None
    atomic_snapshot_runner = (
        IndexAtomicSnapshotMaintenanceRunner(store, parquet_store) if hasattr(store, "list_index_catalog") else None
    )
    index_runner.reconcile_interrupted()
    persisted_runs = [run for run in [index_runner.latest()] if run is not None]
    if atomic_snapshot_runner is not None:
        run = atomic_snapshot_runner.latest()
        if run is not None:
            persisted_runs.append(run)
    if catalog_runner is not None:
        for task_type in INDEX_MAINTENANCE_TASK_TYPES:
            run = catalog_runner.latest(task_type)
            if run is not None:
                persisted_runs.append(run)
    persisted_run = max(persisted_runs, key=lambda run: run.task_id) if persisted_runs else None
    task_status = _task_status_from_run(persisted_run) if persisted_run is not None else MaintenanceTaskStatus()
    task_center = ui.column().classes("w-full")
    _render_task_center(task_center, task_status)

    def refresh_persisted_index_task() -> None:
        if task_status.state != "idle" and task_status.title not in set(INDEX_TASK_TITLES.values()):
            return
        runs = [run for run in [index_runner.latest()] if run is not None]
        if atomic_snapshot_runner is not None:
            run = atomic_snapshot_runner.latest()
            if run is not None:
                runs.append(run)
        if catalog_runner is not None:
            for task_type in INDEX_MAINTENANCE_TASK_TYPES:
                run = catalog_runner.latest(task_type)
                if run is not None:
                    runs.append(run)
        if not runs:
            return
        run = max(runs, key=lambda item: item.task_id)
        restored = _task_status_from_run(run)
        task_status.__dict__.update(restored.__dict__)
        _render_task_center(task_center, task_status)

    timer_factory = getattr(ui, "timer", None)
    if timer_factory is not None:
        timer_factory(1.0, refresh_persisted_index_task, immediate=False)

    _render_master_tasks(store, parquet_store, task_center, task_status)
    _render_etf_history_tasks(snapshot, store, parquet_store, task_center, task_status)
    _render_index_history_tasks(store, parquet_store, task_center, task_status, index_runner)
    if catalog_runner is not None:
        _render_catalog_index_tasks(store, parquet_store, task_center, task_status, catalog_runner, atomic_snapshot_runner)
    _render_batch_tasks(store, parquet_store, task_center, task_status)
    ui.label("补齐任务只在点击后执行，避免打开页面自动触发耗时操作。").classes("text-xs text-slate-500")


def _render_master_tasks(store, parquet_store, task_center, task_status: MaintenanceTaskStatus) -> None:
    with ui.expansion("主列表", icon="database").classes("workbench-task-panel w-full"):
        with ui.row().classes("workbench-toolbar w-full"):
            master_button = ui.button(
                "轻量初始化：拉取全量 A 股 ETF 列表",
                icon="database",
                on_click=lambda: _run_task(
                    master_button,
                    task_center,
                    task_status,
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
                    task_center,
                    task_status,
                    "选择样本ETF",
                    lambda: _service(store, parquet_store).select_sample_etfs(SAMPLE_CATEGORIES),
                    lambda result: f"已筛选 {len(result)} 只样本 ETF",
                ),
            ).props("dense outline")


def _render_etf_history_tasks(snapshot: PlatformSnapshot, store, parquet_store, task_center, task_status: MaintenanceTaskStatus) -> None:
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
                    task_center,
                    task_status,
                    "拉取ETF历史行情",
                    lambda: _service_with_provider(store, parquet_store).fetch_and_store_history(
                        code_from_option(selected.value),
                        str(start_input.value or start),
                        str(end_input.value or end),
                    ),
                    lambda result: f"保存 {len(result)} 行历史行情",
                ),
            ).props("dense outline")
            fetch_all_button = ui.button(
                "一键初始化/补齐全部ETF",
                icon="sync",
                on_click=lambda: _run_task(
                    fetch_all_button,
                    task_center,
                    task_status,
                    "补齐全部ETF历史",
                    lambda: _service_with_provider(store, parquet_store).ensure_all_etf_history(
                        str(start_input.value or start),
                        str(end_input.value or end),
                        refresh_master=True,
                        sleep_seconds=0.15,
                        on_progress=lambda progress: _update_etf_history_progress(task_status, progress),
                    ),
                    _etf_history_batch_success_message,
                ),
            ).props("dense outline")
        ui.label("全量补齐会跳过已新鲜的本地 ETF 历史；中断后再次点击会从缺失或滞后的 ETF 继续。").classes("text-xs text-slate-500")


def _render_index_history_tasks(store, parquet_store, task_center, task_status: MaintenanceTaskStatus, index_runner: IndexHistoryBatchRunner) -> None:
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
                    task_center,
                    task_status,
                    "拉取指数历史",
                    lambda: pd.DataFrame([_service_with_provider(store, parquet_store).ensure_index_history(code_from_option(selected.value), str(end_input.value or end)).__dict__]),
                    lambda result: f"已检查 {len(result)} 个指数",
                ),
            ).props("dense outline")
            fetch_all_button = ui.button(
                "一键初始化/补齐全部指数",
                icon="sync",
                on_click=lambda: _start_persisted_index_history_batch(
                    index_runner,
                    str(end_input.value or end),
                    task_center,
                    task_status,
                ),
            ).props("dense outline")
        ui.label("单个指数失败不会中断全部指数补齐。").classes("text-xs text-slate-500")


def _render_catalog_index_tasks(
    store,
    parquet_store,
    task_center,
    task_status: MaintenanceTaskStatus,
    runner: IndexCatalogMaintenanceRunner,
    atomic_snapshot_runner: IndexAtomicSnapshotMaintenanceRunner,
) -> None:
    end = date.today().isoformat()
    summary = _index_catalog_summary(store)
    with ui.expansion("指数目录与完整性", icon="rule").classes("workbench-task-panel w-full"):
        with ui.row().classes("w-full gap-2"):
            _metric("候选", summary["candidates"], "目录记录")
            _metric("正式", summary["formal"], "核心 + 研究")
            _metric("核心/研究/候补", f"{summary['core']}/{summary['research']}/{summary['reserve']}", "分层")
            _metric("历史完整", summary["complete"], "已核验")
            _metric("待补/待核验", summary["incomplete"], "不作买卖依据")
        ui.label(
            f"行情仍滞后 {summary['stale']}，历史缺失 {summary['missing']}，读取失败 {summary['read_failed']}。"
        ).classes("text-xs text-slate-500")
        with ui.row().classes("workbench-toolbar w-full"):
            end_input = ui.input("目录任务结束日期", value=end).props("dense outlined type=date").classes("w-44")
            for task_type, label in INDEX_MAINTENANCE_TASK_TYPES.items():
                ui.button(
                    label,
                    icon="sync" if task_type != "index_source_validation" else "fact_check",
                    on_click=lambda task_type=task_type: _start_catalog_index_task(
                        runner,
                        task_type,
                        str(end_input.value or end),
                        task_center,
                        task_status,
                    ),
                ).props("dense outline")
            ui.button(
                "重建指数原子指标",
                icon="build",
                on_click=lambda: _start_atomic_snapshot_rebuild_task(
                    atomic_snapshot_runner,
                    task_center,
                    task_status,
                ),
            ).props("dense outline")
        ui.label("目录同步和数据源验证不会拉取全历史；全量与修复操作均从 1990-01-01 请求，并可在刷新页面后恢复查看。").classes("text-xs text-slate-500")
        ui.label("只读取本地指数历史；初始化、补齐或修复历史后，请手动重建。").classes("text-xs text-slate-500")


def _start_catalog_index_task(
    runner: IndexCatalogMaintenanceRunner,
    task_type: str,
    through: str,
    task_center,
    task_status: MaintenanceTaskStatus,
) -> None:
    run = runner.start(task_type, through=through)
    restored = _task_status_from_run(run)
    task_status.__dict__.update(restored.__dict__)
    _render_task_center(task_center, task_status)
    ui.notify(task_status.message, type="info")


def _start_atomic_snapshot_rebuild_task(
    runner: IndexAtomicSnapshotMaintenanceRunner,
    task_center,
    task_status: MaintenanceTaskStatus,
) -> None:
    run = runner.start()
    restored = _task_status_from_run(run)
    task_status.__dict__.update(restored.__dict__)
    _render_task_center(task_center, task_status)
    ui.notify(task_status.message, type="info")


def _index_catalog_summary(store) -> dict[str, int]:
    catalog = store.list_index_catalog(include_reserve=True)
    coverage = store.list_index_history_coverage()
    pools = catalog.get("pool", pd.Series(dtype=str)).fillna("").astype(str)
    completeness = coverage.get("completeness_status", pd.Series(dtype=str)).fillna("").astype(str)
    try:
        with store.connect() as conn:
            state = pd.read_sql_query("SELECT dataset, asset_code, status FROM data_update_state", conn)
    except Exception:  # noqa: BLE001 - a missing optional state table should not hide catalog health
        state = pd.DataFrame()
    stale = 0
    read_failed = int((completeness == "READ_FAILED").sum())
    if not state.empty:
        index_state = state[state.get("dataset", pd.Series(dtype=str)).astype(str) == "index_daily_price"]
        statuses = index_state.get("status", pd.Series(dtype=str)).fillna("").astype(str)
        stale = int((statuses == "STALE").sum())
        read_failed += int((statuses == "FAILED").sum())
    return {
        "candidates": int(len(catalog)),
        "formal": int(pools.isin(["core", "research"]).sum()),
        "core": int((pools == "core").sum()),
        "research": int((pools == "research").sum()),
        "reserve": int((pools == "reserve").sum()),
        "complete": int((completeness == "COMPLETE").sum()),
        "incomplete": int(completeness.isin(["INCOMPLETE", "BASELINE_UNVERIFIED", "SOURCE_LIMITED", "NOT_VALIDATED"]).sum()),
        "missing": int((completeness == "MISSING_HISTORY").sum()),
        "stale": stale,
        "read_failed": read_failed,
    }


def _start_persisted_index_history_batch(
    runner: IndexHistoryBatchRunner,
    through: str,
    task_center,
    task_status: MaintenanceTaskStatus,
) -> None:
    run = runner.start(through)
    restored = _task_status_from_run(run)
    task_status.__dict__.update(restored.__dict__)
    _render_task_center(task_center, task_status)
    ui.notify(task_status.message, type="info")


def _render_batch_tasks(store, parquet_store, task_center, task_status: MaintenanceTaskStatus) -> None:
    with ui.expansion("批量任务", icon="queue").classes("workbench-task-panel w-full"):
        with ui.row().classes("workbench-toolbar w-full"):
            jobs_button = ui.button(
                "为每日计算池创建历史初始化任务",
                icon="playlist_add",
                on_click=lambda: _run_task(
                    jobs_button,
                    task_center,
                    task_status,
                    "生成ETF历史任务",
                    lambda: _service(store, parquet_store).create_history_jobs_for_watchlist(),
                    lambda result: f"已创建 {result} 个历史任务",
                ),
            ).props("dense outline")
            all_master_button = ui.button(
                "为全部ETF主池创建历史初始化任务",
                icon="playlist_add_check",
                on_click=lambda: _run_task(
                    all_master_button,
                    task_center,
                    task_status,
                    "生成全量ETF历史任务",
                    lambda: _service(store, parquet_store).create_history_jobs_for_all_master(),
                    lambda result: f"已创建 {result} 个全量 ETF 历史任务",
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


async def _run_task(button, task_center, task_status: MaintenanceTaskStatus, title: str, action, success_message) -> None:
    if button is not None:
        button.disable()

    task_status.title = title
    task_status.state = "running"
    task_status.message = f"{title}正在执行，请稍候..."
    task_status.started_at = datetime.now()
    task_status.finished_at = None
    task_status.result = None
    task_status.error = ""
    task_status.progress_done = 0
    task_status.progress_total = 0
    task_status.progress_detail = ""
    _render_task_center(task_center, task_status)

    ui.notify(task_status.message, type="info")
    if button is not None:
        button.update()
    task_center.update()
    progress_timer = _start_task_progress_timer(task_center, task_status)

    try:
        result = await run.io_bound(action)
    except Exception as exc:  # noqa: BLE001 - UI should surface provider/storage errors clearly
        task_status.state = "failed"
        task_status.message = f"{title}失败：{exc}"
        task_status.finished_at = datetime.now()
        task_status.result = None
        task_status.error = str(exc)
        ui.notify(task_status.message, type="negative")
        _render_task_center(task_center, task_status)
    else:
        task_status.finished_at = datetime.now()
        if result is None:
            task_status.state = "cancelled"
            task_status.message = f"{title}已取消或服务正在关闭"
            task_status.result = None
            task_status.error = ""
            ui.notify(task_status.message, type="warning")
            _render_task_center(task_center, task_status)
            return
        invalidate_snapshot_cache()
        task_status.state = "success"
        task_status.message = success_message(result)
        task_status.result = result
        task_status.error = ""
        ui.notify(task_status.message, type="positive")
        _render_task_center(task_center, task_status)
    finally:
        if progress_timer is not None:
            progress_timer.cancel()
        if button is not None:
            button.enable()


def _start_task_progress_timer(task_center, task_status: MaintenanceTaskStatus):
    timer_factory = getattr(ui, "timer", None)
    if timer_factory is None:
        return None
    return timer_factory(1.0, lambda: _render_task_center(task_center, task_status), immediate=False)


def _update_etf_history_progress(task_status: MaintenanceTaskStatus, progress: EtfHistoryProgress) -> None:
    task_status.progress_done = progress.done
    task_status.progress_total = progress.total
    task_status.progress_detail = f"{progress.etf_code} {progress.status}"


def _etf_history_batch_success_message(result: pd.DataFrame) -> str:
    if result.empty or "status" not in result.columns:
        return "已检查 0 只 ETF：补齐 0，跳过 0，失败 0"
    statuses = result["status"].astype(str)
    skipped = int((statuses == "SKIPPED").sum())
    failed = int((statuses == "FAILED").sum())
    completed = int(statuses.isin(["INITIALIZED", "UPDATED", "EMPTY"]).sum())
    return f"已检查 {len(result)} 只 ETF：补齐 {completed}，跳过 {skipped}，失败 {failed}"


def _render_task_result(result) -> None:
    if isinstance(result, pd.DataFrame):
        rows = result.fillna("").to_dict("records") if not result.empty else []
    elif isinstance(result, list):
        rows = result
    else:
        rows = [{"结果": result}]
    if rows:
        render_table(rows, pagination=10, ui_module=ui).classes("workbench-data-table w-full")


def _render_rows(rows: list[dict[str, object]], empty_title: str, empty_detail: str) -> None:
    if rows:
        render_table(rows, pagination=12, ui_module=ui).classes("workbench-data-table w-full")
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
