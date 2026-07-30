import asyncio
import json

import pandas as pd

from etf_trading.data.initialization import IndexHistoryProgress
from etf_trading.data.index_valuation_service import OfficialIndexValuationProgress
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


class _FakeCatalogMaintenanceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def ensure_all_index_history(self, through, *, index_codes=None, repair_history=False, on_progress=None):
        self.calls.append(("history", {"through": through, "index_codes": index_codes, "repair_history": repair_history}))
        if on_progress is not None:
            on_progress(IndexHistoryProgress(done=1, total=1, index_code="801010", status="REPAIRED"))
        return pd.DataFrame(
            [
                {
                    "index_code": "801010",
                    "status": "REPAIRED",
                    "completeness_status": "INCOMPLETE",
                    "completeness_message": "历史不完整",
                }
            ]
        )


    def verify_index_baseline_evidence(self, through):
        self.calls.append(("baseline_evidence", {"through": through}))
        return pd.DataFrame(
            [{"index_code": "000300", "evidence_status": "OFFICIAL", "completeness_status": "COMPLETE"}]
        )


class _FakeOfficialValuationSyncService:
    def sync_all(self, through, on_progress=None):
        if on_progress is not None:
            on_progress(OfficialIndexValuationProgress(1, 1, "000300", "UPDATED"))
        return pd.DataFrame(
            [
                {
                    "index_code": "000300",
                    "status": "UPDATED",
                    "fetched_rows": 1,
                    "message": "写入 1 行估值",
                }
            ]
        )

def test_catalog_maintenance_runner_persists_history_incomplete_result(monkeypatch, tmp_path):
    from etf_trading.nicegui_app import maintenance_tasks

    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    service = _FakeCatalogMaintenanceService()
    runner = maintenance_tasks.IndexCatalogMaintenanceRunner(
        store,
        ParquetStore(tmp_path / "parquet"),
        service_factory=lambda: service,
    )
    task = store.create_maintenance_task_run("index_history_repair", progress_total=1)

    async def fake_io_bound(callback):
        return callback()

    monkeypatch.setattr(maintenance_tasks.run, "io_bound", fake_io_bound)
    asyncio.run(runner._run(task.task_id, "index_history_repair", "2026-07-10"))

    persisted = store.get_maintenance_task_run(task.task_id)
    assert persisted is not None
    assert persisted.state == "success"
    assert "INCOMPLETE" in str(persisted.result_json)
    assert service.calls == [
        ("history", {"through": "2026-07-10", "index_codes": [], "repair_history": True})
    ]


def test_catalog_maintenance_runner_verifies_baseline_evidence_without_history_download(monkeypatch, tmp_path):
    from etf_trading.nicegui_app import maintenance_tasks

    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    service = _FakeCatalogMaintenanceService()
    runner = maintenance_tasks.IndexCatalogMaintenanceRunner(
        store,
        ParquetStore(tmp_path / "parquet"),
        service_factory=lambda: service,
    )
    task = store.create_maintenance_task_run("index_baseline_evidence", progress_total=1)

    async def fake_io_bound(callback):
        return callback()

    monkeypatch.setattr(maintenance_tasks.run, "io_bound", fake_io_bound)
    asyncio.run(runner._run(task.task_id, "index_baseline_evidence", "2026-07-10"))

    persisted = store.get_maintenance_task_run(task.task_id)
    assert maintenance_tasks.INDEX_MAINTENANCE_TASK_TYPES["index_baseline_evidence"] == "核验指数历史起点证据"
    assert persisted is not None
    assert persisted.state == "success"
    assert json.loads(persisted.result_json) == [
        {"index_code": "000300", "evidence_status": "OFFICIAL", "completeness_status": "COMPLETE"}
    ]
    assert service.calls == [("baseline_evidence", {"through": "2026-07-10"})]


def test_official_valuation_runner_persists_progress_and_result(monkeypatch, tmp_path):
    from etf_trading.nicegui_app import maintenance_tasks

    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    runner = maintenance_tasks.OfficialIndexValuationMaintenanceRunner(
        store,
        ParquetStore(tmp_path / "parquet"),
        service_factory=_FakeOfficialValuationSyncService,
    )

    async def run_inline(callback):
        return callback()

    monkeypatch.setattr(maintenance_tasks.run, "io_bound", run_inline)
    task = store.create_maintenance_task_run("official_index_valuation_sync", progress_total=6)

    asyncio.run(runner._run(task.task_id, "2026-07-29"))

    persisted = store.get_maintenance_task_run(task.task_id)
    assert persisted is not None
    assert persisted.state == "success"
    assert persisted.progress_done == 1
    assert persisted.progress_total == 1
    assert persisted.progress_detail == "000300 UPDATED"
    assert json.loads(persisted.result_json) == [
        {"index_code": "000300", "status": "UPDATED", "fetched_rows": 1, "message": "写入 1 行估值"}
    ]


def test_official_valuation_runner_marks_orphaned_running_task_interrupted(tmp_path):
    from etf_trading.nicegui_app import maintenance_tasks

    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    task = store.create_maintenance_task_run("official_index_valuation_sync", progress_total=6)
    runner = maintenance_tasks.OfficialIndexValuationMaintenanceRunner(store, ParquetStore(tmp_path / "parquet"))

    reconciled = runner.reconcile_interrupted()

    assert reconciled is not None
    assert reconciled.task_id == task.task_id
    assert reconciled.state == "interrupted"


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
