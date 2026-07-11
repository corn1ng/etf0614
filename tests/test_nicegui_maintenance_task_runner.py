import asyncio
import json

import pandas as pd

from etf_trading.data.initialization import IndexHistoryProgress
from etf_trading.data.storage import ParquetStore, SQLiteStore


class _FakeIndexHistoryService:
    def ensure_all_index_history(self, through, *, on_progress):
        on_progress(IndexHistoryProgress(done=1, total=2, index_code="000300", status="UPDATED"))
        on_progress(IndexHistoryProgress(done=2, total=2, index_code="000905", status="STALE"))
        return pd.DataFrame(
            [
                {"index_code": "000300", "status": "UPDATED"},
                {"index_code": "000905", "status": "STALE"},
            ]
        )


def test_index_history_batch_runner_deduplicates_running_task_and_persists_progress(monkeypatch, tmp_path):
    from etf_trading.nicegui_app import maintenance_tasks

    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    scheduled = []

    def fake_create(awaitable, **kwargs):
        scheduled.append((awaitable, kwargs))
        awaitable.close()

    monkeypatch.setattr(maintenance_tasks.background_tasks, "create", fake_create)
    runner = maintenance_tasks.IndexHistoryBatchRunner(store, ParquetStore(tmp_path / "parquet"))

    first = runner.start("2026-07-10")
    second = runner.start("2026-07-10")

    assert first.task_id == second.task_id
    assert len(scheduled) == 1
    assert store.get_maintenance_task_run(first.task_id).state == "running"


def test_index_history_batch_runner_persists_background_result(monkeypatch, tmp_path):
    from etf_trading.nicegui_app import maintenance_tasks

    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    invalidations = []
    runner = maintenance_tasks.IndexHistoryBatchRunner(
        store,
        ParquetStore(tmp_path / "parquet"),
        service_factory=lambda: _FakeIndexHistoryService(),
    )
    task = store.create_maintenance_task_run("index_history_batch", progress_total=2)

    async def fake_io_bound(callback):
        return callback()

    monkeypatch.setattr(maintenance_tasks.run, "io_bound", fake_io_bound)
    monkeypatch.setattr(
        maintenance_tasks,
        "invalidate_snapshot_cache",
        lambda cache_store, cache_parquet_store: invalidations.append((cache_store, cache_parquet_store)),
    )
    asyncio.run(runner._run(task.task_id, "2026-07-10"))

    persisted = store.get_maintenance_task_run(task.task_id)
    assert persisted is not None
    assert persisted.state == "success"
    assert persisted.progress_done == 2
    assert persisted.progress_total == 2
    assert persisted.progress_detail == "000905 STALE"
    assert json.loads(persisted.result_json) == [
        {"index_code": "000300", "status": "UPDATED"},
        {"index_code": "000905", "status": "STALE"},
    ]
    assert invalidations == [(store, runner.parquet_store)]


def test_index_history_batch_runner_marks_orphaned_running_task_interrupted(tmp_path):
    from etf_trading.nicegui_app import maintenance_tasks

    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    task = store.create_maintenance_task_run("index_history_batch", progress_total=49)
    runner = maintenance_tasks.IndexHistoryBatchRunner(store, ParquetStore(tmp_path / "parquet"))

    reconciled = runner.reconcile_interrupted()

    assert reconciled is not None
    assert reconciled.task_id == task.task_id
    assert reconciled.state == "interrupted"
    assert reconciled.error_message == "服务器已重启，任务未继续执行"
