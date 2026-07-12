# 指数原子指标详情可读性改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 将指数详情改为“位置 → 事件 → 证据”的状态概览，同时保留完整原子指标与数据质量审计。

**Architecture:** 从现有的只读快照摘要行与详情长表构建不可变的 IndexAtomicOverview。market.py 只渲染此展示模型，theme.py 只添加受限的 index-atomic-* 样式；不改变、重建或持久化指标。

**Tech Stack:** Python 3.11、pandas、NiceGUI、pytest。

## Global Constraints

- 只读取 load_index_atomic_snapshot_readonly 的已发布快照；详情打开、标签切换和分组展开不得构建快照、访问外部数据或写入存储。
- 不修改 src/etf_trading/research/index_health_snapshot.py、快照 schema、数据维护任务、指数主表排序或筛选。
- 不创建评分、趋势等级、买卖建议、目标价、仓位建议或其他结论性字段、文案。
- 区间条和均线阶梯只视觉化已有原子事实；展示比例不得保存或反馈到领域层。
- 所有方向与区间状态带有文字；绿色、黄色、红色只表达数据质量的可用、待处理、失败状态。
- 缺失或不能安全换算的指标显示“数据不足”和已有原因，且不渲染其图形。
- 概览在桌面四列、平板两列、720px 以下单列；页面根节点不得横向溢出。

---

## File Structure

| 文件 | 责任 |
| --- | --- |
| src/etf_trading/nicegui_app/view_models.py | 定义并生成只读概览模型。 |
| src/etf_trading/nicegui_app/pages/market.py | 渲染概览、折叠证据组、完整指标和数据质量。 |
| src/etf_trading/nicegui_app/theme.py | 添加限定的响应式详情样式。 |
| tests/test_nicegui_view_models.py | 覆盖概览字段、无事件和数据不足。 |
| tests/test_nicegui_app_import.py | 锁定详情页面的只读边界与中文交互文案。 |
| tests/test_nicegui_theme.py | 锁定布局选择器和断点。 |
| docs/task-memory.md | 记录实际验证和展示边界。 |

### Task 1: 创建只读状态概览 View Model

**Files:**
- Modify: src/etf_trading/nicegui_app/view_models.py:117-134, 699-714, 951-1107
- Modify: tests/test_nicegui_view_models.py:1-35, 153-170, 320-332

**Interfaces:**
- Consumes: summary: dict[str, object]、details: pd.DataFrame、index_code: str。
- Produces: index_atomic_overview(summary, details, index_code) -> IndexAtomicOverview | None。
- Produces: .trend、.range_position、.events、.quality、.evidence_groups；后续页面代码不得重新扫描 DataFrame。

- [ ] **Step 1: 写会失败的概览模型测试**

在测试 imports 中加入 pytest 和 index_atomic_overview；在 _atomic_details 后加入以下 fixture 与两个测试。

~~~python
def _overview_detail(metric_key: str, value: object, *, status: str = "computed", reason: str = "已从本地指数历史计算") -> dict[str, object]:
    return {
        "index_code": "000300", "group_key": "price_ma", "metric_key": metric_key,
        "metric_label": metric_key, "value": value, "status": status, "reason": reason,
        "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "akshare_zh_em",
    }


def test_index_atomic_overview_reads_stored_atoms_without_conclusions():
    summary = {
        "index_code": "000300", "snapshot_status": "computed",
        "history_completeness_status": "COMPLETE", "history_rows": 260,
        "latest_date": "2026-07-11", "data_source": "akshare_zh_em",
    }
    details = pd.DataFrame([
        _overview_detail("close", 100.0),
        _overview_detail("ma_20", 102.0), _overview_detail("ma_60", 98.0),
        _overview_detail("ma_120", 96.0), _overview_detail("ma_250", 90.0),
        _overview_detail("close_above_ma_20", False), _overview_detail("close_above_ma_60", True),
        _overview_detail("close_above_ma_120", True), _overview_detail("close_above_ma_250", True),
        _overview_detail("range_20_high", False), _overview_detail("range_20_low", False),
        _overview_detail("range_20_from_high", -0.05), _overview_detail("range_20_from_low", 0.05),
        _overview_detail("days_since_ma_cross_down_60", 1), _overview_detail("days_since_ma_cross_up_20", 9),
    ])

    overview = index_atomic_overview(summary, details, "000300")

    assert overview is not None
    assert overview.trend.close.value == "100.00"
    assert [(level.label, level.value) for level in overview.trend.levels] == [
        ("MA20", "102.00"), ("MA60", "98.00"), ("MA120", "96.00"), ("MA250", "90.00"),
    ]
    assert overview.range_position.headline == "20日区间内"
    assert overview.range_position.marker == pytest.approx(0.5)
    assert [(event.label, event.days) for event in overview.events] == [
        ("下穿60日均线", "1 日前"), ("上穿20日均线", "9 日前"),
    ]
    assert [item.label for item in overview.quality] == ["快照状态", "历史覆盖", "有效交易日", "数据来源"]
    assert "评分" not in repr(overview) and "买卖" not in repr(overview)


