# ETF Atomic Detail Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two switchable `ETF数据 -> 原子指标` list views and a selected-ETF atomic indicator detail section without changing indicator calculations.

**Architecture:** Keep the calculation layer unchanged. Add UI-neutral view-model helpers that slice the same atomic snapshot into `机会特征` and `体检特征` rows, plus grouped detail rows. Then update the NiceGUI page to render a toggle, a selectable/clickable main table, and a grouped detail area.

**Tech Stack:** Python 3.11, pandas, NiceGUI, pytest.

## Global Constraints

- Do not modify `research.atomic_indicators` calculation fields or ranking rules.
- Do not output composite scores, temperature scores, buy/sell advice, position targets, or trade actions.
- Keep `ETF数据 -> 原子指标` as the only entry point for this workflow.
- Default the list view to `机会特征`.
- Keep current search, category, history-status, feature-status, minimum-amount, breakout, weekly-strength, refresh, and maintenance-link behavior.
- Respect the current dirty worktree: stage and commit only files from the active task.

---

## File Structure

- `src/etf_trading/nicegui_app/view_models.py`
  Owns the UI-neutral list slicing, filtered atomic frame helper, ETF option helper, and grouped detail rows.
- `src/etf_trading/nicegui_app/components/tables.py`
  Adds missing display labels and compact widths for fields surfaced by the new detail/list views.
- `src/etf_trading/nicegui_app/pages/etf_data.py`
  Owns the NiceGUI toggle, selected ETF state, row-click handling, and grouped detail rendering.
- `tests/test_nicegui_view_models.py`
  Verifies the two list views, filtering behavior, detail options, and detail group content.
- `tests/test_nicegui_table_display.py`
  Verifies table labels and display conversion for the newly exposed slope field.
- `tests/test_nicegui_app_import.py`
  Verifies the page uses cached snapshots, defaults to the opportunity view, and renders detail groups.
- `tests/test_nicegui_theme.py`
  Verifies any added CSS hooks if Task 2 adds them.
- `docs/task-memory.md`
  Records reusable notes after implementation and verification.

---

### Task 1: View-Model List Views and Detail Groups

**Files:**
- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Modify: `src/etf_trading/nicegui_app/components/tables.py`
- Test: `tests/test_nicegui_view_models.py`
- Test: `tests/test_nicegui_table_display.py`

**Interfaces:**
- Produces: `ATOMIC_OPPORTUNITY_COLUMNS: tuple[str, ...]`
- Produces: `ATOMIC_HEALTH_COLUMNS: tuple[str, ...]`
- Produces: `ATOMIC_VIEW_MODES: tuple[str, ...]`
- Produces: `AtomicIndicatorDetailGroup(title: str, rows: list[dict[str, object]])`
- Produces: `filter_atomic_indicator_frame(frame: pd.DataFrame, filters: AtomicIndicatorFilters | None = None) -> pd.DataFrame`
- Updates: `atomic_indicator_rows(frame: pd.DataFrame, filters: AtomicIndicatorFilters | None = None, limit: int = 300, view_mode: str = "机会特征") -> list[dict[str, object]]`
- Produces: `atomic_indicator_detail_options(frame: pd.DataFrame, filters: AtomicIndicatorFilters | None = None, limit: int = 300) -> list[str]`
- Produces: `atomic_indicator_detail_groups(frame: pd.DataFrame, etf_code: str) -> list[AtomicIndicatorDetailGroup]`

- [ ] **Step 1: Extend the atomic fixture for newly visible fields**

In `tests/test_nicegui_view_models.py`, update imports:

```python
from etf_trading.nicegui_app.view_models import (
    ATOMIC_HEALTH_COLUMNS,
    ATOMIC_OPPORTUNITY_COLUMNS,
    AtomicIndicatorFilters,
    PlatformSnapshot,
    atomic_indicator_detail_groups,
    atomic_indicator_detail_options,
    atomic_indicator_rows,
    atomic_indicator_summary,
    category_options,
    code_from_option,
    current_ui_audit_findings,
    etf_choice_options,
    etf_overview_rows,
    filter_atomic_indicator_frame,
    filter_etf_rows,
    index_choice_options,
    maintenance_rows,
    market_overview,
    status_metrics,
)
```

