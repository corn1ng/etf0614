# Compact Workbench UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Streamlit ETF workbench globally more compact so each page's primary chart, table, or action appears earlier in the viewport.

**Architecture:** Add a reusable compact page header in `navigation.py`, use it from `app.py`, then tighten global CSS in `styles.py`. Remove duplicated per-page headings from page modules and compact the market-map index reference flow without changing data or trading logic.

**Tech Stack:** Python 3.11, Streamlit >=1.36.0, pandas, pytest, existing ETF workbench UI modules.

## Global Constraints

- Keep current business logic, data sources, strategy calculations, research runner behavior, Parquet layout, and SQLite schema unchanged.
- Do not add a new frontend framework.
- Keep long-running actions user-triggered.
- Keep data-missing, risk, sync failure, and research failure messages visible.
- Use TDD for production-code changes: write a failing test, verify it fails, implement, verify it passes.
- `git` is not available in this shell, so commit steps are documented but expected to be skipped here with the environment limitation recorded.

---

## File Structure

- Modify `src/etf_trading/ui/navigation.py`: add `render_page_header(page: PageSpec) -> None`.
- Modify `src/etf_trading/ui/app.py`: replace the large Streamlit title/caption with the compact page header.
- Modify `src/etf_trading/ui/styles.py`: add compact CSS for page header, headings, controls, alerts, metrics, status bars, and content spacing.
- Modify `src/etf_trading/ui/pages/decision.py`: remove duplicate page title and caption.
- Modify `src/etf_trading/ui/pages/market.py`: remove duplicate page title and caption.
- Modify `src/etf_trading/ui/pages/portfolio.py`: remove duplicate page title and caption.
- Modify `src/etf_trading/ui/pages/data_maintenance.py`: remove duplicate page title and caption.
- Modify `src/etf_trading/ui/app.py`: compact the index-buy-sell reference section by folding the long rule explanation and removing redundant headings.
- Modify `tests/test_ui_navigation.py`: add page-header rendering coverage and app routing assertion.
- Modify `tests/test_ui_styles.py`: assert compact CSS hooks and updated spacing.

---

### Task 1: Add Compact Page Header

**Files:**
- Modify: `src/etf_trading/ui/navigation.py`
- Modify: `src/etf_trading/ui/app.py`
- Modify: `tests/test_ui_navigation.py`

**Interfaces:**
- Consumes: `PageSpec(slug: str, label: str, caption: str, sections: tuple[str, ...])`
- Produces: `render_page_header(page: PageSpec) -> None`
- Keeps: `render_secondary_navigation(page: PageSpec) -> str`

- [ ] **Step 1: Write the failing page-header test**

Append this test to `tests/test_ui_navigation.py`:

```python
def test_render_page_header_outputs_compact_markup(monkeypatch):
    from etf_trading.ui.navigation import PageSpec, render_page_header

    rendered = {}

    def capture_markdown(body, *, unsafe_allow_html=False):
        rendered["body"] = body
        rendered["unsafe"] = unsafe_allow_html

    monkeypatch.setattr("etf_trading.ui.navigation.st.markdown", capture_markdown)
    page = PageSpec(
        slug="market",
        label="市场地图",
        caption="观察指数、ETF行情和趋势结构。",
        sections=("指数买卖参考",),
    )

    render_page_header(page)

    assert rendered["unsafe"] is True
    assert 'class="workbench-page-header"' in rendered["body"]
    assert 'class="workbench-page-header__title"' in rendered["body"]
    assert 'class="workbench-page-header__caption"' in rendered["body"]
    assert "市场地图" in rendered["body"]
    assert "观察指数、ETF行情和趋势结构。" in rendered["body"]
```

