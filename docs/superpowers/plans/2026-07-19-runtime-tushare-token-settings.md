# Runtime Tushare Token Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save a local SQLite Tushare Token from the NiceGUI top bar and use it for later Tushare-first requests.

**Architecture:** `SQLiteStore` owns runtime settings. The provider factory resolves environment credentials first and the persisted Token second. The NiceGUI shell renders a non-secret status button and dialog; each new provider is created with the current store.

**Tech Stack:** Python 3.12, SQLite, NiceGUI, pytest.

## Global Constraints

- SQLite plaintext persistence is explicitly user-approved; credentials never enter source, YAML, logs, task results, market data, or Git.
- The dialog never re-renders a full saved Token.
- No token means explicit AkShare fallback; live proxy tests remain opt-in.

---

### Task 1: Add SQLite runtime settings

**Files:** `src/etf_trading/data/storage.py`, `tests/test_storage.py`

**Produces:** `get_runtime_setting(key) -> str | None`, `set_runtime_setting(key, value) -> None`, `delete_runtime_setting(key) -> None`.

- [ ] **Step 1: Write the failing test**

```python
def test_runtime_setting_round_trip_and_clear(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.set_runtime_setting("tushare_token", "secret-value")
    assert store.get_runtime_setting("tushare_token") == "secret-value"
    store.delete_runtime_setting("tushare_token")
    assert store.get_runtime_setting("tushare_token") is None
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest tests/test_storage.py -q`

Expected: FAIL because runtime-setting methods do not exist.

- [ ] **Step 3: Implement minimal schema and methods**

```sql
CREATE TABLE IF NOT EXISTS runtime_setting (setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
```

Use SQLite `INSERT ... ON CONFLICT(setting_key) DO UPDATE`, `SELECT setting_value`, and `DELETE` respectively.

- [ ] **Step 4: Verify GREEN and commit**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest tests/test_storage.py -q`

Commit: `git add src/etf_trading/data/storage.py tests/test_storage.py && git commit -m "feat: store local runtime settings"`

### Task 2: Resolve saved Token for providers

**Files:** `src/etf_trading/data/providers/factory.py`, `src/etf_trading/nicegui_app/maintenance_tasks.py`, `src/etf_trading/nicegui_app/pages/maintenance.py`, `src/etf_trading/ui/app.py`, `tests/test_provider_factory.py`

**Produces:** `create_data_provider(settings=None, *, environ=None, store=None) -> PrimaryFallbackProvider`.

- [ ] **Step 1: Write the failing test**

```python
def test_factory_uses_saved_token_when_environment_is_empty(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.set_runtime_setting("tushare_token", "saved-token")
    provider = create_data_provider(environ={}, store=store)
    assert provider.primary.settings.token == "saved-token"
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest tests/test_provider_factory.py -q`

Expected: FAIL because the factory lacks `store`.

- [ ] **Step 3: Implement precedence and wire UI call sites**

```python
resolved = settings or load_provider_settings(environ=environ)
if not resolved.token and store is not None:
    resolved = replace(resolved, token=store.get_runtime_setting("tushare_token") or "")
```

Pass `store=store` at NiceGUI construction points; keep environment higher priority.

- [ ] **Step 4: Verify GREEN and commit**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest tests/test_provider_factory.py tests/test_nicegui_maintenance_tasks.py -q`

Commit: `git add src/etf_trading/data/providers/factory.py src/etf_trading/nicegui_app tests/test_provider_factory.py && git commit -m "feat: use saved tushare token for providers"`

### Task 3: Add top-bar configuration dialog

**Files:** `src/etf_trading/nicegui_app/layout.py`, `tests/test_nicegui_maintenance_tasks.py`

**Produces:** `_tushare_status_label(store) -> str` and `_render_data_source_settings(store) -> None`.

- [ ] **Step 1: Write the failing test**

```python
def test_tushare_status_label_does_not_reveal_saved_token(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.set_runtime_setting("tushare_token", "secret-value")
    label = layout._tushare_status_label(store)
    assert label == "Tushare 已配置"
    assert "secret-value" not in label
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest tests/test_nicegui_maintenance_tasks.py -q`

Expected: FAIL because the helper does not exist.

- [ ] **Step 3: Implement dialog and callbacks**

```python
with ui.dialog() as dialog, ui.card():
    token_input = ui.input("Tushare Token", password=True, password_toggle_button=True)
    ui.button("保存", on_click=save_token)
    ui.button("清除", on_click=clear_token)
```

Callbacks trim, persist/delete `tushare_token`, notify without the Token, and refresh the status button.

- [ ] **Step 4: Verify GREEN and commit**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_app_import.py -q`

Commit: `git add src/etf_trading/nicegui_app/layout.py tests/test_nicegui_maintenance_tasks.py && git commit -m "feat: add tushare settings dialog"`

### Task 4: Document and verify

**Files:** `README.md`, `docs/task-memory.md`

- [ ] **Step 1: Document local SQLite persistence and clearing behavior.**
- [ ] **Step 2: Run full offline tests.**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf-runtime-token-final`

Expected: all offline tests pass; live smoke test skips unless enabled.

- [ ] **Step 3: Scan for hard-coded credentials.**

Run: `git grep -n -E "token=[0-9a-f]{20,}|TUSHARE_TOKEN\s*=\s*['\"][^'\"]+" -- . ':!docs/superpowers/plans/*'`

Expected: no hard-coded production credential.

- [ ] **Step 4: Commit documentation.**

Commit: `git add README.md docs/task-memory.md && git commit -m "docs: explain local tushare token settings"`
