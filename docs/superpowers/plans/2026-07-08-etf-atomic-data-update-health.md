# ETF Atomic Data Update Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace misleading row-level `正在刷新` history status with a compact data-update health summary on `ETF数据 -> 原子指标`.

**Architecture:** Keep ETF repair execution in `数据维护 -> 补齐任务`; the atomic page only diagnoses, filters, and links to maintenance. Put status semantics and counts in UI-neutral view models, render a small NiceGUI health panel in the atomic page, and keep styling in `theme.py`.

**Tech Stack:** Python 3.11, pandas, NiceGUI, pytest, existing `nicegui_app` helpers.

## Global Constraints

- Do not fetch ETF history directly from `ETF数据 -> 原子指标`.
- Do not add cross-page task queues or task progress.
- Do not change atomic indicator calculation logic.
- Do not change `数据维护 -> 补齐任务` execution logic.
- Do not add buy/sell advice, composite scores, or target position output.
- Row-level `history_status == "stale"` must display as `行情滞后`.
- Atomic snapshot cache `status == "stale"` must remain a sentence-level cache refresh prompt, not a row-level history label.
- Repair actions must route to `数据维护 -> 补齐任务`.

---

## File Structure

- `src/etf_trading/nicegui_app/view_models.py`
  - Owns atomic status labels, data-update health counts, and display row formatting.
- `src/etf_trading/nicegui_app/components/tables.py`
  - Owns generic table value localization, including `stale -> 行情滞后`.
- `src/etf_trading/nicegui_app/pages/etf_data.py`
  - Renders the atomic health panel and wires status item clicks to existing filters.
- `src/etf_trading/nicegui_app/theme.py`
  - Adds compact health panel CSS hooks.
- `tests/test_nicegui_view_models.py`
  - Covers UI-neutral health counts and row/detail labels.
- `tests/test_nicegui_table_display.py`
  - Covers status filter label mapping.
- `tests/test_nicegui_app_import.py`
  - Covers page rendering and click-to-filter behavior with fake NiceGUI objects.
- `tests/test_nicegui_theme.py`
  - Covers new CSS hooks.
- `docs/task-memory.md`
  - Receives a final dated entry after implementation.

---

### Task 1: Status Labels and Health Summary

**Files:**
- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Modify: `src/etf_trading/nicegui_app/components/tables.py`
- Test: `tests/test_nicegui_view_models.py`
- Test: `tests/test_nicegui_table_display.py`

**Interfaces:**
- Consumes: existing `atomic_indicator_rows(frame, filters=None, limit=300, view_mode="机会特征")`, `atomic_indicator_detail_groups(frame, etf_code)`, and `pages.etf_data._atomic_filter_options(frame, column, all_label)`.
- Produces:
  - `AtomicDataHealthItem`
  - `atomic_data_update_health(frame: pd.DataFrame) -> list[AtomicDataHealthItem]`
  - `ATOMIC_HISTORY_STATUS_LABELS: dict[str, str]`
  - `ATOMIC_FEATURE_STATUS_LABELS: dict[str, str]`

- [ ] **Step 1: Write failing view-model tests**

Append these tests to `tests/test_nicegui_view_models.py`, and add `atomic_data_update_health` to the import list.

