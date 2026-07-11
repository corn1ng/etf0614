"""Server-side coordinators for durable data-maintenance tasks."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
from nicegui import background_tasks, run

from etf_trading.data.initialization import IndexHistoryProgress, InitializationService
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.data.storage import MaintenanceTaskRun, ParquetStore, SQLiteStore


INDEX_HISTORY_BATCH_TASK_TYPE = "index_history_batch"
_ACTIVE_INDEX_TASK_KEYS: set[tuple[str, int]] = set()


class IndexHistoryBatchRunner:
    """Run one index-history batch independently from an individual page session."""

    def __init__(
        self,
        store: SQLiteStore,
        parquet_store: ParquetStore,
        *,
        service_factory: Callable[[], InitializationService] | None = None,
    ) -> None:
        self.store = store
        self.parquet_store = parquet_store
        self.service_factory = service_factory or self._default_service

    def start(self, through: str) -> MaintenanceTaskRun:
        self.reconcile_interrupted()
        running = self.store.get_running_maintenance_task_run(INDEX_HISTORY_BATCH_TASK_TYPE)
        if running is not None:
            return running

        task = self.store.create_maintenance_task_run(INDEX_HISTORY_BATCH_TASK_TYPE, progress_total=49)
        key = self._task_key(task.task_id)
        _ACTIVE_INDEX_TASK_KEYS.add(key)
        try:
            background_tasks.create(self._run(task.task_id, through), name=f"index-history-{task.task_id}")
        except Exception as exc:
            _ACTIVE_INDEX_TASK_KEYS.discard(key)
            self.store.update_maintenance_task_run(task.task_id, state="failed", error_message=str(exc))
            raise
        return task

    def latest(self) -> MaintenanceTaskRun | None:
        self.reconcile_interrupted()
        return self.store.get_latest_maintenance_task_run(INDEX_HISTORY_BATCH_TASK_TYPE)

    def reconcile_interrupted(self) -> MaintenanceTaskRun | None:
        running = self.store.get_running_maintenance_task_run(INDEX_HISTORY_BATCH_TASK_TYPE)
        if running is None or self._task_key(running.task_id) in _ACTIVE_INDEX_TASK_KEYS:
            return None
        return self.store.mark_maintenance_task_interrupted(running.task_id, "服务器已重启，任务未继续执行")

    async def _run(self, task_id: int, through: str) -> None:
        try:
            def on_progress(progress: IndexHistoryProgress) -> None:
                self.store.update_maintenance_task_run(
                    task_id,
                    progress_done=progress.done,
                    progress_total=progress.total,
                    progress_detail=f"{progress.index_code} {progress.status}",
                )

            def action() -> pd.DataFrame:
                return self.service_factory().ensure_all_index_history(through, on_progress=on_progress)

            result = await run.io_bound(action)
            result_json = result.to_json(orient="records", date_format="iso")
            task = self.store.get_maintenance_task_run(task_id)
            self.store.update_maintenance_task_run(
                task_id,
                state="success",
                progress_done=len(result),
                progress_total=max(task.progress_total if task is not None else 0, len(result)),
                result_json=result_json,
            )
        except Exception as exc:  # noqa: BLE001 - persist the provider/storage failure for the next page session
            self.store.update_maintenance_task_run(task_id, state="failed", error_message=str(exc))
        finally:
            _ACTIVE_INDEX_TASK_KEYS.discard(self._task_key(task_id))

    def _default_service(self) -> InitializationService:
        return InitializationService(self.store, provider=AkShareProvider(), parquet_store=self.parquet_store)

    def _task_key(self, task_id: int) -> tuple[str, int]:
        return (str(Path(self.store.db_path).resolve()), task_id)
