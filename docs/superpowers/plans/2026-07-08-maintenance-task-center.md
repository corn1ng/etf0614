# Data Maintenance Task Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a page-level task center for `数据维护 -> 补齐任务` so the latest maintenance task always shows a clear running, success, failure, or cancelled state.

**Architecture:** Keep task state page-local inside `nicegui_app.pages.maintenance`. `_run_task` remains the single task execution wrapper and updates a lightweight status object plus a task-center container before and after `run.io_bound`.

**Tech Stack:** Python 3.11, NiceGUI, pandas, pytest, existing `render_table` helper.

## Global Constraints

- Do not add a durable background queue or cross-page task persistence.
- Do not add real per-index or per-ETF progress such as `3/12 正在拉取 000300`.
- Do not change AkShare, Parquet, SQLite, or `InitializationService` business logic.
- Preserve existing `ui.notify`, button disable/enable, `run.io_bound`, and `invalidate_snapshot_cache()` behavior.
- Keep the task center compact, workbench-style, and no more than 8px rounded.

---

## File Structure

- `src/etf_trading/nicegui_app/pages/maintenance.py`
  Owns `MaintenanceTaskStatus`, task-center rendering, and `_run_task` state transitions.
- `src/etf_trading/nicegui_app/theme.py`
  Owns CSS classes for the task-center panel and status badge colors.
- `tests/test_nicegui_maintenance_tasks.py`
  Covers task-center rendering and task state transitions before and after `run.io_bound`.
- `tests/test_nicegui_theme.py`
  Covers presence of task-center theme classes.
- `docs/task-memory.md`
  Gets a short implementation memory entry after verification.

### Task 1: Add Task-Center State And Renderer

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/maintenance.py`
- Test: `tests/test_nicegui_maintenance_tasks.py`

**Interfaces:**
- Produces: `MaintenanceTaskStatus(title: str = "", state: str = "idle", message: str = "", started_at: datetime | None = None, finished_at: datetime | None = None, result: object | None = None, error: str = "")`
- Produces: `_render_task_center(container, status: MaintenanceTaskStatus) -> None`
- Produces: `_task_state_label(state: str) -> str`

- [ ] **Step 1: Write the failing renderer test**

Add this test to `tests/test_nicegui_maintenance_tasks.py`:

```python
from datetime import datetime


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
```

- [ ] **Step 2: Run the renderer test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_maintenance_tasks.py::test_task_center_renders_idle_and_running_states -q
```

Expected: FAIL because `MaintenanceTaskStatus` or `_render_task_center` does not exist.

- [ ] **Step 3: Add the minimal state model and renderer**

In `src/etf_trading/nicegui_app/pages/maintenance.py`, add imports:

```python
from dataclasses import dataclass
from datetime import date, datetime, timedelta
```

Add this code after `SAMPLE_CATEGORIES`:

```python
@dataclass
class MaintenanceTaskStatus:
    title: str = ""
    state: str = "idle"
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: object | None = None
    error: str = ""


def _task_state_label(state: str) -> str:
    return {
        "idle": "空闲",
        "running": "运行中",
        "success": "成功",
        "failed": "失败",
        "cancelled": "取消",
    }.get(state, "空闲")


def _task_state_tone(state: str) -> str:
    return {
        "idle": "neutral",
        "running": "info",
        "success": "success",
        "failed": "danger",
        "cancelled": "warning",
    }.get(state, "neutral")


def _format_task_time(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else ""


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

            if status.state == "success" and status.result is not None:
                with ui.column().classes("workbench-task-center-result w-full"):
                    _render_task_result(status.result)
            elif status.state == "failed" and status.error:
                ui.label(status.error).classes("text-xs text-red-700")
            elif status.state == "cancelled":
                ui.label("任务没有返回结果，请稍后重试。").classes("text-xs text-amber-700")
```

- [ ] **Step 4: Run the renderer test to verify it passes**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_maintenance_tasks.py::test_task_center_renders_idle_and_running_states -q
```

Expected: PASS.

### Task 2: Wire `_run_task` To The Task Center

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/maintenance.py`
- Test: `tests/test_nicegui_maintenance_tasks.py`

**Interfaces:**
- Consumes: `MaintenanceTaskStatus`, `_render_task_center(container, status)`
- Changes: `_run_task(button, task_center, task_status: MaintenanceTaskStatus, title: str, action, success_message) -> None`

- [ ] **Step 1: Replace the existing task feedback test**

Replace `test_maintenance_task_gives_feedback_before_io_bound_work` with:

```python
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
    assert events.index("button_update") < io_bound_position
    assert events.index("center_update") < io_bound_position
    assert "notify:positive:已检查 1 个指数" in events
    assert "badge:成功" in events
    assert "table" in events
    assert task_status.state == "success"
    assert task_status.result == [{"index_code": "000300"}]
    assert events[-1] == "enable"
```

- [ ] **Step 2: Add failure and cancelled tests**

Add:

```python
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
```