```python
def test_atomic_indicator_rows_display_stale_history_as_price_lag():
    frame = _atomic_frame()
    frame.loc[0, "history_status"] = "stale"

    health_rows = atomic_indicator_rows(frame, view_mode="体检特征")
    groups = atomic_indicator_detail_groups(frame, "510300")
    flattened = {
        row["指标"]: row["数值"]
        for group in groups
        for row in group.rows
    }

    assert health_rows[0]["历史状态"] == "行情滞后"
    assert flattened["历史状态"] == "行情滞后"
    assert "正在刷新" not in " ".join(str(value) for value in health_rows[0].values())


def test_atomic_data_update_health_counts_repair_states():
    frame = pd.DataFrame(
        {
            "etf_code": ["510300", "512880", "159915", "588000", "560000"],
            "history_status": ["complete", "stale", "short_history", "missing_history", "read_failed"],
            "feature_status": ["complete", "complete", "missing_features", "missing_features", "missing_features"],
        }
    )

    items = atomic_data_update_health(frame)
    by_key = {item.key: item for item in items}

    assert [item.label for item in items] == ["行情滞后", "历史不足", "历史缺失", "读取失败", "特征缺失"]
    assert by_key["stale"].count == 1
    assert by_key["short_history"].count == 1
    assert by_key["missing_history"].count == 1
    assert by_key["read_failed"].count == 1
    assert by_key["missing_features"].count == 3
    assert by_key["stale"].filter_type == "history_status"
    assert by_key["stale"].filter_value == "stale"
    assert by_key["missing_features"].filter_type == "feature_status"
    assert by_key["missing_features"].filter_value == "missing_features"


def test_atomic_data_update_health_returns_zero_counts_for_empty_frame():
    items = atomic_data_update_health(pd.DataFrame())

    assert [item.count for item in items] == [0, 0, 0, 0, 0]
```

- [ ] **Step 2: Write failing table/filter tests**

Update `tests/test_nicegui_table_display.py` as follows.

```python
def test_table_rows_translate_internal_status_codes_and_booleans_to_chinese():
    rows = [
        {
            "large_trend": "UP",
            "medium_trend": "RANGE",
            "small_trend": "RIGHT_SIDE_START",
            "allows_new_position": True,
            "history_status": "stale",
            "feature_status": "missing_features",
            "missing_feature_names": "read_failed",
            "action": "BUY",
            "status": "FAILED",
            "note": "short_history",
        }
    ]

    display = table_rows(rows)

    assert display == [
        {
            "large_trend": "上升",
            "medium_trend": "震荡",
            "small_trend": "右侧开始",
            "allows_new_position": "是",
            "history_status": "行情滞后",
            "feature_status": "特征缺失",
            "missing_feature_names": "读取失败",
            "action": "买入",
            "status": "失败",
            "note": "历史不足",
        }
    ]
    rendered_text = " ".join(str(value) for value in display[0].values())
    for raw_code in ["UP", "RANGE", "RIGHT_SIDE_START", "true", "stale", "missing_features", "read_failed", "short_history", "BUY", "FAILED"]:
        assert raw_code not in rendered_text
    assert "正在刷新" not in rendered_text
```

Replace the existing `test_atomic_status_filter_options_show_chinese_labels_but_keep_internal_values` body with this version:

```python
def test_atomic_status_filter_options_show_chinese_labels_but_keep_internal_values():
    frame = {
        "history_status": ["complete", "missing_history", "short_history", "stale"],
    }

    options = _atomic_filter_options(frame, "history_status", "全部历史状态")

    assert list(options) == ["全部历史状态", "完整", "历史缺失", "历史不足", "行情滞后"]
    assert _atomic_filter_value(options, "全部历史状态") == "全部历史状态"
    assert _atomic_filter_value(options, "完整") == "complete"
    assert _atomic_filter_value(options, "历史缺失") == "missing_history"
    assert _atomic_filter_value(options, "历史不足") == "short_history"
    assert _atomic_filter_value(options, "行情滞后") == "stale"
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py::test_atomic_indicator_rows_display_stale_history_as_price_lag tests/test_nicegui_view_models.py::test_atomic_data_update_health_counts_repair_states tests/test_nicegui_view_models.py::test_atomic_data_update_health_returns_zero_counts_for_empty_frame tests/test_nicegui_table_display.py::test_table_rows_translate_internal_status_codes_and_booleans_to_chinese tests/test_nicegui_table_display.py::test_atomic_status_filter_options_show_chinese_labels_but_keep_internal_values -q
```

Expected: FAIL because `atomic_data_update_health` is not defined and `stale` still renders as `正在刷新`.

- [ ] **Step 4: Implement status labels and summary**

In `src/etf_trading/nicegui_app/view_models.py`, add this dataclass after `AtomicIndicatorDetailGroup`:

```python
@dataclass(frozen=True)
class AtomicDataHealthItem:
    key: str
    label: str
    count: int
    detail: str
    filter_type: str
    filter_value: str
    tone: str = "neutral"
```

