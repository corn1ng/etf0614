from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
import threading
from datetime import datetime

import pandas as pd
import pytest

from etf_trading.data.index_catalog import IndexCatalogEntry
from etf_trading.data.storage import MaintenanceTaskRun
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.nicegui_app import state
from etf_trading.research.index_health_snapshot import INDEX_ATOMIC_DETAIL_COLUMNS, INDEX_ATOMIC_SUMMARY_COLUMNS


def _atomic_definition() -> IndexCatalogEntry:
    return IndexCatalogEntry(
        index_code="000300",
        name="沪深300",
        market="A股",
        category_level_1="A股",
        category_level_2="宽基",
        index_type="宽基",
        pool="core",
        index_base_date=None,
        baseline_source="unverified",
        source_kind="csi",
        provider_symbol="000300",
    )


def _atomic_summary(index_code: str = "000300") -> pd.DataFrame:
    row = {column: pd.NA for column in INDEX_ATOMIC_SUMMARY_COLUMNS}
    row.update({"index_code": index_code, "index_name": "沪深300", "snapshot_status": "computed"})
    return pd.DataFrame([row], columns=INDEX_ATOMIC_SUMMARY_COLUMNS)


def _atomic_details(index_code: str = "000300") -> pd.DataFrame:
    row = {column: pd.NA for column in INDEX_ATOMIC_DETAIL_COLUMNS}
    row.update({"index_code": index_code, "metric_key": "close", "status": "computed"})
    return pd.DataFrame([row], columns=INDEX_ATOMIC_DETAIL_COLUMNS)


def _atomic_coverage() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": ["000300"],
            "latest_trade_date": ["2026-07-11"],
            "history_rows": [260],
            "completeness_status": ["COMPLETE"],
        }
    )


def _successful_atomic_builder():
    def build_snapshot(parquet_store, definitions, *, coverage=None, on_progress=None):
        del parquet_store, coverage
        for done, definition in enumerate(definitions, start=1):
            if on_progress is not None:
                on_progress(type("Progress", (), {"done": done, "total": len(definitions), "index_code": definition.index_code})())
        return _atomic_summary(), _atomic_details()

    return build_snapshot


def _failing_atomic_builder():
    def build_snapshot(parquet_store, definitions, *, coverage=None, on_progress=None):
        del parquet_store, definitions, coverage, on_progress
        raise OSError("本地 Parquet 损坏")

    return build_snapshot


def _atomic_runner(tmp_path, build_snapshot, monkeypatch, **runner_kwargs):
    from etf_trading.nicegui_app import maintenance_tasks

    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.upsert_index_catalog((_atomic_definition(),))
    store.upsert_index_history_coverage(
        "000300",
        index_base_date=None,
        baseline_source="unverified",
        local_first_trade_date="2025-07-01",
        source_first_trade_date=None,
        latest_trade_date="2026-07-11",
        history_rows=260,
        completeness_status="COMPLETE",
        completeness_message="完整",
    )
    parquet_store = ParquetStore(tmp_path / "parquet")

    async def run_inline(callback):
        return callback()

    def create_inline(awaitable, **kwargs):
        del kwargs
        asyncio.run(awaitable)

    monkeypatch.setattr(maintenance_tasks.run, "io_bound", run_inline)
    monkeypatch.setattr(maintenance_tasks.background_tasks, "create", create_inline)
    return maintenance_tasks.IndexAtomicSnapshotMaintenanceRunner(
        store,
        parquet_store,
        build_snapshot=build_snapshot,
        **runner_kwargs,
    ), store, parquet_store


def _wait_for_terminal_task(store, task_id: int) -> MaintenanceTaskRun:
    task = store.get_maintenance_task_run(task_id)
    assert task is not None
    assert task.state != "running"
    return task


def _snapshot_meta(parquet_store: ParquetStore) -> dict[str, object]:
    return json.loads((parquet_store.root / "cache" / "index_atomic_snapshot.meta.json").read_text(encoding="utf-8"))


def _write_previous_snapshot(parquet_store: ParquetStore) -> None:
    definitions = (_atomic_definition().to_index_definition(),)
    coverage = _atomic_coverage()
    source_signature = state._index_atomic_snapshot_source_signature(parquet_store, definitions, coverage)
    state.write_index_atomic_snapshot(
        _atomic_summary(),
        _atomic_details(),
        source_signature,
        datetime(2026, 7, 11, 9, 0),
        parquet_store,
        definitions=definitions,
        coverage=coverage,
        expected_input_signature=source_signature,
        task_result_id=99,
    )


