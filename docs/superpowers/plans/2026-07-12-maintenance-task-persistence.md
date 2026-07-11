# 维护任务持久化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让指数全量历史补齐在浏览器刷新后仍能显示并持续执行，同时如实报告未追到目标交易日的滞后数据。

**Architecture:** SQLite 新增一次性维护运行记录，后台协调器通过 NiceGUI `background_tasks.create` 在服务端调度 `run.io_bound` 数据任务。页面只轮询并渲染持久化记录；指数服务提供逐标的进度，并把未达到目标交易日的结果写为 `STALE`。

**Tech Stack:** Python 3.12, SQLite, pandas, NiceGUI 3.14, pytest。

## Global Constraints

- 不新增第三方依赖或外部任务队列。
- 用户可见状态必须使用中文；数据库和 Python 内部状态可使用稳定英文码。
- `H30533` 数据源修复不属于本计划；必须保留其失败原因。
- 每次测试命令都使用 `--basetemp C:\Users\cjj\AppData\Local\Temp\...`，不得污染仓库。
- 不提交 `data/`、`database/*.sqlite`、日志或报告文件。

---

### Task 1: 持久化维护运行记录

**Files:**

- Modify: `src/etf_trading/data/storage.py:1-190`
- Modify: `tests/test_storage_and_services.py`

**Interfaces:**

- Produces: `MaintenanceTaskRun` 冻结数据类，字段为 `task_id`, `task_type`, `state`, `progress_done`, `progress_total`, `progress_detail`, `result_json`, `error_message`, `started_at`, `finished_at`, `updated_at`。
- Produces: `SQLiteStore.create_maintenance_task_run`, `get_maintenance_task_run`, `get_latest_maintenance_task_run`, `get_running_maintenance_task_run`, `update_maintenance_task_run` 和 `mark_maintenance_task_interrupted`。
- Consumed by: Task 3 的后台协调器和 Task 4 的页面任务中心。

- [ ] **Step 1: 写出失败的存储测试**

在 `tests/test_storage_and_services.py` 增加：

```python
def test_maintenance_task_run_persists_progress_result_and_interruption(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()

    created = store.create_maintenance_task_run("index_history_batch", progress_total=49)
    store.update_maintenance_task_run(
        created.task_id,
        progress_done=12,
        progress_detail="930633 STALE",
        state="running",
    )
    running = store.get_running_maintenance_task_run("index_history_batch")
    assert running is not None
    assert running.progress_done == 12
    assert running.progress_detail == "930633 STALE"

    store.mark_maintenance_task_interrupted(created.task_id, "服务器已重启")
    interrupted = store.get_maintenance_task_run(created.task_id)
    assert interrupted is not None
    assert interrupted.state == "interrupted"
    assert interrupted.error_message == "服务器已重启"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\.worktrees\maintenance-task-persistence\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests/test_storage_and_services.py::test_maintenance_task_run_persists_progress_result_and_interruption -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-task-run-storage-red
```

Expected: FAIL，因为 `SQLiteStore` 没有 `create_maintenance_task_run`。

- [ ] **Step 3: 实现表、数据类和存储方法**

在 `initialize_schema` 中创建：

```sql
CREATE TABLE IF NOT EXISTS maintenance_task_run (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'running',
    progress_done INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    progress_detail TEXT NOT NULL DEFAULT '',
    result_json TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_maintenance_task_run_type_time
    ON maintenance_task_run(task_type, task_id DESC);
```

新增 `MaintenanceTaskRun` 和上述存储方法。`update_maintenance_task_run` 只更新传入的可选字段，并始终写入 `updated_at=CURRENT_TIMESTAMP`；`state` 变为 `success`、`failed` 或 `interrupted` 时写入 `finished_at`。

- [ ] **Step 4: 运行测试确认通过**