Add these constants near the atomic column constants:

```python
ATOMIC_HISTORY_STATUS_LABELS = {
    "complete": "完整",
    "stale": "行情滞后",
    "missing_history": "历史缺失",
    "short_history": "历史不足",
    "read_failed": "读取失败",
    "invalid_trade_date": "交易日无效",
}

ATOMIC_FEATURE_STATUS_LABELS = {
    "complete": "完整",
    "missing_features": "特征缺失",
    "feature_calculation_failed": "特征计算失败",
}
```

Add this function after `atomic_indicator_summary`:

```python
def atomic_data_update_health(frame: pd.DataFrame) -> list[AtomicDataHealthItem]:
    history = _string_series(frame, "history_status")
    feature = _string_series(frame, "feature_status")

    return [
        AtomicDataHealthItem("stale", "行情滞后", int((history == "stale").sum()), "本地行情不是最新", "history_status", "stale", "warning"),
        AtomicDataHealthItem("short_history", "历史不足", int((history == "short_history").sum()), "样本行数不足", "history_status", "short_history", "warning"),
        AtomicDataHealthItem("missing_history", "历史缺失", int((history == "missing_history").sum()), "没有本地历史", "history_status", "missing_history", "danger"),
        AtomicDataHealthItem("read_failed", "读取失败", int((history == "read_failed").sum()), "文件或格式异常", "history_status", "read_failed", "danger"),
        AtomicDataHealthItem("missing_features", "特征缺失", int((feature == "missing_features").sum()), "指标字段暂不可算", "feature_status", "missing_features", "warning"),
    ]
```

Add this helper near `_records`:

```python
def _string_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame:
        return pd.Series(dtype=str)
    return frame[column].fillna("").astype(str).str.strip()
```

In `_atomic_display_row`, replace the inline mappings for `历史状态` and `特征状态`:

```python
"历史状态": _status_text(row.get("history_status"), ATOMIC_HISTORY_STATUS_LABELS),
"特征状态": _status_text(row.get("feature_status"), ATOMIC_FEATURE_STATUS_LABELS),
```

In `src/etf_trading/nicegui_app/components/tables.py`, change the `VALUE_LABELS` entry:

```python
"stale": "行情滞后",
```

- [ ] **Step 5: Run tests to verify pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py -q --basetemp pytest-tmp-etf-atomic-health-viewmodels
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add src/etf_trading/nicegui_app/view_models.py src/etf_trading/nicegui_app/components/tables.py tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py
git commit -m "feat: clarify atomic data health statuses"
```

---

### Task 2: Atomic Page Health Panel and Filter Wiring

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/etf_data.py`
- Test: `tests/test_nicegui_app_import.py`

**Interfaces:**
- Consumes:
  - `atomic_data_update_health(frame: pd.DataFrame) -> list[AtomicDataHealthItem]`
  - `AtomicDataHealthItem.key`, `.label`, `.count`, `.detail`, `.filter_type`, `.filter_value`, `.tone`
  - existing `_atomic_filter_options()` and `_atomic_filter_value()`
- Produces:
  - `_atomic_filter_label(options: dict[str, str], value: str) -> str`
  - `_atomic_health_icon(item: AtomicDataHealthItem) -> str`
  - `_render_atomic_indicators()` renders a compact `数据更新体检` panel.

- [ ] **Step 1: Write failing page-render test**

Append this test to `tests/test_nicegui_app_import.py`.