- [ ] **Step 2: Run the page-header test and verify it fails**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py::test_render_page_header_outputs_compact_markup -v
```

Expected: FAIL with `ImportError` or `AttributeError` because `render_page_header` does not exist.

- [ ] **Step 3: Implement the compact page header**

Modify `src/etf_trading/ui/navigation.py`:

```python
import html
```

Add this function after `resolve_section()`:

```python
def render_page_header(page: PageSpec) -> None:
    title = html.escape(page.label)
    caption = html.escape(page.caption)
    st.markdown(
        (
            '<div class="workbench-page-header">'
            f'<div class="workbench-page-header__title">{title}</div>'
            f'<div class="workbench-page-header__caption">{caption}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )
```

- [ ] **Step 4: Run the page-header test and verify it passes**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py::test_render_page_header_outputs_compact_markup -v
```

Expected: PASS.

- [ ] **Step 5: Write the failing app-routing test for the new page header**

Append this assertion to `test_main_reuses_platform_status_for_decision_page()` in `tests/test_ui_navigation.py`:

```python
    header_calls = {"page_header": 0}
```

Add this monkeypatch before `app.main()`:

```python
    monkeypatch.setattr(app, "render_page_header", lambda page: header_calls.__setitem__("page_header", header_calls["page_header"] + 1))
```

Add this assertion after `app.main()`:

```python
    assert header_calls["page_header"] == 1
```

- [ ] **Step 6: Run the app-routing test and verify it fails**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py::test_main_reuses_platform_status_for_decision_page -v
```

Expected: FAIL because `app.main()` still calls `st.title()` and `st.caption()` instead of `render_page_header()`.

- [ ] **Step 7: Route `main()` through the compact header**

Modify imports in `src/etf_trading/ui/app.py`:

```python
from etf_trading.ui.navigation import render_page_header, render_primary_navigation, render_secondary_navigation
```

Replace:

```python
    st.title(page.label)
    st.caption(page.caption)
    section = render_secondary_navigation(page)
```

with:

```python
    render_page_header(page)
    section = render_secondary_navigation(page)
```

- [ ] **Step 8: Run the app-routing test and verify it passes**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py::test_main_reuses_platform_status_for_decision_page -v
```

Expected: PASS.

- [ ] **Step 9: Commit if git is available**

Run:

```powershell
git add src/etf_trading/ui/navigation.py src/etf_trading/ui/app.py tests/test_ui_navigation.py
git commit -m "feat: add compact workbench page header"
```

Expected in this shell: skipped because `git` is not available.

---

### Task 2: Tighten Global UI Spacing

**Files:**
- Modify: `src/etf_trading/ui/styles.py`
- Modify: `tests/test_ui_styles.py`

**Interfaces:**
- Consumes: `inject_global_styles() -> None`
- Produces: CSS selectors `.workbench-page-header`, `.workbench-page-header__title`, `.workbench-page-header__caption`, compact `.workbench-topbar`, compact Streamlit control spacing.

- [ ] **Step 1: Write the failing compact-style assertions**

Update `tests/test_ui_styles.py` so `test_global_styles_keep_sidebar_compact()` includes these assertions:

```python
    assert 'padding: 0.55rem 0.5rem;' in css
    assert '.workbench-page-header' in css
    assert '.workbench-page-header__title' in css
    assert '.workbench-page-header__caption' in css
    assert 'margin: 0 0 0.35rem 0;' in css
    assert '[data-testid="stVerticalBlock"]' in css
    assert '[data-testid="stAlert"]' in css
```

If the existing sidebar padding assertion expects an older value, update it to:

```python
    assert 'padding: 0.55rem 0.5rem;' in css
```

- [ ] **Step 2: Run the compact-style test and verify it fails**

Run:

```powershell
python -m pytest tests/test_ui_styles.py::test_global_styles_keep_sidebar_compact -v
```

Expected: FAIL because the page-header and compact control CSS selectors are not present.

- [ ] **Step 3: Implement compact global CSS**

Modify `src/etf_trading/ui/styles.py` inside the `<style>` block:

```css
.block-container {
    padding-top: 0.55rem;
    padding-bottom: 1rem;
}
[data-testid="stSidebarContent"] {
    padding: 0.55rem 0.5rem;
}
.workbench-page-header {
    margin: 0 0 0.35rem 0;
}
.workbench-page-header__title {
    color: #111827;
    font-size: 1.35rem;
    font-weight: 720;
    line-height: 1.15;
    margin: 0;
}
.workbench-page-header__caption {
    color: #6b7280;
    font-size: 0.86rem;
    line-height: 1.25;
    margin-top: 0.12rem;
}
[data-testid="stVerticalBlock"] {
    gap: 0.45rem;
}
[data-testid="stAlert"] {
    padding: 0.55rem 0.7rem;
}
.workbench-topbar {
    margin: 0 0 0.45rem 0;
}
.workbench-topbar__item {
    padding: 0.48rem 0.65rem;
}
.index-status-code {
    margin: 0.2rem 0 0.45rem 0;
}
.index-status-code__item {
    padding: 0.52rem 0.65rem;
}
div[data-testid="stCaptionContainer"] {
    margin-bottom: 0.15rem;
}
h1, h2, h3 {
    margin-top: 0.25rem;
    margin-bottom: 0.35rem;
}
```

Keep the existing sidebar width and responsive media rules.

- [ ] **Step 4: Run the compact-style test and verify it passes**

Run:

```powershell
python -m pytest tests/test_ui_styles.py::test_global_styles_keep_sidebar_compact -v
```

Expected: PASS.

- [ ] **Step 5: Commit if git is available**

Run:

```powershell
git add src/etf_trading/ui/styles.py tests/test_ui_styles.py
git commit -m "style: tighten workbench spacing"
```

Expected in this shell: skipped because `git` is not available.

---

### Task 3: Remove Duplicate Page Headings

**Files:**
- Modify: `src/etf_trading/ui/pages/decision.py`
- Modify: `src/etf_trading/ui/pages/market.py`
- Modify: `src/etf_trading/ui/pages/portfolio.py`
- Modify: `src/etf_trading/ui/pages/data_maintenance.py`
- Modify: `tests/test_ui_navigation.py`

**Interfaces:**
- Keeps page `render(...) -> None` signatures unchanged.
- Removes page-module calls to `st.subheader()` and repeated page-level `st.caption()`.

- [ ] **Step 1: Write the failing duplicate-heading test**

Append this test to `tests/test_ui_navigation.py`:

```python
def test_page_modules_do_not_render_duplicate_page_titles(monkeypatch):
    calls = {"subheader": 0, "caption": 0}

    def count_subheader(*args, **kwargs):
        calls["subheader"] += 1

    def count_caption(*args, **kwargs):
        calls["caption"] += 1

    monkeypatch.setattr(app.decision.st, "subheader", count_subheader)
    monkeypatch.setattr(app.decision.st, "caption", count_caption)
    monkeypatch.setattr(app.decision.st, "columns", lambda count: [type("Col", (), {"metric": lambda self, *a, **k: None})() for _ in range(count)])
    monkeypatch.setattr(app.decision.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.decision.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.decision.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.decision.st, "markdown", lambda *args, **kwargs: None)

    status = {
        "index_summary": pd.DataFrame(),
        "eligible_categories": [],
        "watchlist": pd.DataFrame(),
        "enabled_watchlist": pd.DataFrame(),
        "issues": [],
        "eligible_index_count": 0,
    }

    app.decision.render(
        store=object(),
        parquet_store=object(),
        view="每日建议",
        status=status,
        render_status_cards=lambda current_status: None,
        render_next_steps=lambda current_status: None,
        index_trend_display_frame=lambda frame: frame,
        render_research_table=lambda frame, height=None: None,
        build_daily_advice_report=lambda store, parquet_store: None,
        watchlist_status_frame=lambda watchlist, parquet_store: watchlist,
    )

    assert calls["subheader"] == 0
    assert calls["caption"] == 0
```

- [ ] **Step 2: Run the duplicate-heading test and verify it fails**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py::test_page_modules_do_not_render_duplicate_page_titles -v
```

Expected: FAIL because `decision.render()` currently calls `st.subheader()` and `st.caption()`.

- [ ] **Step 3: Remove duplicate page-level headings**

Delete these paired calls from the start of each listed page module:

```python
st.subheader("今日行动")
st.caption("先看市场是否允许参与，再看计算池和今日建议；需要补数据时直接给下一步。")
```

```python
st.subheader("市场地图")
st.caption("先看指数过滤和趋势结构，再下钻到 ETF 行情。")
```

```python
st.subheader("ETF池")
st.caption("找 ETF、加入每日计算池，并检查买入许可和历史行情状态。")
```

```python
st.subheader("数据维护")
st.caption("低频维护入口：先看数据健康，再初始化数据、补齐指数历史、查看任务日志。")
```

- [ ] **Step 4: Run the duplicate-heading test and verify it passes**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py::test_page_modules_do_not_render_duplicate_page_titles -v
```

Expected: PASS.

- [ ] **Step 5: Commit if git is available**

Run:

```powershell
git add src/etf_trading/ui/pages tests/test_ui_navigation.py
git commit -m "refactor: remove duplicate workbench page headings"
```

Expected in this shell: skipped because `git` is not available.

---

### Task 4: Compact Market Map Index Reference Flow

**Files:**
- Modify: `src/etf_trading/ui/app.py`
- Modify: `tests/test_ui_navigation.py`

**Interfaces:**
- Keeps `_render_index_filter_explorer(index_summary: pd.DataFrame, parquet_store: ParquetStore) -> None`
- Keeps chart, status-code, trend-regime, and marker logic unchanged.

- [ ] **Step 1: Write the failing market-map compactness test**

Append this test to `tests/test_ui_navigation.py`:

```python
def test_index_filter_explorer_folds_long_rule_copy(monkeypatch):
    markdown_calls = []
    info_calls = []

    monkeypatch.setattr(app.st, "markdown", lambda body, *args, **kwargs: markdown_calls.append(str(body)))
    monkeypatch.setattr(app.st, "info", lambda body, *args, **kwargs: info_calls.append(str(body)))

    app._render_index_filter_explorer(pd.DataFrame(), object())

    assert all("### 指数级买卖参考" not in call for call in markdown_calls)
    assert all("#### 选择指数" not in call for call in markdown_calls)
    assert all("当前规则：三层趋势过滤" not in call for call in info_calls)
```

- [ ] **Step 2: Run the market-map compactness test and verify it fails**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py::test_index_filter_explorer_folds_long_rule_copy -v
```

Expected: FAIL because `_render_index_filter_explorer()` currently emits the large heading and long `st.info()` copy.

- [ ] **Step 3: Compact `_render_index_filter_explorer()`**

In `src/etf_trading/ui/app.py`, replace the first heading and long `st.info()` block:

```python
    st.markdown("### 指数级买卖参考")
    st.info(
        "当前规则：三层趋势过滤 + 长期趋势退出。入场先看大趋势是否向上或修复，再看中趋势是否转强，最后看小趋势是否出现右侧开始或回踩。"
        "持仓后不因短线过热或中期震荡直接卖出，只有长期趋势连续失效才退出。图上的 BUY/SELL 是指数过滤层参考，不是具体 ETF 下单。"
    )
```

with:

```python
    with st.expander("指数过滤规则", expanded=False):
        st.caption(
            "三层趋势过滤 + 长期趋势退出。BUY/SELL 是指数过滤层参考，不是具体 ETF 下单。"
        )
```

Delete this redundant heading:

```python
    st.markdown("#### 选择指数")
```

Keep the empty-data `st.info("暂无指数趋势数据。")` branch unchanged.

- [ ] **Step 4: Run the market-map compactness test and verify it passes**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py::test_index_filter_explorer_folds_long_rule_copy -v
```

Expected: PASS.

- [ ] **Step 5: Commit if git is available**

Run:

```powershell
git add src/etf_trading/ui/app.py tests/test_ui_navigation.py
git commit -m "refactor: compact market map index reference"
```

Expected in this shell: skipped because `git` is not available.

---

### Task 5: Final Verification

**Files:**
- Reads all changed files.

**Interfaces:**
- Verifies no business logic changed.
- Verifies compact UI tests and broader UI-adjacent tests pass.

- [ ] **Step 1: Run focused UI tests**

Run:

```powershell
python -m pytest tests/test_ui_styles.py tests/test_ui_navigation.py -v
```

Expected: PASS.

- [ ] **Step 2: Run broader UI-adjacent tests**

Run:

```powershell
python -m pytest tests/test_ui_styles.py tests/test_ui_navigation.py tests/test_ui_state.py tests/test_research_display_labels.py tests/test_report_and_chart.py -v
```

Expected: PASS.

- [ ] **Step 3: Inspect remaining large app page header usage**

Run:

```powershell
rg -n "st\.title\(page\.label\)|st\.subheader\(\"今日行动\"|st\.subheader\(\"市场地图\"|st\.subheader\(\"ETF池\"|st\.subheader\(\"数据维护\"" src\etf_trading\ui
```

Expected: no matches.

- [ ] **Step 4: Run import check**

Run:

```powershell
python -c "from etf_trading.ui.app import main; print(callable(main))"
```

Expected output:

```text
True
```

- [ ] **Step 5: Run full test suite if time and dependencies allow**

Run:

```powershell
python -m pytest
```

Expected: PASS.

- [ ] **Step 6: Commit if git is available**

Run:

```powershell
git add src/etf_trading/ui tests docs/superpowers/specs/2026-07-04-compact-workbench-ui-design.md docs/superpowers/plans/2026-07-04-compact-workbench-ui-implementation.md
git commit -m "style: compact workbench UI"
```

Expected in this shell: skipped because `git` is not available.
