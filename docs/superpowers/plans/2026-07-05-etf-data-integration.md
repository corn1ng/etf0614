# ETF Data Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clear ETF business hub and a global data-maintenance console that show ETF coverage, index sample membership, and missing-data gaps.

**Architecture:** Add a focused pure-data module for ETF overview and maintenance-gap aggregation, then wire those results into the existing Streamlit page modules. Navigation changes stay in `ui/navigation.py`; UI renderers stay in `ui/app.py` and `ui/pages/*`.

**Tech Stack:** Python, pandas, Streamlit, pytest, existing `SQLiteStore`, `ParquetStore`, and `build_index_etf_universe`.

## Global Constraints

- `ETF数据` is the business-facing ETF entry.
- `数据维护` is the global data quality and repair entry.
- User-facing ETF/index names and table headers must be Chinese, not mixed `Code`/`Name` labels.
- First version uses approximate business-day gaps; no external trading calendar integration.
- Do not change strategy backtest algorithms.

---

### Task 1: Add Tested Coverage Builders

**Files:**
- Create: `src/etf_trading/ui/data_coverage.py`
- Create: `tests/test_data_coverage.py`

**Interfaces:**
- Consumes: pandas DataFrames from ETF master, watchlist, index summary, index ETF universe, and a parquet-like object with `read_prices(code)`.
- Produces:
  - `expected_latest_trade_date(today: date | pd.Timestamp | None = None) -> pd.Timestamp`
  - `build_etf_data_overview(master: pd.DataFrame, watchlist: pd.DataFrame, parquet_store: object, universe: pd.DataFrame, min_history_rows: int = 252) -> pd.DataFrame`
  - `build_data_gap_detail(master: pd.DataFrame, watchlist: pd.DataFrame, index_summary: pd.DataFrame, universe: pd.DataFrame, parquet_store: object, today: date | pd.Timestamp | None = None, min_history_rows: int = 252) -> pd.DataFrame`
  - `build_data_coverage_summary(gaps: pd.DataFrame, master: pd.DataFrame, watchlist: pd.DataFrame, index_summary: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame`

- [ ] **Step 1: Write failing tests**

```python
def test_etf_data_overview_marks_watchlist_index_pool_and_history_status():
    store = FakeParquetStore({"510300": price_frame("2026-06-01", 300), "159915": price_frame("2026-01-01", 120)})
    overview = build_etf_data_overview(master_frame(), watchlist_frame(), store, universe_frame())
    assert overview.loc[overview["ETF代码"] == "510300", "每日计算池"].item() == "是"
    assert overview.loc[overview["ETF代码"] == "510300", "指数样本池"].item() == "是"
    assert overview.loc[overview["ETF代码"] == "510300", "本地历史"].item() == "已就绪"
    assert overview.loc[overview["ETF代码"] == "159915", "状态说明"].item() == "历史不足"
    assert overview.loc[overview["ETF代码"] == "513180", "状态说明"].item() == "未拉历史"
```

```python
def test_data_gap_detail_reports_missing_days_and_global_objects():
    store = FakeParquetStore({"510300": price_frame("2026-06-01", 300), "159915": price_frame("2026-01-01", 120)})
    gaps = build_data_gap_detail(
        master_frame(),
        watchlist_frame(),
        index_summary_frame(),
        universe_frame(),
        store,
        today=pd.Timestamp("2026-07-05"),
    )
    assert {"数据类型": "ETF历史", "代码": "513180", "状态": "未初始化"} in gaps.to_dict("records")
    row = gaps[gaps["代码"] == "510300"].iloc[0]
    assert row["本地最新日期"] == "2026-06-01"
    assert row["应有最新交易日"] == "2026-07-03"
    assert row["缺失天数"] > 0
    assert {"数据类型": "指数历史", "代码": "399006", "状态": "未初始化"} in gaps.to_dict("records")
```

- [ ] **Step 2: Run tests to verify RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests/test_data_coverage.py -v`

Expected: FAIL because `etf_trading.ui.data_coverage` does not exist.

- [ ] **Step 3: Implement coverage builders**

Implement the four public functions with these rules:
- ETF codes are normalized to six digits when numeric.
- `本地历史` values are `已就绪`, `历史不足`, `缺失`, or `读取失败`.
- Missing days count business days from the day after local latest date through the expected latest trade date.
- `expected_latest_trade_date(pd.Timestamp("2026-07-05"))` returns `2026-07-03`.
- Gap rows are emitted only for missing, insufficient, outdated, or failed objects.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests/test_data_coverage.py -v`

Expected: PASS.

### Task 2: Update Navigation Contracts

**Files:**
- Modify: `src/etf_trading/ui/navigation.py`
- Modify: `src/etf_trading/ui/app.py`
- Modify: `tests/test_ui_navigation.py`
- Modify: `tests/test_research_display_labels.py`

**Interfaces:**
- Consumes: existing `PAGE_SPECS`, `WORKFLOW_TABS`.
- Produces: new primary label `ETF数据` and new sections.

- [ ] **Step 1: Write failing navigation assertions**

Expected page labels:

```python
["今日行动", "市场地图", "ETF数据", "策略实验室", "数据维护"]
```