def test_atomic_snapshot_runner_persists_completed_result_and_snapshot_meta(tmp_path, monkeypatch):
    runner, store, parquet_store = _atomic_runner(tmp_path, _successful_atomic_builder(), monkeypatch)

    task = runner.start()
    completed = _wait_for_terminal_task(store, task.task_id)

    assert completed.state == "success"
    assert completed.result_json
    assert completed.progress_done == 1
    assert completed.progress_total == 1
    assert completed.progress_detail == "000300"
    assert json.loads(completed.result_json) == {
        "total_count": 1,
        "successfully_calculated_count": 1,
        "data_status_counts": {"computed": 1},
        "generated_at": _snapshot_meta(parquet_store)["generated_at"],
        "snapshot_files": [
            "index_atomic_snapshot.parquet",
            "index_atomic_snapshot_details.parquet",
            "index_atomic_snapshot.meta.json",
        ],
    }
    assert _snapshot_meta(parquet_store)["task_result_id"] == task.task_id
    definitions, coverage = state.index_atomic_snapshot_inputs(store)
    assert _snapshot_meta(parquet_store)["source_signature"] == state._index_atomic_snapshot_source_signature(
        parquet_store,
        definitions,
        coverage,
    )


def test_atomic_snapshot_runner_uses_local_builder_without_initialization_service(tmp_path, monkeypatch):
    from etf_trading.nicegui_app import maintenance_tasks

    monkeypatch.setattr(
        maintenance_tasks,
        "InitializationService",
        lambda *args, **kwargs: pytest.fail("原子快照重建不能创建初始化服务"),
    )
    monkeypatch.setattr(
        maintenance_tasks,
        "create_data_provider",
        lambda *args, **kwargs: pytest.fail("原子快照重建不能创建数据提供方"),
    )
    runner, store, _ = _atomic_runner(tmp_path, _successful_atomic_builder(), monkeypatch)

    task = runner.start()

    assert _wait_for_terminal_task(store, task.task_id).state == "success"


def test_atomic_snapshot_runner_keeps_previous_snapshot_when_rebuild_fails(tmp_path, monkeypatch):
    runner, store, parquet_store = _atomic_runner(tmp_path, _failing_atomic_builder(), monkeypatch)
    _write_previous_snapshot(parquet_store)

    task = runner.start()
    failed = _wait_for_terminal_task(store, task.task_id)
    definitions = (_atomic_definition().to_index_definition(),)
    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions, coverage=_atomic_coverage())

    assert failed.state == "failed"
    assert failed.error_message == "重建指数原子指标失败：本地 Parquet 损坏"
    assert result.summary.empty is False


def test_atomic_snapshot_runner_rejects_publish_when_local_history_changes_during_build(tmp_path, monkeypatch):
    def build_snapshot(parquet_store, definitions, *, coverage=None, on_progress=None):
        del definitions, coverage, on_progress
        parquet_store.write_index_prices(
            "000300",
            pd.DataFrame({"trade_date": ["2026-07-12"], "close": [1.0]}),
        )
        return _atomic_summary("000905"), _atomic_details("000905")

    runner, store, parquet_store = _atomic_runner(tmp_path, build_snapshot, monkeypatch)
    _write_previous_snapshot(parquet_store)

    task = runner.start()
    failed = _wait_for_terminal_task(store, task.task_id)
    definitions, coverage = state.index_atomic_snapshot_inputs(store)
    result = state.load_index_atomic_snapshot_readonly(parquet_store, definitions, coverage=coverage)

    assert failed.state == "failed"
    assert failed.error_message == "重建指数原子指标失败：本地输入已变化，拒绝发布快照"
    assert result.status == "stale"
    assert result.summary["index_code"].tolist() == ["000300"]
    assert _snapshot_meta(parquet_store)["task_result_id"] == 99


def test_atomic_snapshot_runner_rejects_publish_when_valuation_history_changes_during_build(tmp_path, monkeypatch):
    def build_snapshot(parquet_store, definitions, *, coverage=None, on_progress=None):
        del definitions, coverage, on_progress
        parquet_store.write_index_valuations(
            "000300",
            pd.DataFrame({"trade_date": ["2026-07-12"], "pe_ttm": [12.0]}),
        )
        return _atomic_summary("000905"), _atomic_details("000905")

    runner, store, parquet_store = _atomic_runner(tmp_path, build_snapshot, monkeypatch)
    _write_previous_snapshot(parquet_store)

    task = runner.start()
    failed = _wait_for_terminal_task(store, task.task_id)

    assert failed.state == "failed"
    assert failed.error_message == "重建指数原子指标失败：本地输入已变化，拒绝发布快照"