```python
def test_atomic_indicator_page_renders_data_health_and_filters_from_summary(monkeypatch):
    from etf_trading.nicegui_app.pages import etf_data
    from etf_trading.nicegui_app.state import AtomicSnapshotCacheResult
    from etf_trading.nicegui_app.view_models import PlatformSnapshot

    labels = []
    table_batches = []
    health_actions = {}
    select_by_label = {}

    class FakeProps:
        def __init__(self, owner):
            self.owner = owner
            self.values = {}

        def __call__(self, value):
            self.values[str(value)] = True
            return self.owner

        def __setitem__(self, key, value):
            self.values[key] = value

    class FakeElement:
        def __init__(self, value=None, options=None, label=None):
            self.value = value
            self.options = options or []
            self.label = label
            self.props = FakeProps(self)

        def classes(self, value):
            return self

        def on_value_change(self, handler):
            self.value_handler = handler
            return self

        def on(self, event_name, handler):
            self.event_name = event_name
            self.handler = handler
            return self

        def clear(self):
            return None

        def update(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def element(self, tag):
            return FakeElement()

        def input(self, label):
            return FakeElement(value="", label=label)

        def select(self, options, value=None, label=None):
            element = FakeElement(value=value, options=options, label=label)
            if label:
                select_by_label[label] = element
            return element

        def toggle(self, options, value=None):
            return FakeElement(value=value, options=options)

        def number(self, label, value=None, format=None):
            return FakeElement(value=value, label=label)

        def checkbox(self, label, value=False):
            return FakeElement(value=value, label=label)

        def button(self, label, icon=None, on_click=None):
            if label.startswith("行情滞后"):
                health_actions["行情滞后"] = on_click
            if label.startswith("特征缺失"):
                health_actions["特征缺失"] = on_click
            return FakeElement(label=label)

        def link(self, label, target):
            labels.append(f"{label}->{target}")
            return FakeElement(label=label)

        def label(self, text):
            labels.append(str(text))
            return FakeElement(label=str(text))

        def icon(self, name):
            return FakeElement(label=name)

        def badge(self, text):
            labels.append(str(text))
            return FakeElement(label=str(text))

        def table(self, columns, rows, row_key=None, pagination=None):
            table_batches.append(list(rows))
            table = FakeElement()
            table.row_key = row_key
            return table

        def notify(self, message, type=None):
            return None

    frame = pd.DataFrame(
        {
            "etf_code": ["510300", "512880", "159915"],
            "name": ["沪深300ETF", "证券ETF", "创业板ETF"],
            "category": ["A股宽基", "A股行业", "A股宽基"],
            "exchange": ["SSE", "SSE", "SZSE"],
            "history_status": ["complete", "stale", "short_history"],
            "feature_status": ["complete", "complete", "missing_features"],
            "latest_trade_date": ["2026-07-08", "2026-07-03", "2026-07-08"],
            "history_rows": [520, 520, 120],
            "return_20": [0.05, 0.03, None],
            "return_60": [0.08, 0.04, None],
            "return_20_rank_all": [1, 2, None],
            "return_60_rank_all": [1, 2, None],
            "return_20_rank_category": [1, 1, None],
            "return_60_rank_category": [1, 1, None],
            "close_above_ma20": [True, True, None],
            "ma20_above_ma60": [True, False, None],
            "close_above_ma60": [True, True, None],
            "weekly_close_above_ma10": [True, False, None],
            "weekly_close_above_ma30": [False, False, None],
            "avg_amount_5": [2_000_000, 1_500_000, None],
            "avg_amount_20": [1_800_000, 1_400_000, None],
            "amount_ratio_5_20": [1.11, 1.05, None],
            "distance_ma20_pct": [0.02, 0.01, None],
            "distance_ma20_atr": [1.2, 0.8, None],
            "ma60_slope_20": [0.015, 0.008, None],
            "is_60d_close_breakout": [False, True, None],
            "missing_feature_names": ["", "", "return_60"],
        }
    )

    monkeypatch.setattr(etf_data, "ui", FakeUi())
    monkeypatch.setattr(
        etf_data,
        "load_atomic_snapshot_cached",
        lambda master, parquet_store, *, force_refresh=False: AtomicSnapshotCacheResult(frame=frame, status="ready"),
        raising=False,
    )
    snapshot = PlatformSnapshot(
        master=pd.DataFrame({"ETF代码": ["510300", "512880", "159915"]}),
        watchlist=pd.DataFrame(),
        index_summary=pd.DataFrame(),
        universe=pd.DataFrame(),
        gaps=pd.DataFrame(),
        coverage=pd.DataFrame(),
        generated_at=datetime(2026, 7, 8, 12, 0, 0),
    )

    etf_data._render_atomic_indicators(snapshot, object())

    assert "数据更新体检" in labels
    assert "行情滞后表示本地行情最新交易日落后；补齐后刷新快照即可更新指标。" in labels
    assert any(text.startswith("去补齐任务->/page/maintenance/") for text in labels)
    assert "行情滞后" in health_actions
    assert "特征缺失" in health_actions

    health_actions["行情滞后"]()

    assert select_by_label["历史状态"].value == "行情滞后"
    assert [row["ETF代码"] for row in table_batches[-1]] == ["512880"]

    health_actions["特征缺失"]()

    assert select_by_label["特征状态"].value == "特征缺失"
    assert [row["ETF代码"] for row in table_batches[-1]] == ["159915"]
```