def test_index_atomic_overview_hides_unreliable_visuals_and_reports_empty_events():
    summary = {
        "index_code": "000300", "snapshot_status": "stale",
        "history_completeness_status": "INCOMPLETE", "history_rows": 18,
        "latest_date": "2026-07-11", "data_source": "akshare_zh_em",
    }
    details = pd.DataFrame([
        _overview_detail("close", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
        _overview_detail("range_20_high", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
        _overview_detail("range_20_low", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
        _overview_detail("range_20_from_high", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
        _overview_detail("range_20_from_low", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
    ])

    overview = index_atomic_overview(summary, details, "000300")

    assert overview is not None
    assert overview.trend.visible is False
    assert overview.range_position.marker is None
    assert overview.range_position.reason == "历史不足 20 行"
    assert overview.events == ()
    assert overview.events_empty_text == "暂无已记录事件"
    assert overview.quality[0].value == "待重建"
~~~

- [ ] **Step 2: 运行测试确认失败**

Run:

~~~powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_view_models.py -q
~~~

Expected: FAIL during collection with ImportError: cannot import name index_atomic_overview.

- [ ] **Step 3: 实现不可变模型与展示转换**

在 IndexAtomicDetailGroup 后添加以下类型。

~~~python
@dataclass(frozen=True)
class IndexAtomicOverviewMetric:
    label: str
    value: str
    status: str
    reason: str


@dataclass(frozen=True)
class IndexAtomicTrendOverview:
    close: IndexAtomicOverviewMetric
    levels: tuple[IndexAtomicOverviewMetric, ...]
    relations: tuple[IndexAtomicOverviewMetric, ...]
    visible: bool


@dataclass(frozen=True)
class IndexAtomicRangeOverview:
    headline: str
    from_high: IndexAtomicOverviewMetric
    from_low: IndexAtomicOverviewMetric
    marker: float | None
    reason: str


@dataclass(frozen=True)
class IndexAtomicOverviewEvent:
    label: str
    days: str


@dataclass(frozen=True)
class IndexAtomicOverview:
    trend: IndexAtomicTrendOverview
    range_position: IndexAtomicRangeOverview
    events: tuple[IndexAtomicOverviewEvent, ...]
    events_empty_text: str
    quality: tuple[IndexAtomicOverviewMetric, ...]
    evidence_groups: tuple[IndexAtomicDetailGroup, ...]
~~~

先把 INDEX_ATOMIC_DETAIL_GROUPS 中的 range_position 标题改为“区间位置与突破”、volatility_volume 标题改为“波动与量能”，并把现有 test_index_atomic_detail_groups_are_fact_categories_without_strategy_conclusions 的期望标题同步改为这两个名称。随后在 index_atomic_detail_groups 后实现下面的转换；只从详情长表读 value、status、reason，并复用已有的格式化函数。

~~~python
def index_atomic_overview(summary: dict[str, object], details: pd.DataFrame, index_code: str) -> IndexAtomicOverview | None:
    if not index_code or details.empty or "index_code" not in details:
        return None
    data = details[details["index_code"].fillna("").astype(str) == str(index_code)].copy()
    if data.empty:
        return None
    rows = {str(row.get("metric_key") or ""): row for row in data.to_dict("records")}
    close = _overview_metric(rows.get("close"), "最新收盘")
    levels = tuple(_overview_metric(rows.get("ma_{}".format(window)), "MA{}".format(window)) for window in (20, 60, 120, 250))
    relations = tuple(_overview_metric(rows.get("close_above_ma_{}".format(window)), "相对MA{}".format(window)) for window in (20, 60, 120, 250))
    from_high = _overview_metric(rows.get("range_20_from_high"), "距20日高点")
    from_low = _overview_metric(rows.get("range_20_from_low"), "距20日低点")
    high_flag = _overview_metric(rows.get("range_20_high"), "20日收盘新高")
    low_flag = _overview_metric(rows.get("range_20_low"), "20日收盘新低")
    headline = _range_headline(high_flag, low_flag, from_high, from_low)
    reason = next((item.reason for item in (from_high, from_low, high_flag, low_flag) if item.status != "已计算"), "")
    return IndexAtomicOverview(
        trend=IndexAtomicTrendOverview(close, levels, relations, close.status == "已计算" and all(item.status == "已计算" for item in levels)),
        range_position=IndexAtomicRangeOverview(headline, from_high, from_low, _range_marker(close, from_high, from_low) if headline != "数据不足" else None, reason),
        events=_overview_events(rows),
        events_empty_text="暂无已记录事件",
        quality=_overview_quality(summary),
        evidence_groups=tuple(group for group in index_atomic_detail_groups(details, index_code) if group.title != "数据质量"),
    )


def _overview_metric(row: dict[str, object] | None, label: str) -> IndexAtomicOverviewMetric:
    if row is None:
        return IndexAtomicOverviewMetric(label, "数据不足", "数据不足", "快照中缺少该原子指标")
    metric_key = _text(row.get("metric_key"))
    return IndexAtomicOverviewMetric(label, _format_index_atomic_detail_value(metric_key, row.get("value")), _index_atomic_status_label(row.get("status")), _text(row.get("reason")) or "数据不足")


def _range_headline(high_flag, low_flag, from_high, from_low) -> str:
    if high_flag.status != "已计算" or low_flag.status != "已计算":
        return "数据不足"
    if high_flag.value == "是":
        return "20日收盘新高"
    if low_flag.value == "是":
        return "20日收盘新低"
    return "20日区间内" if from_high.status == "已计算" and from_low.status == "已计算" else "数据不足"


def _range_marker(close, from_high, from_low) -> float | None:
    try:
        close_value = float(close.value.replace(",", ""))
        high_offset = float(from_high.value.replace("%", "")) / 100
        low_offset = float(from_low.value.replace("%", "")) / 100
        high = close_value / (1 + high_offset)
        low = close_value / (1 + low_offset)
        return None if high <= low else max(0.0, min(1.0, (close_value - low) / (high - low)))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _overview_events(rows: dict[str, dict[str, object]]) -> tuple[IndexAtomicOverviewEvent, ...]:
    events: list[tuple[int, IndexAtomicOverviewEvent]] = []
    for direction, label in (("up", "上穿"), ("down", "下穿")):
        for window in (20, 60, 120, 250):
            row = rows.get("days_since_ma_cross_{}_{}".format(direction, window))
            if row is None or _text(row.get("status")) != "computed":
                continue
            try:
                days = int(float(row.get("value")))
            except (TypeError, ValueError):
                continue
            events.append((days, IndexAtomicOverviewEvent("{}{}日均线".format(label, window), "{} 日前".format(days))))
    return tuple(event for _, event in sorted(events, key=lambda item: item[0])[:2])


def _overview_quality(summary: dict[str, object]) -> tuple[IndexAtomicOverviewMetric, ...]:
    return (
        IndexAtomicOverviewMetric("快照状态", _index_atomic_status_label(summary.get("snapshot_status")), "", _text(summary.get("snapshot_reason"))),
        IndexAtomicOverviewMetric("历史覆盖", _index_atomic_status_label(summary.get("history_completeness_status")), "", _text(summary.get("history_completeness_message"))),
        IndexAtomicOverviewMetric("有效交易日", _format_index_atomic_count(summary.get("history_rows")), "", ""),
        IndexAtomicOverviewMetric("数据来源", _index_atomic_data_source_label(summary.get("data_source")), "", ""),
    )
~~~

- [ ] **Step 4: 运行 View Model 测试确认通过**

Run:

~~~powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_view_models.py -q
~~~

Expected: PASS; 现有模型测试和新增正常、无事件、数据不足场景通过。

- [ ] **Step 5: 提交模型边界**

~~~powershell
git add src/etf_trading/nicegui_app/view_models.py tests/test_nicegui_view_models.py
git commit -m "feat: add index atomic overview view model"
~~~

### Task 2: 渲染状态概览并保留完整审计分组

**Files:**
- Modify: src/etf_trading/nicegui_app/pages/market.py:12-32, 53-61, 220-338
- Modify: tests/test_nicegui_app_import.py:8-140

**Interfaces:**
- Consumes: Task 1 的 IndexAtomicOverview | None；不得读取 Parquet、构建快照或再次处理原始详情 DataFrame。
- Produces: 状态概览标签、四个概览卡片、概览证据折叠组和可展开的完整原子分组。
- Preserves: 关闭按钮、全部原子指标、数据质量、主表行点击和现有只读重载。

- [ ] **Step 1: 写会失败的页面契约测试**

更新 test_market_page_declares_pool_search_and_tabbed_detail_dialog，要求状态概览替代关键指标。追加：

~~~python
def test_market_page_uses_overview_model_without_snapshot_builder():
    source = Path("src/etf_trading/nicegui_app/pages/market.py").read_text(encoding="utf-8")

    assert "index_atomic_overview" in source
    assert "状态概览" in source
    assert "ui.expansion" in source
    assert "build_index_atomic_snapshot" not in source
    assert "load_index_atomic_snapshot_readonly" in source


def test_market_detail_rows_hide_normal_computed_status_but_keep_failures():
    from etf_trading.nicegui_app.pages import market
    from etf_trading.nicegui_app.view_models import IndexAtomicDetailItem

    computed = IndexAtomicDetailItem("close", "收盘价", "4,780.79", "已计算", "已从本地指数历史计算", "2026-07-11", "260", "akshare_zh_em")
    missing = IndexAtomicDetailItem("amount_avg_20", "20日平均成交额", "数据不足", "缺少输入字段", "缺少 amount 字段", "2026-07-11", "260", "akshare_zh_em")

    assert {label: status for label, _value, status in market._detail_metric_rows([computed, missing])} == {
        "收盘价": "", "20日平均成交额": "缺少输入字段",
    }
~~~

- [ ] **Step 2: 运行页面契约测试确认失败**

Run:

~~~powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_app_import.py -q
~~~

Expected: FAIL because the old tab, numeric-grid renderer, and normal computed status remain.

- [ ] **Step 3: 替换旧关键数字栅格**

删除 _KEY_METRICS、_render_key_metrics、_key_metric_rows、_range_20_text。导入 IndexAtomicOverview 和 index_atomic_overview，并将弹窗切换为：

~~~python
def _open_index_atomic_dialog(result, index_code: str) -> None:
    if not index_code:
        return
    summary = _summary_row(result.summary, index_code)
    overview = index_atomic_overview(summary, result.details, index_code)
    groups = index_atomic_detail_groups(result.details, index_code)
    dialog = ui.dialog()
    with dialog:
        with ui.card().classes("index-atomic-dialog"):
            with ui.row().classes("w-full items-center justify-between gap-2"):
                ui.label("指数原子指标：{}".format(_summary_identity(summary, index_code))).classes("text-lg font-bold")
                ui.button("关闭", icon="close", on_click=dialog.close).props("flat dense")
            with ui.tabs().classes("w-full") as tabs:
                overview_tab = ui.tab("状态概览")
                all_tab = ui.tab("全部原子指标")
                quality_tab = ui.tab("数据质量")
            with ui.tab_panels(tabs, value=overview_tab).classes("w-full"):
                with ui.tab_panel(overview_tab):
                    _render_atomic_overview(overview)
                with ui.tab_panel(all_tab):
                    _render_all_atomic_groups(groups)
                with ui.tab_panel(quality_tab):
                    _render_snapshot_quality(result, summary)
    dialog.open()
~~~

实现以下四个入口。_render_trend_card 仅在 visible 为 True 时渲染均线阶梯；_render_range_card 仅在 marker 不是 None 时渲染区间条；_render_events_card 在空元组时只渲染 empty_text；三种情形均不得生成伪图形。

~~~python
def _render_atomic_overview(overview: IndexAtomicOverview | None) -> None:
    if overview is None:
        empty_state("暂无状态概览", "当前快照中没有这只指数的原子指标。")
        return
    ui.label("今天的市场状态").classes("index-atomic-overview-title")
    ui.label("先看价格在哪里、发生过什么，再按分组核对全部原子事实。").classes("index-atomic-overview-note")
    with ui.element("div").classes("index-atomic-overview-grid"):
        _render_trend_card(overview.trend)
        _render_range_card(overview.range_position)
        _render_events_card(overview.events, overview.events_empty_text)
        _render_quality_card(overview.quality)
    ui.label("完整原子事实").classes("index-atomic-evidence-heading")
    _render_expandable_groups(overview.evidence_groups, "index-atomic-evidence-groups")


def _render_expandable_groups(groups, class_name: str) -> None:
    with ui.element("div").classes(class_name):
        for group in groups:
            with ui.expansion(group.title, value=group.title == "价格与均线").classes("index-atomic-expand-group"):
                if group.items:
                    _render_metric_grid(_detail_metric_rows(group.items))
                else:
                    ui.label("该组没有存储指标。").classes("text-sm text-slate-500")


def _render_all_atomic_groups(groups) -> None:
    _render_expandable_groups(groups, "index-atomic-full-groups")


def _detail_metric_rows(items) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for item in items:
        status = _status_text(item.status, "数据不足")
        rows.append((item.label, _detail_metric_value(item), "" if status == "已计算" else status))
    return rows
~~~

将四个概览卡片实现为以下具体 DOM。均线关系用每条 MA 的名称、数值和显式“上方/下方”文字行表达；区间 marker 的 left 百分比只来自 Task 1 的 marker。

~~~python
def _render_trend_card(trend) -> None:
    with ui.element("section").classes("index-atomic-overview-card"):
        ui.label("趋势结构").classes("index-atomic-card-title")
        if not trend.visible:
            ui.label(trend.close.value).classes("index-atomic-card-value")
            ui.label(trend.close.reason).classes("index-atomic-card-reason")
            return
        ui.label(trend.close.value).classes("index-atomic-card-value")
        with ui.element("div").classes("index-atomic-ma-ladder"):
            for level, relation in zip(trend.levels, trend.relations, strict=True):
                with ui.row().classes("index-atomic-ma-row w-full justify-between"):
                    ui.label("{} {}".format(level.label, level.value))
                    ui.label(relation.value).classes("index-atomic-ma-relation")


def _render_range_card(range_position) -> None:
    with ui.element("section").classes("index-atomic-overview-card"):
        ui.label("区间位置").classes("index-atomic-card-title")
        ui.label(range_position.headline).classes("index-atomic-card-value")
        if range_position.marker is None:
            ui.label(range_position.reason or "数据不足").classes("index-atomic-card-reason")
            return
        with ui.element("div").classes("index-atomic-range-track"):
            ui.element("span").classes("index-atomic-range-marker").style(
                "left: {}%".format(range_position.marker * 100)
            )
        with ui.row().classes("w-full justify-between"):
            ui.label(range_position.from_low.value)
            ui.label(range_position.from_high.value)


def _render_events_card(events, empty_text: str) -> None:
    with ui.element("section").classes("index-atomic-overview-card"):
        ui.label("最近事件").classes("index-atomic-card-title")
        if not events:
            ui.label(empty_text).classes("index-atomic-card-reason")
            return
        with ui.element("div").classes("index-atomic-event-timeline"):
            for event in events:
                with ui.row().classes("w-full justify-between"):
                    ui.label(event.label)
                    ui.label(event.days)


def _render_quality_card(items) -> None:
    with ui.element("section").classes("index-atomic-overview-card"):
        ui.label("数据质量").classes("index-atomic-card-title")
        for item in items:
            with ui.row().classes("w-full justify-between"):
                ui.label(item.label)
                ui.label(item.value)
~~~

- [ ] **Step 4: 运行页面契约测试确认通过**

Run:

~~~powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_app_import.py tests\test_nicegui_view_models.py -q
~~~

Expected: PASS; 新标签、只读概览模型和缺失状态稳定，普通指标不再显示已计算。

- [ ] **Step 5: 提交详情渲染**

~~~powershell
git add src/etf_trading/nicegui_app/pages/market.py tests/test_nicegui_app_import.py
git commit -m "feat: render readable index atomic detail"
~~~

### Task 3: 添加响应式详情样式并完成验收

**Files:**
- Modify: src/etf_trading/nicegui_app/theme.py:601-704
- Modify: tests/test_nicegui_theme.py:47-59
- Modify: docs/task-memory.md:1-10

**Interfaces:**
- Consumes: Task 2 的 index-atomic-overview-*、index-atomic-expand-group、index-atomic-evidence-groups、index-atomic-full-groups 类名。
- Produces: 四/二/一列响应式布局和无横向溢出保护。

- [ ] **Step 1: 写会失败的主题契约测试**

在 tests/test_nicegui_theme.py 追加：

~~~python
def test_theme_contains_readable_index_atomic_overview_rules():
    for css_class in [
        ".index-atomic-overview-grid", ".index-atomic-overview-card", ".index-atomic-ma-ladder",
        ".index-atomic-range-track", ".index-atomic-event-timeline", ".index-atomic-expand-group",
        ".index-atomic-evidence-groups", ".index-atomic-full-groups",
    ]:
        assert css_class in WORKBENCH_CSS
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in WORKBENCH_CSS
    assert "@media (max-width: 960px)" in WORKBENCH_CSS
    assert ".index-atomic-overview-grid { grid-template-columns: 1fr; }" in WORKBENCH_CSS
    assert "overflow-x: clip;" in WORKBENCH_CSS
~~~

- [ ] **Step 2: 运行主题测试确认失败**

Run:

~~~powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_theme.py -q
~~~

Expected: FAIL because overview CSS and its responsive selectors do not exist.

- [ ] **Step 3: 添加限定 CSS 与任务记忆**

在现有 .index-atomic-* 区域加入以下规则；不改动任何 .workbench-* 或其他页面选择器。

~~~css
.index-atomic-overview-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; width: 100%; min-width: 0; }
.index-atomic-overview-card, .index-atomic-expand-group { min-width: 0; border: 1px solid var(--wb-line); border-radius: 8px; background: #ffffff; }
.index-atomic-overview-card { padding: 10px; }
.index-atomic-overview-title { font-size: 16px; font-weight: 800; color: #1e293b; }
.index-atomic-overview-note { margin: 2px 0 10px; color: var(--wb-muted); font-size: 12px; }
.index-atomic-ma-ladder { position: relative; min-height: 84px; overflow: hidden; }
.index-atomic-range-track { position: relative; height: 8px; border-radius: 999px; background: #dbe5f1; }
.index-atomic-range-marker { position: absolute; top: -4px; width: 16px; height: 16px; border: 3px solid #ffffff; border-radius: 50%; background: var(--wb-blue); transform: translateX(-50%); }
.index-atomic-event-timeline { display: grid; gap: 8px; border-left: 2px solid #cbd5e1; padding-left: 10px; }
.index-atomic-evidence-heading { margin-top: 16px; font-size: 14px; font-weight: 800; color: #334155; }
.index-atomic-evidence-groups, .index-atomic-full-groups { display: grid; gap: 8px; margin-top: 8px; min-width: 0; }
.index-atomic-expand-group .q-item { min-height: 38px; }
@media (max-width: 960px) { .index-atomic-overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 720px) { .index-atomic-overview-grid { grid-template-columns: 1fr; } .index-atomic-dialog { overflow-x: clip; } }
~~~

在 docs/task-memory.md 顶部添加实施记录：概览只转换存储快照事实；缺失原子项不绘图；记录实际执行的 pytest 命令、浏览器端口和 1440px/390px 检查结果。不要提交缓存、日志、临时目录或截图。

- [ ] **Step 4: 运行聚焦回归测试**

Run:

~~~powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py tests\test_nicegui_theme.py tests\test_nicegui_navigation.py tests\test_index_health_snapshot.py -q
~~~

Expected: PASS; 快照口径、只读导入边界、页面结构和主题测试均通过。

- [ ] **Step 5: 浏览器验收桌面、待重建与窄屏**

Run:

~~~powershell
.\.venv-win\Scripts\python.exe scripts\run_nicegui.py
~~~

在 市场地图 -> 指数体检 打开一条已生成快照的指数，验证约 1440px 宽度可见四个概览区块且没有“评分”“买卖”“已计算”。切换至完整指标，验证每组可展开/收起、缺失项保留原因。缩至约 390px，验证概览单列、标签与折叠组可用、根节点没有水平滚动。用 stale 快照确认页面级提示“不是最新结果”且仅展示上次成功数据；用缺失或失败快照确认不出现均线阶梯、区间 marker 或伪事件。检查浏览器控制台无错误或警告。

- [ ] **Step 6: 运行全量回归并提交视觉交付**

Run:

~~~powershell
.\.venv-win\Scripts\python.exe -m pytest -q
~~~

Expected: PASS; 全量测试通过。

~~~powershell
git add src/etf_trading/nicegui_app/theme.py tests/test_nicegui_theme.py docs/task-memory.md
git commit -m "style: refine index atomic detail layout"
~~~