Expected `ETF数据` sections:

```python
["数据总览", "搜索加入", "每日计算池", "指数样本池"]
```

Expected `策略实验室` sections:

```python
["策略库", "新建策略", "运行回测", "策略比较", "ETF复盘", "指数过滤实验"]
```

Expected `数据维护` sections:

```python
["数据总览", "缺口明细", "补齐任务", "日志与设置"]
```

- [ ] **Step 2: Run focused navigation tests to verify RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py::test_primary_navigation_follows_investment_workflow tests/test_ui_navigation.py::test_each_page_exposes_expected_secondary_sections tests/test_research_display_labels.py::test_workspace_tabs_follow_investment_workflow -v`

Expected: FAIL with old `ETF池` and old data-maintenance sections.

- [ ] **Step 3: Update navigation definitions**

Update `PAGE_SPECS` and `WORKFLOW_TABS` to match the assertions. Update user-facing helper copy that still says `ETF池` or `数据中心` for this workflow.

- [ ] **Step 4: Run focused navigation tests to verify GREEN**

Run: same command as Step 2.

Expected: PASS.

### Task 3: Wire ETF数据 Pages

**Files:**
- Modify: `src/etf_trading/ui/pages/portfolio.py`
- Modify: `src/etf_trading/ui/app.py`
- Modify: `tests/test_ui_navigation.py`

**Interfaces:**
- Consumes:
  - `build_etf_data_overview(...)`
  - existing `_render_etf_search_and_add(...)`
  - existing `_watchlist_status_frame(...)`
  - existing `_render_index_etf_pool(universe)`
- Produces:
  - `_render_etf_data_overview(store: SQLiteStore, parquet_store: ParquetStore) -> None`
  - `_render_portfolio_index_etf_pool(store: SQLiteStore, parquet_store: ParquetStore) -> None`

- [ ] **Step 1: Write failing page-dispatch test**

In `tests/test_ui_navigation.py`, add a test that calls `portfolio.render(...)` with `view="数据总览"` and asserts the injected `render_data_overview` callback is called once. Add a second assertion for `view="指数样本池"` and `render_index_etf_pool`.

- [ ] **Step 2: Run test to verify RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py::test_portfolio_page_routes_etf_data_views -v`

Expected: FAIL because the callbacks are not accepted/routed yet.

- [ ] **Step 3: Implement page routing and renderers**

Update `portfolio.render` signature to accept `render_data_overview` and `render_index_etf_pool`. In `app.main`, pass `_render_etf_data_overview` and `_render_portfolio_index_etf_pool`. The overview renderer builds `master`, `watchlist`, `universe`, calls `build_etf_data_overview`, exposes compact filters, and renders a single table.

- [ ] **Step 4: Run page-dispatch test to verify GREEN**

Run: same command as Step 2.

Expected: PASS.

### Task 4: Wire 数据维护 Console

**Files:**
- Modify: `src/etf_trading/ui/pages/data_maintenance.py`
- Modify: `src/etf_trading/ui/app.py`
- Modify: `tests/test_ui_navigation.py`

**Interfaces:**
- Consumes:
  - `build_data_gap_detail(...)`
  - `build_data_coverage_summary(...)`
  - existing `_tab_data_center(...)` logic as the `补齐任务` view.
- Produces:
  - `_render_data_coverage_overview(store, parquet_store, status) -> None`
  - `_render_data_gap_detail(store, parquet_store, status) -> None`
  - `_render_data_repair_tasks(store, parquet_store) -> None`

- [ ] **Step 1: Write failing page-dispatch test**

Add a test that calls `data_maintenance.render(...)` with views `数据总览`, `缺口明细`, `补齐任务`, and `日志与设置`, asserting the correct injected callback is called for each.

- [ ] **Step 2: Run test to verify RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py::test_data_maintenance_routes_data_console_views -v`

Expected: FAIL because the new callbacks are not accepted/routed yet.

- [ ] **Step 3: Implement data-maintenance routing and renderers**

Update `data_maintenance.render` signature and `app.main` wiring. `数据总览` renders metric cards plus the coverage summary table. `缺口明细` renders the filtered gap table. `补齐任务` calls the existing initialization/history/index task UI with updated heading text.

- [ ] **Step 4: Run page-dispatch test to verify GREEN**

Run: same command as Step 2.

Expected: PASS.

### Task 5: Verify Integration

**Files:**
- Modify as required by failures only.

**Interfaces:**
- Consumes all previous tasks.
- Produces a passing test suite for this feature.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests/test_data_coverage.py tests/test_ui_navigation.py tests/test_research_display_labels.py tests/test_index_etf_universe.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full tests**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Inspect git diff**

Run:

```powershell
& 'C:\Users\cjj\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe' diff -- src/etf_trading/ui/data_coverage.py src/etf_trading/ui/navigation.py src/etf_trading/ui/pages/portfolio.py src/etf_trading/ui/pages/data_maintenance.py src/etf_trading/ui/app.py tests/test_data_coverage.py tests/test_ui_navigation.py tests/test_research_display_labels.py
```

Expected: Diff only includes the intended ETF data integration changes.
