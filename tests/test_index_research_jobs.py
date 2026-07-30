from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from etf_trading.data.storage import ParquetStore
from etf_trading.research.index_validation import IndexResearchCancelled
from etf_trading.research.index_jobs import (
    IndexResearchAlreadyRunning,
    IndexResearchJobManager,
    index_research_is_stale,
)


@dataclass(frozen=True)
class _Published:
    run_id: str = "published-run"
    data_cutoff: str = "2026-07-28"


def _wait_for(manager: IndexResearchJobManager, status: str) -> object:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = manager.snapshot()
        if snapshot.status == status:
            return snapshot
        time.sleep(0.01)
    pytest.fail(f"job did not reach {status}; current={manager.snapshot()}")


def _write_index_price(root: Path, code: str, latest_date: str) -> None:
    ParquetStore(root).write_index_prices(code, pd.DataFrame({"trade_date": [latest_date], "close": [1.0]}))


def test_newer_index_data_marks_result_stale_but_etf_data_does_not(tmp_path: Path):
    _write_index_price(tmp_path, "000300", "2026-07-29")
    ParquetStore(tmp_path).write_prices("510300", pd.DataFrame({"trade_date": ["2030-01-01"], "close": [1.0]}))

    assert index_research_is_stale({"data_cutoff": "2026-07-28"}, tmp_path) is True
    assert index_research_is_stale({"data_cutoff": "2026-07-29"}, tmp_path) is False
    assert index_research_is_stale({"data_cutoff": "2026-07-30"}, tmp_path) is False


def test_stale_scan_ignores_bad_index_parquet_and_missing_metadata(tmp_path: Path):
    index_dir = tmp_path / "indexes"
    index_dir.mkdir()
    (index_dir / "bad.parquet").write_text("not parquet", encoding="utf-8")

    assert index_research_is_stale(None, tmp_path) is False
    assert index_research_is_stale({}, tmp_path) is False
    assert index_research_is_stale({"data_cutoff": "2026-07-28"}, tmp_path) is False


def test_job_manager_rejects_second_concurrent_run_and_reports_progress():
    release = threading.Event()

    def runner(*, progress, should_stop):
        progress(1, 2, "000300", "completed")
        release.wait(2)
        progress(2, 2, "000905", "completed")
        return _Published()

    manager = IndexResearchJobManager(runner)
    first_id = manager.start()
    with pytest.raises(IndexResearchAlreadyRunning):
        manager.start()
    running = _wait_for(manager, "running")
    assert running.job_id == first_id
    assert running.done == 1 and running.total == 2 and running.index_code == "000300"
    release.set()
    completed = _wait_for(manager, "completed")
    assert completed.run_id == "published-run"
    assert completed.data_cutoff == "2026-07-28"


def test_cancel_is_idempotent_and_only_completes_at_research_boundary():
    entered = threading.Event()

    def runner(*, progress, should_stop):
        entered.set()
        while not should_stop():
            time.sleep(0.005)
        raise IndexResearchCancelled("cancelled at index boundary")

    manager = IndexResearchJobManager(runner)
    manager.cancel()
    manager.start()
    assert entered.wait(2)
    manager.cancel()
    manager.cancel()
    cancelled = _wait_for(manager, "cancelled")
    assert cancelled.error == ""
    manager.cancel()
    assert manager.snapshot().status == "cancelled"


def test_late_callback_from_old_job_cannot_pollute_a_new_job():
    first_finished = threading.Event()
    callbacks: list[object] = []

    def runner(*, progress, should_stop):
        callbacks.append(progress)
        if len(callbacks) == 1:
            progress(1, 1, "OLD", "completed")
            first_finished.set()
            return _Published("one", "2026-07-28")
        progress(0, 2, "NEW", "starting")
        return _Published("two", "2026-07-29")

    manager = IndexResearchJobManager(runner)
    manager.start()
    assert first_finished.wait(2)
    _wait_for(manager, "completed")
    manager.start()
    callbacks[0](99, 99, "OLD", "late")
    completed = _wait_for(manager, "completed")
    assert completed.run_id == "two"
    assert completed.index_code != "OLD"


def test_failed_job_preserves_safe_error_summary():
    def runner(*, progress, should_stop):
        raise RuntimeError("expected failure")

    manager = IndexResearchJobManager(runner)
    manager.start()
    failed = _wait_for(manager, "failed")
    assert "expected failure" in failed.error
