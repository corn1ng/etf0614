# Market ETF Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate `市场地图` into an index decision layer and move ETF chart drilldown into `ETF数据`.

**Architecture:** Keep the existing Streamlit page-module pattern. `navigation.py` owns page labels and sections, `pages/market.py` and `pages/portfolio.py` own lightweight routing, and `ui/app.py` keeps reusable render functions plus dependency wiring.

**Tech Stack:** Python 3.11, Streamlit, pandas, pytest, existing `etf_trading.ui` modules.

## Global Constraints

- Do not change strategy, backtest, ETF signal, or risk calculation logic.
- Do not add a new top-level `指数数据` navigation item.
- Do not remove the index ETF universe capability; keep it under `ETF数据` as ETF sample attribution.
- Reuse `platform_status["index_summary"]` for `市场地图` instead of recomputing index trend summaries.
- Preserve unrelated working-tree changes in `src/etf_trading/ui/app.py`, `tests/test_ui_index_picker.py`, and `docs/task-memory.md`.

---

### Task 1: Update Navigation Contract

**Files:**
- Modify: `src/etf_trading/ui/navigation.py`
- Test: `tests/test_ui_navigation.py`

**Interfaces:**
- Consumes: existing `PAGE_SPECS`, `page_labels()`, `section_options(page)`, `default_section(page)`.
- Produces: `PAGE_SPECS` where market sections are `("市场总览", "指数买卖参考", "指数K线")` and ETF data sections are `("ETF总览", "ETF行情", "搜索加入", "每日计算池", "指数样本池")`.

- [ ] **Step 1: Write the failing navigation assertions**

Replace the secondary-section assertions in `tests/test_ui_navigation.py`:

```python
assert sections_by_label["市场地图"] == ["市场总览", "指数买卖参考", "指数K线"]
assert sections_by_label["ETF数据"] == ["ETF总览", "ETF行情", "搜索加入", "每日计算池", "指数样本池"]
```

Also update the market header fixture caption in `test_render_page_header_outputs_compact_markup`:

```python
caption="观察指数和市场参与状态。",
...
assert "观察指数和市场参与状态。" in rendered["body"]
```

- [ ] **Step 2: Run the focused navigation test and verify it fails**

Run: `.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py::test_each_page_exposes_expected_secondary_sections -q`

Expected: FAIL because `PAGE_SPECS` still exposes `ETF行情` under `市场地图` and `数据总览` under `ETF数据`.

- [ ] **Step 3: Implement the navigation change**

In `src/etf_trading/ui/navigation.py`, update the market and portfolio page specs:

```python
PageSpec(
    slug="market",
    label="市场地图",
    caption="观察指数和市场参与状态，不承载 ETF 行情下钻。",
    sections=("市场总览", "指数买卖参考", "指数K线"),
),
PageSpec(
    slug="portfolio",
    label="ETF数据",
    caption="统一查看 ETF 主列表、行情、计算池和样本归属。",
    sections=("ETF总览", "ETF行情", "搜索加入", "每日计算池", "指数样本池"),
),
```

- [ ] **Step 4: Run the focused navigation test and verify it passes**

Run: `.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py::test_each_page_exposes_expected_secondary_sections tests/test_ui_navigation.py::test_render_page_header_outputs_compact_markup -q`

Expected: PASS.

### Task 2: Route Market And ETF Data Pages

**Files:**
- Modify: `src/etf_trading/ui/pages/market.py`
- Modify: `src/etf_trading/ui/pages/portfolio.py`
- Modify: `src/etf_trading/ui/app.py`
- Test: `tests/test_ui_navigation.py`

**Interfaces:**
- Consumes: `market.render(..., render_market_overview, render_index_filter_explorer, render_index_watch)`.
- Produces: `portfolio.render(..., render_etf_chart, render_data_overview, render_index_etf_pool, render_search_and_add, watchlist_status_frame)`.

- [ ] **Step 1: Write failing page-routing tests**

Add this test to `tests/test_ui_navigation.py`:

```python
def test_market_page_routes_index_decision_views():
    calls = {"overview": 0, "explorer": 0, "index_watch": 0}
    index_summary = pd.DataFrame({"index_code": ["000300"], "allows_new_position": [True]})

    app.market.render(
        store=object(),
        parquet_store=object(),
        view="市场总览",
        index_summary=index_summary,
        render_market_overview=lambda frame: calls.__setitem__("overview", calls["overview"] + 1),
        render_index_filter_explorer=lambda frame, parquet_store: calls.__setitem__("explorer", calls["explorer"] + 1),
        render_index_watch=lambda parquet_store: calls.__setitem__("index_watch", calls["index_watch"] + 1),
    )
    app.market.render(
        store=object(),
        parquet_store=object(),
        view="指数买卖参考",
        index_summary=index_summary,
        render_market_overview=lambda frame: calls.__setitem__("overview", calls["overview"] + 1),
        render_index_filter_explorer=lambda frame, parquet_store: calls.__setitem__("explorer", calls["explorer"] + 1),
        render_index_watch=lambda parquet_store: calls.__setitem__("index_watch", calls["index_watch"] + 1),
    )
    app.market.render(
        store=object(),
        parquet_store=object(),
        view="指数K线",
        index_summary=index_summary,
        render_market_overview=lambda frame: calls.__setitem__("overview", calls["overview"] + 1),
        render_index_filter_explorer=lambda frame, parquet_store: calls.__setitem__("explorer", calls["explorer"] + 1),
        render_index_watch=lambda parquet_store: calls.__setitem__("index_watch", calls["index_watch"] + 1),
    )

    assert calls == {"overview": 1, "explorer": 1, "index_watch": 1}
```

Update `test_portfolio_page_routes_etf_data_views` to include `render_etf_chart` and `view="ETF总览"`:

```python
calls = {"overview": 0, "chart": 0, "index_pool": 0}
...
view="ETF总览",
render_etf_chart=lambda store, parquet_store: calls.__setitem__("chart", calls["chart"] + 1),
...
app.portfolio.render(..., view="ETF行情", ...)
...
assert calls == {"overview": 1, "chart": 1, "index_pool": 1}
```

- [ ] **Step 2: Run the routing tests and verify they fail**

Run: `.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py::test_market_page_routes_index_decision_views tests/test_ui_navigation.py::test_portfolio_page_routes_etf_data_views -q`

Expected: FAIL because `market.render` does not accept `render_market_overview` and `portfolio.render` does not accept `render_etf_chart`.

- [ ] **Step 3: Implement page routing**

In `src/etf_trading/ui/pages/market.py`, replace the render signature and branches:

```python
def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    index_summary,
    render_market_overview,
    render_index_filter_explorer,
    render_index_watch,
) -> None:
    if view == "指数买卖参考":
        render_index_filter_explorer(index_summary, parquet_store)
        return
    if view == "指数K线":
        render_index_watch(parquet_store)
        return
    render_market_overview(index_summary)
```

In `src/etf_trading/ui/pages/portfolio.py`, add `render_etf_chart` and route `ETF总览` and `ETF行情`:

```python
def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    render_data_overview,
    render_etf_chart,
    render_index_etf_pool,
    render_search_and_add,
    watchlist_status_frame,
) -> None:
    watchlist = store.list_watchlist()

    if view == "ETF总览":
        render_data_overview(store, parquet_store)
        return

    if view == "ETF行情":
        render_etf_chart(store, parquet_store)
        return
```

In `src/etf_trading/ui/app.py`, update dispatch:

```python
render_market_overview=_render_market_overview,
...
render_etf_chart=_tab_chart,
```

- [ ] **Step 4: Run the routing tests and verify they pass**

Run: `.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py::test_market_page_routes_index_decision_views tests/test_ui_navigation.py::test_portfolio_page_routes_etf_data_views -q`

Expected: PASS.

### Task 3: Add Market Overview Renderer

**Files:**
- Modify: `src/etf_trading/ui/app.py`
- Test: `tests/test_ui_navigation.py`

**Interfaces:**
- Consumes: `_index_trend_display_frame(index_summary: pd.DataFrame) -> pd.DataFrame`, `_render_research_table(frame: pd.DataFrame, height: int | None = None) -> None`.
- Produces: `_render_market_overview(index_summary: pd.DataFrame) -> None`.

- [ ] **Step 1: Write failing market overview tests**

Add this test to `tests/test_ui_navigation.py`:

```python
def test_market_overview_summarizes_index_state(monkeypatch):
    metrics = []
    dataframe_calls = []

    class FakeMetricColumn:
        def metric(self, label, value):
            metrics.append((label, value))

    summary = pd.DataFrame(
        {
            "index_code": ["000300", "000905", "399006"],
            "category": ["A股宽基", "A股宽基", "A股成长"],
            "allows_new_position": [True, False, True],
        }
    )

    monkeypatch.setattr(app.st, "columns", lambda count: [FakeMetricColumn() for _ in range(count)])
    monkeypatch.setattr(app.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "dataframe", lambda frame, *args, **kwargs: dataframe_calls.append(frame.copy()))
    monkeypatch.setattr(app, "_render_research_table", lambda frame, height=None: dataframe_calls.append(frame.copy()))
    monkeypatch.setattr(app, "_index_trend_display_frame", lambda frame: frame[["index_code", "allows_new_position"]])

    app._render_market_overview(summary)

    assert metrics == [
        ("指数总数", "3"),
        ("可找买点", "2"),
        ("暂不参与", "1"),
        ("覆盖分类", "2"),
    ]
    category_frame = dataframe_calls[0]
    assert category_frame.to_dict("records") == [
        {"分类": "A股宽基", "指数数量": 2, "可参与数量": 1},
        {"分类": "A股成长", "指数数量": 1, "可参与数量": 1},
    ]
```