Add `history_rows` and `ma60_slope_20` to `_atomic_frame()`:

```python
            "latest_trade_date": ["2026-07-03", ""],
            "history_rows": [520, 0],
            "return_20": [0.08, None],
            "return_60": [0.12, None],
```

and:

```python
            "close_above_ma60": [True, None],
            "ma60_slope_20": [0.015, None],
            "weekly_close_above_ma10": [True, None],
```

- [ ] **Step 2: Write failing tests for the two table views**

Append to `tests/test_nicegui_view_models.py`:

```python
def test_atomic_indicator_rows_support_opportunity_and_health_views():
    opportunity = atomic_indicator_rows(_atomic_frame(), view_mode="机会特征")
    health = atomic_indicator_rows(_atomic_frame(), view_mode="体检特征")

    assert tuple(opportunity[0].keys()) == ATOMIC_OPPORTUNITY_COLUMNS
    assert tuple(health[0].keys()) == ATOMIC_HEALTH_COLUMNS
    assert opportunity[0]["ETF代码"] == "510300"
    assert opportunity[0]["20日收益"] == "8.0%"
    assert opportunity[0]["60日突破"] == "是"
    assert opportunity[0]["周线>10周"] == "是"
    assert health[0]["历史行数"] == 520
    assert health[0]["收盘>20日线"] == "是"
    assert health[0]["周线>30周"] == "否"
    assert "缺失字段" in health[1]
```

Append:

```python
def test_atomic_indicator_view_switch_keeps_filter_results_stable():
    filters = AtomicIndicatorFilters(query="300", only_breakout=True, only_weekly_ma10=True)

    filtered = filter_atomic_indicator_frame(_atomic_frame(), filters)
    opportunity = atomic_indicator_rows(_atomic_frame(), filters, view_mode="机会特征")
    health = atomic_indicator_rows(_atomic_frame(), filters, view_mode="体检特征")

    assert filtered["etf_code"].tolist() == ["510300"]
    assert [row["ETF代码"] for row in opportunity] == ["510300"]
    assert [row["ETF代码"] for row in health] == ["510300"]
```

- [ ] **Step 3: Write failing tests for detail options and grouped detail rows**

Append to `tests/test_nicegui_view_models.py`:

```python
def test_atomic_indicator_detail_options_follow_current_filters():
    options = atomic_indicator_detail_options(
        _atomic_frame(),
        AtomicIndicatorFilters(category="A股宽基"),
    )

    assert options == ["510300 沪深300ETF · A股宽基"]
    assert code_from_option(options[0]) == "510300"
```

Append:

```python
def test_atomic_indicator_detail_groups_show_all_atomic_sections_without_advice():
    groups = atomic_indicator_detail_groups(_atomic_frame(), "510300")

    assert [group.title for group in groups] == ["身份信息", "数据体检", "相对强度", "趋势结构", "量能位置", "偏离程度"]
    flattened = {
        row["指标"]: row["数值"]
        for group in groups
        for row in group.rows
    }
    assert flattened["ETF代码"] == "510300"
    assert flattened["历史状态"] == "完整"
    assert flattened["20日收益"] == "8.0%"
    assert flattened["60日线20日斜率"] == "0.01"
    assert flattened["5/20成交额"] == "1.33"
    assert flattened["距20日线ATR"] == "1.20"
    forbidden = {"综合分", "温度分", "买入", "卖出", "目标仓位"}
    assert forbidden.isdisjoint(flattened)
```

Append:

```python
def test_atomic_indicator_detail_groups_return_empty_for_missing_code():
    assert atomic_indicator_detail_groups(_atomic_frame(), "999999") == []
```

- [ ] **Step 4: Write failing table-label test for the exposed slope field**

Append to `tests/test_nicegui_table_display.py`:

```python
def test_atomic_indicator_new_detail_labels_are_human_readable():
    rows = [{"ma60_slope_20": 0.015, "history_rows": 520}]

    labels = [column["label"] for column in table_columns(rows)]

    assert labels == ["60日线20日斜率", "历史行数"]
```