def test_atomic_snapshot_runner_start_deduplicates_concurrent_calls_per_store(tmp_path, monkeypatch):
    from etf_trading.nicegui_app import maintenance_tasks

    build_calls = []
    writer_task_ids = []

    def build_snapshot(parquet_store, definitions, *, coverage=None, on_progress=None):
        del parquet_store, coverage
        build_calls.append(tuple(definition.index_code for definition in definitions))
        for done, definition in enumerate(definitions, start=1):
            if on_progress is not None:
                on_progress(type("Progress", (), {"done": done, "total": len(definitions), "index_code": definition.index_code})())
        return _atomic_summary(), _atomic_details()

    runner, store, parquet_store = _atomic_runner(tmp_path, build_snapshot, monkeypatch)
    second_runner = maintenance_tasks.IndexAtomicSnapshotMaintenanceRunner(
        store,
        parquet_store,
        build_snapshot=build_snapshot,
    )
    monkeypatch.setattr(runner, "reconcile_interrupted", lambda: None)
    monkeypatch.setattr(second_runner, "reconcile_interrupted", lambda: None)

    original_get_running = store.get_running_maintenance_task_run
    checked_lock = threading.Lock()
    checked_count = 0
    both_checked = threading.Event()

    def race_running_check(task_type):
        nonlocal checked_count
        result = original_get_running(task_type)
        with checked_lock:
            checked_count += 1
            if checked_count == 2:
                both_checked.set()
        both_checked.wait(timeout=1)
        return result

    scheduled = []
    scheduled_lock = threading.Lock()

    def collect_background(awaitable, **kwargs):
        del kwargs
        with scheduled_lock:
            scheduled.append(awaitable)

    original_writer = maintenance_tasks.write_index_atomic_snapshot

    def track_writer(*args, **kwargs):
        writer_task_ids.append(kwargs["task_result_id"])
        return original_writer(*args, **kwargs)

    monkeypatch.setattr(store, "get_running_maintenance_task_run", race_running_check)
    monkeypatch.setattr(maintenance_tasks.background_tasks, "create", collect_background)
    monkeypatch.setattr(maintenance_tasks, "write_index_atomic_snapshot", track_writer)
    runner.write_snapshot = track_writer
    second_runner.write_snapshot = track_writer

    callers_ready = threading.Barrier(2)
    results = []
    errors = []

    def start_in_thread(active_runner):
        try:
            callers_ready.wait(timeout=1)
            results.append(active_runner.start())
        except Exception as exc:  # noqa: BLE001 - propagate thread failures into assertions
            errors.append(exc)

    first = threading.Thread(target=start_in_thread, args=(runner,))
    second = threading.Thread(target=start_in_thread, args=(second_runner,))
    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert len(results) == 2
    for awaitable in scheduled:
        asyncio.run(awaitable)

    assert [task.task_id for task in results] == [results[0].task_id, results[0].task_id]
    assert len(scheduled) == 1
    assert build_calls == [("000300",)]
    assert writer_task_ids == [results[0].task_id]
    assert _snapshot_meta(parquet_store)["task_result_id"] == results[0].task_id


def test_atomic_snapshot_runner_keeps_previous_snapshot_when_final_publish_fails(tmp_path, monkeypatch):
    runner, store, parquet_store = _atomic_runner(
        tmp_path,
        _successful_atomic_builder(),
        monkeypatch,
        write_snapshot=state.write_index_atomic_snapshot,
    )
    _write_previous_snapshot(parquet_store)
    _, _, meta_file = state._index_atomic_snapshot_cache_paths(parquet_store)
    original_replace = Path.replace
    failed = False

    def fail_final_meta_publish(path, target):
        nonlocal failed
        if not failed and Path(target) == meta_file and ".tmp" in path.name:
            failed = True
            raise OSError("final publish failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_final_meta_publish)

    task = runner.start()
    persisted = _wait_for_terminal_task(store, task.task_id)
    result = state.load_index_atomic_snapshot_readonly(
        parquet_store,
        (_atomic_definition().to_index_definition(),),
        coverage=_atomic_coverage(),
    )

    assert persisted.state == "failed"
    assert persisted.error_message == "重建指数原子指标失败：final publish failed"
    assert result.summary["index_code"].tolist() == ["000300"]
    assert _snapshot_meta(parquet_store)["task_result_id"] == 99


def test_render_tasks_restores_persisted_atomic_snapshot_result_after_page_refresh(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=16,
        task_type="index_atomic_snapshot_rebuild",
        state="success",
        progress_done=1,
        progress_total=1,
        progress_detail="000300",
        result_json=json.dumps(
            {
                "total_count": 1,
                "successfully_calculated_count": 1,
                "data_status_counts": {"computed": 1},
                "generated_at": "2026-07-12T10:00:00",
                "snapshot_files": ["index_atomic_snapshot.parquet"],
            }
        ),
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at="2026-07-12 10:01:00",
        updated_at="2026-07-12 10:01:00",
    )
    captured = []

    class FakeHistoryRunner:
        def __init__(self, store, parquet_store):
            del store, parquet_store

        def reconcile_interrupted(self):
            return None

        def latest(self):
            return None

    class FakeAtomicRunner(FakeHistoryRunner):
        def latest(self):
            return run

    class FakeCatalogRunner(FakeHistoryRunner):
        def latest(self, task_type):
            del task_type
            return None

    class FakeStore:
        def list_index_catalog(self, **kwargs):
            del kwargs
            return pd.DataFrame()

    class FakeElement:
        def classes(self, value):
            return self

    class FakeUi:
        def column(self):
            return FakeElement()

        def timer(self, interval, callback, immediate=False):
            del interval, callback, immediate
            return FakeElement()

        def label(self, text):
            return FakeElement()

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance, "IndexHistoryBatchRunner", FakeHistoryRunner)
    monkeypatch.setattr(maintenance, "OfficialIndexValuationMaintenanceRunner", FakeHistoryRunner)
    monkeypatch.setattr(maintenance, "IndexAtomicSnapshotMaintenanceRunner", FakeAtomicRunner)
    monkeypatch.setattr(maintenance, "IndexCatalogMaintenanceRunner", FakeCatalogRunner)
    monkeypatch.setattr(maintenance, "_render_task_center", lambda container, status: captured.append(status))
    monkeypatch.setattr(maintenance, "_render_master_tasks", lambda *args: None)
    monkeypatch.setattr(maintenance, "_render_etf_history_tasks", lambda *args: None)
    monkeypatch.setattr(maintenance, "_render_index_history_tasks", lambda *args: None)
    monkeypatch.setattr(maintenance, "_render_catalog_index_tasks", lambda *args: None)
    monkeypatch.setattr(maintenance, "_render_batch_tasks", lambda *args: None)

    maintenance._render_tasks(object(), FakeStore(), object())

    assert captured[0].title == "重建指数原子指标"
    assert captured[0].state == "success"
    assert captured[0].result == json.loads(run.result_json)


