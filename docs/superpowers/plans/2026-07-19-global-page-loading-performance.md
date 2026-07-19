# Global Page Loading Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every NiceGUI menu and Tab load only its required local data.

**Architecture:** Extend route snapshot modes in `layout.py`; add focused cached/read-only loaders in `state.py`; keep heavyweight ETF mapping and gap calculation exclusively in the pages that render them.

**Tech Stack:** Python, pandas, SQLite, Parquet, NiceGUI, pytest.

## Global Constraints

- Do not alter data calculations, data source behavior, button behavior, or task semantics.
- Do not call external providers from page-load paths.
- Preserve current snapshot cache behavior.

---

### Task 1: Audit and introduce route-specific snapshot modes

**Files:** `src/etf_trading/nicegui_app/layout.py`, `tests/test_nicegui_app_import.py`

- [ ] Write failing tests asserting market, ETF-data, research, and maintenance routes resolve to non-full modes unless their active section needs full gaps/universe.
- [ ] Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py -q`; expect FAIL.
- [ ] Add named modes and make `snapshot_mode_for_route(page_slug, section)` use page/section-specific selection.
- [ ] Re-run the focused tests; expect PASS.
- [ ] Commit: `git add src/etf_trading/nicegui_app/layout.py tests/test_nicegui_app_import.py && git commit -m "perf: select lightweight snapshots by route"`.

### Task 2: Add lightweight state loaders

**Files:** `src/etf_trading/nicegui_app/state.py`, `tests/test_nicegui_app_import.py`

- [ ] Write failing tests that monkeypatch `build_index_etf_universe` and `build_data_gap_detail`, then assert market and maintenance loaders do not call them.
- [ ] Run the test; expect FAIL because those routes load a full snapshot.
- [ ] Add read-only loaders returning `PlatformSnapshot` with only each route's required master, catalog/coverage, atomic snapshot summary, or empty frames.
- [ ] Re-run focused tests; expect PASS.
- [ ] Commit: `git add src/etf_trading/nicegui_app/state.py tests/test_nicegui_app_import.py && git commit -m "perf: add focused page snapshot loaders"`.

### Task 3: Validate page contracts and full regression

**Files:** `tests/test_ui_navigation.py`, `tests/test_nicegui_maintenance_tasks.py`, `docs/task-memory.md`

- [ ] Add page-contract tests for all navigation entries and sections, asserting expected data frames exist and heavyweight builders are isolated.
- [ ] Run relevant navigation and maintenance tests; expect PASS.
- [ ] Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf-page-load-final`; expect all offline tests PASS.
- [ ] Document measured loading-path change and commit: `git add tests docs/task-memory.md && git commit -m "test: cover lazy page loading"`.
