# ETF Workbench Navigation Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current top-tab Streamlit workbench with a left-sidebar navigation shell, a compact top status bar, stable per-page secondary menus, and a maintainable UI module structure.

**Architecture:** Build the navigation shell first while preserving existing page behavior, then extract low-risk shared components, then migrate pages out of `ui/app.py`. Existing private helpers imported by tests from `etf_trading.ui.app` stay re-exported until tests are intentionally moved.

**Tech Stack:** Python 3.11, Streamlit >=1.36.0, pandas, Altair, pytest, existing SQLiteStore and ParquetStore.

## Global Constraints

- Do not change strategy logic, research calculations, data provider behavior, Parquet schema, or SQLite schema.
- Do not add a new frontend framework.
- Do not implement cross-module global search; optional search is limited to ETF code and name.
- Keep long-running actions user-triggered: index sync, ETF history fetch, index history fetch, and research runs.
- Preserve existing `renderLightweightCharts` JSON fallback behavior.
- Keep `tests/test_research_display_labels.py` passing by preserving `etf_trading.ui.app` imports for moved helper functions.
- If `git` is unavailable in the execution shell, run the listed verification command and record that the commit command could not run.

---

## File Structure

- Create `src/etf_trading/ui/navigation.py`: page and section configuration plus Streamlit navigation controls.
- Create `src/etf_trading/ui/state.py`: shared app context and pure status-summary helpers.
- Create `src/etf_trading/ui/styles.py`: global CSS injection.
- Create `src/etf_trading/ui/components/__init__.py`: component package marker.
- Create `src/etf_trading/ui/components/status.py`: top status bar, status cards, and next-step prompts.
- Create `src/etf_trading/ui/components/research_tables.py`: research table display helpers.
- Create `src/etf_trading/ui/components/charts.py`: chart display controls and range controls.
- Create `src/etf_trading/ui/pages/__init__.py`: page package marker.
- Create `src/etf_trading/ui/pages/decision.py`: daily action page.
- Create `src/etf_trading/ui/pages/market.py`: market map page.
- Create `src/etf_trading/ui/pages/portfolio.py`: ETF pool page.
- Create `src/etf_trading/ui/pages/research.py`: research replay page.
- Create `src/etf_trading/ui/pages/data_maintenance.py`: data maintenance page.
- Modify `src/etf_trading/ui/app.py`: shrink to app bootstrap, dependency creation, compatibility re-exports, and routing.
- Create `tests/test_ui_navigation.py`: pure navigation configuration tests.
- Create `tests/test_ui_state.py`: pure status summary tests.
- Modify `tests/test_research_display_labels.py`: only when a helper moves to a more specific module and no compatibility re-export exists.

---

### Task 1: Add Navigation Model and Pure Tests

**Files:**
- Create: `src/etf_trading/ui/navigation.py`
- Create: `tests/test_ui_navigation.py`

**Interfaces:**
- Produces: `PageSpec(slug: str, label: str, caption: str, sections: tuple[str, ...])`
- Produces: `PAGE_SPECS: tuple[PageSpec, ...]`
- Produces: `page_labels() -> list[str]`
- Produces: `default_page() -> PageSpec`
- Produces: `get_page_by_label(label: str | None) -> PageSpec`
- Produces: `section_options(page: PageSpec) -> list[str]`
- Produces: `default_section(page: PageSpec) -> str`
- Produces: `resolve_section(page: PageSpec, selected: str | None) -> str`
- Produces: `render_primary_navigation() -> PageSpec`
- Produces: `render_secondary_navigation(page: PageSpec) -> str`

- [ ] **Step 1: Write failing navigation tests**

Create `tests/test_ui_navigation.py`:

```python
from etf_trading.ui.navigation import (
    PAGE_SPECS,
    default_page,
    default_section,
    get_page_by_label,
    page_labels,
    resolve_section,
    section_options,
)


def test_primary_navigation_follows_investment_workflow():
    assert page_labels() == ["今日行动", "市场地图", "ETF池", "研究复盘", "数据维护"]
    assert [page.slug for page in PAGE_SPECS] == ["decision", "market", "portfolio", "research", "data"]


def test_each_page_exposes_expected_secondary_sections():
    sections_by_label = {page.label: section_options(page) for page in PAGE_SPECS}

    assert sections_by_label["今日行动"] == ["行动摘要", "每日建议", "计算池明细"]
    assert sections_by_label["市场地图"] == ["指数买卖参考", "ETF行情", "指数K线"]
    assert sections_by_label["ETF池"] == ["搜索加入", "每日计算池"]
    assert sections_by_label["研究复盘"] == ["研究总览", "策略对比", "ETF复盘", "明细表", "运行研究"]
    assert sections_by_label["数据维护"] == ["数据健康", "数据中心", "日志与设置"]


def test_navigation_defaults_to_daily_action_summary():
    page = default_page()

    assert page.label == "今日行动"
    assert default_section(page) == "行动摘要"


def test_unknown_page_and_section_fall_back_to_safe_defaults():
    page = get_page_by_label("不存在")

    assert page.label == "今日行动"
    assert resolve_section(page, "不存在") == "行动摘要"
```