def test_catalog_index_tasks_show_atomic_snapshot_rebuild_help(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    labels = []
    buttons = {}

    class FakeElement:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

        def props(self, value):
            return self

    class FakeUi:
        def expansion(self, title, icon=None):
            return FakeElement()

        def row(self):
            return FakeElement()

        def input(self, label, value=None):
            return FakeElement()

        def button(self, text, icon=None, on_click=None):
            buttons[text] = on_click
            return FakeElement()

        def label(self, text):
            labels.append(text)
            return FakeElement()

    class FakeStore:
        def list_index_catalog(self, *, include_reserve=False):
            del include_reserve
            return pd.DataFrame(columns=["pool"])

        def list_index_history_coverage(self):
            return pd.DataFrame(columns=["completeness_status"])

        def connect(self):
            raise AssertionError("空数据不应读取更新状态")

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance, "_metric", lambda *args: None)

    maintenance._render_catalog_index_tasks(
        FakeStore(),
        object(),
        object(),
        maintenance.MaintenanceTaskStatus(),
        object(),
        object(),
        object(),
    )

    assert "重建指数原子指标" in buttons
    assert "只读取本地指数历史；初始化、补齐或修复历史后，请手动重建。" in labels


def test_catalog_panel_exposes_explicit_official_valuation_sync():
    from etf_trading.nicegui_app.pages import maintenance

    source = inspect.getsource(maintenance._render_catalog_index_tasks)

    assert '"同步官方指数估值"' in source
    assert "_start_official_index_valuation_sync_task" in source


