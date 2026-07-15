# Maintenance Task Durability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make full-ETF and index maintenance tasks durable across page refreshes and safe when multiple NiceGUI processes share one SQLite database.

**Architecture:** Extend `maintenance_task_run` with a database-backed worker lease and add an ETF batch runner that follows the existing index runner pattern. Replace page-local latest-only recovery with a read-only recent-run list; page polling never mutates task state. Store UTC ISO timestamps and convert them to Asia/Shanghai only at the UI boundary.

**Tech Stack:** Python 3.11+, SQLite, pandas, NiceGUI, pytest

## Global Constraints

- Do not add an external queue or third-party dependency.
- Keep ETF freshness skipping, per-ETF failure isolation, and resumable reruns unchanged.
- Persist only full-universe long-running tasks in this change; short single-asset actions retain page-local feedback.
- Production and test servers must not share SQLite or Parquet paths.
- Preserve unrelated user changes in the dirty working tree.

---

### Task 1: Add lease-aware task storage

**Files:**
- Modify: `src/etf_trading/data/storage.py`
- Modify: `tests/test_storage_and_services.py`

**Interfaces:**
- Produces: `SQLiteStore.acquire_maintenance_task_run(task_type: str, *, progress_total: int, worker_id: str, lease_seconds: float) -> tuple[MaintenanceTaskRun, bool]`.
- Produces: `SQLiteStore.update_running_maintenance_task_run(task_id: int, *, worker_id: str, progress_done: int | None = None, progress_total: int | None = None, progress_detail: str | None = None) -> MaintenanceTaskRun`.
- Produces: `SQLiteStore.list_maintenance_task_runs(limit: int = 10) -> list[MaintenanceTaskRun]`.
- Extends: `MaintenanceTaskRun.worker_id` and `MaintenanceTaskRun.heartbeat_at` as optional strings.

- [ ] **Step 1: Write failing storage tests**

Add tests which initialize a temporary store and assert:

```python
first, created = store.acquire_maintenance_task_run(
    "etf_history_batch", progress_total=3, worker_id="worker-a", lease_seconds=30
)
same, created_again = store.acquire_maintenance_task_run(
    "etf_history_batch", progress_total=3, worker_id="worker-b", lease_seconds=30
)
assert created is True
assert created_again is False
assert same.task_id == first.task_id
assert same.state == "running"
```

Also set `heartbeat_at` and `updated_at` to an expired UTC value with SQL, acquire from `worker-b`, and assert the old run becomes `interrupted` while a new run is created. Complete the new run with `state="success", error_message=""`, then assert a subsequent `update_running_maintenance_task_run` does not change its progress. Assert `list_maintenance_task_runs(limit=2)` returns newest first.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_storage_and_services.py -k "maintenance_task_lease or maintenance_task_list or terminal_task" -q
```

Expected: FAIL because the lease-aware methods and columns do not exist.

- [ ] **Step 3: Implement the schema migration and storage methods**

Use UTC ISO values generated with:

```python
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
```

After `CREATE TABLE IF NOT EXISTS`, inspect `PRAGMA table_info(maintenance_task_run)` and add missing `worker_id TEXT` and `heartbeat_at TEXT` columns. `acquire_maintenance_task_run` must use `BEGIN IMMEDIATE`, return a fresh running record without changing it, conditionally interrupt an expired record, and insert the replacement in the same transaction. Treat old naive SQLite timestamps as UTC.

`update_running_maintenance_task_run` must update only with:

```sql
WHERE task_id = ? AND state = 'running' AND worker_id = ?
```

and refresh both `heartbeat_at` and `updated_at`. Final success must explicitly store an empty error string so a prior interruption message cannot survive.

- [ ] **Step 4: Run the storage tests and verify GREEN**

Run the command from Step 2. Expected: all selected tests PASS.

- [ ] **Step 5: Run nearby storage regression**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_storage_and_services.py -q
```

Expected: PASS.

### Task 2: Make ETF and index runners use leases

**Files:**
- Modify: `src/etf_trading/nicegui_app/maintenance_tasks.py`
- Modify: `tests/test_nicegui_maintenance_task_runner.py`

**Interfaces:**
- Produces: `ETF_HISTORY_BATCH_TASK_TYPE = "etf_history_batch"`.
- Produces: `EtfHistoryBatchRunner.start(start_date: str, through: str) -> MaintenanceTaskRun`.
- Changes: all durable runners acquire through SQLite and use `update_running_maintenance_task_run` for progress.

- [ ] **Step 1: Write failing runner tests**

Add a fake ETF service whose `ensure_all_etf_history` emits two `EtfHistoryProgress` events and returns two rows. Assert `_run` persists `success`, `2/2`, detail `512880 INITIALIZED`, result JSON, and an empty error. Add a two-worker test:

```python
runner_a = EtfHistoryBatchRunner(store, parquet, worker_id="worker-a", service_factory=factory)
runner_b = EtfHistoryBatchRunner(store, parquet, worker_id="worker-b", service_factory=factory)
first = runner_a.start("2021-01-01", "2026-07-14")
same = runner_b.start("2021-01-01", "2026-07-14")
assert same.task_id == first.task_id
```

Update the orphaned-index test so a fresh heartbeat is not interrupted and an explicitly expired heartbeat is interrupted only when `start` acquires a replacement.

