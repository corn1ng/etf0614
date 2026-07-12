# NiceGUI UI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a NiceGUI-based ETF workbench UI that is visually polished, compact, and professionally usable while preserving existing backend data, storage, and strategy logic.

**Architecture:** Add a new `src/etf_trading/nicegui_app/` UI package beside the existing Streamlit UI. The new package owns app shell, theme, navigation, page rendering, and UI-neutral view models that reuse existing stores, coverage builders, chart payloads, and research modules. Streamlit remains available as a fallback during migration.

**Tech Stack:** Python 3.11+, NiceGUI 3.14+, pandas, existing `SQLiteStore`/`ParquetStore`, existing Streamlit-independent data builders, pytest.

## Global Constraints

- Add `nicegui>=3.14.0` to `pyproject.toml`; keep Streamlit dependencies during migration.
- Do not change ETF master data semantics, index data semantics, storage schema, Parquet layout, strategy calculations, or AkShare provider behavior.
- Keep NiceGUI work in a new UI layer and extract only UI-neutral view models from existing Streamlit code when needed.
- Each migrated high-frequency page must record 2-4 current UI problems and reflect fixes in the NiceGUI layout.
- Visual style must be a professional quantitative workbench: modern, compact, polished, and data-first.
- Visual polish must not reduce table/chart readability, operating speed, risk visibility, or narrow-screen usability.
- Expensive maintenance tasks must be user-triggered and show loading/disabled/error states.
- Preserve existing Streamlit entry points until the NiceGUI version passes local browser verification.

---

## File Structure

Create:

- `src/etf_trading/nicegui_app/__init__.py`  
  Package marker and public exports for the NiceGUI app.
- `src/etf_trading/nicegui_app/navigation.py`  
  NiceGUI page/section definitions independent of Streamlit.
- `src/etf_trading/nicegui_app/state.py`  
  Store factories, platform snapshot loading, and action callbacks.
- `src/etf_trading/nicegui_app/view_models.py`  
  UI-neutral data shaping for status metrics, current UI audit notes, market summaries, ETF tables, and maintenance summaries.
- `src/etf_trading/nicegui_app/theme.py`  
  Global CSS, density tokens, status colors, and table/chart visual rules.
- `src/etf_trading/nicegui_app/layout.py`  
  App shell, sidebar, top status bar, page header, section tabs, and routing container.
- `src/etf_trading/nicegui_app/main.py`  
  NiceGUI app factory, route registration, and `run()` entry point.
- `src/etf_trading/nicegui_app/components/__init__.py`
- `src/etf_trading/nicegui_app/components/alerts.py`
- `src/etf_trading/nicegui_app/components/charts.py`
- `src/etf_trading/nicegui_app/components/controls.py`
- `src/etf_trading/nicegui_app/components/status.py`
- `src/etf_trading/nicegui_app/components/tables.py`
- `src/etf_trading/nicegui_app/pages/__init__.py`
- `src/etf_trading/nicegui_app/pages/action.py`
- `src/etf_trading/nicegui_app/pages/market.py`
- `src/etf_trading/nicegui_app/pages/etf_data.py`
- `src/etf_trading/nicegui_app/pages/maintenance.py`
- `src/etf_trading/nicegui_app/pages/research.py`
- `scripts/run_nicegui.py`
- `tests/test_nicegui_navigation.py`
- `tests/test_nicegui_view_models.py`
- `tests/test_nicegui_theme.py`
- `tests/test_nicegui_charts.py`
- `tests/test_nicegui_app_import.py`

Modify:

- `pyproject.toml`  
  Add NiceGUI dependency.
- `docs/task-memory.md`  
  Append task result and verification notes after implementation.

Do not modify unless a test proves it is necessary:

- Existing storage, provider, strategy, research calculation, and Streamlit rendering modules.

---

### Task 1: NiceGUI Dependency, Navigation, and Importable App Skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/etf_trading/nicegui_app/__init__.py`
- Create: `src/etf_trading/nicegui_app/navigation.py`
- Create: `src/etf_trading/nicegui_app/main.py`
- Create: `scripts/run_nicegui.py`
- Test: `tests/test_nicegui_navigation.py`
- Test: `tests/test_nicegui_app_import.py`

**Interfaces:**
- Produces: `NicePageSpec`, `NICEGUI_PAGES`, `page_labels()`, `default_page()`, `get_page_by_slug(slug)`, `section_options(page)`, `default_section(page)`, `resolve_section(page, selected)`.
- Produces: `create_app() -> None` in `main.py`; it registers NiceGUI routes but does not call `ui.run()`.
- Produces: `run(host: str = "127.0.0.1", port: int = 8502, reload: bool = False) -> None`.

- [ ] **Step 1: Write failing navigation tests**

Create `tests/test_nicegui_navigation.py`:

```python
from etf_trading.nicegui_app.navigation import (
    NICEGUI_PAGES,
    default_page,
    default_section,
    get_page_by_slug,
    page_labels,
    resolve_section,
    section_options,
)


def test_nicegui_primary_navigation_matches_workbench_flow():
    assert page_labels() == ["今日行动", "市场地图", "ETF数据", "策略实验室", "数据维护"]
    assert [page.slug for page in NICEGUI_PAGES] == ["action", "market", "etf-data", "research", "maintenance"]


def test_nicegui_sections_keep_market_and_etf_boundaries():
    sections_by_slug = {page.slug: section_options(page) for page in NICEGUI_PAGES}

    assert sections_by_slug["market"] == ["市场总览", "指数买卖参考", "指数K线"]
    assert sections_by_slug["etf-data"] == ["ETF总览", "ETF行情", "搜索加入", "每日计算池", "指数样本池"]
    assert "ETF行情" not in sections_by_slug["market"]


def test_nicegui_navigation_defaults_are_safe():
    page = default_page()

    assert page.slug == "action"
    assert page.label == "今日行动"
    assert default_section(page) == "行动摘要"
    assert get_page_by_slug("missing").slug == "action"
    assert resolve_section(page, "不存在") == "行动摘要"
```

Create `tests/test_nicegui_app_import.py`:

```python
def test_nicegui_app_factory_imports_without_running_server():
    from etf_trading.nicegui_app.main import create_app, run

    assert callable(create_app)
    assert callable(run)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_app_import.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'etf_trading.nicegui_app'`.

- [ ] **Step 3: Add dependency and package skeleton**

Modify `pyproject.toml` dependencies:

```toml
  "nicegui>=3.14.0",
```

Create `src/etf_trading/nicegui_app/__init__.py`:

```python
"""NiceGUI workbench UI."""

from .main import create_app, run

__all__ = ["create_app", "run"]
```

Create `src/etf_trading/nicegui_app/navigation.py`:

```python
"""Navigation definitions for the NiceGUI workbench."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NicePageSpec:
    slug: str
    label: str
    caption: str
    sections: tuple[str, ...]


NICEGUI_PAGES: tuple[NicePageSpec, ...] = (
    NicePageSpec(
        slug="action",
        label="今日行动",
        caption="先看系统状态、市场参与条件和今日计算池。",
        sections=("行动摘要", "每日建议", "计算池明细"),
    ),
    NicePageSpec(
        slug="market",
        label="市场地图",
        caption="观察指数和市场参与状态，不承载 ETF 行情下钻。",
        sections=("市场总览", "指数买卖参考", "指数K线"),
    ),
    NicePageSpec(
        slug="etf-data",
        label="ETF数据",
        caption="统一查看 ETF 主列表、行情、计算池和样本归属。",
        sections=("ETF总览", "ETF行情", "搜索加入", "每日计算池", "指数样本池"),
    ),
    NicePageSpec(
        slug="research",
        label="策略实验室",
        caption="查看研究任务和已有结果，复杂回测迁移到后续版本。",
        sections=("策略概览", "已有结果"),
    ),
    NicePageSpec(
        slug="maintenance",
        label="数据维护",
        caption="检查数据缺口、补齐历史和查看任务结果。",
        sections=("数据健康", "补齐任务", "任务日志", "设置"),
    ),
)


def page_labels() -> list[str]:
    return [page.label for page in NICEGUI_PAGES]


def default_page() -> NicePageSpec:
    return NICEGUI_PAGES[0]


def get_page_by_slug(slug: str | None) -> NicePageSpec:
    for page in NICEGUI_PAGES:
        if page.slug == slug:
            return page
    return default_page()


def section_options(page: NicePageSpec) -> list[str]:
    return list(page.sections)


def default_section(page: NicePageSpec) -> str:
    return page.sections[0]


def resolve_section(page: NicePageSpec, selected: str | None) -> str:
    if selected in page.sections:
        return str(selected)
    return default_section(page)
```

Create `src/etf_trading/nicegui_app/main.py`:

```python
"""NiceGUI application entry point."""

from __future__ import annotations

from nicegui import ui


def create_app() -> None:
    """Register NiceGUI routes.

    Importing this module must not start a web server.
    """

    @ui.page("/")
    def index() -> None:
        ui.label("ETF 工作台")


def run(host: str = "127.0.0.1", port: int = 8502, reload: bool = False) -> None:
    create_app()
    ui.run(host=host, port=port, reload=reload, title="ETF 工作台")
```

Create `scripts/run_nicegui.py`:

```python
from etf_trading.nicegui_app.main import run


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_app_import.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml scripts/run_nicegui.py src/etf_trading/nicegui_app tests/test_nicegui_navigation.py tests/test_nicegui_app_import.py
git commit -m "feat: add NiceGUI app skeleton"
```

---

### Task 2: UI Audit Notes and View Models

**Files:**
- Create: `src/etf_trading/nicegui_app/view_models.py`
- Create: `src/etf_trading/nicegui_app/state.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Consumes: `SQLiteStore`, `ParquetStore`, `build_etf_data_overview`, `build_data_gap_detail`, `build_data_coverage_summary`, `build_index_etf_universe`.
- Produces: `MetricTile(label: str, value: str, tone: str = "neutral", detail: str = "")`.
- Produces: `AuditFinding(page_slug: str, problem: str, fix: str)`.
- Produces: `PlatformSnapshot(master, watchlist, index_summary, universe, gaps, coverage, generated_at)`.
- Produces: `current_ui_audit_findings() -> tuple[AuditFinding, ...]`.
- Produces: `status_metrics(snapshot: PlatformSnapshot) -> list[MetricTile]`.
- Produces: `market_overview(snapshot: PlatformSnapshot) -> dict[str, object]`.
- Produces: `etf_overview_rows(snapshot: PlatformSnapshot) -> list[dict[str, object]]`.
- Produces: `maintenance_rows(snapshot: PlatformSnapshot) -> list[dict[str, object]]`.
- Produces: `load_snapshot(store: SQLiteStore, parquet_store: ParquetStore) -> PlatformSnapshot`.

- [ ] **Step 1: Write failing view-model tests**

Create `tests/test_nicegui_view_models.py`:

```python
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from etf_trading.nicegui_app.view_models import (
    PlatformSnapshot,
    current_ui_audit_findings,
    etf_overview_rows,
    maintenance_rows,
    market_overview,
    status_metrics,
)


def _snapshot() -> PlatformSnapshot:
    return PlatformSnapshot(
        master=pd.DataFrame(
            {
                "etf_code": ["510300", "512880"],
                "name": ["沪深300ETF", "证券ETF"],
                "category": ["A股宽基", "A股行业"],
                "exchange": ["SH", "SH"],
                "amount": [120000000.0, 80000000.0],
            }
        ),
        watchlist=pd.DataFrame({"etf_code": ["510300"], "allow_buy": [True], "enabled": [True]}),
        index_summary=pd.DataFrame(
            {
                "index_code": ["000300", "000905"],
                "index_name": ["沪深300", "中证500"],
                "category": ["A股宽基", "A股宽基"],
                "allows_new_position": [True, False],
                "history_rows": [300, 30],
                "latest_date": ["2026-07-03", "2026-07-03"],
            }
        ),
        universe=pd.DataFrame({"etf_code": ["510300"], "is_top_sample": [True]}),
        gaps=pd.DataFrame({"数据类型": ["指数历史"], "状态": ["历史不足"]}),
        coverage=pd.DataFrame({"数据类型": ["ETF历史"], "覆盖率": ["50.0%"]}),
        generated_at=datetime(2026, 7, 5, 10, 0, 0),
    )


def test_status_metrics_are_dense_and_human_readable():
    metrics = status_metrics(_snapshot())

    assert [metric.label for metric in metrics] == ["ETF总数", "计算池", "可参与指数", "数据缺口"]
    assert [metric.value for metric in metrics] == ["2", "1", "1", "1"]
    assert metrics[-1].tone == "warning"


def test_current_ui_audit_findings_cover_high_frequency_pages():
    findings = current_ui_audit_findings()
    pages = {finding.page_slug for finding in findings}

    assert {"action", "market", "etf-data", "maintenance"}.issubset(pages)
    assert all(finding.problem and finding.fix for finding in findings)


def test_market_overview_groups_index_state():
    overview = market_overview(_snapshot())

    assert overview["total_indexes"] == 2
    assert overview["allowed_indexes"] == 1
    assert overview["categories"] == [{"category": "A股宽基", "total": 2, "allowed": 1}]