def test_task_center_renders_idle_and_running_states(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def __enter__(self):
            events.append("enter_center")
            return self

        def __exit__(self, *args):
            events.append("exit_center")
            return None

    class FakeElement:
        def __enter__(self):
            events.append("enter_element")
            return self

        def __exit__(self, *args):
            events.append("exit_element")
            return None

        def classes(self, value):
            events.append(f"classes:{value}")
            return self

    class FakeUi:
        def row(self):
            events.append("row")
            return FakeElement()

        def column(self):
            events.append("column")
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def icon(self, name):
            events.append(f"icon:{name}")
            return FakeElement()

    monkeypatch.setattr(maintenance, "ui", FakeUi())

    maintenance._render_task_center(FakeContainer(), maintenance.MaintenanceTaskStatus())
    maintenance._render_task_center(
        FakeContainer(),
        maintenance.MaintenanceTaskStatus(
            title="补齐全部指数历史",
            state="running",
            message="正在执行，请稍候...",
            started_at=datetime(2026, 7, 8, 22, 30, 0),
        ),
    )

    assert "label:任务中心" in events
    assert "badge:空闲" in events
    assert "label:暂无任务" in events
    assert "badge:运行中" in events
    assert "label:补齐全部指数历史" in events
    assert "label:正在执行，请稍候..." in events
    assert "label:开始 2026-07-08 22:30:00" in events


def test_task_center_renders_running_progress(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeElement:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

        def props(self, value):
            return self

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def icon(self, name):
            return FakeElement()

        def linear_progress(self, value=0):
            events.append(f"progress:{value:.2f}")
            return FakeElement()

    monkeypatch.setattr(maintenance, "ui", FakeUi())

    maintenance._render_task_center(
        FakeContainer(),
        maintenance.MaintenanceTaskStatus(
            title="补齐全部ETF历史",
            state="running",
            message="补齐全部ETF历史正在执行，请稍候...",
            progress_done=2,
            progress_total=5,
            progress_detail="512880 INITIALIZED",
        ),
    )

    assert "progress:0.40" in events
    assert "label:2/5 · 512880 INITIALIZED" in events


def test_etf_history_tasks_include_resumable_all_etf_button(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []
    buttons = {}

    class FakeElement:
        value = None

        def __init__(self, value=None):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

        def props(self, value):
            return self

    class FakeUi:
        def expansion(self, title, icon=None):
            events.append(f"expansion:{title}:{icon}")
            return FakeElement()

        def row(self):
            return FakeElement()

        def select(self, options, value=None, label=None):
            return FakeElement(value)

        def input(self, label, value=None):
            return FakeElement(value)

        def button(self, text, icon=None, on_click=None):
            events.append(f"button:{text}:{icon}")
            buttons[text] = on_click
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

    class FakeService:
        def __init__(self):
            self.calls = []

        def fetch_and_store_history(self, *args, **kwargs):
            return pd.DataFrame()

        def ensure_all_etf_history(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            kwargs["on_progress"](
                maintenance.EtfHistoryProgressView(done=1, total=2, etf_code="510300", status="SKIPPED")
            )
            return pd.DataFrame(
                [
                    {"etf_code": "510300", "status": "SKIPPED"},
                    {"etf_code": "512880", "status": "INITIALIZED"},
                ]
            )

    fake_service = FakeService()
    captured = {}

    def fake_run_task(button, task_center, task_status, title, action, success_message):
        result = action()
        captured["title"] = title
        captured["message"] = success_message(result)
        captured["progress_done"] = task_status.progress_done
        captured["progress_total"] = task_status.progress_total
        return result

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance, "etf_overview_rows", lambda snapshot: [{"ETF代码": "510300", "ETF名称": "Fresh ETF"}])
    monkeypatch.setattr(maintenance, "_service_with_provider", lambda store, parquet_store: fake_service)
    monkeypatch.setattr(maintenance, "_run_task", fake_run_task)

    task_status = maintenance.MaintenanceTaskStatus()
    maintenance._render_etf_history_tasks(object(), object(), object(), FakeElement(), task_status)
    buttons["一键初始化/补齐全部ETF"]()

    assert "button:一键初始化/补齐全部ETF:sync" in events
    assert captured["title"] == "补齐全部ETF历史"
    assert captured["message"] == "已检查 2 只 ETF：补齐 1，跳过 1，失败 0"
    assert captured["progress_done"] == 1
    assert captured["progress_total"] == 2
    args, kwargs = fake_service.calls[0]
    assert kwargs["refresh_master"] is True
    assert kwargs["sleep_seconds"] == 0.15


def test_etf_history_tasks_do_not_render_full_master_as_select_options(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []

    class FakeElement:
        def __init__(self, value=None):
            self.value = value

        def classes(self, text):
            events.append(f"classes:{text}")
            return self

        def props(self, text):
            events.append(f"props:{text}")
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeUi:
        def expansion(self, title, icon=None):
            events.append(f"expansion:{title}:{icon}")
            return FakeElement()

        def row(self):
            return FakeElement()

        def input(self, label, value=None):
            events.append(f"input:{label}:{value}")
            return FakeElement(value)

        def select(self, *args, **kwargs):
            pytest.fail("ETF history tasks must not render the full ETF master as a select")

        def button(self, text, icon=None, on_click=None):
            events.append(f"button:{text}:{icon}")
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

    rows = [{"ETF代码": f"{510000 + index:06d}", "ETF名称": f"测试ETF{index}"} for index in range(1500)]
    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance, "etf_overview_rows", lambda snapshot: rows)

    maintenance._render_etf_history_tasks(object(), object(), object(), FakeElement(), maintenance.MaintenanceTaskStatus())

    assert any(event.startswith("input:ETF") for event in events)


def test_task_result_preview_is_capped_on_maintenance_page(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    captured_rows: list[list[dict[str, object]]] = []
    labels: list[str] = []

    class FakeElement:
        def classes(self, text):
            return self

    class FakeUi:
        def label(self, text):
            labels.append(str(text))
            return FakeElement()

    def fake_render_table(rows, **kwargs):
        del kwargs
        captured_rows.append(rows)
        return FakeElement()

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance, "render_table", fake_render_table)

    maintenance._render_task_result([{"序号": index} for index in range(80)])

    assert len(captured_rows[0]) == maintenance.TASK_RESULT_PREVIEW_LIMIT
    assert any("仅展示前" in label for label in labels)


def test_maintenance_task_center_updates_before_io_bound_work(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    assert inspect.iscoroutinefunction(maintenance._run_task)

    events: list[str] = []
    io_bound_entered = False

    class FakeButton:
        def disable(self):
            events.append("disable")

        def enable(self):
            events.append("enable")

        def update(self):
            events.append("button_update")

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def update(self):
            events.append("center_update")

        def __enter__(self):
            events.append("enter_center")
            return self

        def __exit__(self, *args):
            events.append("exit_center")
            return None

    class FakeElement:
        def __enter__(self):
            events.append("enter_element")
            return self

        def __exit__(self, *args):
            events.append("exit_element")
            return None

        def classes(self, value):
            return self

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def icon(self, name):
            events.append(f"icon:{name}")
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def table(self, columns, rows, pagination=None):
            events.append("table")
            return FakeElement()

        def notify(self, message, type=None):
            events.append(f"notify:{type}:{message}")

    async def fake_io_bound(callback):
        nonlocal io_bound_entered
        events.append("io_bound")
        io_bound_entered = True
        return callback()

    def action():
        assert io_bound_entered
        events.append("action")
        return [{"index_code": "000300"}]

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance.run, "io_bound", fake_io_bound)
    monkeypatch.setattr(maintenance, "invalidate_snapshot_cache", lambda: events.append("invalidate"))

    task_status = maintenance.MaintenanceTaskStatus()
    asyncio.run(
        maintenance._run_task(
            FakeButton(),
            FakeContainer(),
            task_status,
            "补齐全部指数历史",
            action,
            lambda result: f"已检查 {len(result)} 个指数",
        )
    )

    io_bound_position = events.index("io_bound")
    assert events.index("disable") < io_bound_position
    assert events.index("badge:运行中") < io_bound_position
    assert events.index("label:补齐全部指数历史") < io_bound_position
    assert events.index("label:补齐全部指数历史正在执行，请稍候...") < io_bound_position
    assert events.index("notify:info:补齐全部指数历史正在执行，请稍候...") < io_bound_position
    assert events.index("button_update") < io_bound_position
    assert events.index("center_update") < io_bound_position
    assert "notify:positive:已检查 1 个指数" in events
    assert "badge:成功" in events
    assert "table" in events
    assert task_status.state == "success"
    assert task_status.result == [{"index_code": "000300"}]
    assert events[-1] == "enable"


def test_maintenance_task_center_shows_failure(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []

    class FakeButton:
        def disable(self):
            events.append("disable")

        def enable(self):
            events.append("enable")

        def update(self):
            events.append("button_update")

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def update(self):
            events.append("center_update")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeElement:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def icon(self, name):
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def notify(self, message, type=None):
            events.append(f"notify:{type}:{message}")

    async def fake_io_bound(callback):
        return callback()

    def action():
        raise RuntimeError("provider timeout")

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance.run, "io_bound", fake_io_bound)

    task_status = maintenance.MaintenanceTaskStatus()
    asyncio.run(
        maintenance._run_task(
            FakeButton(),
            FakeContainer(),
            task_status,
            "拉取指数历史",
            action,
            lambda result: "不会执行",
        )
    )

    assert "badge:失败" in events
    assert "label:拉取指数历史失败：provider timeout" in events
    assert "notify:negative:拉取指数历史失败：provider timeout" in events
    assert task_status.state == "failed"
    assert task_status.error == "provider timeout"
    assert events[-1] == "enable"


def test_maintenance_task_center_shows_cancelled_when_result_is_none(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []

    class FakeButton:
        def disable(self):
            events.append("disable")

        def enable(self):
            events.append("enable")

        def update(self):
            events.append("button_update")

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def update(self):
            events.append("center_update")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeElement:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def icon(self, name):
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def notify(self, message, type=None):
            events.append(f"notify:{type}:{message}")

    async def fake_io_bound(callback):
        return callback()

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance.run, "io_bound", fake_io_bound)

    task_status = maintenance.MaintenanceTaskStatus()
    asyncio.run(
        maintenance._run_task(
            FakeButton(),
            FakeContainer(),
            task_status,
            "补齐全部指数历史",
            lambda: None,
            lambda result: "不会执行",
        )
    )

    assert "badge:取消" in events
    assert "label:补齐全部指数历史已取消或服务正在关闭" in events
    assert "notify:warning:补齐全部指数历史已取消或服务正在关闭" in events
    assert task_status.state == "cancelled"
    assert events[-1] == "enable"


def test_task_status_from_persisted_running_run_shows_chinese_progress():
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=7,
        task_type="index_history_batch",
        state="running",
        progress_done=11,
        progress_total=49,
        progress_detail="930633 STALE",
        result_json=None,
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at=None,
        updated_at="2026-07-12 10:01:00",
    )

    status = maintenance._task_status_from_run(run)

    assert status.title == "补齐全部指数历史"
    assert status.state == "running"
    assert status.progress_done == 11
    assert status.progress_total == 49
    assert status.progress_detail == "930633 行情仍滞后"
    assert status.started_at == datetime(2026, 7, 12, 10, 0, 0)


def test_task_status_from_run_preserves_provider_fallback_warning():
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=1,
        task_type="index_history_batch",
        state="warning",
        progress_done=1,
        progress_total=1,
        progress_detail="",
        result_json="[]",
        error_message="Tushare 异常后已使用 AkShare：1 次",
        started_at="2026-07-19 10:00:00",
        finished_at="2026-07-19 10:01:00",
        updated_at="2026-07-19 10:01:00",
    )

    status = maintenance._task_status_from_run(run)

    assert status.state == "warning"
    assert status.error == "Tushare 异常后已使用 AkShare：1 次"
    assert maintenance._task_state_label("warning") == "已完成（已回退）"
    assert maintenance._task_state_tone("warning") == "warning"


def test_persisted_baseline_evidence_task_uses_the_dedicated_chinese_title():
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=16,
        task_type="index_baseline_evidence",
        state="success",
        progress_done=1,
        progress_total=1,
        progress_detail="",
        result_json='[{"index_code":"000300","evidence_status":"OFFICIAL","completeness_status":"COMPLETE"}]',
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at="2026-07-12 10:01:00",
        updated_at="2026-07-12 10:01:00",
    )

    status = maintenance._task_status_from_run(run)

    assert status.title == "核验指数历史起点证据"