- [ ] **Step 5: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py -q
```

Expected: FAIL because `ATOMIC_OPPORTUNITY_COLUMNS`, `ATOMIC_HEALTH_COLUMNS`, `filter_atomic_indicator_frame`, `atomic_indicator_detail_options`, `atomic_indicator_detail_groups`, and the `ma60_slope_20` label do not exist yet.

- [ ] **Step 6: Add table labels for fields surfaced by the detail view**

In `src/etf_trading/nicegui_app/components/tables.py`, add these entries to `COLUMN_LABELS`:

```python
    "ma60_slope_20": "60日线20日斜率",
    "history_rows": "历史行数",
```

Keep the existing `history_rows` entry if already present; add only `ma60_slope_20` when `history_rows` already exists.

Add compact widths:

```python
    "history_rows": 88,
    "ma60_slope_20": 120,
```

If `history_rows` already exists in `COMPACT_COLUMN_WIDTHS`, add only `ma60_slope_20`.

- [ ] **Step 7: Add the view-model constants and detail dataclass**

In `src/etf_trading/nicegui_app/view_models.py`, add imports:

```python
from dataclasses import dataclass
```

This import already exists; do not duplicate it.

Below `AtomicIndicatorFilters`, add:

```python
ATOMIC_VIEW_MODES = ("机会特征", "体检特征")

ATOMIC_OPPORTUNITY_COLUMNS = (
    "ETF代码",
    "ETF名称",
    "分类",
    "20日收益",
    "60日收益",
    "20日全池排名",
    "60日全池排名",
    "20日同类排名",
    "60日同类排名",
    "60日突破",
    "周线>10周",
    "20日成交额",
)

ATOMIC_HEALTH_COLUMNS = (
    "ETF代码",
    "ETF名称",
    "分类",
    "最新交易日",
    "历史状态",
    "特征状态",
    "历史行数",
    "缺失字段",
    "收盘>20日线",
    "20日线>60日线",
    "收盘>60日线",
    "周线>30周",
    "距20日线",
    "距20日线ATR",
    "5/20成交额",
)


@dataclass(frozen=True)
class AtomicIndicatorDetailGroup:
    title: str
    rows: list[dict[str, object]]