Append this smaller helper test too:

```python
def test_atomic_filter_label_returns_display_label_for_internal_value():
    from etf_trading.nicegui_app.pages.etf_data import _atomic_filter_label

    options = {"全部历史状态": "全部历史状态", "行情滞后": "stale"}

    assert _atomic_filter_label(options, "stale") == "行情滞后"
    assert _atomic_filter_label(options, "missing_history") == ""
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py::test_atomic_indicator_page_renders_data_health_and_filters_from_summary tests/test_nicegui_app_import.py::test_atomic_filter_label_returns_display_label_for_internal_value -q
```

Expected: FAIL because the health panel and `_atomic_filter_label` do not exist.

- [ ] **Step 3: Import health model**

In `src/etf_trading/nicegui_app/pages/etf_data.py`, add these names to the `view_models` import block:

```python
    AtomicDataHealthItem,
    atomic_data_update_health,
```

- [ ] **Step 4: Add the health panel container**

Inside `_render_atomic_indicators()`, create `health_area` after `metric_area`:

```python
    health_area = ui.column().classes("w-full")
```

- [ ] **Step 5: Add filter wiring functions**

Inside `_render_atomic_indicators()`, after `current_filters()`, add:

```python
    def apply_health_filter(item: AtomicDataHealthItem) -> None:
        if item.count <= 0:
            return
        if item.filter_type == "history_status":
            label = _atomic_filter_label(history_statuses, item.filter_value)
            if label:
                history_status.value = label
                history_status.update()
        elif item.filter_type == "feature_status":
            label = _atomic_filter_label(feature_statuses, item.filter_value)
            if label:
                feature_status.value = label
                feature_status.update()
        refresh_table()

    def render_data_health() -> None:
        health_area.clear()
        items = atomic_data_update_health(frame_holder["frame"])
        issue_total = sum(item.count for item in items)
        with health_area:
            with ui.column().classes("atomic-data-health w-full"):
                with ui.row().classes("atomic-data-health-header w-full"):
                    ui.icon("monitoring").classes("tone-info")
                    ui.label("数据更新体检").classes("text-sm font-semibold text-slate-700")
                    ui.badge("数据就绪" if issue_total == 0 else f"{issue_total} 项需关注").classes(
                        "atomic-data-health-status is-ready" if issue_total == 0 else "atomic-data-health-status is-warning"
                    )
                    if issue_total:
                        ui.link("去补齐任务", f"/page/maintenance/{quote(chr(34917) + chr(40784) + chr(20219) + chr(21153), safe='')}").classes("workbench-section-tab")
                ui.label("行情滞后表示本地行情最新交易日落后；补齐后刷新快照即可更新指标。").classes("atomic-data-health-note")
                with ui.row().classes("atomic-data-health-items"):
                    for item in items:
                        if item.count > 0:
                            ui.button(
                                f"{item.label} {item.count}",
                                icon=_atomic_health_icon(item),
                                on_click=lambda item=item: apply_health_filter(item),
                            ).props("dense flat").classes(f"atomic-data-health-item tone-{item.tone}")
                        else:
                            with ui.row().classes("atomic-data-health-item is-empty"):
                                ui.icon(_atomic_health_icon(item))
                                ui.label(f"{item.label} 0")
                        ui.label(item.detail).classes("atomic-data-health-detail")
```