- [ ] **Step 2: Run navigation tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'etf_trading.ui.navigation'`.

- [ ] **Step 3: Implement navigation model**

Create `src/etf_trading/ui/navigation.py`:

```python
"""Navigation configuration and controls for the Streamlit workbench."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class PageSpec:
    slug: str
    label: str
    caption: str
    sections: tuple[str, ...]


PAGE_SPECS: tuple[PageSpec, ...] = (
    PageSpec(
        slug="decision",
        label="今日行动",
        caption="先看市场是否允许参与，再看今日建议。",
        sections=("行动摘要", "每日建议", "计算池明细"),
    ),
    PageSpec(
        slug="market",
        label="市场地图",
        caption="观察指数、ETF行情和趋势结构。",
        sections=("指数买卖参考", "ETF行情", "指数K线"),
    ),
    PageSpec(
        slug="portfolio",
        label="ETF池",
        caption="搜索 ETF、加入每日计算池并检查历史行情。",
        sections=("搜索加入", "每日计算池"),
    ),
    PageSpec(
        slug="research",
        label="研究复盘",
        caption="查看策略研究、对比结果和单 ETF 复盘。",
        sections=("研究总览", "策略对比", "ETF复盘", "明细表", "运行研究"),
    ),
    PageSpec(
        slug="data",
        label="数据维护",
        caption="检查数据健康、补齐历史和查看日志。",
        sections=("数据健康", "数据中心", "日志与设置"),
    ),
)


def page_labels() -> list[str]:
    return [page.label for page in PAGE_SPECS]


def default_page() -> PageSpec:
    return PAGE_SPECS[0]


def get_page_by_label(label: str | None) -> PageSpec:
    for page in PAGE_SPECS:
        if page.label == label:
            return page
    return default_page()


def section_options(page: PageSpec) -> list[str]:
    return list(page.sections)


def default_section(page: PageSpec) -> str:
    return page.sections[0]


def resolve_section(page: PageSpec, selected: str | None) -> str:
    if selected in page.sections:
        return str(selected)
    return default_section(page)


def render_primary_navigation() -> PageSpec:
    with st.sidebar:
        st.markdown("### ETF 工作台")
        selected = st.radio(
            "主菜单",
            page_labels(),
            index=0,
            key="primary_navigation",
            label_visibility="collapsed",
        )
    return get_page_by_label(selected)


def render_secondary_navigation(page: PageSpec) -> str:
    options = section_options(page)
    control = getattr(st, "segmented_control", None)
    if control is not None:
        selected = control(
            "页面视图",
            options,
            default=default_section(page),
            key=f"secondary_navigation_{page.slug}",
        )
        return resolve_section(page, selected)

    selected = st.radio(
        "页面视图",
        options,
        horizontal=True,
        key=f"secondary_navigation_{page.slug}",
    )
    return resolve_section(page, selected)
```

- [ ] **Step 4: Run navigation tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit navigation model**

Run:

```powershell
git add src/etf_trading/ui/navigation.py tests/test_ui_navigation.py
git commit -m "feat: add workbench navigation model"
```

Expected: commit succeeds when `git` is available.

---

### Task 2: Add Status Summary State Helpers

**Files:**
- Create: `src/etf_trading/ui/state.py`
- Create: `tests/test_ui_state.py`

**Interfaces:**
- Consumes: existing `_platform_status()` dictionary shape from `src/etf_trading/ui/app.py`
- Produces: `StatusSummary`
- Produces: `summarize_platform_status(status: Mapping[str, object]) -> StatusSummary`

- [ ] **Step 1: Write failing status summary tests**

Create `tests/test_ui_state.py`:

```python
import pandas as pd

from etf_trading.ui.state import summarize_platform_status


def test_status_summary_marks_ready_platform_when_no_issues():
    status = {
        "eligible_index_count": 3,
        "eligible_categories": ["A股宽基", "A股行业"],
        "enabled_watchlist": pd.DataFrame({"etf_code": ["510300", "512880"]}),
        "issues": [],
    }

    summary = summarize_platform_status(status)

    assert summary.data_health == "已就绪"
    assert summary.eligible_index_count == 3
    assert summary.eligible_category_count == 2
    assert summary.enabled_watchlist_count == 2
    assert summary.issue_count == 0


def test_status_summary_marks_attention_when_issues_exist():
    status = {
        "eligible_index_count": 0,
        "eligible_categories": [],
        "enabled_watchlist": pd.DataFrame(),
        "issues": [
            {"title": "补齐指数历史", "detail": "数据维护中执行一键补齐。"},
            {"title": "建立每日计算池", "detail": "ETF池中加入常看 ETF。"},
        ],
    }

    summary = summarize_platform_status(status)

    assert summary.data_health == "需处理"
    assert summary.eligible_index_count == 0
    assert summary.eligible_category_count == 0
    assert summary.enabled_watchlist_count == 0
    assert summary.issue_count == 2
```

- [ ] **Step 2: Run status summary tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_ui_state.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'etf_trading.ui.state'`.

- [ ] **Step 3: Implement state helpers**

Create `src/etf_trading/ui/state.py`:

```python
"""Shared UI state helpers for the Streamlit workbench."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class StatusSummary:
    data_health: str
    eligible_index_count: int
    eligible_category_count: int
    enabled_watchlist_count: int
    issue_count: int


def summarize_platform_status(status: Mapping[str, object]) -> StatusSummary:
    issues = status.get("issues", [])
    issue_count = len(issues) if isinstance(issues, list) else 0

    eligible_categories = status.get("eligible_categories", [])
    eligible_category_count = len(eligible_categories) if isinstance(eligible_categories, list) else 0

    enabled_watchlist = status.get("enabled_watchlist", pd.DataFrame())
    enabled_watchlist_count = len(enabled_watchlist) if isinstance(enabled_watchlist, pd.DataFrame) else 0

    return StatusSummary(
        data_health="已就绪" if issue_count == 0 else "需处理",
        eligible_index_count=int(status.get("eligible_index_count", 0) or 0),
        eligible_category_count=eligible_category_count,
        enabled_watchlist_count=enabled_watchlist_count,
        issue_count=issue_count,
    )
```

- [ ] **Step 4: Run status summary tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_ui_state.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit state helpers**

Run:

```powershell
git add src/etf_trading/ui/state.py tests/test_ui_state.py
git commit -m "feat: add workbench status summary"
```

Expected: commit succeeds when `git` is available.

---

### Task 3: Add Global Styles and Top Status Component

**Files:**
- Create: `src/etf_trading/ui/styles.py`
- Create: `src/etf_trading/ui/components/__init__.py`
- Create: `src/etf_trading/ui/components/status.py`

**Interfaces:**
- Consumes: `StatusSummary` from `etf_trading.ui.state`
- Produces: `inject_global_styles() -> None`
- Produces: `render_top_status_bar(summary: StatusSummary) -> None`
- Produces: `render_status_cards(status: dict[str, object]) -> None`
- Produces: `render_next_steps(status: dict[str, object]) -> None`

- [ ] **Step 1: Create global style injector**

Create `src/etf_trading/ui/styles.py`:

```python
"""CSS helpers for the Streamlit workbench."""

from __future__ import annotations