- [ ] **Step 2: Run runner tests and verify RED**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_maintenance_task_runner.py -q
```

Expected: FAIL because the ETF runner and lease constructor arguments do not exist.

- [ ] **Step 3: Implement shared runner lease behavior and ETF runner**

Generate one process-level worker ID from hostname, PID, and UUID. Each runner accepts optional `worker_id` and `lease_seconds` for deterministic tests. `start` calls `acquire_maintenance_task_run`; it creates a background task only when `created is True`.

For ETF execution call:

```python
service.ensure_all_etf_history(
    start_date,
    through,
    refresh_master=True,
    sleep_seconds=0.15,
    on_progress=on_progress,
)
```

Progress callbacks update only the owner's running record. Final updates use owner-checked terminal writes. Remove `latest()` side effects and change `reconcile_interrupted()` to expire leases only; page reads must not call it.

- [ ] **Step 4: Run runner tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Run initialization and runner regression**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_storage_and_services.py tests\test_nicegui_maintenance_task_runner.py -q
```

Expected: PASS.

### Task 3: Render durable ETF progress and recent task history

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/maintenance.py`
- Modify: `tests/test_nicegui_maintenance_tasks.py`

**Interfaces:**
- Consumes: `EtfHistoryBatchRunner` and `SQLiteStore.list_maintenance_task_runs`.
- Produces: `_parse_task_time(value: str | None) -> datetime | None` converted to naive Asia/Shanghai display time.
- Produces: task-center rendering for all active runs plus the newest 10 runs.

- [ ] **Step 1: Write failing page tests**

Add tests asserting:

1. The all-ETF button calls `EtfHistoryBatchRunner.start` and does not call page-local `_run_task`.
2. Two persisted runs (`etf_history_batch` and `index_history_batch`) render both Chinese titles.
3. The page timer calls only read methods and never `reconcile_interrupted`.
4. `_parse_task_time("2026-07-13T16:10:13+00:00")` and `_parse_task_time("2026-07-13 16:10:13")` both display `datetime(2026, 7, 14, 0, 10, 13)`.

- [ ] **Step 2: Run page tests and verify RED**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_maintenance_tasks.py -q
```

Expected: FAIL on ETF runner binding, recent history, and timezone conversion.

- [ ] **Step 3: Implement page wiring and history rendering**

Instantiate `EtfHistoryBatchRunner` beside the index runners. Load recent runs with `store.list_maintenance_task_runs(limit=10)`, derive statuses with `_task_status_from_run`, and pass the list into the task-center renderer. Render active records first and recent records newest-first; expand the newest result and keep older entries compact.

The one-second timer reloads the list and rerenders it. It must not call any runner reconciliation method. Start helpers rerender from the store immediately after `runner.start`.

Parse timestamps with `datetime.fromisoformat`, attach UTC to legacy naive values, convert with `ZoneInfo("Asia/Shanghai")`, and remove timezone info for the existing formatter.

- [ ] **Step 4: Run page tests and verify GREEN**

Run the command from Step 2. Expected: PASS.

- [ ] **Step 5: Run maintenance UI regression**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_maintenance_tasks.py tests\test_nicegui_app_import.py tests\test_nicegui_table_display.py -q
```

Expected: PASS.

### Task 4: Verify the complete fix and record operational guidance

**Files:**
- Modify: `docs/task-memory.md`
- Test: `tests/test_storage_and_services.py`
- Test: `tests/test_nicegui_maintenance_task_runner.py`
- Test: `tests/test_nicegui_maintenance_tasks.py`

**Interfaces:**
- Consumes all prior task behavior.
- Produces a durable regression record and handoff notes.

- [ ] **Step 1: Run the focused durability suite**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_storage_and_services.py tests\test_nicegui_maintenance_task_runner.py tests\test_nicegui_maintenance_tasks.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-maintenance-durability-focused
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-maintenance-durability-full
```

Expected: PASS.

- [ ] **Step 3: Validate the rendered flow**

The flow under test is: `/page/maintenance/补齐任务` -> start a short isolated ETF batch -> reload -> the same run and progress remain visible -> start an isolated index batch -> both runs remain in recent history.

Use the Browser plugin when available. If absent, use the repository's available Playwright path without installing dependencies. The test service must point to a temporary SQLite and Parquet root and must not share `database/etf_system.sqlite`.

Verify page identity, nonblank content, no framework overlay, no relevant console errors, visible ETF and index records after reload, and screenshot evidence.

- [ ] **Step 4: Update task memory**

Append a `2026-07-15` entry to `docs/task-memory.md` with the summary, exact focused/full verification commands, browser availability, and this caution:

```text
Do not use process-local active-task sets to decide that a SQLite task owned by another process was interrupted; use a persisted lease and isolate QA databases from production data.
```

- [ ] **Step 5: Review the final diff**

Run:

```powershell
git diff --check
git status --short
git diff -- src/etf_trading/data/storage.py src/etf_trading/nicegui_app/maintenance_tasks.py src/etf_trading/nicegui_app/pages/maintenance.py tests/test_storage_and_services.py tests/test_nicegui_maintenance_task_runner.py tests/test_nicegui_maintenance_tasks.py docs/task-memory.md
```

Expected: no whitespace errors; only scoped files plus pre-existing unrelated user changes are present.
