"""Single-flight background execution for published index-trend research."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Literal
from uuid import uuid4

import pandas as pd

from etf_trading.research.index_report import PublishedIndexResearch, run_and_publish_index_research
from etf_trading.research.index_validation import IndexResearchCancelled


IndexResearchJobStatus = Literal["idle", "queued", "running", "completed", "failed", "cancelled"]


class IndexResearchAlreadyRunning(RuntimeError):
    """Raised when a caller tries to overlap two index research runs."""


@dataclass(frozen=True)
class IndexResearchJobSnapshot:
    """An immutable, coherent view of the sole background research job."""

    job_id: str | None = None
    status: IndexResearchJobStatus = "idle"
    phase: str = ""
    done: int = 0
    total: int = 0
    index_code: str = ""
    message: str = ""
    error: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    run_id: str | None = None
    data_cutoff: str | None = None


class IndexResearchJobManager:
    """Run the locked research pipeline once at a time in a daemon worker."""

    def __init__(
        self,
        runner: Callable[..., PublishedIndexResearch] = run_and_publish_index_research,
    ) -> None:
        self._runner = runner
        self._lock = RLock()
        self._cancel_event = Event()
        self._snapshot = IndexResearchJobSnapshot()
        self._worker: Thread | None = None

    def start(self) -> str:
        """Atomically queue a fresh job and then start its daemon worker."""

        with self._lock:
            if self._snapshot.status in {"queued", "running"}:
                raise IndexResearchAlreadyRunning("指数趋势回测正在运行，请等待或取消当前任务")
            job_id = uuid4().hex
            self._cancel_event = Event()
            self._snapshot = IndexResearchJobSnapshot(
                job_id=job_id,
                status="queued",
                phase="queued",
                message="任务已排队，等待后台启动",
                started_at=datetime.now(timezone.utc),
            )
            worker = Thread(target=self._work, args=(job_id, self._cancel_event), daemon=True, name=f"index-research-{job_id[:8]}")
            self._worker = worker
            worker.start()
            return job_id

    def cancel(self) -> None:
        """Request cooperative cancellation; repeated calls are harmless."""

        with self._lock:
            if self._snapshot.status in {"queued", "running"}:
                self._cancel_event.set()
                message = "取消已请求，任务尚未开始" if self._snapshot.status == "queued" else "取消已请求，将在当前指数完成后取消"
                self._snapshot = self._replace_current(message=message)

    def snapshot(self) -> IndexResearchJobSnapshot:
        """Return the immutable current snapshot."""

        with self._lock:
            return self._snapshot

    def _work(self, job_id: str, cancel_event: Event) -> None:
        with self._lock:
            if self._snapshot.job_id != job_id:
                return
            self._snapshot = self._replace_current(status="running", phase="preparing", message="正在准备指数样本")

        def should_stop() -> bool:
            with self._lock:
                return cancel_event.is_set() or self._snapshot.job_id != job_id

        def progress(done: int, total: int, index_code: str, phase: str) -> None:
            self._update_progress(job_id, done, total, index_code, phase)

        try:
            if should_stop():
                raise IndexResearchCancelled("index research cancelled before start")
            published = self._runner(progress=progress, should_stop=should_stop)
        except IndexResearchCancelled:
            self._finish(job_id, "cancelled", phase="cancelled", message="回测已取消；最近一次已发布结果保持不变")
        except Exception as exc:  # noqa: BLE001 - worker errors must not tear down the UI
            self._finish(job_id, "failed", phase="failed", message="后台回测失败", error=_safe_error_summary(exc))
        else:
            self._finish(
                job_id,
                "completed",
                phase="completed",
                message="回测完成，已发布新的完整结果",
                run_id=str(published.run_id),
                data_cutoff=str(published.data_cutoff),
            )

    def _update_progress(self, job_id: str, done: int, total: int, index_code: str, phase: str) -> None:
        with self._lock:
            current = self._snapshot
            if current.job_id != job_id or current.status not in {"queued", "running"}:
                return
            parsed_total = max(0, int(total))
            if parsed_total == 0:
                if current.total > 0:
                    self._snapshot = self._replace_current(
                        status="running",
                        phase=str(phase or "running"),
                        done=min(current.total, max(current.done, max(0, int(done)))),
                        total=current.total,
                        index_code=str(index_code or current.index_code),
                        message="正在执行指数理论回测",
                    )
                    return
                self._snapshot = self._replace_current(
                    status="running",
                    phase=str(phase or "running"),
                    done=0,
                    total=0,
                    index_code=str(index_code or current.index_code),
                    message="正在执行指数理论回测",
                )
                return
            stable_total = current.total or parsed_total
            if stable_total and parsed_total and parsed_total != stable_total:
                parsed_total = stable_total
            next_done = max(current.done, max(0, int(done)))
            if stable_total:
                next_done = min(next_done, stable_total)
            self._snapshot = self._replace_current(
                status="running",
                phase=str(phase or "running"),
                done=next_done,
                total=stable_total,
                index_code=str(index_code or current.index_code),
                message="正在执行指数理论回测",
            )

    def _finish(
        self,
        job_id: str,
        status: IndexResearchJobStatus,
        *,
        phase: str,
        message: str,
        error: str = "",
        run_id: str | None = None,
        data_cutoff: str | None = None,
    ) -> None:
        with self._lock:
            if self._snapshot.job_id != job_id:
                return
            self._snapshot = self._replace_current(
                status=status,
                phase=phase,
                message=message,
                error=error,
                finished_at=datetime.now(timezone.utc),
                run_id=run_id,
                data_cutoff=data_cutoff,
            )

    def _replace_current(self, **changes: object) -> IndexResearchJobSnapshot:
        values = {field: getattr(self._snapshot, field) for field in self._snapshot.__dataclass_fields__}
        values.update(changes)
        return IndexResearchJobSnapshot(**values)


def index_research_is_stale(latest_meta: Mapping[str, object] | object | None, parquet_root: str | Path | object) -> bool:
    """Return whether any readable local *index* price history is newer than cutoff.

    The scan is deliberately read-only and excludes ETF histories, report artifacts,
    and staging directories by considering only direct ``indexes/*.parquet`` files.
    Corrupt or schema-incompatible files are treated as unavailable evidence.
    """

    cutoff = _data_cutoff(latest_meta)
    if cutoff is None:
        return False
    root = Path(parquet_root) if isinstance(parquet_root, (str, Path)) else Path(getattr(parquet_root, "root", "data/parquet"))
    newest: pd.Timestamp | None = None
    for path in sorted((root / "indexes").glob("*.parquet")):
        try:
            frame = pd.read_parquet(path, columns=["trade_date"])
        except Exception:  # noqa: BLE001 - stale detection cannot break rendering
            continue
        if "trade_date" not in frame:
            continue
        dates = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
        if dates.empty:
            continue
        candidate = pd.Timestamp(dates.max()).normalize()
        if newest is None or candidate > newest:
            newest = candidate
    return newest is not None and newest > cutoff


def _data_cutoff(latest_meta: Mapping[str, object] | object | None) -> pd.Timestamp | None:
    if latest_meta is None:
        return None
    if isinstance(latest_meta, Mapping):
        value = latest_meta.get("data_cutoff")
    else:
        value = getattr(latest_meta, "data_cutoff", None)
        if value is None:
            value = getattr(latest_meta, "run_meta", {}).get("data_cutoff")
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    return parsed.normalize() if not pd.isna(parsed) else None


def _safe_error_summary(exc: Exception) -> str:
    detail = " ".join(str(exc).split())[:300]
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