Also add an empty-state test:

```python
def test_market_overview_handles_empty_index_summary(monkeypatch):
    info_calls = []

    monkeypatch.setattr(app.st, "info", lambda body: info_calls.append(body))

    app._render_market_overview(pd.DataFrame())

    assert info_calls == ["暂无指数趋势数据。请到“数据维护 -> 补齐任务”补齐指数历史。"]
```

- [ ] **Step 2: Run the market overview tests and verify they fail**

Run: `.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py::test_market_overview_summarizes_index_state tests/test_ui_navigation.py::test_market_overview_handles_empty_index_summary -q`

Expected: FAIL because `_render_market_overview` is not defined.

- [ ] **Step 3: Implement `_render_market_overview`**

Add this function near `_render_data_health` in `src/etf_trading/ui/app.py`:

```python
def _render_market_overview(index_summary: pd.DataFrame) -> None:
    if index_summary.empty:
        st.info("暂无指数趋势数据。请到“数据维护 -> 补齐任务”补齐指数历史。")
        return

    available = index_summary.copy()
    if "allows_new_position" not in available.columns:
        available["allows_new_position"] = False
    if "category" not in available.columns:
        available["category"] = ""

    allowed_mask = available["allows_new_position"].fillna(False).astype(bool)
    category_count = int(available["category"].dropna().astype(str).replace("", pd.NA).dropna().nunique())
    metric_cols = st.columns(4)
    metric_cols[0].metric("指数总数", f"{len(available)}")
    metric_cols[1].metric("可找买点", f"{int(allowed_mask.sum())}")
    metric_cols[2].metric("暂不参与", f"{int((~allowed_mask).sum())}")
    metric_cols[3].metric("覆盖分类", f"{category_count}")

    category_summary = (
        available.assign(_allowed=allowed_mask)
        .groupby("category", dropna=False)
        .agg(指数数量=("category", "size"), 可参与数量=("_allowed", "sum"))
        .reset_index()
        .rename(columns={"category": "分类"})
    )
    category_summary["分类"] = category_summary["分类"].fillna("").replace("", "未分类")
    category_summary["可参与数量"] = category_summary["可参与数量"].astype(int)
    st.markdown("### 分类参与状态")
    st.dataframe(category_summary, width="stretch", hide_index=True, height=_compact_dataframe_height(category_summary, max_height=260))

    st.markdown("### 指数状态")
    _render_research_table(_index_trend_display_frame(index_summary), height=420)
```

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py -q`

Expected: PASS.

### Task 4: Verify Integration And Record Memory

**Files:**
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: all tests from earlier tasks.
- Produces: updated task memory entry with summary, verification command, and reusable notes.

- [ ] **Step 1: Run focused UI tests**

Run: `.venv-win\Scripts\python.exe -m pytest tests/test_ui_navigation.py tests/test_research_display_labels.py tests/test_ui_index_picker.py -q`

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `.venv-win\Scripts\python.exe -m pytest -q`

Expected: PASS.

- [ ] **Step 3: Append implementation memory**

Append this entry to `docs/task-memory.md` after existing entries:

```markdown
## 2026-07-05 - Implement market and ETF page boundary

- Summary: Moved ETF chart drilldown into `ETF数据`, made `市场地图` focus on market/index overview, index buy/sell reference, and index K lines.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q` passed.
- Watch out next time:
  - Route market pages by decision workflow, not by ETF-versus-index asset type.
  - Keep `platform_status["index_summary"]` as the shared source for market overview and index reference pages.
```

- [ ] **Step 4: Review final diff**

Run: `git diff -- src\etf_trading\ui\navigation.py src\etf_trading\ui\pages\market.py src\etf_trading\ui\pages\portfolio.py src\etf_trading\ui\app.py tests\test_ui_navigation.py docs\task-memory.md docs\superpowers\plans\2026-07-05-market-etf-boundary.md`

Expected: diff contains only the boundary implementation, the plan, and task-memory additions. Existing unrelated quick-index changes may still appear in `src\etf_trading\ui\app.py`, `tests\test_ui_index_picker.py`, and `docs\task-memory.md`; do not revert them and do not stage them unless explicitly requested.
