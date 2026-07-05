# NiceGUI Global Chart Toolbar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all NiceGUI K-line pages use a compact, globally consistent chart header and left-aligned ETF/index selector area.

**Architecture:** Put chart title, range metadata, range toggle, custom date controls, and chart rendering in the shared `render_ranged_lightweight_chart` component. Keep page modules responsible only for selecting the ETF/index and showing a nearby low-priority note. Add CSS classes in the existing workbench theme so all pages inherit the same spacing and wrapping behavior.

**Tech Stack:** Python 3.11, NiceGUI, ECharts through `ui.echart`, pytest, existing `WORKBENCH_CSS`.

## Global Constraints

- Keep existing business logic, data loading, chart payload, ECharts options, range filtering, tooltip, and navigation behavior unchanged.
- Do not adjust Streamlit pages.
- Do not add decorative cards, marketing layout, new chart libraries, or new runtime dependencies.
- Do not use `justify-between` for business-level chart selector rows or inside `render_ranged_lightweight_chart`.
- Do not stage or commit unrelated existing dirty worktree changes; inspect staged files before any commit.

---

## File Structure

- `src/etf_trading/nicegui_app/components/charts.py`: owns shared K-line chart header, record range metadata, custom date controls, and chart render area.
- `src/etf_trading/nicegui_app/pages/market.py`: owns `市场地图 -> 指数K线` selector and explanatory note.
- `src/etf_trading/nicegui_app/pages/etf_data.py`: owns `ETF数据 -> ETF行情` selector and explanatory note.
- `src/etf_trading/nicegui_app/theme.py`: owns global workbench CSS classes for chart headers and selector rows.
- `tests/test_nicegui_charts.py`: verifies shared chart component class structure and preserved chart behavior.
- `tests/test_nicegui_app_import.py`: verifies page-level selector rows avoid wide-screen split alignment.
- `docs/task-memory.md`: records the completed UI alignment change and verification.

---

### Task 1: Add Layout Regression Tests

**Files:**
- Modify: `tests/test_nicegui_charts.py`
- Modify: `tests/test_nicegui_app_import.py`

**Interfaces:**
- Consumes: `render_ranged_lightweight_chart(payload, *, element_id: str, title: str, default_range_label: str = ...) -> None`
- Consumes: `market._render_index_chart(snapshot: PlatformSnapshot, parquet_store) -> None`
- Consumes: `etf_data._render_etf_chart(snapshot: PlatformSnapshot, parquet_store) -> None`
- Produces: failing tests that define the compact chart header and selector alignment contract.

- [ ] **Step 1: Add the failing shared chart header test**

Append this test to `tests/test_nicegui_charts.py` after the existing tooltip formatter test:

```python
def test_ranged_chart_component_uses_compact_header_classes():
    import inspect

    from etf_trading.nicegui_app.components import charts
    from etf_trading.nicegui_app.theme import WORKBENCH_CSS

    source = inspect.getsource(charts.render_ranged_lightweight_chart)

    assert "workbench-chart-header" in source
    assert "workbench-chart-title-group" in source
    assert "workbench-chart-meta" in source
    assert "workbench-chart-custom-controls" in source
    assert "workbench-toolbar w-full justify-between" not in source
    assert "workbench-toolbar w-full justify-end" not in source
    assert ".workbench-chart-header" in WORKBENCH_CSS
    assert ".workbench-chart-title-group" in WORKBENCH_CSS
    assert ".workbench-chart-meta" in WORKBENCH_CSS
    assert ".workbench-chart-custom-controls" in WORKBENCH_CSS
```

- [ ] **Step 2: Add the failing page selector alignment test**

Append this test to `tests/test_nicegui_app_import.py` after `test_nicegui_page_header_places_section_tabs_under_title`:

```python
def test_kline_selector_rows_do_not_split_across_wide_pages():
    import inspect

    from etf_trading.nicegui_app.pages import etf_data, market
    from etf_trading.nicegui_app.theme import WORKBENCH_CSS

    market_source = inspect.getsource(market._render_index_chart)
    etf_source = inspect.getsource(etf_data._render_etf_chart)

    assert "workbench-chart-selector" in market_source
    assert "workbench-chart-selector" in etf_source
    assert "workbench-chart-note" in market_source
    assert "workbench-chart-note" in etf_source
    assert "justify-between" not in market_source
    assert "justify-between" not in etf_source
    assert ".workbench-chart-selector" in WORKBENCH_CSS
    assert ".workbench-chart-note" in WORKBENCH_CSS
```