Run 与 Step 2 相同。

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/etf_trading/data/storage.py tests/test_storage_and_services.py
git commit -m "feat: persist maintenance task runs"
```

### Task 2: 如实判定指数新鲜度并提供批量进度

**Files:**

- Modify: `src/etf_trading/data/initialization.py:25-300`
- Modify: `tests/test_storage_and_services.py`

**Interfaces:**

- Produces: `IndexHistoryProgress(done: int, total: int, index_code: str, status: str)`。
- Changes: `InitializationService.ensure_all_index_history(through, index_codes=None, *, on_progress=None)`。
- Changes: `ensure_index_history` 在最新日早于 `expected_latest_trade_date(through)` 时返回 `IndexHistoryResult(status="STALE")` 并将 `data_update_state.status` 设为 `STALE`。
- Consumed by: Task 3 的后台协调器。

- [ ] **Step 1: 写出失败的服务测试**

在 `tests/test_storage_and_services.py` 增加：

```python
def test_ensure_index_history_marks_existing_history_stale_when_provider_returns_no_new_dates(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    parquet = ParquetStore(tmp_path / "parquet")
    store.initialize_schema()
    parquet.write_index_prices("000300", _index_prices_through("2026-07-01"))
    service = InitializationService(store, provider=_EmptyIndexProvider(), parquet_store=parquet)

    result = service.ensure_index_history("000300", "2026-07-10")

    assert result.status == "STALE"
    with store.connect() as conn:
        state = pd.read_sql_query("SELECT status, error_message FROM data_update_state WHERE dataset='index_daily_price' AND asset_code='000300'", conn).iloc[0]
    assert state["status"] == "STALE"
    assert "2026-07-01" in state["error_message"]
    assert "2026-07-10" in state["error_message"]
```

并增加批量回调测试：

```python
def test_ensure_all_index_history_reports_each_index_progress(tmp_path):
    progress = []
    service = InitializationService(SQLiteStore(tmp_path / "etf.sqlite"), provider=_IndexProvider(), parquet_store=ParquetStore(tmp_path / "parquet"))

    result = service.ensure_all_index_history("2026-07-10", index_codes=["000300", "000905"], on_progress=progress.append)

    assert result["index_code"].tolist() == ["000300", "000905"]
    assert [(item.done, item.total, item.index_code) for item in progress] == [(1, 2, "000300"), (2, 2, "000905")]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\.worktrees\maintenance-task-persistence\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests/test_storage_and_services.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-index-freshness-red
```

Expected: FAIL，因为旧代码返回 `UPDATED`/`SUCCESS` 且没有 `on_progress` 参数。

- [ ] **Step 3: 实现最小新鲜度和进度逻辑**

在 `initialization.py`：

```python
@dataclass(frozen=True)
class IndexHistoryProgress:
    done: int
    total: int
    index_code: str
    status: str
```

`ensure_index_history` 使用现有数据质量模块的 `expected_latest_trade_date`。合并后若 `last_date < expected_date`，调用：

```python
message = f"本地最新交易日 {last_date.isoformat()}，未达到目标交易日 {expected_date.isoformat()}"
self.store.upsert_update_state("index_daily_price", index_code, last_date.isoformat(), status="STALE", error_message=message)
return IndexHistoryResult(index_code=index_code, status="STALE", fetched_rows=fetched_rows, total_rows=len(featured), start_date=first_date, end_date=last_date, error_message=message)
```

当 `fetched` 为空且已有文件不为空时，不重写旧 Parquet；直接按已有最新日返回 `STALE`。在 `ensure_all_index_history` 中，每个结果生成后调用：

```python
if on_progress is not None:
    on_progress(IndexHistoryProgress(done=done, total=total, index_code=index_code, status=result.status))
```

- [ ] **Step 4: 运行测试确认通过**

Run 与 Step 2 相同。

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/etf_trading/data/initialization.py tests/test_storage_and_services.py
git commit -m "fix: report stale index history accurately"
```

### Task 3: 服务端后台协调器

**Files:**

- Create: `src/etf_trading/nicegui_app/maintenance_tasks.py`
- Create: `tests/test_nicegui_maintenance_task_runner.py`

**Interfaces:**

- Produces: `INDEX_HISTORY_BATCH_TASK_TYPE = "index_history_batch"`。
- Produces: `IndexHistoryBatchRunner(store, parquet_store)`，方法 `start(through: str) -> MaintenanceTaskRun`、`latest() -> MaintenanceTaskRun | None`、`reconcile_interrupted()`。
- Consumes: Task 1 的 SQLite 运行记录和 Task 2 的 `IndexHistoryProgress`。
- Consumed by: Task 4 的维护页面。

- [ ] **Step 1: 写出失败的协调器测试**

创建 `tests/test_nicegui_maintenance_task_runner.py`：

```python
def test_index_history_batch_runner_deduplicates_running_task_and_persists_progress(monkeypatch, tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    scheduled = []
    monkeypatch.setattr(maintenance_tasks.background_tasks, "create", lambda awaitable, **kwargs: scheduled.append(awaitable))
    runner = maintenance_tasks.IndexHistoryBatchRunner(store, ParquetStore(tmp_path / "parquet"))

    first = runner.start("2026-07-10")
    second = runner.start("2026-07-10")

    assert first.task_id == second.task_id
    assert len(scheduled) == 1
    assert store.get_maintenance_task_run(first.task_id).state == "running"
```

并增加执行测试，使用假的 `InitializationService.ensure_all_index_history` 调用其 `on_progress` 两次并返回两行结果，断言最终记录 `state == "success"`、`progress_done == 2`、`result_json` 可恢复两行。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\.worktrees\maintenance-task-persistence\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests/test_nicegui_maintenance_task_runner.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-task-runner-red
```

Expected: FAIL，因为模块尚不存在。

- [ ] **Step 3: 实现协调器**

实现模块级活动 ID 集合，避免同一服务器进程中重复排程。`start` 先查询 `get_running_maintenance_task_run`；已有运行记录直接返回。新任务创建后立即通过：

```python
background_tasks.create(self._run(task_id, through), name=f"index-history-{task_id}")
```

在 `_run` 中以 `await run.io_bound(...)` 调用 `InitializationService(..., provider=AkShareProvider()).ensure_all_index_history`。进度回调只写 SQLite；完成后将 DataFrame 序列化为 `result_json`，并写入 `success`、失败信息或 `failed`。无活动 ID 的旧 `running` 记录由 `reconcile_interrupted` 标记 `interrupted`，错误信息为“服务器已重启，任务未继续执行”。

- [ ] **Step 4: 运行测试确认通过**

Run 与 Step 2 相同。

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/etf_trading/nicegui_app/maintenance_tasks.py tests/test_nicegui_maintenance_task_runner.py
git commit -m "feat: run index maintenance tasks in background"
```

### Task 4: 维护页恢复任务中心与指数进度

**Files:**

- Modify: `src/etf_trading/nicegui_app/pages/maintenance.py:20-410`
- Modify: `tests/test_nicegui_maintenance_tasks.py`
- Modify: `tests/test_nicegui_app_import.py`

**Interfaces:**

- Consumes: `IndexHistoryBatchRunner.latest`, `start` 和 Task 1 的 `MaintenanceTaskRun`。
- Produces: `_task_status_from_run(run)` 和 `_index_history_batch_message(rows)` 页面辅助函数。

- [ ] **Step 1: 写出失败的页面测试**

在 `tests/test_nicegui_maintenance_tasks.py` 增加：

```python
def test_task_status_from_persisted_running_run_shows_chinese_progress():
    run = MaintenanceTaskRun(task_id=7, task_type="index_history_batch", state="running", progress_done=11, progress_total=49, progress_detail="930633 STALE", result_json=None, error_message=None, started_at="2026-07-12 10:00:00", finished_at=None, updated_at="2026-07-12 10:01:00")

    status = maintenance._task_status_from_run(run)

    assert status.title == "补齐全部指数历史"
    assert status.state == "running"
    assert status.progress_done == 11
    assert status.progress_total == 49
    assert status.progress_detail == "930633 STALE"
```

再增加全量指数按钮测试：假的 runner 返回 `running` 记录时，点击“一键初始化/补齐全部指数”只调用 `runner.start`，任务中心文字出现 `11/49 · 930633 STALE`；重复点击不会产生第二个任务。

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\.worktrees\maintenance-task-persistence\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_app_import.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-maintenance-page-red
```

Expected: FAIL，因为页面尚未读取持久化运行记录。

- [ ] **Step 3: 实现页面恢复和轮询**

保留现有本地 `_run_task` 给主列表、单指数和 ETF 操作使用。仅“补齐全部指数历史”改为 `IndexHistoryBatchRunner.start`。页面初始渲染调用 `reconcile_interrupted` 和 `latest`，用 `_task_status_from_run` 还原任务中心；`ui.timer(1.0, refresh_persisted_index_task, immediate=False)` 每秒读取同一运行记录并更新任务中心。

补充状态标签：

```python
"interrupted": "已中断"
```

新增 `_index_history_batch_message`，统计结果中 `INITIALIZED`、`UPDATED`、`SKIPPED`、`STALE`、`FAILED` 和 `EMPTY`，输出中文摘要，例如：

```python
"已检查 49 个指数：补齐 11，跳过 36，行情仍滞后 1，失败/无数据 1"
```

任务成功后继续调用 `invalidate_snapshot_cache()`，使数据体检读取新状态。

- [ ] **Step 4: 运行测试确认通过**

Run 与 Step 2 相同。

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/etf_trading/nicegui_app/pages/maintenance.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_app_import.py
git commit -m "feat: restore maintenance task progress after refresh"
```

### Task 5: 全量验证、浏览器复现和任务记忆

**Files:**

- Modify: `docs/task-memory.md`

**Interfaces:**

- Verifies: 页面刷新后任务状态来自 SQLite，任务完成后数据快照失效，`STALE` 结果不会被显示为成功。

- [ ] **Step 1: 运行全量测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\.worktrees\maintenance-task-persistence\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-maintenance-persistence-full
```

Expected: 全部测试通过。

- [ ] **Step 2: 浏览器验证刷新恢复**

在隔离工作区启动 NiceGUI：

```powershell
$env:PYTHONPATH='src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -c "from etf_trading.nicegui_app.main import run; run(port=8512)"
```

用 Playwright 打开 `http://127.0.0.1:8512/page/maintenance/补齐任务`，触发一个使用测试服务的运行记录或短任务，刷新页面，确认“任务中心”仍显示同一任务 ID、状态和进度；检查浏览器控制台没有应用错误。

- [ ] **Step 3: 写入任务记忆**

向 `docs/task-memory.md` 追加 2026-07-12 条目，说明持久化维护运行记录、刷新恢复、指数 `STALE` 语义，记录全量测试和浏览器验收命令，并提醒后续不要把遍历完成当作数据新鲜度成功。

- [ ] **Step 4: 提交**

```powershell
git add docs/task-memory.md
git commit -m "docs: record maintenance task persistence"
```