- [ ] **Step 3: Run the task tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_maintenance_tasks.py -q
```

Expected: FAIL because `_run_task` still accepts the old `result_area` signature and `_render_tasks` does not create a task center.

- [ ] **Step 4: Wire `render_tasks` and `_run_task`**

In `src/etf_trading/nicegui_app/pages/maintenance.py`, replace `_render_tasks` with:

```python
def _render_tasks(snapshot: PlatformSnapshot, store, parquet_store) -> None:
    task_status = MaintenanceTaskStatus()
    task_center = ui.column().classes("w-full")
    _render_task_center(task_center, task_status)
    _render_master_tasks(store, parquet_store, task_center, task_status)
    _render_etf_history_tasks(snapshot, store, parquet_store, task_center, task_status)
    _render_index_history_tasks(store, parquet_store, task_center, task_status)
    _render_batch_tasks(store, parquet_store, task_center, task_status)
    ui.label("补齐任务只在点击后执行，避免打开页面自动触发耗时操作。").classes("text-xs text-slate-500")
```

Change each task renderer signature and `_run_task` call:

```python
def _render_master_tasks(store, parquet_store, task_center, task_status) -> None:
```

```python
_run_task(master_button, task_center, task_status, "初始化ETF主列表", ...)
```

Apply the same parameter pattern to:

```python
_render_etf_history_tasks(snapshot, store, parquet_store, task_center, task_status)
_render_index_history_tasks(store, parquet_store, task_center, task_status)
_render_batch_tasks(store, parquet_store, task_center, task_status)
```

Replace `_run_task` with:

```python
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
    _render_task_center(task_center, task_status)

    ui.notify(task_status.message, type="info")
    if button is not None:
        button.update()
    task_center.update()

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
        if button is not None:
            button.enable()
```

- [ ] **Step 5: Run task tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_maintenance_tasks.py -q
```

Expected: PASS.

### Task 3: Add Task-Center Theme Classes

**Files:**
- Modify: `src/etf_trading/nicegui_app/theme.py`
- Test: `tests/test_nicegui_theme.py`

**Interfaces:**
- Produces CSS classes: `.workbench-task-center`, `.workbench-task-center-header`, `.workbench-task-center-status`, `.workbench-task-center-meta`, `.workbench-task-center-result`

- [ ] **Step 1: Write the failing theme test**

Add to `tests/test_nicegui_theme.py`:

```python
def test_task_center_theme_classes_exist():
    from etf_trading.nicegui_app.theme import WORKBENCH_CSS

    for css_class in [
        ".workbench-task-center",
        ".workbench-task-center-header",
        ".workbench-task-center-status",
        ".workbench-task-center-meta",
        ".workbench-task-center-result",
    ]:
        assert css_class in WORKBENCH_CSS
```

- [ ] **Step 2: Run the theme test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_theme.py::test_task_center_theme_classes_exist -q
```

Expected: FAIL because the task-center classes are not in `WORKBENCH_CSS`.

- [ ] **Step 3: Add compact task-center CSS**

In `src/etf_trading/nicegui_app/theme.py`, add after `.workbench-task-panel`:

```css
.workbench-task-center {
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 10px 12px;
  gap: 6px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.workbench-task-center-header {
  min-height: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.workbench-task-center-status {
  border-radius: 999px;
  font-size: 12px;
  line-height: 18px;
  padding: 0 8px;
  color: #475569;
  background: #f1f5f9;
}
.workbench-task-center-status.is-running {
  color: #1d4ed8;
  background: #eff6ff;
}
.workbench-task-center-status.is-success {
  color: #047857;
  background: #ecfdf5;
}
.workbench-task-center-status.is-failed {
  color: #b91c1c;
  background: #fef2f2;
}
.workbench-task-center-status.is-cancelled {
  color: #b45309;
  background: #fffbeb;
}
.workbench-task-center-meta {
  font-size: 12px;
  line-height: 16px;
  color: var(--wb-muted);
}
.workbench-task-center-result {
  margin-top: 4px;
}
```

- [ ] **Step 4: Run the theme test to verify it passes**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_theme.py::test_task_center_theme_classes_exist -q
```

Expected: PASS.

### Task 4: Focused Regression And Memory Entry

**Files:**
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: all task-center implementation from Tasks 1-3.
- Produces: a short task-memory entry documenting verification and future cautions.

- [ ] **Step 1: Run focused regression**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_theme.py tests/test_nicegui_app_import.py -q --basetemp pytest-tmp-maintenance-task-center-focused
```

Expected: PASS.

- [ ] **Step 2: Run broader NiceGUI regression**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_table_display.py tests/test_nicegui_state_cache.py -q --basetemp pytest-tmp-maintenance-task-center-regression
```

Expected: PASS.

- [ ] **Step 3: Append task memory**

Append to `docs/task-memory.md`:

```md
## 2026-07-08 - Implement maintenance task center

- Summary: Added a page-level task center to `数据维护 -> 补齐任务` so maintenance actions show running, success, failure, or cancelled state with the latest result.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_theme.py tests/test_nicegui_app_import.py -q --basetemp pytest-tmp-maintenance-task-center-focused` passed; `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_table_display.py tests/test_nicegui_state_cache.py -q --basetemp pytest-tmp-maintenance-task-center-regression` passed.
- Watch out next time:
  - Keep maintenance task feedback visible before entering `run.io_bound`.
  - Do not add per-asset progress to the task center until the service exposes real progress callbacks.
```

- [ ] **Step 4: Inspect local diff**

Run:

```powershell
git diff -- src/etf_trading/nicegui_app/pages/maintenance.py src/etf_trading/nicegui_app/theme.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_theme.py docs/task-memory.md
```

Expected: Diff contains task-center code, tests, CSS, and the task-memory entry. Existing unrelated dirty files may remain outside this path set.