- [ ] **Step 6: Re-render health panel on cache refresh**

In `reload_snapshot()`, add `render_data_health()` after `render_metrics()`:

```python
        render_cache_status()
        render_metrics()
        render_data_health()
        refresh_table()
```

At the bottom of `_render_atomic_indicators()`, call it between metrics and table refresh:

```python
    render_cache_status()
    render_metrics()
    render_data_health()
    refresh_table()
```

- [ ] **Step 7: Add module helpers**

At module level near `_atomic_filter_value()`, add:

```python
def _atomic_filter_label(options: dict[str, str], value: str) -> str:
    for label, option_value in options.items():
        if option_value == value:
            return label
    return ""


def _atomic_health_icon(item: AtomicDataHealthItem) -> str:
    return {
        "stale": "update",
        "short_history": "hourglass_empty",
        "missing_history": "folder_off",
        "read_failed": "error_outline",
        "missing_features": "analytics",
    }.get(item.key, "info")
```

- [ ] **Step 8: Run tests to verify pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py -q --basetemp pytest-tmp-etf-atomic-health-page
```

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

Run:

```powershell
git add src/etf_trading/nicegui_app/pages/etf_data.py tests/test_nicegui_app_import.py
git commit -m "feat: show atomic data update health"
```

---

### Task 3: Health Panel Styling

**Files:**
- Modify: `src/etf_trading/nicegui_app/theme.py`
- Test: `tests/test_nicegui_theme.py`

**Interfaces:**
- Consumes: CSS classes emitted by Task 2.
- Produces: compact layout hooks for `.atomic-data-health`, `.atomic-data-health-header`, `.atomic-data-health-status`, `.atomic-data-health-note`, `.atomic-data-health-items`, `.atomic-data-health-item`, `.atomic-data-health-detail`.

- [ ] **Step 1: Write failing theme test**

Append this test to `tests/test_nicegui_theme.py`.

```python
def test_theme_contains_atomic_data_health_layout_hooks():
    for css_class in [
        ".atomic-data-health",
        ".atomic-data-health-header",
        ".atomic-data-health-status",
        ".atomic-data-health-note",
        ".atomic-data-health-items",
        ".atomic-data-health-item",
        ".atomic-data-health-detail",
    ]:
        assert css_class in WORKBENCH_CSS
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_theme.py::test_theme_contains_atomic_data_health_layout_hooks -q
```

Expected: FAIL because the CSS hooks are absent.

- [ ] **Step 3: Add compact CSS**

In `src/etf_trading/nicegui_app/theme.py`, add this block after `.atomic-metric-strip`:

```css
.atomic-data-health {
  border: 1px solid var(--wb-line);
  border-radius: 8px;
  background: #ffffff;
  padding: 9px 10px;
  gap: 7px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
}
.atomic-data-health-header {
  min-height: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.atomic-data-health-status {
  border-radius: 999px;
  font-size: 12px;
  line-height: 18px;
  padding: 0 8px;
}
.atomic-data-health-status.is-ready {
  color: #047857;
  background: #ecfdf5;
}
.atomic-data-health-status.is-warning {
  color: #b45309;
  background: #fffbeb;
}
.atomic-data-health-note {
  font-size: 12px;
  line-height: 16px;
  color: var(--wb-muted);
}
.atomic-data-health-items {
  display: flex;
  align-items: stretch;
  gap: 8px;
  flex-wrap: wrap;
}
.atomic-data-health-item {
  min-height: 30px;
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  background: #f8fafc;
  padding: 4px 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.atomic-data-health-item.is-empty {
  color: #64748b;
  background: #ffffff;
}
.atomic-data-health-detail {
  align-self: center;
  max-width: 140px;
  font-size: 11px;
  line-height: 14px;
  color: var(--wb-muted);
}
```

- [ ] **Step 4: Run theme tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_theme.py -q --basetemp pytest-tmp-etf-atomic-health-theme
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add src/etf_trading/nicegui_app/theme.py tests/test_nicegui_theme.py
git commit -m "style: add atomic data health panel"
```

---

### Task 4: Verification, Browser QA, and Memory

**Files:**
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: all public and private interfaces from Tasks 1-3.
- Produces: verified working feature and project memory entry.

- [ ] **Step 1: Run focused regression tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q --basetemp pytest-tmp-etf-atomic-health-focused
```

Expected: PASS.

- [ ] **Step 2: Run adjacent regression tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_atomic_indicators.py tests/test_nicegui_navigation.py tests/test_nicegui_state_cache.py tests/test_nicegui_maintenance_tasks.py -q --basetemp pytest-tmp-etf-atomic-health-regression
```

Expected: PASS.

- [ ] **Step 3: Start NiceGUI for browser verification**

If port `8502` is free, run:

```powershell
$env:PYTHONPATH='src'; .venv-win\Scripts\python.exe -c "from etf_trading.nicegui_app.main import run; run(port=8502)"
```

If port `8502` is occupied, use the next free port:

```powershell
$env:PYTHONPATH='src'; .venv-win\Scripts\python.exe -c "from etf_trading.nicegui_app.main import run; run(port=8514)"
```

Expected: server starts and keeps running until browser verification is complete.

- [ ] **Step 4: Browser-check desktop atomic page**

Use the Browser plugin or Playwright to open:

```text
http://127.0.0.1:8502/page/etf-data/原子指标
```

If using port `8514`, open:

```text
http://127.0.0.1:8514/page/etf-data/原子指标
```

Verify visible page text contains:

```text
数据更新体检
行情滞后
历史不足
历史缺失
读取失败
特征缺失
去补齐任务
```

Verify visible row-level text does not contain:

```text
正在刷新
```

The snapshot-level sentence may contain:

```text
原子指标快照正在后台刷新
```

- [ ] **Step 5: Browser-check filter interaction**

Click the `行情滞后` health item when its count is greater than zero.

Expected:

```text
历史状态
行情滞后
```

The table should show rows whose `历史状态` column is `行情滞后`. The right-side ETF checker should update to one of the filtered rows.

- [ ] **Step 6: Browser-check mobile width**

Set viewport width to `390px` and keep the atomic page open.

Expected:

```text
数据更新体检
列表视图
历史状态
ETF检查器
```

No controls or labels overlap. Horizontal table scrolling is acceptable inside the table pane.

- [ ] **Step 7: Update task memory**

Append this entry to `docs/task-memory.md`:

```md
## 2026-07-08 - ETF atomic data update health

- Summary: Replaced misleading row-level `正在刷新` history status with `行情滞后`, added a data-update health summary to `ETF数据 -> 原子指标`, and linked the summary to existing filters and maintenance flow.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q --basetemp pytest-tmp-etf-atomic-health-focused` passed; `.venv-win\Scripts\python.exe -m pytest tests/test_atomic_indicators.py tests/test_nicegui_navigation.py tests/test_nicegui_state_cache.py tests/test_nicegui_maintenance_tasks.py -q --basetemp pytest-tmp-etf-atomic-health-regression` passed; browser verified desktop and 390px atomic page.
- Watch out next time:
  - Keep row-level history freshness labels separate from snapshot cache refresh status.
  - Keep repair execution in `数据维护 -> 补齐任务`; the atomic page should diagnose and filter.
```

- [ ] **Step 8: Commit Task 4**

Run:

```powershell
git add docs/task-memory.md
git commit -m "docs: record atomic data health"
```

---

## Self-Review Checklist

- Spec coverage:
  - Status copy: Task 1.
  - Data-update health summary: Tasks 1 and 2.
  - Filter linkage: Task 2.
  - Existing maintenance routing: Task 2.
  - Styling: Task 3.
  - Browser and regression verification: Task 4.
- Placeholder scan: run a red-flag text search before handoff and keep this plan free of unfinished markers.
- Type consistency:
  - `AtomicDataHealthItem.filter_type` is consumed by `apply_health_filter()`.
  - `AtomicDataHealthItem.filter_value` maps through `_atomic_filter_label()`.
  - `atomic_data_update_health()` returns exactly the five visible health items in display order.

Expected: no unfinished markers, contradictory names, or undefined interfaces.