def test_table_rows_convert_dataframes_to_records():
    snapshot = _snapshot()

    assert etf_overview_rows(snapshot)[0]["ETF代码"] == "510300"
    assert maintenance_rows(snapshot) == [{"数据类型": "指数历史", "状态": "历史不足"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py -q
```

Expected: FAIL with missing module or missing functions.

- [ ] **Step 3: Implement view models**

Create `src/etf_trading/nicegui_app/view_models.py`:

```python
"""UI-neutral view models for the NiceGUI workbench."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass(frozen=True)
class MetricTile:
    label: str
    value: str
    tone: str = "neutral"
    detail: str = ""


@dataclass(frozen=True)
class AuditFinding:
    page_slug: str
    problem: str
    fix: str


@dataclass(frozen=True)
class PlatformSnapshot:
    master: pd.DataFrame
    watchlist: pd.DataFrame
    index_summary: pd.DataFrame
    universe: pd.DataFrame
    gaps: pd.DataFrame
    coverage: pd.DataFrame
    generated_at: datetime


def current_ui_audit_findings() -> tuple[AuditFinding, ...]:
    return (
        AuditFinding("action", "状态、建议和计算池分散，打开后需要向下找重点。", "首屏压成状态条、行动摘要和计算池预览。"),
        AuditFinding("market", "指数筛选、说明和图表之间空隙过大，K线下沉。", "用工具栏承载筛选和区间，图表作为主视觉区域。"),
        AuditFinding("etf-data", "ETF主数据、行情和样本池入口语义混在一起。", "按ETF资产层拆成总览、行情、搜索、计算池和样本池。"),
        AuditFinding("maintenance", "数据健康和补齐动作不够贴近，错误/空状态不够明确。", "健康摘要、缺口表和补齐按钮同屏呈现。"),
        AuditFinding("research", "研究功能复杂，第一版不适合抢占高频页面节奏。", "先保留状态和结果入口，复杂回测后续迁移。"),
    )


def status_metrics(snapshot: PlatformSnapshot) -> list[MetricTile]:
    eligible = _count_allowed_indexes(snapshot.index_summary)
    gap_count = len(snapshot.gaps)
    return [
        MetricTile("ETF总数", str(len(snapshot.master)), "neutral", "主列表"),
        MetricTile("计算池", str(len(snapshot.watchlist)), "info", "每日跟踪"),
        MetricTile("可参与指数", str(eligible), "success" if eligible else "warning", "市场状态"),
        MetricTile("数据缺口", str(gap_count), "warning" if gap_count else "success", "维护项"),
    ]


def market_overview(snapshot: PlatformSnapshot) -> dict[str, object]:
    frame = snapshot.index_summary.copy()
    if frame.empty:
        return {"total_indexes": 0, "allowed_indexes": 0, "categories": []}
    allowed = frame["allows_new_position"].fillna(False).astype(bool) if "allows_new_position" in frame else pd.Series(False, index=frame.index)
    categories = []
    if "category" in frame:
        grouped = frame.assign(_allowed=allowed).groupby("category", dropna=False)
        for category, group in grouped:
            categories.append({"category": str(category), "total": int(len(group)), "allowed": int(group["_allowed"].sum())})
    return {"total_indexes": int(len(frame)), "allowed_indexes": int(allowed.sum()), "categories": categories}


def etf_overview_rows(snapshot: PlatformSnapshot) -> list[dict[str, object]]:
    return _records(snapshot.master)


def maintenance_rows(snapshot: PlatformSnapshot) -> list[dict[str, object]]:
    return _records(snapshot.gaps)


def _count_allowed_indexes(index_summary: pd.DataFrame) -> int:
    if index_summary.empty or "allows_new_position" not in index_summary:
        return 0
    return int(index_summary["allows_new_position"].fillna(False).astype(bool).sum())


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return frame.fillna("").to_dict("records")
```

Create `src/etf_trading/nicegui_app/state.py`:

```python
"""State loading for the NiceGUI workbench."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.research.index_etf_universe import build_index_etf_universe
from etf_trading.ui.app import _build_index_trend_summary
from etf_trading.ui.data_coverage import (
    build_data_coverage_summary,
    build_data_gap_detail,
    build_etf_data_overview,
)

from .view_models import PlatformSnapshot


def create_store(db_path: str | Path = "data/etf_trading.db") -> SQLiteStore:
    return SQLiteStore(db_path)


def create_parquet_store(root: str | Path = "data/prices") -> ParquetStore:
    return ParquetStore(root)


def load_snapshot(store: SQLiteStore, parquet_store: ParquetStore) -> PlatformSnapshot:
    master = store.list_etf_master()
    watchlist = store.list_watchlist()
    index_summary = _build_index_trend_summary(parquet_store)
    universe = build_index_etf_universe(master, parquet_store)
    etf_overview = build_etf_data_overview(master, watchlist, parquet_store, universe)
    gaps = build_data_gap_detail(master, watchlist, index_summary, universe, parquet_store)
    coverage = build_data_coverage_summary(gaps, master, watchlist, index_summary, universe)
    return PlatformSnapshot(
        master=etf_overview if not etf_overview.empty else pd.DataFrame(),
        watchlist=watchlist,
        index_summary=index_summary,
        universe=universe,
        gaps=gaps,
        coverage=coverage,
        generated_at=datetime.now(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/nicegui_app/view_models.py src/etf_trading/nicegui_app/state.py tests/test_nicegui_view_models.py
git commit -m "feat: add NiceGUI view models"
```

---

### Task 3: Professional Workbench Theme and Reusable Components

**Files:**
- Create: `src/etf_trading/nicegui_app/theme.py`
- Create: `src/etf_trading/nicegui_app/components/__init__.py`
- Create: `src/etf_trading/nicegui_app/components/alerts.py`
- Create: `src/etf_trading/nicegui_app/components/controls.py`
- Create: `src/etf_trading/nicegui_app/components/status.py`
- Create: `src/etf_trading/nicegui_app/components/tables.py`
- Test: `tests/test_nicegui_theme.py`

**Interfaces:**
- Produces: `WORKBENCH_CSS: str`.
- Produces: `apply_theme() -> None`.
- Produces: `tone_class(tone: str) -> str`.
- Produces: `table_columns(rows: list[dict[str, object]]) -> list[dict[str, str]]`.

- [ ] **Step 1: Write failing theme tests**

Create `tests/test_nicegui_theme.py`:

```python
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.theme import WORKBENCH_CSS, tone_class


def test_theme_contains_dense_professional_workbench_rules():
    assert ".workbench-shell" in WORKBENCH_CSS
    assert ".workbench-sidebar" in WORKBENCH_CSS
    assert ".workbench-topbar" in WORKBENCH_CSS
    assert ".workbench-data-table" in WORKBENCH_CSS
    assert "height: 34px" in WORKBENCH_CSS
    assert "#0f172a" in WORKBENCH_CSS


def test_tone_class_maps_unknown_to_neutral():
    assert tone_class("success") == "tone-success"
    assert tone_class("warning") == "tone-warning"
    assert tone_class("unknown") == "tone-neutral"


def test_table_columns_derive_stable_field_names():
    columns = table_columns([{"ETF代码": "510300", "状态": "完整"}])

    assert columns == [
        {"name": "ETF代码", "label": "ETF代码", "field": "ETF代码", "align": "left"},
        {"name": "状态", "label": "状态", "field": "状态", "align": "left"},
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_theme.py -q
```

Expected: FAIL with missing modules.

- [ ] **Step 3: Implement theme and components**

Create `src/etf_trading/nicegui_app/theme.py`:

```python
"""Visual system for the NiceGUI ETF workbench."""

from __future__ import annotations

from nicegui import ui


WORKBENCH_CSS = """
:root {
  --wb-bg: #f4f7fb;
  --wb-panel: #ffffff;
  --wb-ink: #111827;
  --wb-muted: #64748b;
  --wb-sidebar: #0f172a;
  --wb-sidebar-soft: #172554;
  --wb-line: #dbe3ef;
  --wb-blue: #2563eb;
  --wb-green: #16a34a;
  --wb-red: #dc2626;
  --wb-amber: #d97706;
}
body { background: var(--wb-bg); color: var(--wb-ink); }
.workbench-shell { min-height: 100vh; background: var(--wb-bg); }
.workbench-sidebar { width: 188px; background: var(--wb-sidebar); color: #e5edf7; }
.workbench-brand { height: 44px; display: flex; align-items: center; padding: 0 14px; font-weight: 700; }
.workbench-nav-item { height: 38px; border-radius: 6px; padding: 0 10px; display: flex; align-items: center; }
.workbench-nav-item.is-active { background: rgba(37, 99, 235, 0.22); color: #ffffff; }
.workbench-main { min-width: 0; }
.workbench-topbar { height: 42px; border-bottom: 1px solid var(--wb-line); background: rgba(255, 255, 255, 0.92); }
.workbench-page { padding: 14px 18px 18px; gap: 12px; }
.workbench-page-title { font-size: 22px; line-height: 28px; font-weight: 800; letter-spacing: 0; }
.workbench-page-caption { color: var(--wb-muted); font-size: 13px; line-height: 18px; }
.workbench-toolbar { min-height: 36px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.workbench-metric { border: 1px solid var(--wb-line); border-radius: 8px; background: var(--wb-panel); padding: 9px 10px; min-width: 128px; }
.workbench-metric-value { font-size: 20px; line-height: 24px; font-weight: 800; }
.workbench-metric-label { color: var(--wb-muted); font-size: 12px; }
.workbench-data-table .q-table th { height: 34px; font-size: 12px; color: #334155; background: #f8fafc; }
.workbench-data-table .q-table td { height: 34px; font-size: 13px; }
.workbench-chart-panel { min-height: 420px; border: 1px solid var(--wb-line); border-radius: 8px; background: #ffffff; overflow: hidden; }
.tone-neutral { color: #475569; }
.tone-info { color: var(--wb-blue); }
.tone-success { color: var(--wb-green); }
.tone-warning { color: var(--wb-amber); }
.tone-danger { color: var(--wb-red); }
"""


def apply_theme() -> None:
    ui.add_head_html(f"<style>{WORKBENCH_CSS}</style>")


def tone_class(tone: str) -> str:
    if tone in {"neutral", "info", "success", "warning", "danger"}:
        return f"tone-{tone}"
    return "tone-neutral"
```

Create `src/etf_trading/nicegui_app/components/__init__.py`:

```python
"""Reusable NiceGUI workbench components."""
```

Create `src/etf_trading/nicegui_app/components/tables.py`:

```python
"""Dense table helpers."""

from __future__ import annotations


def table_columns(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    if not rows:
        return []
    return [{"name": key, "label": key, "field": key, "align": "left"} for key in rows[0].keys()]
```

Create `src/etf_trading/nicegui_app/components/alerts.py`:

```python
"""Compact alert helpers."""

from __future__ import annotations

from nicegui import ui


def empty_state(title: str, detail: str) -> None:
    with ui.column().classes("w-full items-center justify-center gap-1 py-6 text-slate-500"):
        ui.icon("info").classes("text-2xl")
        ui.label(title).classes("text-sm font-semibold")
        ui.label(detail).classes("text-xs")
```

Create `src/etf_trading/nicegui_app/components/controls.py`:

```python
"""Compact controls."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui


def refresh_button(on_click: Callable[[], None] | None = None) -> None:
    ui.button("刷新", icon="refresh", on_click=on_click).props("dense outline").classes("h-8")
```

Create `src/etf_trading/nicegui_app/components/status.py`:

```python
"""Status metric components."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.theme import tone_class
from etf_trading.nicegui_app.view_models import MetricTile


def metric_strip(metrics: list[MetricTile]) -> None:
    with ui.row().classes("w-full gap-2"):
        for metric in metrics:
            with ui.column().classes("workbench-metric gap-0"):
                ui.label(metric.label).classes("workbench-metric-label")
                ui.label(metric.value).classes(f"workbench-metric-value {tone_class(metric.tone)}")
                if metric.detail:
                    ui.label(metric.detail).classes("text-xs text-slate-400")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_theme.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/nicegui_app/theme.py src/etf_trading/nicegui_app/components tests/test_nicegui_theme.py
git commit -m "feat: add NiceGUI workbench theme"
```

---

### Task 4: App Shell, Sidebar, Topbar, and Routing

**Files:**
- Create: `src/etf_trading/nicegui_app/layout.py`
- Modify: `src/etf_trading/nicegui_app/main.py`
- Test: `tests/test_nicegui_app_import.py`

**Interfaces:**
- Consumes: `NICEGUI_PAGES`, `get_page_by_slug`, `default_section`, `resolve_section`.
- Produces: `render_shell(page_slug: str | None = None, section: str | None = None) -> None`.
- Produces: page URLs `/`, `/page/{page_slug}`, `/page/{page_slug}/{section}`.

- [ ] **Step 1: Extend app import test for route registration**

Modify `tests/test_nicegui_app_import.py`:

```python
def test_nicegui_layout_exports_shell_renderer():
    from etf_trading.nicegui_app.layout import render_shell

    assert callable(render_shell)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py -q
```

Expected: FAIL with missing `layout`.

- [ ] **Step 3: Implement shell**

Create `src/etf_trading/nicegui_app/layout.py`:

```python
"""Application shell for the NiceGUI workbench."""

from __future__ import annotations

from nicegui import ui

from .navigation import NICEGUI_PAGES, default_page, default_section, get_page_by_slug, resolve_section
from .theme import apply_theme


def render_shell(page_slug: str | None = None, section: str | None = None) -> None:
    apply_theme()
    page = get_page_by_slug(page_slug)
    active_section = resolve_section(page, section)

    with ui.row().classes("workbench-shell w-full no-wrap"):
        _render_sidebar(page.slug)
        with ui.column().classes("workbench-main flex-1 no-wrap"):
            _render_topbar()
            with ui.column().classes("workbench-page w-full"):
                _render_page_header(page.label, page.caption, page.sections, active_section)
                ui.label(f"{page.label} / {active_section}").classes("text-sm text-slate-500")


def _render_sidebar(active_slug: str) -> None:
    with ui.column().classes("workbench-sidebar min-h-screen gap-1 p-2"):
        ui.label("ETF 工作台").classes("workbench-brand")
        for page in NICEGUI_PAGES:
            classes = "workbench-nav-item"
            if page.slug == active_slug:
                classes += " is-active"
            ui.link(page.label, f"/page/{page.slug}").classes(classes)


def _render_topbar() -> None:
    with ui.row().classes("workbench-topbar w-full items-center justify-between px-4"):
        ui.label("本地量化工作台").classes("text-sm font-semibold text-slate-700")
        ui.label("NiceGUI").classes("text-xs text-slate-400")


def _render_page_header(label: str, caption: str, sections: tuple[str, ...], active_section: str) -> None:
    with ui.row().classes("w-full items-end justify-between gap-3"):
        with ui.column().classes("gap-0"):
            ui.label(label).classes("workbench-page-title")
            ui.label(caption).classes("workbench-page-caption")
        with ui.row().classes("workbench-toolbar"):
            for item in sections:
                ui.link(item, f"#").classes("text-sm font-medium text-slate-600" + (" text-blue-600" if item == active_section else ""))
```

Modify `src/etf_trading/nicegui_app/main.py`:

```python
"""NiceGUI application entry point."""

from __future__ import annotations

from urllib.parse import unquote

from nicegui import ui

from .layout import render_shell


def create_app() -> None:
    @ui.page("/")
    def index() -> None:
        render_shell()

    @ui.page("/page/{page_slug}")
    def page(page_slug: str) -> None:
        render_shell(page_slug=page_slug)

    @ui.page("/page/{page_slug}/{section}")
    def page_section(page_slug: str, section: str) -> None:
        render_shell(page_slug=page_slug, section=unquote(section))


def run(host: str = "127.0.0.1", port: int = 8502, reload: bool = False) -> None:
    create_app()
    ui.run(host=host, port=port, reload=reload, title="ETF 工作台")
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py tests/test_nicegui_navigation.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/nicegui_app/layout.py src/etf_trading/nicegui_app/main.py tests/test_nicegui_app_import.py
git commit -m "feat: add NiceGUI workbench shell"
```

---

### Task 5: Lightweight Chart Component

**Files:**
- Create: `src/etf_trading/nicegui_app/components/charts.py`
- Test: `tests/test_nicegui_charts.py`

**Interfaces:**
- Consumes: chart payload from `build_lightweight_chart_payload(...)`.
- Produces: `build_chart_html(payload: list[dict], element_id: str = "workbench-chart") -> str`.
- Produces: `render_lightweight_chart(payload: list[dict], element_id: str = "workbench-chart") -> None`.

- [ ] **Step 1: Write failing chart tests**

Create `tests/test_nicegui_charts.py`:

```python
from etf_trading.nicegui_app.components.charts import build_chart_html


def test_build_chart_html_embeds_payload_and_container():
    html = build_chart_html([{"chart": {"height": 320}, "series": []}], element_id="chart-a")

    assert 'id="chart-a"' in html
    assert "LightweightCharts" in html
    assert '"height": 320' in html
    assert "ResizeObserver" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py -q
```

Expected: FAIL with missing `charts`.

- [ ] **Step 3: Implement chart HTML**

Create `src/etf_trading/nicegui_app/components/charts.py`:

```python
"""Lightweight Charts rendering helpers for NiceGUI."""

from __future__ import annotations

import json
from html import escape

from nicegui import ui


def build_chart_html(payload: list[dict], element_id: str = "workbench-chart") -> str:
    safe_id = escape(element_id, quote=True)
    payload_json = json.dumps(payload, ensure_ascii=False)
    return f"""
<div id="{safe_id}" class="workbench-chart-panel"></div>
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
<script>
(() => {{
  const root = document.getElementById("{safe_id}");
  const payload = {payload_json};
  root.innerHTML = "";
  payload.forEach((item) => {{
    const chartNode = document.createElement("div");
    chartNode.style.height = `${{item.chart?.height || 320}}px`;
    root.appendChild(chartNode);
    const chart = LightweightCharts.createChart(chartNode, {{...item.chart, width: root.clientWidth}});
    (item.series || []).forEach((series) => {{
      const type = series.type || "Line";
      const factory = type === "Candlestick" ? chart.addCandlestickSeries :
        type === "Histogram" ? chart.addHistogramSeries : chart.addLineSeries;
      const created = factory.call(chart, series.options || {{}});
      created.setData(series.data || []);
      if (series.markers && created.setMarkers) created.setMarkers(series.markers);
    }});
    new ResizeObserver(() => chart.applyOptions({{width: root.clientWidth}})).observe(root);
  }});
}})();
</script>
"""


def render_lightweight_chart(payload: list[dict], element_id: str = "workbench-chart") -> None:
    ui.html(build_chart_html(payload, element_id=element_id)).classes("w-full")
```

- [ ] **Step 4: Run test**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/nicegui_app/components/charts.py tests/test_nicegui_charts.py
git commit -m "feat: add NiceGUI chart component"
```

---

### Task 6: Market Page Migration

**Files:**
- Create: `src/etf_trading/nicegui_app/pages/market.py`
- Modify: `src/etf_trading/nicegui_app/pages/__init__.py`
- Modify: `src/etf_trading/nicegui_app/layout.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Consumes: `PlatformSnapshot`, `market_overview(...)`, `current_ui_audit_findings()`, `build_lightweight_chart_payload`.
- Produces: `render(snapshot: PlatformSnapshot, section: str) -> None`.

- [ ] **Step 1: Extend view-model tests for market page audit**

Modify `tests/test_nicegui_view_models.py`:

```python
def test_market_audit_names_density_and_chart_fixes():
    market_findings = [item for item in current_ui_audit_findings() if item.page_slug == "market"]

    assert any("K线" in item.problem or "图表" in item.problem for item in market_findings)
    assert any("工具栏" in item.fix or "图表" in item.fix for item in market_findings)
```

- [ ] **Step 2: Run test**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py::test_market_audit_names_density_and_chart_fixes -q
```

Expected: PASS. If it fails, change the `market` audit finding text in `current_ui_audit_findings()` so one problem names K线 or 图表 and one fix names 工具栏 or 图表.

- [ ] **Step 3: Implement market page**

Create `src/etf_trading/nicegui_app/pages/__init__.py`:

```python
"""NiceGUI page renderers."""
```

Create `src/etf_trading/nicegui_app/pages/market.py`:

```python
"""Market map page."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, market_overview


def render(snapshot: PlatformSnapshot, section: str) -> None:
    if section == "市场总览":
        _render_overview(snapshot)
    elif section == "指数买卖参考":
        _render_index_reference(snapshot)
    else:
        _render_index_chart_placeholder(snapshot)


def _render_overview(snapshot: PlatformSnapshot) -> None:
    overview = market_overview(snapshot)
    with ui.row().classes("w-full gap-2"):
        _metric("指数总数", overview["total_indexes"])
        _metric("可参与指数", overview["allowed_indexes"])
    rows = overview["categories"]
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, row_key="category").classes("workbench-data-table w-full")
    else:
        empty_state("暂无指数状态", "到数据维护补齐指数历史后再查看市场总览。")
    _render_audit("market")


def _render_index_reference(snapshot: PlatformSnapshot) -> None:
    rows = snapshot.index_summary.fillna("").to_dict("records") if not snapshot.index_summary.empty else []
    if rows:
        ui.table(columns=table_columns(rows), rows=rows).classes("workbench-data-table w-full")
    else:
        empty_state("暂无指数买卖参考", "先补齐指数历史。")
    _render_audit("market")


def _render_index_chart_placeholder(snapshot: PlatformSnapshot) -> None:
    if snapshot.index_summary.empty:
        empty_state("暂无指数K线", "先补齐指数历史。")
        return
    with ui.column().classes("workbench-chart-panel w-full items-center justify-center"):
        ui.icon("show_chart").classes("text-3xl text-blue-600")
        ui.label("指数K线图将在接入历史行情后显示").classes("text-sm text-slate-500")
    _render_audit("market")


def _metric(label: str, value: object) -> None:
    with ui.column().classes("workbench-metric"):
        ui.label(label).classes("workbench-metric-label")
        ui.label(str(value)).classes("workbench-metric-value")


def _render_audit(page_slug: str) -> None:
    findings = [item for item in current_ui_audit_findings() if item.page_slug == page_slug]
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in findings:
            ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
```

Modify `src/etf_trading/nicegui_app/layout.py` to call the market page. In `render_shell`, replace the placeholder label with:

```python
                _render_page(page.slug, active_section)
```

Add below `_render_page_header`:

```python
def _render_page(page_slug: str, section: str) -> None:
    from .state import create_parquet_store, create_store, load_snapshot
    from .pages import market

    snapshot = load_snapshot(create_store(), create_parquet_store())
    if page_slug == "market":
        market.render(snapshot, section)
    else:
        ui.label("页面迁移中").classes("text-sm text-slate-500")
```

- [ ] **Step 4: Run targeted tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_app_import.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/nicegui_app/pages src/etf_trading/nicegui_app/layout.py tests/test_nicegui_view_models.py
git commit -m "feat: add NiceGUI market page"
```

---

### Task 7: ETF Data and Maintenance Pages

**Files:**
- Create: `src/etf_trading/nicegui_app/pages/etf_data.py`
- Create: `src/etf_trading/nicegui_app/pages/maintenance.py`
- Modify: `src/etf_trading/nicegui_app/layout.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Consumes: `etf_overview_rows(snapshot)`, `maintenance_rows(snapshot)`, `snapshot.coverage`, `snapshot.watchlist`, `snapshot.universe`.
- Produces: `etf_data.render(snapshot: PlatformSnapshot, section: str) -> None`.
- Produces: `maintenance.render(snapshot: PlatformSnapshot, section: str) -> None`.

- [ ] **Step 1: Extend tests for ETF and maintenance audit notes**

Modify `tests/test_nicegui_view_models.py`:

```python
def test_etf_and_maintenance_audit_notes_are_explicit():
    findings = current_ui_audit_findings()
    by_page = {}
    for finding in findings:
        by_page.setdefault(finding.page_slug, []).append(finding)

    assert any("ETF" in item.problem for item in by_page["etf-data"])
    assert any("健康" in item.problem or "补齐" in item.fix for item in by_page["maintenance"])
```

- [ ] **Step 2: Run test**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py::test_etf_and_maintenance_audit_notes_are_explicit -q
```

Expected: PASS. If it fails, change the `etf-data` or `maintenance` audit finding text in `current_ui_audit_findings()` so ETF and maintenance fixes are explicit.

- [ ] **Step 3: Implement ETF data page**

Create `src/etf_trading/nicegui_app/pages/etf_data.py`:

```python
"""ETF data page."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, etf_overview_rows


def render(snapshot: PlatformSnapshot, section: str) -> None:
    if section == "ETF总览":
        rows = etf_overview_rows(snapshot)
    elif section == "每日计算池":
        rows = snapshot.watchlist.fillna("").to_dict("records") if not snapshot.watchlist.empty else []
    elif section == "指数样本池":
        rows = snapshot.universe.fillna("").to_dict("records") if not snapshot.universe.empty else []
    elif section == "搜索加入":
        _render_search_placeholder()
        return
    else:
        _render_chart_placeholder()
        return

    if rows:
        ui.table(columns=table_columns(rows), rows=rows).classes("workbench-data-table w-full")
    else:
        empty_state("暂无ETF数据", "先到数据维护初始化主列表或补齐历史。")
    _render_audit("etf-data")


def _render_search_placeholder() -> None:
    with ui.row().classes("workbench-toolbar w-full"):
        ui.input("代码 / 名称 / 分类").props("dense outlined").classes("w-72")
        ui.button("加入计算池", icon="add").props("dense unelevated color=primary")
    _render_audit("etf-data")


def _render_chart_placeholder() -> None:
    with ui.column().classes("workbench-chart-panel w-full items-center justify-center"):
        ui.icon("candlestick_chart").classes("text-3xl text-blue-600")
        ui.label("ETF K线图将在接入历史行情后显示").classes("text-sm text-slate-500")
    _render_audit("etf-data")


def _render_audit(page_slug: str) -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == page_slug:
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
```

- [ ] **Step 4: Implement maintenance page**

Create `src/etf_trading/nicegui_app/pages/maintenance.py`:

```python
"""Data maintenance page."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, maintenance_rows


def render(snapshot: PlatformSnapshot, section: str) -> None:
    if section == "数据健康":
        rows = snapshot.coverage.fillna("").to_dict("records") if not snapshot.coverage.empty else []
    elif section == "补齐任务":
        _render_tasks()
        return
    elif section == "任务日志":
        rows = maintenance_rows(snapshot)
    else:
        rows = [{"设置项": "自动运行耗时任务", "当前值": "关闭"}, {"设置项": "Streamlit回退入口", "当前值": "保留"}]

    if rows:
        ui.table(columns=table_columns(rows), rows=rows).classes("workbench-data-table w-full")
    else:
        empty_state("暂无维护数据", "当前没有检测到需要处理的数据缺口。")
    _render_audit()


def _render_tasks() -> None:
    with ui.row().classes("workbench-toolbar w-full"):
        ui.button("初始化ETF主列表", icon="database").props("dense outline")
        ui.button("补齐ETF历史", icon="history").props("dense outline")
        ui.button("补齐指数历史", icon="stacked_line_chart").props("dense outline")
    ui.label("补齐任务只在点击后执行，避免打开页面自动触发耗时操作。").classes("text-xs text-slate-500")
    _render_audit()


def _render_audit() -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "maintenance":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
```

- [ ] **Step 5: Wire pages into layout**

Modify `_render_page` in `src/etf_trading/nicegui_app/layout.py`:

```python
def _render_page(page_slug: str, section: str) -> None:
    from .state import create_parquet_store, create_store, load_snapshot
    from .pages import etf_data, maintenance, market

    snapshot = load_snapshot(create_store(), create_parquet_store())
    if page_slug == "market":
        market.render(snapshot, section)
    elif page_slug == "etf-data":
        etf_data.render(snapshot, section)
    elif page_slug == "maintenance":
        maintenance.render(snapshot, section)
    else:
        ui.label("页面迁移中").classes("text-sm text-slate-500")
```

- [ ] **Step 6: Run tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_app_import.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/etf_trading/nicegui_app/pages/etf_data.py src/etf_trading/nicegui_app/pages/maintenance.py src/etf_trading/nicegui_app/layout.py tests/test_nicegui_view_models.py
git commit -m "feat: add NiceGUI ETF and maintenance pages"
```

---

### Task 8: Action and Research Pages

**Files:**
- Create: `src/etf_trading/nicegui_app/pages/action.py`
- Create: `src/etf_trading/nicegui_app/pages/research.py`
- Modify: `src/etf_trading/nicegui_app/layout.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Consumes: `status_metrics(snapshot)`, `snapshot.watchlist`, `snapshot.index_summary`.
- Produces: `action.render(snapshot: PlatformSnapshot, section: str) -> None`.
- Produces: `research.render(snapshot: PlatformSnapshot, section: str) -> None`.

- [ ] **Step 1: Implement action page**

Create `src/etf_trading/nicegui_app/pages/action.py`:

```python
"""Daily action page."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.status import metric_strip
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, status_metrics


def render(snapshot: PlatformSnapshot, section: str) -> None:
    metric_strip(status_metrics(snapshot))
    if section == "计算池明细":
        rows = snapshot.watchlist.fillna("").to_dict("records") if not snapshot.watchlist.empty else []
    elif section == "每日建议":
        rows = snapshot.index_summary.fillna("").to_dict("records") if not snapshot.index_summary.empty else []
    else:
        rows = snapshot.gaps.fillna("").to_dict("records") if not snapshot.gaps.empty else []

    if rows:
        ui.table(columns=table_columns(rows), rows=rows).classes("workbench-data-table w-full")
    else:
        empty_state("当前无待处理事项", "系统状态可用时，这里会保持轻量。")
    _render_audit()


def _render_audit() -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "action":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
```

- [ ] **Step 2: Implement research page**

Create `src/etf_trading/nicegui_app/pages/research.py`:

```python
"""Minimal research page for the first NiceGUI migration."""

from __future__ import annotations

from nicegui import ui

from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings


def render(snapshot: PlatformSnapshot, section: str) -> None:
    with ui.column().classes("w-full gap-2"):
        ui.label("策略实验室第一版先保留研究状态和结果入口，复杂回测表单后续迁移。").classes("text-sm text-slate-600")
        with ui.row().classes("workbench-toolbar"):
            ui.button("查看已有结果", icon="analytics").props("dense outline")
            ui.button("返回Streamlit研究页", icon="open_in_new").props("dense outline")
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "research":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
```

- [ ] **Step 3: Wire pages into layout**

Modify `_render_page` in `src/etf_trading/nicegui_app/layout.py`:

```python
def _render_page(page_slug: str, section: str) -> None:
    from .state import create_parquet_store, create_store, load_snapshot
    from .pages import action, etf_data, maintenance, market, research

    snapshot = load_snapshot(create_store(), create_parquet_store())
    if page_slug == "action":
        action.render(snapshot, section)
    elif page_slug == "market":
        market.render(snapshot, section)
    elif page_slug == "etf-data":
        etf_data.render(snapshot, section)
    elif page_slug == "maintenance":
        maintenance.render(snapshot, section)
    elif page_slug == "research":
        research.render(snapshot, section)
    else:
        action.render(snapshot, "行动摘要")
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_nicegui_app_import.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/nicegui_app/pages/action.py src/etf_trading/nicegui_app/pages/research.py src/etf_trading/nicegui_app/layout.py
git commit -m "feat: add NiceGUI action and research pages"
```

---

### Task 9: Wire ETF and Index K-Line Payloads

**Files:**
- Modify: `src/etf_trading/nicegui_app/state.py`
- Modify: `src/etf_trading/nicegui_app/pages/market.py`
- Modify: `src/etf_trading/nicegui_app/pages/etf_data.py`
- Test: `tests/test_nicegui_charts.py`

**Interfaces:**
- Consumes: `ParquetStore.read_index_prices(...)`, `ParquetStore.read_prices(...)`, `add_technical_features(...)`, `build_lightweight_chart_payload(...)`.
- Produces: `index_chart_payload(parquet_store: ParquetStore, index_code: str) -> list[dict]`.
- Produces: `etf_chart_payload(parquet_store: ParquetStore, etf_code: str) -> list[dict]`.

- [ ] **Step 1: Extend chart tests for empty and populated payload helpers**

Modify `tests/test_nicegui_charts.py`:

```python
import pandas as pd

from etf_trading.nicegui_app.state import etf_chart_payload, index_chart_payload


class FakeParquetStore:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def read_index_prices(self, index_code: str) -> pd.DataFrame:
        return self.frame

    def read_prices(self, etf_code: str) -> pd.DataFrame:
        return self.frame


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=260, freq="B"),
            "open": [10.0] * 260,
            "high": [10.5] * 260,
            "low": [9.8] * 260,
            "close": [10.2] * 260,
            "volume": [1000] * 260,
        }
    )


def test_index_chart_payload_uses_lightweight_chart_shape():
    payload = index_chart_payload(FakeParquetStore(_prices()), "000300")

    assert payload[0]["series"]
    assert payload[0]["chart"]["height"] == 520


def test_etf_chart_payload_returns_empty_chart_for_missing_history():
    payload = etf_chart_payload(FakeParquetStore(pd.DataFrame()), "510300")

    assert payload[0]["series"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py -q
```

Expected: FAIL with missing `index_chart_payload` and `etf_chart_payload`.

- [ ] **Step 3: Add chart payload helpers**

Modify `src/etf_trading/nicegui_app/state.py`:

```python
from etf_trading.strategy.features import add_technical_features
from etf_trading.ui.chart_renderer import build_lightweight_chart_payload
```

Add:

```python
def index_chart_payload(parquet_store: ParquetStore, index_code: str) -> list[dict]:
    prices = parquet_store.read_index_prices(index_code)
    if prices.empty:
        return build_lightweight_chart_payload(prices)
    featured = add_technical_features(prices.rename(columns={"index_code": "etf_code"}))
    recent = featured.tail(500)
    return build_lightweight_chart_payload(recent, chart_type="candlestick", price_scale_mode="normal")


def etf_chart_payload(parquet_store: ParquetStore, etf_code: str) -> list[dict]:
    prices = parquet_store.read_prices(etf_code)
    if prices.empty:
        return build_lightweight_chart_payload(prices)
    featured = add_technical_features(prices)
    recent = featured.tail(500)
    return build_lightweight_chart_payload(recent, chart_type="candlestick", price_scale_mode="normal")
```

- [ ] **Step 4: Replace chart placeholders in pages**

Modify `src/etf_trading/nicegui_app/pages/market.py` so `render(...)` accepts `parquet_store`:

```python
def render(snapshot: PlatformSnapshot, section: str, parquet_store=None) -> None:
    if section == "市场总览":
        _render_overview(snapshot)
    elif section == "指数买卖参考":
        _render_index_reference(snapshot)
    else:
        _render_index_chart(snapshot, parquet_store)
```

Replace `_render_index_chart_placeholder` with:

```python
def _render_index_chart(snapshot: PlatformSnapshot, parquet_store) -> None:
    from etf_trading.nicegui_app.components.charts import render_lightweight_chart
    from etf_trading.nicegui_app.state import index_chart_payload

    if snapshot.index_summary.empty or parquet_store is None:
        empty_state("暂无指数K线", "先补齐指数历史。")
        return
    selected = str(snapshot.index_summary.iloc[0]["index_code"])
    payload = index_chart_payload(parquet_store, selected)
    if not payload[0]["series"]:
        empty_state("暂无指数K线", "先补齐指数历史。")
        return
    render_lightweight_chart(payload, element_id=f"index-chart-{selected}")
    _render_audit("market")
```

Modify `src/etf_trading/nicegui_app/pages/etf_data.py` so `render(...)` accepts `parquet_store`:

```python
def render(snapshot: PlatformSnapshot, section: str, parquet_store=None) -> None:
```

Replace `_render_chart_placeholder()` with:

```python
def _render_etf_chart(snapshot: PlatformSnapshot, parquet_store) -> None:
    from etf_trading.nicegui_app.components.charts import render_lightweight_chart
    from etf_trading.nicegui_app.state import etf_chart_payload

    rows = etf_overview_rows(snapshot)
    if not rows or parquet_store is None:
        empty_state("暂无ETF K线", "先初始化ETF主列表并补齐历史。")
        return
    selected = str(rows[0]["ETF代码"])
    payload = etf_chart_payload(parquet_store, selected)
    if not payload[0]["series"]:
        empty_state("暂无ETF K线", "先到数据维护补齐该ETF历史。")
        return
    render_lightweight_chart(payload, element_id=f"etf-chart-{selected}")
    _render_audit("etf-data")
```

In the `ETF行情` branch, call:

```python
        _render_etf_chart(snapshot, parquet_store)
        return
```

Modify `_render_page` in `src/etf_trading/nicegui_app/layout.py`:

```python
    store = create_store()
    parquet_store = create_parquet_store()
    snapshot = load_snapshot(store, parquet_store)
    if page_slug == "action":
        action.render(snapshot, section)
    elif page_slug == "market":
        market.render(snapshot, section, parquet_store=parquet_store)
    elif page_slug == "etf-data":
        etf_data.render(snapshot, section, parquet_store=parquet_store)
```

- [ ] **Step 5: Run chart tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/etf_trading/nicegui_app/state.py src/etf_trading/nicegui_app/pages/market.py src/etf_trading/nicegui_app/pages/etf_data.py src/etf_trading/nicegui_app/layout.py tests/test_nicegui_charts.py
git commit -m "feat: wire NiceGUI K-line charts"
```

---

### Task 10: Local Run, Screenshot Verification, and Polish Pass

**Files:**
- Modify: `src/etf_trading/nicegui_app/theme.py`
- Modify: `src/etf_trading/nicegui_app/layout.py`
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified local NiceGUI URL, screenshot notes, and final task memory entry.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest -q
```

Expected: PASS.

- [ ] **Step 2: Start NiceGUI server**

Run:

```powershell
.venv-win\Scripts\python.exe scripts\run_nicegui.py
```

Expected: server starts on `http://127.0.0.1:8502`.

- [ ] **Step 3: Browser verification**

Open these URLs:

```text
http://127.0.0.1:8502/
http://127.0.0.1:8502/page/market
http://127.0.0.1:8502/page/etf-data
http://127.0.0.1:8502/page/maintenance
```

Verify:

- Sidebar is dark, compact, and stable.
- Topbar height is about 42px.
- Tables have compact row height and fixed visual rhythm.
- Market and ETF pages no longer look like loose Streamlit pages.
- Each migrated page shows UI correction notes.
- No text overlaps at desktop width around 1920px and narrow width around 390px.

- [ ] **Step 4: Polish CSS if screenshots show spacing or contrast problems**

Only adjust CSS tokens in `theme.py` and layout classes in `layout.py`. Keep fixes scoped to:

```python
WORKBENCH_CSS = WORKBENCH_CSS.replace("padding: 14px 18px 18px", "padding: 12px 16px 16px")
```

Use direct edits instead of runtime string replacement in final code; the snippet above names the intended value change.

- [ ] **Step 5: Update task memory**

Append to `docs/task-memory.md`:

```md
## 2026-07-05 - Implement NiceGUI UI migration v1

- Summary: Added a NiceGUI-based ETF workbench UI with independent app shell, professional compact theme, high-frequency pages, UI audit notes, and Streamlit fallback preserved.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q` passed; NiceGUI manually verified at `http://127.0.0.1:8502`.
- Watch out next time:
  - Keep future visual polish in `nicegui_app/theme.py` and page-specific layout classes instead of touching backend logic.
  - Finish full K-line chart integration before removing Streamlit chart fallback.
```

- [ ] **Step 6: Commit**

```powershell
git add src/etf_trading/nicegui_app/theme.py src/etf_trading/nicegui_app/layout.py docs/task-memory.md
git commit -m "polish: verify NiceGUI workbench UI"
```

---

## Self-Review

Spec coverage:

- NiceGUI dependency and separate UI package: Task 1.
- Backend preservation and UI-neutral reuse: Task 2.
- Current UI audit requirement: Tasks 2, 6, 7, 8, 9.
- Professional visual quality bar: Tasks 3, 4, 9.
- High-frequency pages: Tasks 6, 7, 8.
- Chart strategy: Task 5 renders chart HTML and Task 9 wires ETF/index chart payloads before browser verification.
- State and explicit maintenance actions: Tasks 2, 7.
- Tests and browser verification: Tasks 1-10.

Placeholder scan:

- Task bodies contain concrete file paths, commands, expected results, and code snippets.

Type consistency:

- `PlatformSnapshot`, `MetricTile`, and `AuditFinding` are introduced in Task 2 and reused by Tasks 3, 6, 7, and 8.
- `render(snapshot: PlatformSnapshot, section: str) -> None` is consistent across page modules.
- `build_chart_html(payload: list[dict], element_id: str)` is introduced in Task 5 and does not require backend changes.