import streamlit as st


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.1rem;
        }
        [data-testid="stSidebar"] {
            min-width: 15rem;
        }
        [data-testid="stMetricLabel"] p {
            white-space: normal;
            overflow: visible;
            text-overflow: clip;
            line-height: 1.25;
        }
        .workbench-topbar {
            display: grid;
            grid-template-columns: minmax(220px, 1.6fr) repeat(5, minmax(120px, 1fr));
            gap: 1px;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            overflow: hidden;
            background: #e5e7eb;
            margin: 0 0 1rem 0;
        }
        .workbench-topbar__item {
            background: #ffffff;
            padding: 0.65rem 0.8rem;
            min-width: 0;
        }
        .workbench-topbar__label {
            color: #6b7280;
            font-size: 0.78rem;
            line-height: 1.2;
        }
        .workbench-topbar__value {
            color: #111827;
            font-size: 1.05rem;
            font-weight: 650;
            line-height: 1.25;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .index-status-code {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 1px;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            overflow: hidden;
            margin: 0.35rem 0 1rem 0;
            background: #e5e7eb;
        }
        .index-status-code__item {
            background: #ffffff;
            padding: 0.75rem 0.9rem;
            min-width: 0;
        }
        .index-status-code__label {
            color: #6b7280;
            font-size: 0.82rem;
            line-height: 1.2;
            margin-bottom: 0.35rem;
        }
        .index-status-code__value {
            color: #111827;
            font-size: 1.3rem;
            font-weight: 650;
            line-height: 1.2;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        @media (max-width: 900px) {
            .workbench-topbar {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .index-status-code {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
```

- [ ] **Step 2: Create component package marker**

Create `src/etf_trading/ui/components/__init__.py`:

```python
"""Reusable Streamlit UI components."""
```

- [ ] **Step 3: Create status components**

Create `src/etf_trading/ui/components/status.py`:

```python
"""Status display components for the workbench."""

from __future__ import annotations

import html

import streamlit as st

from etf_trading.ui.state import StatusSummary


def render_top_status_bar(summary: StatusSummary) -> None:
    items = [
        ("工作台", "ETF 今日行动"),
        ("数据健康", summary.data_health),
        ("可参与指数", str(summary.eligible_index_count)),
        ("可参与分类", str(summary.eligible_category_count)),
        ("计算池 ETF", str(summary.enabled_watchlist_count)),
        ("数据缺口", str(summary.issue_count)),
    ]
    cells = "".join(
        (
            '<div class="workbench-topbar__item">'
            f'<div class="workbench-topbar__label">{html.escape(label)}</div>'
            f'<div class="workbench-topbar__value">{html.escape(value)}</div>'
            "</div>"
        )
        for label, value in items
    )
    st.markdown(f'<div class="workbench-topbar">{cells}</div>', unsafe_allow_html=True)


def render_status_cards(status: dict[str, object]) -> None:
    cols = st.columns(4)
    cols[0].metric("可参与指数", f"{int(status['eligible_index_count'])}")
    cols[1].metric("可参与分类", f"{len(status['eligible_categories'])}")
    cols[2].metric("计算池 ETF", f"{len(status['enabled_watchlist'])}")
    cols[3].metric("数据缺口", f"{len(status['issues'])}")


def render_next_steps(status: dict[str, object]) -> None:
    issues = status["issues"]
    if not issues:
        st.success("数据和计算池已就绪，可以直接查看今日建议。")
        return

    st.warning("当前还有准备项未完成，建议按下面顺序处理：")
    for index, issue in enumerate(issues, start=1):
        st.markdown(f"{index}. **{issue['title']}**：{issue['detail']}")
```

- [ ] **Step 4: Run focused import checks**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py tests/test_ui_state.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit style and status components**

Run:

```powershell
git add src/etf_trading/ui/styles.py src/etf_trading/ui/components/__init__.py src/etf_trading/ui/components/status.py
git commit -m "feat: add workbench status components"
```

Expected: commit succeeds when `git` is available.

---

### Task 4: Replace Top Tabs With Sidebar Navigation Shell

**Files:**
- Modify: `src/etf_trading/ui/app.py`

**Interfaces:**
- Consumes: `render_primary_navigation() -> PageSpec`
- Consumes: `render_top_status_bar(summary: StatusSummary) -> None`
- Consumes: `summarize_platform_status(status: Mapping[str, object]) -> StatusSummary`
- Produces: `main() -> None` with sidebar primary navigation and top status bar

- [ ] **Step 1: Add navigation and status imports**

Modify the import block in `src/etf_trading/ui/app.py`:

```python
from etf_trading.ui.components.status import render_top_status_bar
from etf_trading.ui.navigation import render_primary_navigation
from etf_trading.ui.state import summarize_platform_status
from etf_trading.ui.styles import inject_global_styles
```

- [ ] **Step 2: Replace `main()` tab routing**

Replace the existing `main()` body with:

```python
def main() -> None:
    st.set_page_config(page_title="ETF 今日行动工作台", layout="wide")
    inject_global_styles()

    store = _store()
    parquet_store = _parquet()
    service = InitializationService(store=store, provider=None, parquet_store=parquet_store)

    page = render_primary_navigation()
    status = _platform_status(store, parquet_store)

    render_top_status_bar(summarize_platform_status(status))
    st.title(page.label)
    st.caption(page.caption)

    if page.slug == "decision":
        _tab_decision(store, parquet_store)
    elif page.slug == "market":
        _tab_market_watch(store, parquet_store)
    elif page.slug == "portfolio":
        _tab_portfolio(store, parquet_store)
    elif page.slug == "research":
        _tab_research(store, parquet_store)
    else:
        _tab_data_and_settings(store, parquet_store, service)
```

- [ ] **Step 3: Remove old top-level title copy**

Delete these lines from `main()`:

```python
st.title("ETF 今日行动工作台")
st.caption("动线版 v2：今日行动 -> 市场地图 -> ETF池 -> 研究复盘 -> 数据维护。本系统只输出仓位比例和交易指引，不自动下单。")
st.info("已切换为任务流版：先看今日能不能参与，再看市场地图、管理 ETF 池、复盘研究，最后做数据维护。")
tabs = st.tabs(WORKFLOW_TABS)
```

Delete the `with tabs[...]` routing block that follows those lines.

- [ ] **Step 4: Keep `WORKFLOW_TABS` for compatibility tests**

Leave this constant in `app.py`:

```python
WORKFLOW_TABS = ["今日行动", "市场地图", "ETF池", "研究复盘", "数据维护"]
```

Existing tests import it from `etf_trading.ui.app`.

- [ ] **Step 5: Run UI-adjacent tests**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py tests/test_ui_state.py tests/test_research_display_labels.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit sidebar shell**

Run:

```powershell
git add src/etf_trading/ui/app.py
git commit -m "feat: replace workbench tabs with sidebar navigation"
```

Expected: commit succeeds when `git` is available.

---

### Task 5: Add Secondary Navigation Routing to Existing Pages

**Files:**
- Modify: `src/etf_trading/ui/app.py`

**Interfaces:**
- Consumes: `render_secondary_navigation(page: PageSpec) -> str`
- Produces: `_tab_decision(store: SQLiteStore, parquet_store: ParquetStore, view: str | None = None) -> None`
- Produces: `_tab_market_watch(store: SQLiteStore, parquet_store: ParquetStore, view: str | None = None) -> None`
- Produces: `_tab_portfolio(store: SQLiteStore, parquet_store: ParquetStore, view: str | None = None) -> None`
- Produces: `_tab_data_and_settings(store: SQLiteStore, parquet_store: ParquetStore, service: InitializationService, view: str | None = None) -> None`
- Produces: `_tab_research(store: SQLiteStore, parquet_store: ParquetStore, research_view: str | None = None) -> None`

- [ ] **Step 1: Import secondary navigation**

Modify the navigation import in `app.py`:

```python
from etf_trading.ui.navigation import render_primary_navigation, render_secondary_navigation
```

- [ ] **Step 2: Render secondary navigation in `main()`**

Update the routing part of `main()`:

```python
    section = render_secondary_navigation(page)

    if page.slug == "decision":
        _tab_decision(store, parquet_store, view=section)
    elif page.slug == "market":
        _tab_market_watch(store, parquet_store, view=section)
    elif page.slug == "portfolio":
        _tab_portfolio(store, parquet_store, view=section)
    elif page.slug == "research":
        _tab_research(store, parquet_store, research_view=section)
    else:
        _tab_data_and_settings(store, parquet_store, service, view=section)
```

- [ ] **Step 3: Update `_tab_decision()`**

Change the signature:

```python
def _tab_decision(store: SQLiteStore, parquet_store: ParquetStore, view: str | None = None) -> None:
```

Replace the existing `st.radio("今日视图", ...)` assignment with:

```python
    if view is None:
        view = st.radio(
            "今日视图",
            ["行动摘要", "每日建议", "计算池明细"],
            horizontal=True,
            key="daily_action_view",
        )
```

Leave the existing `if view == "行动摘要"` branches unchanged.

- [ ] **Step 4: Update `_tab_market_watch()`**

Change the signature:

```python
def _tab_market_watch(store: SQLiteStore, parquet_store: ParquetStore, view: str | None = None) -> None:
```

Replace the existing `st.radio("地图视图", ...)` assignment with:

```python
    if view is None:
        view = st.radio("地图视图", ["指数买卖参考", "ETF行情", "指数K线"], horizontal=True, key="market_map_view")
```

Leave the existing branch behavior unchanged.

- [ ] **Step 5: Update `_tab_portfolio()`**

Change the signature:

```python
def _tab_portfolio(store: SQLiteStore, parquet_store: ParquetStore, view: str | None = None) -> None:
```

Replace the body after the caption with:

```python
    view = view or "搜索加入"
    watchlist = store.list_watchlist()

    if view == "搜索加入":
        _render_etf_search_and_add(store)
        st.markdown("### 每日计算池")
        if watchlist.empty:
            st.info("每日计算池为空。请先在上方搜索 ETF 并保存。")
        else:
            st.dataframe(_watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=320)
        return

    st.markdown("### 每日计算池")
    if watchlist.empty:
        st.info("每日计算池为空。请先在“搜索加入”中保存 ETF。")
    else:
        st.dataframe(_watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=520)
```

- [ ] **Step 6: Extract quick index sync helper**

Create this helper near `_tab_data_and_settings()`:

```python
def _render_index_quick_sync(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    quick_cols = st.columns([1, 2])
    if quick_cols[0].button("一键补齐全部指数", type="primary", width="stretch", key="data_quick_sync_indexes"):
        provider = _provider()
        sync_service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
        with st.spinner("正在检查并补齐全部指数历史..."):
            summary = sync_service.ensure_all_index_history(date.today())
        level, message = _index_sync_status_message(summary)
        st.session_state["latest_index_sync_message"] = {"level": level, "message": message}
        st.session_state["latest_index_sync_summary"] = summary
    quick_cols[1].caption("指数历史是今日行动和研究过滤的前置数据；补齐后回到“今日行动”查看可参与范围。")
    _render_latest_index_sync_result()
```

- [ ] **Step 7: Update `_tab_data_and_settings()`**

Change the signature:

```python
def _tab_data_and_settings(
    store: SQLiteStore,
    parquet_store: ParquetStore,
    service: InitializationService,
    view: str | None = None,
) -> None:
```

Replace the body after the caption with:

```python
    status = _platform_status(store, parquet_store)
    view = view or "数据健康"

    if view == "数据健康":
        _render_data_health(status)
        _render_index_quick_sync(store, parquet_store)
    elif view == "数据中心":
        _render_data_health(status)
        _render_index_quick_sync(store, parquet_store)
        _tab_data_center(store, parquet_store)
    else:
        _render_data_health(status)
        _tab_settings(store, service)
```

- [ ] **Step 8: Extract research run controls**

Inside `_tab_research()`, move the entire current block that starts with:

```python
with st.expander("运行研究", expanded=False):
```

into a new helper:

```python
def _render_research_run_controls(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    index_summary: pd.DataFrame,
    min_rows: int,
    job_manager: ResearchJobManager,
    output_dir: Path,
) -> None:
    with st.expander("运行研究", expanded=True):
        st.caption("重新运行会在后台执行；停止不会覆盖旧结果。建议先同步指数数据，再运行趋势研究。")
        col1, col2, col3 = st.columns([1, 1, 2])
        min_rows = int(col1.number_input("最少历史行数", min_value=120, max_value=1200, value=min_rows, step=20))
        limit_input = col2.number_input("最多ETF数量", min_value=0, max_value=1000, value=0, step=10)
        limit = int(limit_input) or None
        use_index_filter = col3.checkbox("按当前指数趋势过滤ETF范围", value=True, key="research_use_index_filter")

        sync_cols = st.columns([1, 1, 2])
        sync_end = sync_cols[1].date_input("指数同步到", value=date.today(), key="research_index_sync_end")
        if sync_cols[0].button("先同步指数历史", key="research_sync_indexes"):
            provider = _provider()
            sync_service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
            with st.spinner("正在同步指数历史到今天..."):
                try:
                    sync_summary = sync_service.ensure_all_index_history(sync_end)
                except Exception as exc:  # noqa: BLE001 - UI should preserve provider failure text
                    st.session_state["latest_index_sync_message"] = {
                        "level": "error",
                        "message": f"指数同步失败：{exc}",
                    }
                    st.session_state.pop("latest_index_sync_summary", None)
                else:
                    level, message = _index_sync_status_message(sync_summary)
                    st.session_state["latest_index_sync_message"] = {"level": level, "message": message}
                    st.session_state["latest_index_sync_summary"] = sync_summary
            st.rerun()
        sync_cols[2].caption("趋势研究依赖指数过滤。若指数历史滞后，先同步再运行。")
        _render_latest_index_sync_result()

        candidates = load_research_candidates(RESEARCH_CONFIG)
        categories = _category_map(store)
        research_codes = None
        if use_index_filter:
            eligible_categories = _eligible_index_categories(index_summary)
            research_codes = _filter_etf_codes_by_categories(store.list_etf_master(), eligible_categories)

        confirm_nonce = int(st.session_state.setdefault("research_run_confirm_nonce", 0))
        confirm_run = st.checkbox("确认运行本次趋势研究", value=False, key=f"confirm_research_run_{confirm_nonce}")
        if st.button("开始运行趋势研究", width="stretch", disabled=job_manager.is_running() or not confirm_run):
            if use_index_filter and not research_codes:
                st.error("指数趋势过滤后没有可回测ETF，本次不运行策略回测。")
                return
            scope_text = "指数趋势过滤后" if use_index_filter else "全市场模式"
            started = job_manager.start(
                parquet_root=PARQUET_ROOT,
                candidates=candidates,
                categories=categories,
                min_rows=min_rows,
                limit=limit,
                etf_codes=research_codes,
                output_dir=output_dir,
                index_summary=index_summary,
                scope_text=scope_text,
            )
            if started:
                st.success("趋势研究已在后台启动。运行中可以点击停止，不会覆盖旧结果，完成后刷新本页即可查看新结果。")
                st.session_state["research_run_confirm_nonce"] = confirm_nonce + 1
                st.rerun()
            else:
                st.warning("已有趋势研究正在运行。")
```

- [ ] **Step 9: Update `_tab_research()` selection handling**

Change the signature:

```python
def _tab_research(store: SQLiteStore, parquet_store: ParquetStore, research_view: str | None = None) -> None:
```

Replace the current research view radio with:

```python
    research_view = research_view or st.radio(
        "研究视图",
        ["研究总览", "策略对比", "ETF复盘", "明细表", "运行研究"],
        horizontal=True,
        key="research_view",
    )
```

Replace the old inline run expander block with:

```python
    if research_view == "运行研究":
        _render_research_run_controls(
            store=store,
            parquet_store=parquet_store,
            index_summary=index_summary,
            min_rows=min_rows,
            job_manager=job_manager,
            output_dir=output_dir,
        )
        return
```

Keep `_render_research_job_status(job_manager)` above this branch so running tasks remain visible.

- [ ] **Step 10: Run UI-adjacent tests**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py tests/test_ui_state.py tests/test_research_display_labels.py -v
```

Expected: PASS.

- [ ] **Step 11: Commit secondary routing**

Run:

```powershell
git add src/etf_trading/ui/app.py
git commit -m "feat: add secondary workbench navigation"
```

Expected: commit succeeds when `git` is available.

---

### Task 6: Extract Research Table Components While Preserving App Imports

**Files:**
- Create: `src/etf_trading/ui/components/research_tables.py`
- Modify: `src/etf_trading/ui/app.py`
- Test: `tests/test_research_display_labels.py`

**Interfaces:**
- Moves from `app.py`: `_research_column_config(frame: pd.DataFrame) -> dict[str, object]`
- Moves from `app.py`: `_render_research_table(frame: pd.DataFrame, *, height: int | None = None) -> None`
- Moves from `app.py`: `_research_bar_chart(...) -> alt.Chart`
- Keeps app compatibility imports for these private names.

- [ ] **Step 1: Create research table component module**

Create `src/etf_trading/ui/components/research_tables.py` with the exact definitions of these functions copied from `app.py`:

```python
"""Research table and chart components."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st


def research_column_config(
    frame: pd.DataFrame,
    *,
    compact_header_labels: dict[str, str],
    percent_labels: set[str],
    count_labels: set[str],
) -> dict[str, object]:
    config: dict[str, object] = {}
    for column in frame.columns:
        label = compact_header_labels.get(column, column)
        if column == "ETF代码 ETF Code":
            config[column] = st.column_config.TextColumn(label, width=92)
        elif column == "ETF名称 ETF Name":
            config[column] = st.column_config.TextColumn(label, width=160)
        elif column == "指数代码 Index Code":
            config[column] = st.column_config.TextColumn(label, width=92)
        elif column == "指数名称 Index Name":
            config[column] = st.column_config.TextColumn(label, width=150)
        elif column in {"大趋势 Large Trend", "中趋势 Medium Trend", "小趋势 Small Trend"}:
            config[column] = st.column_config.TextColumn(label, width=132)
        elif column == "可开仓 Eligible":
            config[column] = st.column_config.TextColumn(label, width=118)
        elif column in percent_labels:
            config[column] = st.column_config.NumberColumn(label, format="%.1f%%", width=112)
        elif column in count_labels:
            config[column] = st.column_config.NumberColumn(label, format="%.0f", width=82)
        elif pd.api.types.is_numeric_dtype(frame[column]):
            config[column] = st.column_config.NumberColumn(label, format="%.2f", width=88)
        elif column in {"候选策略 Strategy", "基准策略 Base Strategy"}:
            config[column] = st.column_config.TextColumn(label, width=260)
        elif column == "分类 Category":
            config[column] = st.column_config.TextColumn(label, width=88)
        else:
            config[column] = st.column_config.TextColumn(label, width=90)
    return config


def render_research_table(
    frame: pd.DataFrame,
    *,
    column_config: dict[str, object],
    height: int | None = None,
) -> None:
    st.dataframe(
        frame,
        width="stretch",
        height=height or "auto",
        hide_index=True,
        column_config=column_config,
        row_height=34,
    )


def research_bar_chart(
    frame: pd.DataFrame,
    index_column: str,
    value_column: str,
    *,
    title: str,
    color: str,
    percent_columns: set[str],
    column_labels: dict[str, str],
    candidate_display_name,
    height_per_row: int = 34,
) -> alt.Chart:
    if index_column not in frame.columns or value_column not in frame.columns:
        return alt.Chart(pd.DataFrame({"策略 Strategy": [], "数值 Value": []})).mark_bar()

    data = frame[[index_column, value_column]].dropna().copy()
    if index_column in {"candidate_name", "base_candidate"}:
        data[index_column] = data[index_column].map(candidate_display_name)
    data = data.rename(columns={index_column: "策略 Strategy", value_column: "数值 Value"})
    if value_column in percent_columns:
        data["数值 Value"] = data["数值 Value"] * 100
        value_format = ".1f"
        axis_title = f"{column_labels.get(value_column, value_column)} (%)"
    else:
        value_format = ".3f"
        axis_title = column_labels.get(value_column, value_column)

    row_count = max(len(data), 1)
    chart_height = max(150, min(420, row_count * height_per_row))
    tooltip_title = column_labels.get(value_column, value_column)
    return (
        alt.Chart(data)
        .mark_bar(color=color)
        .encode(
            y=alt.Y("策略 Strategy:N", sort="-x", title=None),
            x=alt.X("数值 Value:Q", title=axis_title),
            tooltip=[
                alt.Tooltip("策略 Strategy:N", title="策略 Strategy"),
                alt.Tooltip("数值 Value:Q", title=tooltip_title, format=value_format),
            ],
        )
        .properties(title=title, height=chart_height)
    )
```

- [ ] **Step 2: Wrap component functions in `app.py`**

Add this import:

```python
from etf_trading.ui.components.research_tables import (
    render_research_table,
    research_bar_chart,
    research_column_config,
)
```

Replace `_research_column_config()` in `app.py` with:

```python
def _research_column_config(frame: pd.DataFrame) -> dict[str, object]:
    return research_column_config(
        frame,
        compact_header_labels=RESEARCH_COMPACT_HEADER_LABELS,
        percent_labels=RESEARCH_PERCENT_LABELS,
        count_labels=RESEARCH_COUNT_LABELS,
    )
```

Replace `_render_research_table()` in `app.py` with:

```python
def _render_research_table(frame: pd.DataFrame, *, height: int | None = None) -> None:
    render_research_table(frame, column_config=_research_column_config(frame), height=height)
```

Replace `_research_bar_chart()` in `app.py` with:

```python
def _research_bar_chart(
    frame: pd.DataFrame,
    index_column: str,
    value_column: str,
    *,
    title: str,
    color: str,
    height_per_row: int = 34,
) -> alt.Chart:
    return research_bar_chart(
        frame,
        index_column,
        value_column,
        title=title,
        color=color,
        percent_columns=RESEARCH_PERCENT_COLUMNS,
        column_labels=RESEARCH_COLUMN_LABELS,
        candidate_display_name=_candidate_display_name,
        height_per_row=height_per_row,
    )
```

- [ ] **Step 3: Run research display tests**

Run:

```powershell
python -m pytest tests/test_research_display_labels.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit research table extraction**

Run:

```powershell
git add src/etf_trading/ui/components/research_tables.py src/etf_trading/ui/app.py
git commit -m "refactor: extract research table components"
```

Expected: commit succeeds when `git` is available.

---

### Task 7: Extract Chart Control Components While Preserving App Imports

**Files:**
- Create: `src/etf_trading/ui/components/charts.py`
- Modify: `src/etf_trading/ui/app.py`
- Test: `tests/test_research_display_labels.py`

**Interfaces:**
- Moves from `app.py`: `_chart_display_controls(...)`
- Moves from `app.py`: `_chart_range_controls(...)`
- Moves from `app.py`: `_filter_date_range_frame(...)`
- Keeps app compatibility wrappers for existing tests.

- [ ] **Step 1: Create chart component module**

Create `src/etf_trading/ui/components/charts.py`:

```python
"""Chart control components shared by ETF and index pages."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st


def filter_date_range_frame(frame: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return frame
    dates = pd.to_datetime(frame["trade_date"])
    mask = (dates.dt.date >= start_date) & (dates.dt.date <= end_date)
    return frame[mask].copy()


def chart_display_controls(
    key_prefix: str,
    *,
    chart_type_options: dict[str, str],
    price_scale_options: dict[str, str],
    ma_display_options: dict[str, str],
    default_chart_label: str,
    default_ma_labels: list[str],
) -> tuple[str, str, list[str]]:
    control_cols = st.columns([1, 1, 2])
    chart_label = control_cols[0].radio(
        "图表类型",
        list(chart_type_options),
        index=list(chart_type_options).index(default_chart_label),
        horizontal=True,
        key=f"{key_prefix}_chart_type",
    )
    price_scale_label = control_cols[1].radio(
        "坐标",
        list(price_scale_options),
        horizontal=True,
        key=f"{key_prefix}_price_scale",
    )
    selected_ma_labels = control_cols[2].multiselect(
        "均线",
        list(ma_display_options),
        default=default_ma_labels,
        key=f"{key_prefix}_ma_columns",
    )
    return (
        chart_type_options[chart_label],
        price_scale_options[price_scale_label],
        [ma_display_options[label] for label in selected_ma_labels],
    )


def chart_range_controls(
    frame: pd.DataFrame,
    key_prefix: str,
    *,
    range_presets: dict[str, int | str | None],
    default_label: str,
) -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return frame
    range_label = st.radio(
        "显示区间",
        list(range_presets),
        index=list(range_presets).index(default_label),
        horizontal=True,
        key=f"{key_prefix}_range",
    )
    preset = range_presets[range_label]
    if preset == "custom":
        cols = st.columns(2)
        min_date = pd.to_datetime(frame["trade_date"]).min().date()
        max_date = pd.to_datetime(frame["trade_date"]).max().date()
        start = cols[0].date_input("开始日期", value=min_date, key=f"{key_prefix}_start")
        end = cols[1].date_input("结束日期", value=max_date, key=f"{key_prefix}_end")
        if start > end:
            st.warning("开始日期晚于结束日期，已临时按完整区间显示。")
            return frame
        return filter_date_range_frame(frame, start, end)
    if preset is None:
        return frame
    return frame.tail(int(preset)).copy()
```

- [ ] **Step 2: Wrap chart functions in `app.py`**

Add this import:

```python
from etf_trading.ui.components.charts import chart_display_controls, chart_range_controls, filter_date_range_frame
```

Replace `_filter_date_range_frame()` with:

```python
def _filter_date_range_frame(frame: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    return filter_date_range_frame(frame, start_date, end_date)
```

Replace `_chart_display_controls()` with:

```python
def _chart_display_controls(
    key_prefix: str,
    *,
    default_chart_label: str = "K线 Candlestick",
    default_ma_labels: list[str] | None = None,
) -> tuple[str, str, list[str]]:
    return chart_display_controls(
        key_prefix,
        chart_type_options=CHART_TYPE_OPTIONS,
        price_scale_options=PRICE_SCALE_OPTIONS,
        ma_display_options=MA_DISPLAY_OPTIONS,
        default_chart_label=default_chart_label,
        default_ma_labels=default_ma_labels or ["MA51", "MA120", "MA250", "MA850"],
    )
```

Replace `_chart_range_controls()` with:

```python
def _chart_range_controls(frame: pd.DataFrame, key_prefix: str, *, default_label: str = "近2年") -> pd.DataFrame:
    return chart_range_controls(frame, key_prefix, range_presets=CHART_RANGE_PRESETS, default_label=default_label)
```

- [ ] **Step 3: Run chart-related tests**

Run:

```powershell
python -m pytest tests/test_research_display_labels.py::test_filter_date_range_frame_keeps_arbitrary_chart_window -v
```

Expected: PASS.

- [ ] **Step 4: Run UI-adjacent tests**

Run:

```powershell
python -m pytest tests/test_research_display_labels.py tests/test_report_and_chart.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit chart component extraction**

Run:

```powershell
git add src/etf_trading/ui/components/charts.py src/etf_trading/ui/app.py
git commit -m "refactor: extract chart control components"
```

Expected: commit succeeds when `git` is available.

---

### Task 8: Move Page Renderers Into Page Modules

**Files:**
- Create: `src/etf_trading/ui/pages/__init__.py`
- Create: `src/etf_trading/ui/pages/decision.py`
- Create: `src/etf_trading/ui/pages/market.py`
- Create: `src/etf_trading/ui/pages/portfolio.py`
- Create: `src/etf_trading/ui/pages/research.py`
- Create: `src/etf_trading/ui/pages/data_maintenance.py`
- Modify: `src/etf_trading/ui/app.py`

**Interfaces:**
- Produces: `pages.decision.render(...) -> None`
- Produces: `pages.market.render(...) -> None`
- Produces: `pages.portfolio.render(...) -> None`
- Produces: `pages.research.render(...) -> None`
- Produces: `pages.data_maintenance.render(...) -> None`
- Keeps private helper functions imported by tests available from `etf_trading.ui.app`.

- [ ] **Step 1: Create page package marker**

Create `src/etf_trading/ui/pages/__init__.py`:

```python
"""Workbench page renderers."""
```

- [ ] **Step 2: Create decision page wrapper**

Create `src/etf_trading/ui/pages/decision.py`:

```python
"""Daily action page."""

from __future__ import annotations

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(*, store: SQLiteStore, parquet_store: ParquetStore, view: str, legacy_render) -> None:
    legacy_render(store, parquet_store, view=view)
```

- [ ] **Step 3: Create market page wrapper**

Create `src/etf_trading/ui/pages/market.py`:

```python
"""Market map page."""

from __future__ import annotations

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(*, store: SQLiteStore, parquet_store: ParquetStore, view: str, legacy_render) -> None:
    legacy_render(store, parquet_store, view=view)
```

- [ ] **Step 4: Create portfolio page wrapper**

Create `src/etf_trading/ui/pages/portfolio.py`:

```python
"""ETF pool page."""

from __future__ import annotations

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(*, store: SQLiteStore, parquet_store: ParquetStore, view: str, legacy_render) -> None:
    legacy_render(store, parquet_store, view=view)
```

- [ ] **Step 5: Create research page wrapper**

Create `src/etf_trading/ui/pages/research.py`:

```python
"""Research replay page."""

from __future__ import annotations

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(*, store: SQLiteStore, parquet_store: ParquetStore, view: str, legacy_render) -> None:
    legacy_render(store, parquet_store, research_view=view)
```

- [ ] **Step 6: Create data maintenance page wrapper**

Create `src/etf_trading/ui/pages/data_maintenance.py`:

```python
"""Data maintenance page."""

from __future__ import annotations

from etf_trading.data.initialization import InitializationService
from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    service: InitializationService,
    view: str,
    legacy_render,
) -> None:
    legacy_render(store, parquet_store, service, view=view)
```

- [ ] **Step 7: Route through page modules in `app.py`**

Add imports:

```python
from etf_trading.ui.pages import data_maintenance, decision, market, portfolio, research
```

Replace the page routing in `main()` with:

```python
    if page.slug == "decision":
        decision.render(store=store, parquet_store=parquet_store, view=section, legacy_render=_tab_decision)
    elif page.slug == "market":
        market.render(store=store, parquet_store=parquet_store, view=section, legacy_render=_tab_market_watch)
    elif page.slug == "portfolio":
        portfolio.render(store=store, parquet_store=parquet_store, view=section, legacy_render=_tab_portfolio)
    elif page.slug == "research":
        research.render(store=store, parquet_store=parquet_store, view=section, legacy_render=_tab_research)
    else:
        data_maintenance.render(
            store=store,
            parquet_store=parquet_store,
            service=service,
            view=section,
            legacy_render=_tab_data_and_settings,
        )
```

- [ ] **Step 8: Run UI-adjacent tests**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py tests/test_ui_state.py tests/test_research_display_labels.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit page wrapper extraction**

Run:

```powershell
git add src/etf_trading/ui/pages src/etf_trading/ui/app.py
git commit -m "refactor: route workbench through page modules"
```

Expected: commit succeeds when `git` is available.

---

### Task 9: Move Low-Risk Legacy Page Functions Into Page Modules

**Files:**
- Modify: `src/etf_trading/ui/pages/portfolio.py`
- Modify: `src/etf_trading/ui/pages/data_maintenance.py`
- Modify: `src/etf_trading/ui/app.py`

**Interfaces:**
- Moves `_tab_portfolio()` body into `pages.portfolio.render()`
- Moves `_tab_data_and_settings()` body into `pages.data_maintenance.render()`
- Keeps helpers that are still shared in `app.py` until their dependencies are extracted.

- [ ] **Step 1: Move portfolio renderer body**

Replace `pages/portfolio.py` with:

```python
"""ETF pool page."""

from __future__ import annotations

import streamlit as st

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    render_search_and_add,
    watchlist_status_frame,
) -> None:
    st.subheader("ETF池")
    st.caption("找 ETF、加入每日计算池，并检查买入许可和历史行情状态。")
    watchlist = store.list_watchlist()

    if view == "搜索加入":
        render_search_and_add(store)
        st.markdown("### 每日计算池")
        if watchlist.empty:
            st.info("每日计算池为空。请先在上方搜索 ETF 并保存。")
        else:
            st.dataframe(watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=320)
        return

    st.markdown("### 每日计算池")
    if watchlist.empty:
        st.info("每日计算池为空。请先在“搜索加入”中保存 ETF。")
    else:
        st.dataframe(watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=520)
```

Update the portfolio routing in `app.py`:

```python
        portfolio.render(
            store=store,
            parquet_store=parquet_store,
            view=section,
            render_search_and_add=_render_etf_search_and_add,
            watchlist_status_frame=_watchlist_status_frame,
        )
```

- [ ] **Step 2: Remove `_tab_portfolio()`**

Delete the old `_tab_portfolio()` function from `app.py` after the new page module route passes tests.

- [ ] **Step 3: Move data maintenance renderer body**

Replace `pages/data_maintenance.py` with:

```python
"""Data maintenance page."""

from __future__ import annotations

import streamlit as st

from etf_trading.data.initialization import InitializationService
from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    service: InitializationService,
    view: str,
    platform_status,
    render_data_health,
    render_index_quick_sync,
    render_data_center,
    render_settings,
) -> None:
    st.subheader("数据维护")
    st.caption("低频维护入口：先看数据健康，再初始化数据、补齐指数历史、查看任务日志。")
    status = platform_status(store, parquet_store)

    if view == "数据健康":
        render_data_health(status)
        render_index_quick_sync(store, parquet_store)
    elif view == "数据中心":
        render_data_health(status)
        render_index_quick_sync(store, parquet_store)
        render_data_center(store, parquet_store)
    else:
        render_data_health(status)
        render_settings(store, service)
```

Update the data route in `app.py`:

```python
        data_maintenance.render(
            store=store,
            parquet_store=parquet_store,
            service=service,
            view=section,
            platform_status=_platform_status,
            render_data_health=_render_data_health,
            render_index_quick_sync=_render_index_quick_sync,
            render_data_center=_tab_data_center,
            render_settings=_tab_settings,
        )
```

- [ ] **Step 4: Remove `_tab_data_and_settings()`**

Delete the old `_tab_data_and_settings()` function from `app.py` after the new page module route passes tests.

- [ ] **Step 5: Run UI-adjacent tests**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py tests/test_ui_state.py tests/test_research_display_labels.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit page body migration**

Run:

```powershell
git add src/etf_trading/ui/pages/portfolio.py src/etf_trading/ui/pages/data_maintenance.py src/etf_trading/ui/app.py
git commit -m "refactor: move low-risk page renderers"
```

Expected: commit succeeds when `git` is available.

---

### Task 10: Move Daily Action and Market Renderers Into Page Modules

**Files:**
- Modify: `src/etf_trading/ui/pages/decision.py`
- Modify: `src/etf_trading/ui/pages/market.py`
- Modify: `src/etf_trading/ui/app.py`

**Interfaces:**
- Moves `_tab_decision()` body into `pages.decision.render()`
- Moves `_tab_market_watch()` body into `pages.market.render()`
- Keeps research rendering in `app.py` for this plan because it carries the background job manager and the highest number of private test imports.

- [ ] **Step 1: Move daily action renderer body**

Replace `src/etf_trading/ui/pages/decision.py` with:

```python
"""Daily action page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    platform_status,
    render_status_cards,
    render_next_steps,
    index_trend_display_frame,
    render_research_table,
    build_daily_advice_report,
    watchlist_status_frame,
) -> None:
    st.subheader("今日行动")
    st.caption("先看市场是否允许参与，再看计算池和今日建议；需要补数据时直接给下一步。")

    status = platform_status(store, parquet_store)
    index_summary = status["index_summary"]
    eligible_categories = status["eligible_categories"]
    watchlist = status["watchlist"]

    render_status_cards(status)
    if eligible_categories:
        st.info("当前指数趋势允许参与的分类：" + "、".join(eligible_categories))
    else:
        st.warning("当前没有指数分类满足新开仓条件，今日行动应偏防守。")
    render_next_steps(status)

    if view == "行动摘要":
        top_indexes = (
            index_summary[index_summary["allows_new_position"].fillna(False).astype(bool)].head(8)
            if not index_summary.empty and "allows_new_position" in index_summary.columns
            else pd.DataFrame()
        )
        if top_indexes.empty:
            st.info("暂无可开仓指数。可到“数据维护”补齐指数历史，或等待趋势条件改善。")
        else:
            st.markdown("### 当前通过趋势过滤的指数")
            render_research_table(index_trend_display_frame(top_indexes), height=260)
        st.markdown("### 今日建议")
        report = build_daily_advice_report(store, parquet_store)
        if report is None:
            st.info("每日计算池为空。请先到“ETF池”加入 ETF。")
        else:
            st.markdown(report)
        with st.expander("查看原始计算池", expanded=False):
            if watchlist.empty:
                st.info("每日计算池为空。")
            else:
                st.dataframe(watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=320)
    elif view == "每日建议":
        report = build_daily_advice_report(store, parquet_store)
        if report is None:
            st.info("每日计算池为空。请先到“ETF池”加入 ETF。")
        else:
            st.markdown(report)
    else:
        if watchlist.empty:
            st.info("每日计算池为空。请先到“ETF池”加入 ETF。")
        else:
            st.dataframe(watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=420)
```

- [ ] **Step 2: Route daily action through moved renderer**

Update the decision route in `app.py`:

```python
        decision.render(
            store=store,
            parquet_store=parquet_store,
            view=section,
            platform_status=_platform_status,
            render_status_cards=render_status_cards,
            render_next_steps=render_next_steps,
            index_trend_display_frame=_index_trend_display_frame,
            render_research_table=_render_research_table,
            build_daily_advice_report=_build_daily_advice_report,
            watchlist_status_frame=_watchlist_status_frame,
        )
```

Import the component renderers at the top of `app.py` if they are not already imported:

```python
from etf_trading.ui.components.status import render_next_steps, render_status_cards, render_top_status_bar
```

- [ ] **Step 3: Remove `_tab_decision()`**

Delete the old `_tab_decision()` function from `app.py` after the route passes tests.

- [ ] **Step 4: Move market renderer body**

Replace `src/etf_trading/ui/pages/market.py` with:

```python
"""Market map page."""

from __future__ import annotations

import streamlit as st

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    build_index_trend_summary,
    render_index_filter_explorer,
    render_etf_chart,
    render_index_watch,
) -> None:
    st.subheader("市场地图")
    st.caption("先看指数过滤和趋势结构，再下钻到 ETF 行情。")
    index_summary = build_index_trend_summary(parquet_store)

    if view == "指数买卖参考":
        render_index_filter_explorer(index_summary, parquet_store)
    elif view == "ETF行情":
        render_etf_chart(store, parquet_store)
    else:
        render_index_watch(parquet_store)
```

- [ ] **Step 5: Route market map through moved renderer**

Update the market route in `app.py`:

```python
        market.render(
            store=store,
            parquet_store=parquet_store,
            view=section,
            build_index_trend_summary=_build_index_trend_summary,
            render_index_filter_explorer=_render_index_filter_explorer,
            render_etf_chart=_tab_chart,
            render_index_watch=_tab_index_watch,
        )
```

- [ ] **Step 6: Remove `_tab_market_watch()`**

Delete the old `_tab_market_watch()` function from `app.py` after the route passes tests.

- [ ] **Step 7: Run UI-adjacent tests**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py tests/test_ui_state.py tests/test_research_display_labels.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit daily action and market migration**

Run:

```powershell
git add src/etf_trading/ui/pages/decision.py src/etf_trading/ui/pages/market.py src/etf_trading/ui/app.py
git commit -m "refactor: move daily action and market pages"
```

Expected: commit succeeds when `git` is available.

---

### Task 11: Final Verification and Documentation Check

**Files:**
- Modify: `docs/superpowers/specs/2026-07-04-ui-navigation-refactor-design.md` only if implementation reveals a documented constraint that must be corrected.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: verified UI navigation refactor.

- [ ] **Step 1: Run focused UI tests**

Run:

```powershell
python -m pytest tests/test_ui_navigation.py tests/test_ui_state.py tests/test_research_display_labels.py tests/test_report_and_chart.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
python -m pytest
```

Expected: PASS.

- [ ] **Step 3: Inspect that main app no longer uses top tabs**

Run:

```powershell
rg -n "st\\.tabs|tabs = st\\.tabs" src\\etf_trading\\ui\\app.py
```

Expected: no matches.

- [ ] **Step 4: Inspect that new UI modules exist**

Run:

```powershell
rg --files src\\etf_trading\\ui
```

Expected output includes:

```text
src/etf_trading/ui/navigation.py
src/etf_trading/ui/state.py
src/etf_trading/ui/styles.py
src/etf_trading/ui/components/status.py
src/etf_trading/ui/components/research_tables.py
src/etf_trading/ui/components/charts.py
src/etf_trading/ui/pages/decision.py
src/etf_trading/ui/pages/market.py
src/etf_trading/ui/pages/portfolio.py
src/etf_trading/ui/pages/data_maintenance.py
```

- [ ] **Step 5: Run Streamlit syntax import check**

Run:

```powershell
python -c "from etf_trading.ui.app import main; print(callable(main))"
```

Expected output:

```text
True
```

- [ ] **Step 6: Optional manual app run**

Run:

```powershell
streamlit run app.py
```

Expected: app opens with sidebar primary navigation and top status bar. If `streamlit` is not available in PATH, run:

```powershell
python -m streamlit run app.py
```

Expected: same behavior.

- [ ] **Step 7: Commit final verification changes**

Run:

```powershell
git status --short
git add src/etf_trading/ui docs/superpowers/specs/2026-07-04-ui-navigation-refactor-design.md tests
git commit -m "test: verify workbench navigation refactor"
```

Expected: commit succeeds when `git` is available, or reports no changes if all prior tasks were committed.