def test_index_history_batch_message_distinguishes_stale_from_success():
    from etf_trading.nicegui_app.pages import maintenance

    message = maintenance._index_history_batch_message(
        [
            {"index_code": "000300", "status": "UPDATED"},
            {"index_code": "000905", "status": "INITIALIZED"},
            {"index_code": "930633", "status": "STALE"},
            {"index_code": "H30533", "status": "FAILED"},
            {"index_code": "HSI", "status": "SKIPPED"},
        ]
    )

    assert message == "已检查 5 个指数：补齐 2，跳过 1，行情仍滞后 1，失败/无数据 1"


def test_persisted_history_repair_task_uses_chinese_incomplete_history_summary():
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=12,
        task_type="index_history_repair",
        state="success",
        progress_done=1,
        progress_total=1,
        progress_detail="801010 REPAIRED",
        result_json='[{"index_code":"801010","status":"REPAIRED","completeness_status":"INCOMPLETE"}]',
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at="2026-07-12 10:01:00",
        updated_at="2026-07-12 10:01:00",
    )

    status = maintenance._task_status_from_run(run)

    assert status.title == "仅补历史不完整"
    assert status.message == "已检查 1 个指数：历史不完整 1"
    assert status.progress_detail == "801010 已修复"


def test_persisted_legacy_index_history_result_upgrades_baseline_explanation():
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=13,
        task_type="index_history_batch",
        state="success",
        progress_done=1,
        progress_total=1,
        progress_detail="000300 UPDATED",
        result_json=(
            '[{"index_code":"000300","status":"UPDATED","start_date":"1990-12-19",'
            '"end_date":"2026-07-10","completeness_status":"BASELINE_UNVERIFIED",'
            '"completeness_message":"基日待核验，不能判定历史完整"}]'
        ),
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at="2026-07-12 10:01:00",
        updated_at="2026-07-12 10:01:00",
    )

    status = maintenance._task_status_from_run(run)

    assert status.result[0]["completeness_message"] == (
        "已有 1990-12-19 至 2026-07-10 的行情，但缺少官方基日；"
        "暂时无法判断是否从指数起点完整，不作为交易依据。"
    )