- [ ] **Step 3: Run tests to verify they fail for the intended reason**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py::test_ranged_chart_component_uses_compact_header_classes tests/test_nicegui_app_import.py::test_kline_selector_rows_do_not_split_across_wide_pages -q
```

Expected: both tests fail because the new `workbench-chart-*` classes are not implemented and the page selector rows still use `justify-between`.

- [ ] **Step 4: Do not commit yet**

Keep the failing tests in the worktree. They become the red phase for Tasks 2 and 3.

---

### Task 2: Compact the Shared Ranged Chart Header

**Files:**
- Modify: `src/etf_trading/nicegui_app/components/charts.py`
- Modify: `src/etf_trading/nicegui_app/theme.py`
- Test: `tests/test_nicegui_charts.py`

**Interfaces:**
- Consumes: `chart_date_bounds(payload: list[dict]) -> tuple[str | None, str | None]`
- Consumes: `chart_range_window(payload: list[dict], range_label: str, *, start_date: str | date | None = None, end_date: str | date | None = None) -> tuple[str | None, str | None]`
- Consumes: `chart_record_label(payload: list[dict], *, range_label: str | None = None, visible_start: str | None = None, visible_end: str | None = None) -> str`
- Produces: `render_ranged_lightweight_chart(...)` with compact header classes and unchanged range/chart behavior.

- [ ] **Step 1: Replace the chart component layout**

In `src/etf_trading/nicegui_app/components/charts.py`, replace only the top layout block inside `render_ranged_lightweight_chart`:

```python
    with ui.column().classes("w-full gap-2"):
        with ui.row().classes("workbench-toolbar w-full justify-between"):
            ui.label(title).classes("text-sm font-semibold text-slate-700")
            ui.toggle(
                list(CHART_RANGE_PRESETS),
                value=state["label"],
                on_change=lambda event: select_range(str(event.value)),
            ).props("dense unelevated no-caps").classes("workbench-range-toggle")
        custom_area = ui.row().classes("workbench-toolbar w-full justify-end")
        chart_area = ui.column().classes("w-full gap-2")
```

with this layout:

```python
    with ui.column().classes("w-full gap-2"):
        with ui.row().classes("workbench-chart-header w-full"):
            with ui.column().classes("workbench-chart-title-group"):
                ui.label(title).classes("workbench-chart-title")
                record_area = ui.row().classes("workbench-chart-meta-row")
            ui.toggle(
                list(CHART_RANGE_PRESETS),
                value=state["label"],
                on_change=lambda event: select_range(str(event.value)),
            ).props("dense unelevated no-caps").classes("workbench-range-toggle")
        custom_area = ui.row().classes("workbench-chart-custom-controls w-full")
        chart_area = ui.column().classes("w-full gap-2")