```

- [ ] **Step 8: Extract the current filter logic into a reusable frame helper**

Replace the filtering block inside `atomic_indicator_rows()` with a new helper:

```python
def filter_atomic_indicator_frame(
    frame: pd.DataFrame,
    filters: AtomicIndicatorFilters | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    filters = filters or AtomicIndicatorFilters()
    data = frame.copy()
    query = filters.query.strip().lower()
    if query:
        searchable = (
            data.get("etf_code", "").astype(str)
            + " "
            + data.get("name", "").astype(str)
            + " "
            + data.get("category", "").astype(str)
        ).str.lower()
        data = data[searchable.str.contains(query, na=False)]

    if filters.category not in {"", "全部", "全部分类"} and "category" in data:
        data = data[data["category"].fillna("").astype(str) == filters.category]
    if filters.history_status not in {"", "全部", "全部历史状态"} and "history_status" in data:
        data = data[data["history_status"].fillna("").astype(str) == filters.history_status]
    if filters.feature_status not in {"", "全部", "全部特征状态"} and "feature_status" in data:
        data = data[data["feature_status"].fillna("").astype(str) == filters.feature_status]
    if filters.min_avg_amount_20 is not None and "avg_amount_20" in data:
        data = data[pd.to_numeric(data["avg_amount_20"], errors="coerce").fillna(0) >= float(filters.min_avg_amount_20)]
    if filters.only_breakout and "is_60d_close_breakout" in data:
        data = data[data["is_60d_close_breakout"].map(_truthy)]
    if filters.only_weekly_ma10 and "weekly_close_above_ma10" in data:
        data = data[data["weekly_close_above_ma10"].map(_truthy)]

    if "return_20_rank_all" in data:
        data = data.assign(_rank=pd.to_numeric(data["return_20_rank_all"], errors="coerce"))
        data = data.sort_values(["_rank", "etf_code"], na_position="last").drop(columns=["_rank"])
    return data
```

Update `atomic_indicator_rows()` to consume it:

```python
def atomic_indicator_rows(
    frame: pd.DataFrame,
    filters: AtomicIndicatorFilters | None = None,
    limit: int = 300,
    view_mode: str = "机会特征",
) -> list[dict[str, object]]:
    data = filter_atomic_indicator_frame(frame, filters)
    if data.empty:
        return []

    columns = ATOMIC_HEALTH_COLUMNS if view_mode == "体检特征" else ATOMIC_OPPORTUNITY_COLUMNS
    rows = []
    for row in data.head(limit).to_dict("records"):
        display = _atomic_display_row(row)
        rows.append({column: display.get(column, "") for column in columns})
    return rows
```

- [ ] **Step 9: Add detail options and grouped details**

In `src/etf_trading/nicegui_app/view_models.py`, add:

```python
def atomic_indicator_detail_options(
    frame: pd.DataFrame,
    filters: AtomicIndicatorFilters | None = None,
    limit: int = 300,
) -> list[str]:
    data = filter_atomic_indicator_frame(frame, filters)
    options: list[str] = []
    for row in data.head(limit).fillna("").to_dict("records"):
        code = str(row.get("etf_code", "")).strip()
        if not code:
            continue
        name = str(row.get("name", "")).strip()
        category = str(row.get("category", "")).strip()
        label = f"{code} {name}".strip()
        if category:
            label = f"{label} · {category}"
        options.append(label)
    return options
```

Add:

```python
def atomic_indicator_detail_groups(frame: pd.DataFrame, etf_code: str) -> list[AtomicIndicatorDetailGroup]:
    if frame.empty or not etf_code or "etf_code" not in frame:
        return []

    matches = frame[frame["etf_code"].fillna("").astype(str) == str(etf_code)]
    if matches.empty:
        return []

    display = _atomic_display_row(matches.iloc[0].to_dict())
    groups = (
        ("身份信息", ("ETF代码", "ETF名称", "分类", "交易所", "最新交易日")),
        ("数据体检", ("历史状态", "特征状态", "历史行数", "缺失字段")),
        ("相对强度", ("20日收益", "60日收益", "20日全池排名", "60日全池排名", "20日同类排名", "60日同类排名")),
        ("趋势结构", ("收盘>20日线", "20日线>60日线", "收盘>60日线", "周线>10周", "周线>30周", "60日突破", "60日线20日斜率")),
        ("量能位置", ("5日成交额", "20日成交额", "5/20成交额")),
        ("偏离程度", ("距20日线", "距20日线ATR")),
    )
    return [
        AtomicIndicatorDetailGroup(
            title=title,
            rows=[{"指标": label, "数值": display.get(label, "")} for label in labels],
        )
        for title, labels in groups
    ]
```

- [ ] **Step 10: Add missing display values in `_atomic_display_row()`**

In `_atomic_display_row()`, add:

```python
        "历史行数": _value_or_blank(row.get("history_rows")),
```

after `特征状态`, and add:

```python
        "60日线20日斜率": _format_number(row.get("ma60_slope_20")),
```

near the trend fields.

Add helper:

```python
def _value_or_blank(value: object) -> object:
    if _missing(value):
        return ""
    return value
```

- [ ] **Step 11: Run focused tests to verify Task 1 passes**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py -q
```

Expected: PASS.

- [ ] **Step 12: Commit Task 1**

```powershell
git add src/etf_trading/nicegui_app/view_models.py src/etf_trading/nicegui_app/components/tables.py tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py
git commit -m "feat: add ETF atomic view model slices"
```

---

### Task 2: NiceGUI Toggle, Selection, and Detail Rendering

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/etf_data.py`
- Modify: `src/etf_trading/nicegui_app/theme.py`
- Test: `tests/test_nicegui_app_import.py`
- Test: `tests/test_nicegui_theme.py`

**Interfaces:**
- Consumes: `ATOMIC_VIEW_MODES`
- Consumes: `atomic_indicator_rows(frame, filters, limit=300, view_mode="机会特征")`
- Consumes: `atomic_indicator_detail_options(frame, filters, limit=300) -> list[str]`
- Consumes: `atomic_indicator_detail_groups(frame, etf_code) -> list[AtomicIndicatorDetailGroup]`
- Produces: `_event_row_code(event) -> str`
- Updates: `_render_atomic_indicators(snapshot, parquet_store) -> None`

- [ ] **Step 1: Write failing page smoke test for toggle and detail rendering**

In `tests/test_nicegui_app_import.py`, update `test_atomic_indicator_page_uses_cached_snapshot`.

Inside `FakeElement`, add:

```python
        def on(self, event_name, handler):
            self.event_name = event_name
            self.handler = handler
            return self
```

Inside `FakeUi`, add:

```python
        def toggle(self, options, value=None):
            return FakeElement(value=value, options=options)
```

Change collected values before `FakeUi`:

```python
    labels = []
    table_rows = []
    toggle_values = []
```

In `FakeUi.toggle`, capture options:

```python
        def toggle(self, options, value=None):
            toggle_values.append((tuple(options), value))
            return FakeElement(value=value, options=options)
```

In `FakeUi.label`, capture labels:

```python
        def label(self, text):
            labels.append(text)
            return FakeElement()
```

Add fields to `frame`:

```python
            "latest_trade_date": ["2026-07-03"],
            "history_rows": [520],
            "ma60_slope_20": [0.015],
```

Replace final assertions with:

```python
    assert calls == [False]
    assert toggle_values == [(("机会特征", "体检特征"), "机会特征")]
    assert table_rows[0]["ETF代码"] == "510300"
    assert tuple(table_rows[0].keys()) == (
        "ETF代码",
        "ETF名称",
        "分类",
        "20日收益",
        "60日收益",
        "20日全池排名",
        "60日全池排名",
        "20日同类排名",
        "60日同类排名",
        "60日突破",
        "周线>10周",
        "20日成交额",
    )
    assert "原子指标详情：510300" in labels
    assert {"身份信息", "数据体检", "相对强度", "趋势结构", "量能位置", "偏离程度"}.issubset(set(labels))
```

- [ ] **Step 2: Write failing unit test for row-click event extraction**

Append to `tests/test_nicegui_app_import.py`:

```python
def test_atomic_row_click_event_extracts_etf_code():
    from etf_trading.nicegui_app.pages.etf_data import _event_row_code

    class Event:
        def __init__(self, args):
            self.args = args

    assert _event_row_code(Event([None, {"ETF代码": "510300"}])) == "510300"
    assert _event_row_code(Event({"row": {"ETF代码": "512880"}})) == "512880"
    assert _event_row_code(Event({"ETF代码": "159915"})) == "159915"
    assert _event_row_code(Event([])) == ""
```

- [ ] **Step 3: Write failing theme test for detail layout hooks**

Append to `tests/test_nicegui_theme.py`:

```python
def test_theme_contains_atomic_detail_layout_hooks():
    assert ".workbench-detail-grid" in WORKBENCH_CSS
    assert ".workbench-detail-group-title" in WORKBENCH_CSS
```

- [ ] **Step 4: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q
```

Expected: FAIL because `_event_row_code` and the new page rendering hooks do not exist.

- [ ] **Step 5: Add theme hooks for compact detail groups**

In `src/etf_trading/nicegui_app/theme.py`, add before `.workbench-action-panel`:

```css
.workbench-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
  width: 100%;
}
.workbench-detail-group {
  min-width: 0;
}
.workbench-detail-group-title {
  font-size: 13px;
  line-height: 18px;
  font-weight: 700;
  color: #334155;
}
```

- [ ] **Step 6: Import the new view-model helpers in `pages/etf_data.py`**

Update the import block from `etf_trading.nicegui_app.view_models`:

```python
from etf_trading.nicegui_app.view_models import (
    ATOMIC_VIEW_MODES,
    AtomicIndicatorFilters,
    PlatformSnapshot,
    atomic_indicator_detail_groups,
    atomic_indicator_detail_options,
    atomic_indicator_rows,
    atomic_indicator_summary,
    category_options,
    code_from_option,
    current_ui_audit_findings,
    etf_category_for_code,
    etf_choice_options,
    etf_overview_rows,
    filter_etf_rows,
)
```

- [ ] **Step 7: Add the row-click event helper**

In `src/etf_trading/nicegui_app/pages/etf_data.py`, add near other helper functions:

```python
def _event_row_code(event) -> str:
    args = getattr(event, "args", None)
    row = None
    if isinstance(args, dict):
        row = args.get("row") if isinstance(args.get("row"), dict) else args
    elif isinstance(args, (list, tuple)) and len(args) >= 2 and isinstance(args[1], dict):
        row = args[1]
    if not isinstance(row, dict):
        return ""
    return str(row.get("ETF代码") or row.get("etf_code") or "").strip()
```

- [ ] **Step 8: Add toggle, detail selector, and selected state to `_render_atomic_indicators()`**

Inside `_render_atomic_indicators()`, after `feature_statuses`:

```python
    selected_holder = {"code": ""}
```

Inside the toolbar, after `weekly_ma10` and before `刷新快照`:

```python
        view_mode = ui.toggle(list(ATOMIC_VIEW_MODES), value=ATOMIC_VIEW_MODES[0]).props("dense unelevated toggle-color=primary")
        detail_select = ui.select([], value=None, label="查看详情").props("dense outlined").classes("w-72")
```

After `result_area`:

```python
    detail_area = ui.column().classes("w-full gap-2")
```

- [ ] **Step 9: Render main rows with the selected view mode**

Replace `refresh_table()` in `pages/etf_data.py` with:

```python
    def refresh_table() -> None:
        filters = current_filters()
        rows = atomic_indicator_rows(frame_holder["frame"], filters, view_mode=str(view_mode.value or ATOMIC_VIEW_MODES[0]))
        options = atomic_indicator_detail_options(frame_holder["frame"], filters)
        current_code = selected_holder["code"]
        option_by_code = {code_from_option(option): option for option in options}
        if not current_code or current_code not in option_by_code:
            current_code = code_from_option(options[0]) if options else current_code
            selected_holder["code"] = current_code
        detail_select.options = options
        detail_select.value = option_by_code.get(current_code)
        detail_select.update()

        result_area.clear()
        with result_area:
            if rows:
                ui.table(
                    columns=table_columns(rows, compact=True),
                    rows=table_rows(rows),
                    row_key="ETF代码",
                    pagination=15,
                ).classes("workbench-data-table w-full").on("rowClick", lambda event: select_detail(_event_row_code(event)))
            else:
                empty_state("没有匹配原子指标", "换一个筛选条件，或到数据维护补齐历史。")
        render_details()
```

- [ ] **Step 10: Add detail selection and grouped detail rendering**

Inside `_render_atomic_indicators()`, before `reload_snapshot()`:

```python
    def select_detail(etf_code: str) -> None:
        if not etf_code:
            return
        selected_holder["code"] = etf_code
        for option in detail_select.options:
            if code_from_option(option) == etf_code:
                detail_select.value = option
                detail_select.update()
                break
        render_details()

    def render_details() -> None:
        detail_area.clear()
        etf_code = selected_holder["code"]
        with detail_area:
            if not etf_code:
                empty_state("暂无原子指标详情", "请选择一只 ETF 查看完整原子指标。")
                return
            groups = atomic_indicator_detail_groups(frame_holder["frame"], etf_code)
            if not groups:
                empty_state("暂无原子指标详情", "当前快照中没有这只 ETF。")
                return
            ui.label(f"原子指标详情：{etf_code}").classes("text-sm font-semibold text-slate-700")
            with ui.element("div").classes("workbench-detail-grid"):
                for group in groups:
                    with ui.column().classes("workbench-detail-group gap-1"):
                        ui.label(group.title).classes("workbench-detail-group-title")
                        ui.table(
                            columns=table_columns(group.rows, compact=True),
                            rows=table_rows(group.rows),
                            pagination=False,
                        ).classes("workbench-data-table workbench-data-table--compact")
```

- [ ] **Step 11: Wire handlers and reload behavior**

Add handlers near existing `on_value_change` calls:

```python
    view_mode.on_value_change(lambda event: refresh_table())
    detail_select.on_value_change(lambda event: select_detail(code_from_option(str(detail_select.value or ""))))
```

In `reload_snapshot()`, keep the existing calls and ensure it still calls:

```python
        refresh_table()
```

`refresh_table()` now refreshes details, so do not add a second `render_details()` call in `reload_snapshot()`.

- [ ] **Step 12: Run focused page and theme tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q
```

Expected: PASS.

- [ ] **Step 13: Commit Task 2**

```powershell
git add src/etf_trading/nicegui_app/pages/etf_data.py src/etf_trading/nicegui_app/theme.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py
git commit -m "feat: render ETF atomic detail toggle"
```

---

### Task 3: Verification, Browser Check, and Task Memory

**Files:**
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: Task 1 and Task 2 implemented behavior.
- Produces: Verification evidence and a reusable memory note.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q --basetemp pytest-tmp-etf-atomic-toggle-focused
```

Expected: PASS.

- [ ] **Step 2: Run nearby regressions**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_atomic_indicators.py tests/test_nicegui_navigation.py tests/test_nicegui_state_cache.py tests/test_nicegui_charts.py -q --basetemp pytest-tmp-etf-atomic-toggle-regression
```

Expected: PASS.

- [ ] **Step 3: Run forbidden-output scan**

Run:

```powershell
rg -n "综合分|温度分|估值总分|买卖分|target_weight|目标仓位|BUY|SELL|REDUCE|买入|卖出|减仓" src\etf_trading\nicegui_app\view_models.py src\etf_trading\nicegui_app\pages\etf_data.py tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py
```

Expected: no production UI output introduces score or trading advice labels. Existing tests may contain forbidden strings only inside absence assertions.

- [ ] **Step 4: Browser-check the running page**

Start or reuse the app:

```powershell
Set-Location 'H:\pythonproject\etf0614\etf0614'; .\.venv-win\Scripts\python.exe scripts\run_nicegui.py
```

Open:

```text
http://127.0.0.1:8502/page/etf-data/%E5%8E%9F%E5%AD%90%E6%8C%87%E6%A0%87
```

Verify visually:

- The default toggle is `机会特征`.
- The main table shows opportunity columns, not the full wide table.
- Clicking `体检特征` changes the columns.
- Selecting or clicking `510300` or the first visible ETF shows `原子指标详情`.
- The detail section shows the six groups from the spec.

- [ ] **Step 5: Append task memory**

Append to `docs/task-memory.md`:

```markdown
## 2026-07-07 - ETF atomic detail toggle

- Summary: Added `机会特征` and `体检特征` views for `ETF数据 -> 原子指标`, plus selected-ETF grouped atomic indicator details.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q --basetemp pytest-tmp-etf-atomic-toggle-focused` passed; `.venv-win\Scripts\python.exe -m pytest tests/test_atomic_indicators.py tests/test_nicegui_navigation.py tests/test_nicegui_state_cache.py tests/test_nicegui_charts.py -q --basetemp pytest-tmp-etf-atomic-toggle-regression` passed; browser checked `ETF数据 -> 原子指标`.
- Watch out next time:
  - Keep the atomic snapshot calculation unchanged when adding UI views; view models should slice and format only.
  - Keep list views narrow and purpose-specific; use the detail area for complete per-ETF diagnostics.
  - Avoid adding scores or trade advice to the atomic indicator page.
```

- [ ] **Step 6: Commit Task 3**

```powershell
git add docs/task-memory.md
git commit -m "docs: record ETF atomic detail toggle work"
```

---

## Self-Review

**Spec coverage:**
Task 1 covers the two list column sets, default row slicing, filtering stability, detail options, and grouped detail data. Task 2 covers the clickable toggle, selected ETF state, row-click support, and detail rendering. Task 3 covers focused tests, regressions, forbidden-output scan, browser verification, and task memory.

**Placeholder scan:**
This plan contains exact file paths, interfaces, test snippets, implementation snippets, commands, and expected outcomes. It does not contain deferred placeholders.

**Type consistency:**
`atomic_indicator_rows()` keeps its existing arguments and adds `view_mode` at the end with default `机会特征`. `atomic_indicator_detail_options()` returns option labels compatible with existing `code_from_option()`. `atomic_indicator_detail_groups()` returns `AtomicIndicatorDetailGroup` objects consumed directly by `pages/etf_data.py`.