def test_legacy_index_history_upgrade_loads_default_catalog_once(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    calls = []

    def fake_default_index_catalog():
        calls.append("load")
        return (
            IndexCatalogEntry(
                index_code="000300",
                name="沪深300",
                market="A股",
                category_level_1="A股",
                category_level_2="宽基",
                index_type="宽基",
                pool="core",
                index_base_date="2004-12-31",
                baseline_source="official",
                source_kind="csi",
                provider_symbol="000300",
            ),
        )

    cache_factory = getattr(maintenance, "_default_index_source_kind_by_code", None)
    if cache_factory is not None:
        cache_factory.cache_clear()
    monkeypatch.setattr(maintenance, "default_index_catalog", fake_default_index_catalog)

    try:
        maintenance._upgrade_legacy_index_history_result(
            [
                {"index_code": "000300", "status": "UPDATED", "completeness_status": "COMPLETE"},
                {"index_code": "000300", "status": "SKIPPED", "completeness_status": "COMPLETE"},
                {"index_code": "000300", "status": "STALE", "completeness_status": "BASELINE_UNVERIFIED"},
            ]
        )

        assert calls == ["load"]
    finally:
        if cache_factory is not None:
            cache_factory.cache_clear()


def test_persisted_legacy_stale_result_upgrades_technical_gap_message():
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=14,
        task_type="index_history_batch",
        state="success",
        progress_done=1,
        progress_total=1,
        progress_detail="000300 STALE",
        result_json=(
            '[{"index_code":"000300","status":"STALE",'
            '"error_message":"本地最新交易日 2026-07-09，未达到目标交易日 2026-07-10"}]'
        ),
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at="2026-07-12 10:01:00",
        updated_at="2026-07-12 10:01:00",
    )

    status = maintenance._task_status_from_run(run)

    assert status.result[0]["error_message"] == "已更新至 2026-07-09，缺少 2026-07-10 行情。"


def test_persisted_legacy_empty_result_names_default_source_and_index_code():
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=15,
        task_type="index_history_batch",
        state="success",
        progress_done=1,
        progress_total=1,
        progress_detail="H30533 EMPTY",
        result_json=(
            '[{"index_code":"H30533","status":"EMPTY","completeness_status":"MISSING_HISTORY",'
            '"completeness_message":"历史数据缺失"}]'
        ),
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at="2026-07-12 10:01:00",
        updated_at="2026-07-12 10:01:00",
    )

    status = maintenance._task_status_from_run(run)

    assert status.result[0]["error_message"] == "港股数据源未返回 H30533 的历史行情。"
    assert status.result[0]["completeness_message"] == "港股数据源未返回 H30533 的历史行情。"