```

- [ ] **Step 2: Move the record label into the compact header**

In the `render_chart()` nested function in `src/etf_trading/nicegui_app/components/charts.py`, replace this block:

```python
            with ui.row().classes("workbench-toolbar w-full justify-end"):
                ui.label(
                    chart_record_label(
                        payload,
                        range_label=str(state["label"]),
                        visible_start=visible_start,
                        visible_end=visible_end,
                    )
                ).classes("text-xs text-slate-500")
            render_lightweight_chart(
```

with:

```python
            record_area.clear()
            with record_area:
                ui.label(
                    chart_record_label(
                        payload,
                        range_label=str(state["label"]),
                        visible_start=visible_start,
                        visible_end=visible_end,
                    )
                ).classes("workbench-chart-meta")
            render_lightweight_chart(
```

- [ ] **Step 3: Add shared chart CSS**

In `src/etf_trading/nicegui_app/theme.py`, add these rules after `.workbench-toolbar`:

```css
.workbench-chart-header {
  min-height: 36px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px 14px;
  flex-wrap: wrap;
  min-width: 0;
}
.workbench-chart-title-group {
  min-width: 220px;
  flex: 1 1 320px;
  gap: 0;
}
.workbench-chart-title {
  font-size: 13px;
  line-height: 18px;
  font-weight: 700;
  color: #334155;
}
.workbench-chart-meta-row {
  min-height: 16px;
}
.workbench-chart-meta {
  font-size: 12px;
  line-height: 16px;
  color: var(--wb-muted);
}
.workbench-chart-custom-controls {
  min-height: 0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
```

- [ ] **Step 4: Run the shared chart tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py -q
```

Expected: all chart tests pass except `test_kline_selector_rows_do_not_split_across_wide_pages`, which belongs to Task 3 and may still fail if run together.

- [ ] **Step 5: Review the diff before continuing**

Run:

```powershell
git diff -- src/etf_trading/nicegui_app/components/charts.py src/etf_trading/nicegui_app/theme.py tests/test_nicegui_charts.py
```

Expected: diffs only cover compact chart header layout, chart CSS, and the chart layout test.

---

### Task 3: Align ETF and Index Selector Rows

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/market.py`
- Modify: `src/etf_trading/nicegui_app/pages/etf_data.py`
- Modify: `src/etf_trading/nicegui_app/theme.py`
- Test: `tests/test_nicegui_app_import.py`

**Interfaces:**
- Consumes: `index_choice_options(snapshot.index_summary) -> list[str]`
- Consumes: `etf_choice_options(etf_overview_rows(snapshot)) -> list[str]`
- Produces: `workbench-chart-selector` rows for K-line page selectors and nearby `workbench-chart-note` labels.

- [ ] **Step 1: Add selector CSS**

In `src/etf_trading/nicegui_app/theme.py`, add these rules after the chart header CSS from Task 2:

```css
.workbench-chart-selector {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 8px 12px;
  flex-wrap: wrap;
  min-width: 0;
}
.workbench-chart-selector .q-field {
  flex: 0 1 420px;
  max-width: 100%;
}
.workbench-chart-note {
  font-size: 12px;
  line-height: 16px;
  color: var(--wb-muted);
  max-width: 560px;
}
```

- [ ] **Step 2: Update the market index selector**

In `src/etf_trading/nicegui_app/pages/market.py`, replace:

```python
    with ui.row().classes("workbench-toolbar w-full justify-between"):
        ui.select(
            options,
            value=options[0],
            label="选择指数",
            on_change=lambda event: draw_chart(event.value),
        ).props("dense outlined").classes("w-96")
        ui.label("指数只做市场状态判断，ETF 交易载体在 ETF 数据页处理。").classes("text-xs text-slate-500")
```

with:

```python
    with ui.row().classes("workbench-chart-selector w-full"):
        ui.select(
            options,
            value=options[0],
            label="选择指数",
            on_change=lambda event: draw_chart(event.value),
        ).props("dense outlined").classes("w-96")
        ui.label("指数只做市场状态判断，ETF 交易载体在 ETF 数据页处理。").classes("workbench-chart-note")
```

- [ ] **Step 3: Update the ETF selector**

In `src/etf_trading/nicegui_app/pages/etf_data.py`, replace:

```python
    with ui.row().classes("workbench-toolbar w-full justify-between"):
        ui.select(
            options,
            value=options[0],
            label="选择ETF",
            on_change=lambda event: draw_chart(event.value),
        ).props("dense outlined").classes("w-96")
        ui.label("这里只看 ETF 交易载体行情，指数状态在市场地图查看。").classes("text-xs text-slate-500")
```

with:

```python
    with ui.row().classes("workbench-chart-selector w-full"):
        ui.select(
            options,
            value=options[0],
            label="选择ETF",
            on_change=lambda event: draw_chart(event.value),
        ).props("dense outlined").classes("w-96")
        ui.label("这里只看 ETF 交易载体行情，指数状态在市场地图查看。").classes("workbench-chart-note")
```

- [ ] **Step 4: Run selector and chart tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py::test_kline_selector_rows_do_not_split_across_wide_pages tests/test_nicegui_charts.py::test_ranged_chart_component_uses_compact_header_classes -q
```

Expected: both tests pass.

- [ ] **Step 5: Review the selector diff**

Run:

```powershell
git diff -- src/etf_trading/nicegui_app/pages/market.py src/etf_trading/nicegui_app/pages/etf_data.py src/etf_trading/nicegui_app/theme.py tests/test_nicegui_app_import.py
```

Expected: diffs only cover chart selector alignment, selector CSS, and selector layout test.

---

### Task 4: Verify, Browser-Check, and Record Memory

**Files:**
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: all changes from Tasks 1-3.
- Produces: verified implementation and task-memory note.

- [ ] **Step 1: Run focused automated verification**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Start or reuse the NiceGUI dev server**

If no server is running for this repo, run:

```powershell
.venv-win\Scripts\python.exe scripts/run_nicegui.py --host 127.0.0.1 --port 8505
```

Expected: server starts and exposes `http://127.0.0.1:8505`.

- [ ] **Step 3: Browser-check affected pages**

Open these URLs in the app browser:

```text
http://127.0.0.1:8505/page/market/%E6%8C%87%E6%95%B0K%E7%BA%BF
http://127.0.0.1:8505/page/etf-data/ETF%E8%A1%8C%E6%83%85
http://127.0.0.1:8505/page/research/ETF%E5%A4%8D%E7%9B%98
```

Expected visual result:

- ETF/index selector and explanatory note sit together near the left content edge.
- Chart title, record range, and range toggle form one compact header.
- No large blank gap appears between selector area and chart.
- Desktop and narrow viewport layouts wrap without overlap.

- [ ] **Step 4: Add task memory entry**

Append this entry to `docs/task-memory.md` with the actual verification commands and browser URLs used:

```md
## 2026-07-05 - Align NiceGUI chart controls globally

- Summary: Unified NiceGUI K-line selector rows and the shared ranged chart header so ETF/index selection, chart titles, record counts, and range toggles stay visually grouped across market, ETF, and research pages.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q` passed; browser checked market index K-line, ETF行情, and research ETF复盘 pages.
- Watch out next time:
  - Keep business toolbars left-aligned unless a shell-level layout genuinely needs split alignment.
  - Put K-line title, record count, and range controls in the shared chart component so research pages inherit fixes automatically.
```

- [ ] **Step 5: Final diff and staging safety check**

Run:

```powershell
git status --short
git diff -- src/etf_trading/nicegui_app/components/charts.py src/etf_trading/nicegui_app/pages/market.py src/etf_trading/nicegui_app/pages/etf_data.py src/etf_trading/nicegui_app/theme.py tests/test_nicegui_charts.py tests/test_nicegui_app_import.py docs/task-memory.md
git diff --cached --name-only
```

Expected: implementation diffs are limited to the files listed in this plan; `git diff --cached --name-only` is empty unless a deliberate, reviewed commit is being made. If the touched files include unrelated pre-existing hunks, leave the implementation uncommitted and report that explicitly.
