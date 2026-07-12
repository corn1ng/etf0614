"""Server-side coordinators for durable data-maintenance tasks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
import json
from threading import RLock

import pandas as pd
from nicegui import background_tasks, run

from etf_trading.data.initialization import IndexHistoryProgress, InitializationService
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.data.storage import MaintenanceTaskRun, ParquetStore, SQLiteStore
from etf_trading.nicegui_app.state import (
    _index_atomic_snapshot_source_signature,
    index_atomic_snapshot_inputs,
    invalidate_snapshot_cache,
    write_index_atomic_snapshot,
)
from etf_trading.research.index_health_snapshot import IndexAtomicSnapshotProgress, build_index_atomic_snapshot


INDEX_HISTORY_BATCH_TASK_TYPE = "index_history_batch"
_ACTIVE_INDEX_TASK_KEYS: set[tuple[str, int]] = set()
INDEX_ATOMIC_SNAPSHOT_REBUILD_TASK_TYPE = "index_atomic_snapshot_rebuild"
_ACTIVE_INDEX_ATOMIC_SNAPSHOT_TASK_KEYS: set[tuple[str, int]] = set()
_INDEX_ATOMIC_SNAPSHOT_START_LOCK = RLock()
INDEX_MAINTENANCE_TASK_TYPES = {
    "index_catalog_sync": "同步指数目录",
    "index_source_validation": "验证指数数据源",
    "index_history_full": "补齐全部指数历史",
    "index_history_repair": "仅补历史不完整",
    "index_history_incremental": "仅更新最新行情",
}
_ACTIVE_CATALOG_TASK_KEYS: set[tuple[str, str, int]] = set()


class IndexCatalogMaintenanceRunner:
    """Run durable catalogue operations independently from the page session."""

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

    def start(self, task_type: str, *, through: str) -> MaintenanceTaskRun:
        if task_type not in INDEX_MAINTENANCE_TASK_TYPES:
            raise ValueError(f"unsupported index maintenance task: {task_type}")
        self.reconcile_interrupted(task_type)
        running = self.store.get_running_maintenance_task_run(task_type)
        if running is not None:
            return running

        task = self.store.create_maintenance_task_run(task_type, progress_total=self._progress_total(task_type))
        key = self._task_key(task_type, task.task_id)
        _ACTIVE_CATALOG_TASK_KEYS.add(key)
        try:
            background_tasks.create(self._run(task.task_id, task_type, through), name=f"{task_type}-{task.task_id}")
        except Exception as exc:
            _ACTIVE_CATALOG_TASK_KEYS.discard(key)
            self.store.update_maintenance_task_run(task.task_id, state="failed", error_message=str(exc))
            raise
        return task

    def latest(self, task_type: str) -> MaintenanceTaskRun | None:
        self.reconcile_interrupted(task_type)
        return self.store.get_latest_maintenance_task_run(task_type)

    def reconcile_interrupted(self, task_type: str) -> MaintenanceTaskRun | None:
        running = self.store.get_running_maintenance_task_run(task_type)
        if running is None or self._task_key(task_type, running.task_id) in _ACTIVE_CATALOG_TASK_KEYS:
            return None
        return self.store.mark_maintenance_task_interrupted(running.task_id, "服务器已重启，任务未继续执行")

    async def _run(self, task_id: int, task_type: str, through: str) -> None:
        try:
            def on_progress(progress: IndexHistoryProgress) -> None:
                self.store.update_maintenance_task_run(
                    task_id,
                    progress_done=progress.done,
                    progress_total=progress.total,
                    progress_detail=f"{progress.index_code} {progress.status}",
                )

            def action() -> pd.DataFrame:
                service = self.service_factory()
                if task_type == "index_catalog_sync":
                    return service.sync_index_catalog()
                if task_type == "index_source_validation":
                    return service.validate_index_sources(through)
                if task_type == "index_history_full":
                    return service.ensure_all_index_history(through, repair_history=True, on_progress=on_progress)
                if task_type == "index_history_repair":
                    return service.ensure_all_index_history(
                        through,
                        index_codes=self._repair_index_codes(),
                        repair_history=True,
                        on_progress=on_progress,
                    )
                return service.ensure_all_index_history(through, repair_history=False, on_progress=on_progress)

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
            invalidate_snapshot_cache(self.store, self.parquet_store)
        except Exception as exc:  # noqa: BLE001 - persist failures for recovery after a page reload
            self.store.update_maintenance_task_run(task_id, state="failed", error_message=str(exc))
        finally:
            _ACTIVE_CATALOG_TASK_KEYS.discard(self._task_key(task_type, task_id))

    def _repair_index_codes(self) -> list[str]:
        coverage = self.store.list_index_history_coverage()
        if coverage.empty or "completeness_status" not in coverage:
            return []
        repair_statuses = {"INCOMPLETE", "MISSING_HISTORY", "SOURCE_LIMITED"}
        return coverage.loc[
            coverage["completeness_status"].fillna("").astype(str).isin(repair_statuses), "index_code"
        ].astype(str).tolist()

    def _progress_total(self, task_type: str) -> int:
        if task_type == "index_catalog_sync":
            return 1
        catalog = self.store.list_index_catalog()
        return int(len(catalog))

    def _default_service(self) -> InitializationService:
        return InitializationService(self.store, provider=AkShareProvider(), parquet_store=self.parquet_store)

    def _task_key(self, task_type: str, task_id: int) -> tuple[str, str, int]:
        return (str(Path(self.store.db_path).resolve()), task_type, task_id)


class IndexAtomicSnapshotMaintenanceRunner:
    """Persist a local-only rebuild of the index atomic indicator snapshot."""

    def __init__(
        self,
        store: SQLiteStore,
        parquet_store: ParquetStore,
        *,
        build_snapshot: Callable[..., tuple[pd.DataFrame, pd.DataFrame]] = build_index_atomic_snapshot,
        write_snapshot: Callable[..., None] = write_index_atomic_snapshot,
    ) -> None:
        self.store = store
        self.parquet_store = parquet_store
        self.build_snapshot = build_snapshot
        self.write_snapshot = write_snapshot

    def start(self) -> MaintenanceTaskRun:
        with _INDEX_ATOMIC_SNAPSHOT_START_LOCK:
            self.reconcile_interrupted()
            running = self.store.get_running_maintenance_task_run(INDEX_ATOMIC_SNAPSHOT_REBUILD_TASK_TYPE)
            if running is not None:
                return running

            try:
                definitions, _ = index_atomic_snapshot_inputs(self.store)
                progress_total = len(definitions)
            except Exception:  # noqa: BLE001 - persist the same local-read failure in the task run
                progress_total = 0
            task = self.store.create_maintenance_task_run(
                INDEX_ATOMIC_SNAPSHOT_REBUILD_TASK_TYPE,
                progress_total=progress_total,
            )
            key = self._task_key(task.task_id)
            _ACTIVE_INDEX_ATOMIC_SNAPSHOT_TASK_KEYS.add(key)
            try:
                background_tasks.create(self._run(task.task_id), name=f"index-atomic-snapshot-{task.task_id}")
            except Exception as exc:
                _ACTIVE_INDEX_ATOMIC_SNAPSHOT_TASK_KEYS.discard(key)
                self.store.update_maintenance_task_run(
                    task.task_id,
                    state="failed",
                    error_message=f"重建指数原子指标失败：{exc}",
                )
                raise
            return task

    def latest(self) -> MaintenanceTaskRun | None:
        self.reconcile_interrupted()
        return self.store.get_latest_maintenance_task_run(INDEX_ATOMIC_SNAPSHOT_REBUILD_TASK_TYPE)

    def reconcile_interrupted(self) -> MaintenanceTaskRun | None:
        with _INDEX_ATOMIC_SNAPSHOT_START_LOCK:
            running = self.store.get_running_maintenance_task_run(INDEX_ATOMIC_SNAPSHOT_REBUILD_TASK_TYPE)
            if running is None or self._task_key(running.task_id) in _ACTIVE_INDEX_ATOMIC_SNAPSHOT_TASK_KEYS:
                return None
            return self.store.mark_maintenance_task_interrupted(running.task_id, "服务器已重启，任务未继续执行")

    async def _run(self, task_id: int) -> None:
        try:
            definitions, coverage = index_atomic_snapshot_inputs(self.store)
            total = len(definitions)
            self.store.update_maintenance_task_run(task_id, progress_done=0, progress_total=total, progress_detail="")

            def on_progress(progress: IndexAtomicSnapshotProgress) -> None:
                self.store.update_maintenance_task_run(
                    task_id,
                    progress_done=progress.done,
                    progress_total=progress.total,
                    progress_detail=progress.index_code,
                )

            def action() -> tuple[pd.DataFrame, datetime]:
                expected_input_signature = _index_atomic_snapshot_source_signature(
                    self.parquet_store,
                    definitions,
                    coverage,
                )

                def current_input_signature() -> str:
                    current_definitions, current_coverage = index_atomic_snapshot_inputs(self.store)
                    return _index_atomic_snapshot_source_signature(
                        self.parquet_store,
                        current_definitions,
                        current_coverage,
                    )

                summary, details = self.build_snapshot(
                    self.parquet_store,
                    definitions,
                    coverage=coverage,
                    on_progress=on_progress,
                )
                generated_at = datetime.now()
                self.write_snapshot(
                    summary,
                    details,
                    expected_input_signature,
                    generated_at,
                    self.parquet_store,
                    definitions=definitions,
                    coverage=coverage,
                    expected_input_signature=expected_input_signature,
                    current_input_signature=current_input_signature,
                    task_result_id=task_id,
                )
                return summary, generated_at

            summary, generated_at = await run.io_bound(action)
            result_json = json.dumps(
                {
                    "total_count": total,
                    "successfully_calculated_count": _successfully_calculated_count(summary),
                    "data_status_counts": _index_atomic_data_status_counts(summary),
                    "generated_at": generated_at.isoformat(timespec="seconds"),
                    "snapshot_files": [
                        "index_atomic_snapshot.parquet",
                        "index_atomic_snapshot_details.parquet",
                        "index_atomic_snapshot.meta.json",
                    ],
                },
                ensure_ascii=False,
            )
            self.store.update_maintenance_task_run(
                task_id,
                state="success",
                progress_done=total,
                progress_total=total,
                result_json=result_json,
            )
        except Exception as exc:  # noqa: BLE001 - keep the previous atomically-published snapshot readable
            self.store.update_maintenance_task_run(
                task_id,
                state="failed",
                error_message=f"重建指数原子指标失败：{exc}",
            )
        finally:
            _ACTIVE_INDEX_ATOMIC_SNAPSHOT_TASK_KEYS.discard(self._task_key(task_id))

    def _task_key(self, task_id: int) -> tuple[str, int]:
        return (str(Path(self.store.db_path).resolve()), task_id)


def _index_atomic_data_status_counts(summary: pd.DataFrame) -> dict[str, int]:
    for column in ("data_status", "snapshot_status", "history_status"):
        if column in summary:
            counts = summary[column].fillna("missing").astype(str).value_counts()
            return {str(status): int(count) for status, count in counts.items()}
    return {}


def _successfully_calculated_count(summary: pd.DataFrame) -> int:
    if "snapshot_status" not in summary:
        return int(len(summary))
    return int(summary["snapshot_status"].fillna("").astype(str).eq("computed").sum())


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
            invalidate_snapshot_cache(self.store, self.parquet_store)
        except Exception as exc:  # noqa: BLE001 - persist the provider/storage failure for the next page session
            self.store.update_maintenance_task_run(task_id, state="failed", error_message=str(exc))
        finally:
            _ACTIVE_INDEX_TASK_KEYS.discard(self._task_key(task_id))

    def _default_service(self) -> InitializationService:
        return InitializationService(self.store, provider=AkShareProvider(), parquet_store=self.parquet_store)

    def _task_key(self, task_id: int) -> tuple[str, int]:
        return (str(Path(self.store.db_path).resolve()), task_id)