def test_render_tasks_restores_persisted_index_batch_after_page_refresh(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=7,
        task_type="index_history_batch",
        state="running",
        progress_done=11,
        progress_total=49,
        progress_detail="930633 STALE",
        result_json=None,
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at=None,
        updated_at="2026-07-12 10:01:00",
    )
    captured = []

    class FakeRunner:
        def __init__(self, store, parquet_store):
            self.store = store

        def reconcile_interrupted(self):
            return None

        def latest(self):
            return run

    class FakeElement:
        def classes(self, value):
            return self

    class FakeUi:
        def column(self):
            return FakeElement()

        def timer(self, interval, callback, immediate=False):
            return FakeElement()

        def label(self, text):
            return FakeElement()

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance, "IndexHistoryBatchRunner", FakeRunner)
    monkeypatch.setattr(maintenance, "OfficialIndexValuationMaintenanceRunner", FakeRunner)
    monkeypatch.setattr(maintenance, "_render_task_center", lambda container, status: captured.append(status))
    monkeypatch.setattr(maintenance, "_render_master_tasks", lambda *args: None)
    monkeypatch.setattr(maintenance, "_render_etf_history_tasks", lambda *args: None)
    monkeypatch.setattr(maintenance, "_render_index_history_tasks", lambda *args: None)
    monkeypatch.setattr(maintenance, "_render_batch_tasks", lambda *args: None)

    maintenance._render_tasks(object(), object(), object())

    assert captured[0].state == "running"
    assert captured[0].progress_done == 11
    assert captured[0].progress_detail == "930633 行情仍滞后"


def test_start_persisted_index_history_batch_uses_runner_result(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events = []
    run = MaintenanceTaskRun(
        task_id=8,
        task_type="index_history_batch",
        state="running",
        progress_done=0,
        progress_total=49,
        progress_detail="",
        result_json=None,
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at=None,
        updated_at="2026-07-12 10:00:00",
    )

    class FakeRunner:
        def __init__(self):
            self.calls = []

        def start(self, through):
            self.calls.append(through)
            return run

    class FakeContainer:
        def clear(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeElement:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

        def props(self, value):
            return self

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def icon(self, name):
            return FakeElement()

        def badge(self, text):
            return FakeElement()

        def label(self, text):
            return FakeElement()

        def linear_progress(self, value=0):
            return FakeElement()

        def notify(self, message, type=None):
            events.append((message, type))

    runner = FakeRunner()
    task_status = maintenance.MaintenanceTaskStatus()
    monkeypatch.setattr(maintenance, "ui", FakeUi())

    maintenance._start_persisted_index_history_batch(runner, "2026-07-10", FakeContainer(), task_status)

    assert runner.calls == ["2026-07-10"]
    assert task_status.title == "补齐全部指数历史"
    assert task_status.state == "running"
    assert events == [("补齐全部指数历史正在执行，请稍候...", "info")]


def test_persisted_index_timer_does_not_replace_another_active_task(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    run = MaintenanceTaskRun(
        task_id=9,
        task_type="index_history_batch",
        state="success",
        progress_done=49,
        progress_total=49,
        progress_detail="H30533 STALE",
        result_json="[]",
        error_message=None,
        started_at="2026-07-12 10:00:00",
        finished_at="2026-07-12 10:05:00",
        updated_at="2026-07-12 10:05:00",
    )
    callbacks = []
    captured = []

    class FakeRunner:
        def __init__(self, store, parquet_store):
            return None

        def reconcile_interrupted(self):
            return None

        def latest(self):
            return run

    class FakeElement:
        def classes(self, value):
            return self

    class FakeUi:
        def column(self):
            return FakeElement()

        def timer(self, interval, callback, immediate=False):
            callbacks.append(callback)
            return FakeElement()

        def label(self, text):
            return FakeElement()

    active_task = maintenance.MaintenanceTaskStatus(
        state="running",
        title="active-etf-task",
        message="working",
    )
    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance, "IndexHistoryBatchRunner", FakeRunner)
    monkeypatch.setattr(maintenance, "OfficialIndexValuationMaintenanceRunner", FakeRunner)
    monkeypatch.setattr(maintenance, "_render_task_center", lambda container, status: captured.append(status.title))
    monkeypatch.setattr(maintenance, "_render_master_tasks", lambda *args: None)
    def render_active_etf_task(*args):
        args[4].__dict__.update(active_task.__dict__)
        maintenance._render_task_center(args[3], args[4])

    monkeypatch.setattr(maintenance, "_render_etf_history_tasks", render_active_etf_task)
    monkeypatch.setattr(maintenance, "_render_index_history_tasks", lambda *args: None)
    monkeypatch.setattr(maintenance, "_render_batch_tasks", lambda *args: None)

    maintenance._render_tasks(object(), object(), object())
    callbacks[0]()

    assert captured[-1] == "active-etf-task"
