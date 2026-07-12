# 指数体检原子指标工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把“市场地图 -> 指数体检”改造成只读的原子指标工作台：按指数目录顺序展示核心池或研究池，支持搜索和行点击详情弹窗；原始历史与原子快照必须分别在数据维护中手动处理，快照缺失、过期或生成失败时持续强提醒，不展示估值、趋势层级、评分、策略或交易结论。

**Architecture:** 原子计算内核只读取本地指数历史和历史覆盖信息，产出摘要、长表详情及可审计元数据。新的持久化“重建指数原子指标”维护任务调用这个内核并写入版本化快照；页面加载器只读取快照、校验输入签名并返回状态，绝不计算或发起外部数据请求。市场页使用核心/研究池切换、目录稳定排序、搜索过滤和宽屏三标签弹窗渲染已落盘的数据。

**Tech Stack:** Python 3.11、pandas、SQLite、Parquet、NiceGUI、pytest、Playwright/Chrome。

## 全局约束

- 所有新增用户可见文本使用中文；内部状态码通过统一映射显示，不能直接暴露为主要文案。
- 页面不得导入、读取或展示估值数据；不得出现“大趋势”“中趋势”“小趋势”“允许开仓”、评分、排名、策略或交易建议。
- 目录正式池仅为核心 100 和研究 80；保留池 30 不进入指数体检。两个可见池均按 `IndexCatalogEntry` 的配置顺序排序，搜索只能过滤。
- 指数体检刷新仅重新读取磁盘快照和状态；不能调用 `build_index_atomic_snapshot`、`InitializationService`、AkShare 或后台构建函数。
- 原始指数历史或覆盖信息变化后，快照必须因输入签名不匹配成为“待重建”；旧快照可显示，但页面持续显示生成时间与当前输入最新日期。
- 原子指标只能使用本地历史行情。缺少 `amount` 只让成交额/成交额比指标标记缺失，不使价格、均线、区间、收益或波动指标失效。
- 以 `trade_date` 升序清洗重复日期；收盘价无效时对应价格类指标标记计算失败或缺失，不以零值填充。
- 不提交数据文件、缓存、构建标记、日志或 `pytest-tmp-*` 目录；保留现有用户对 `quality.py`、`test_index_support.py` 和设计文档的修改。

---

## 文件结构

| 文件 | 责任 |
| --- | --- |
| `src/etf_trading/research/index_health_snapshot.py` | 无估值、无趋势结论的指数原子指标计算内核及摘要/详情列定义。 |
| `src/etf_trading/nicegui_app/state.py` | 原子快照输入签名、读写、内存缓存和严格只读的页面加载结果。 |
| `src/etf_trading/nicegui_app/maintenance_tasks.py` | 可持久化、可恢复显示的“重建指数原子指标”后台维护任务。 |
| `src/etf_trading/nicegui_app/pages/maintenance.py` | 指数数据维护区中的原子快照重建入口、进度和上次结果。 |
| `src/etf_trading/nicegui_app/view_models.py` | 核心/研究池筛选、稳定排序、详情分组和快照状态视图模型。 |
| `src/etf_trading/nicegui_app/pages/market.py` | 指数体检的快照状态栏、表格、搜索、池切换与三标签详情弹窗。 |
| `src/etf_trading/nicegui_app/components/tables.py` | 原子字段中文列标题、值格式化和状态标签。 |
| `src/etf_trading/nicegui_app/theme.py` | 持续警示条、宽弹窗、详情网格的响应式样式。 |
| `tests/test_index_health_snapshot.py` | 计算公式、指标缺失隔离、快照元数据和签名语义。 |
| `tests/test_nicegui_state_cache.py` | 页面只读加载、就绪/待重建/不存在/失败状态及旧快照保留。 |
| `tests/test_nicegui_maintenance_tasks.py` | 原子快照维护任务创建、进度、持久化、失败和重启恢复。 |
| `tests/test_nicegui_view_models.py` | 池切换、目录排序、搜索、详情分组和状态文案。 |
| `tests/test_nicegui_table_display.py` | 列标题及原子状态的中文表格显示。 |
| `tests/test_nicegui_app_import.py` | 页面模块不再引用遗留估值/趋势健康字段。 |
| `tests/test_nicegui_theme.py` | 提示条和详情弹窗 CSS 选择器存在。 |

## Task 1: 以测试驱动重写指数原子指标计算内核

**Files:**

- Modify: `src/etf_trading/research/index_health_snapshot.py`
- Modify: `tests/test_index_health_snapshot.py`

**Interfaces:**

- Replace: `build_index_health_snapshot(...)` with `build_index_atomic_snapshot(parquet_store, definitions, *, coverage=None, as_of_date=None, min_history_rows=252) -> tuple[pd.DataFrame, pd.DataFrame]`.
- Export: `INDEX_ATOMIC_SUMMARY_COLUMNS` and `INDEX_ATOMIC_DETAIL_COLUMNS`.
- Summary contains identity, `catalog_order`, data quality, `close`, `ma_20`/`60`/`120`/`250`, `close_vs_ma_20`/`60`, `range_20_status`, `return_20`, snapshot-ready status fields.
- Detail rows contain `index_code`, `group_key`, `metric_key`, `metric_label`, `value`, `status`, `reason`, `as_of_date`, `sample_count`, `data_source`.

- [ ] **Step 1: 写失败测试，固定原子指标的数值和事件定义。**

```python
def test_build_index_atomic_snapshot_calculates_price_ma_cross_range_return_and_drawdown(tmp_path):
    store = _store_with_index_prices(tmp_path, "000300", _price_history(260, amount=100_000_000))

    summary, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    row = summary.iloc[0]
    assert row["ma_20"] == pytest.approx(_price_history(260).tail(20)["close"].mean())
    assert row["close_above_ma_20"] is True
    assert row["return_20"] == pytest.approx(row["close"] / _price_history(260).iloc[-21]["close"] - 1)
    assert _detail_value(details, "000300", "ma_cross_up_20") in {True, False}
    assert _detail_status(details, "000300", "range_20_high") == "computed"
    assert _detail_value(details, "000300", "drawdown_60") <= 0


def test_cross_is_true_only_when_current_and_previous_day_switch_sides(tmp_path):
    store = _store_with_index_prices(tmp_path, "000300", _crossing_history())

    _, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    assert _detail_value(details, "000300", "ma_cross_up_20") is True
    assert _detail_value(details, "000300", "ma_cross_down_20") is False


def test_missing_amount_only_marks_volume_metrics_missing(tmp_path):
    store = _store_with_index_prices(tmp_path, "000300", _price_history(260, amount=None))

    summary, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    assert summary.iloc[0]["return_20"] is not None
    assert _detail_status(details, "000300", "amount_avg_20") == "missing_input"
    assert _detail_status(details, "000300", "return_20") == "computed"
```

- [ ] **Step 2: 运行红灯测试，证明遗留快照仍在产出趋势和估值字段。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_health_snapshot.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-kernel-red
```

Expected: FAIL，因为不存在新构建函数或断言字段，且旧模块仍导入 `CORE_VALUATION_METRICS` 与 `TrendRegimeClassifier`。

- [ ] **Step 3: 实现完整的原子计算和行级状态。**

删除估值、趋势分类、`allows_new_position` 和旧健康理由的导入与输出。每个指数按以下顺序生成长表详情：

1. `价格与均线`：最新收盘价、MA20/60/120/250、收盘是否高于每条均线、相对各均线偏离率。
2. `均线穿越`：四条均线的当日向上/向下穿越，以及距最近向上/向下穿越的交易日数。向上穿越公式为 `close[t-1] <= ma[t-1] and close[t] > ma[t]`；向下公式对称。
3. `区间位置`：20/60/120/250 日收盘新高/新低、距滚动收盘最高/最低的比例。
4. `收益与回撤`：5/20/60/120/250 日收益率，以及从各相同窗口滚动最高收盘价计算的回撤。
5. `波动与成交`：ATR14（使用本地 high/low/close）、20 日收益率标准差、5/20 日平均成交额和两者比值。
6. `数据质量`：历史状态、最新日期、行数、覆盖信息、数据源和错误文本。

每个指标独立写 `computed`、`insufficient_history`、`missing_input`、`read_failed` 或 `calculation_failed`。摘要采用对应详情的实际值，不产生方向性判断。把当前目录输入的枚举顺序写入 `catalog_order`，供页面稳定排序使用。

- [ ] **Step 4: 运行计算内核和相关研究回归。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_health_snapshot.py tests\test_index_valuations.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-kernel-green
```

Expected: PASS；指数原子测试不读取估值文件，短历史只影响需要更长窗口的指标。

- [ ] **Step 5: 提交原子计算内核。**

```powershell
git add src/etf_trading/research/index_health_snapshot.py tests/test_index_health_snapshot.py
git commit -m "feat: compute index atomic indicator snapshots"
```

## Task 2: 建立版本化快照并让页面加载严格只读

**Files:**

- Modify: `src/etf_trading/nicegui_app/state.py`
- Modify: `tests/test_nicegui_state_cache.py`

**Interfaces:**

- Add: `IndexAtomicSnapshotCacheResult(summary, details, status, generated_at, current_latest_date, message, task_result_id)`.
- Add: `index_atomic_snapshot_inputs(store) -> tuple[tuple[IndexDefinition, ...], pd.DataFrame]`，从已持久化目录获取非保留池定义和覆盖信息。
- Add: `write_index_atomic_snapshot(...)`，仅供维护任务调用。
- Add: `load_index_atomic_snapshot_readonly(parquet_store, definitions, *, coverage=None)`，只读取和比较签名。
- Cache paths: `cache/index_atomic_snapshot.parquet`、`cache/index_atomic_snapshot_details.parquet`、`cache/index_atomic_snapshot.meta.json`。

- [ ] **Step 1: 为只读行为、元数据和旧快照保留写失败测试。**

```python
def test_readonly_loader_never_calls_builder_when_snapshot_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(state, "build_index_atomic_snapshot", lambda *args, **kwargs: pytest.fail("page must not build"))

    result = state.load_index_atomic_snapshot_readonly(_parquet_store(tmp_path), (_definition("000300"),))

    assert result.status == "missing"
    assert result.summary.empty


def test_readonly_loader_marks_signature_mismatch_stale_and_keeps_previous_rows(tmp_path):
    parquet_store = _parquet_store(tmp_path)
    state.write_index_atomic_snapshot(_summary("000300"), _details("000300"), "old-signature", datetime(2026, 7, 12, 9, 0))

    result = state.load_index_atomic_snapshot_readonly(parquet_store, (_definition("000300"),))

    assert result.status == "stale"
    assert result.summary["index_code"].tolist() == ["000300"]
    assert result.generated_at == datetime(2026, 7, 12, 9, 0)


def test_atomic_snapshot_meta_records_schema_catalog_source_and_task_result(tmp_path):
    meta = _read_meta_after_write(tmp_path, task_result_id=17)

    assert meta["schema_version"] == state.INDEX_ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION
    assert isinstance(meta["catalog_signature"], str)
    assert isinstance(meta["source_signature"], str)
    assert meta["generated_at"] == "2026-07-12T09:00:00"
    assert meta["task_result_id"] == 17
    assert isinstance(meta["data_status_counts"], dict)
```

- [ ] **Step 2: 运行红灯缓存测试。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_state_cache.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-state-red
```

Expected: FAIL；当前 `load_index_health_snapshot_cached` 会在缺少或失效快照时直接调用构建器。

- [ ] **Step 3: 实现新缓存契约，并删除页面时间重建路径。**

输入签名必须包含：模式版本、非保留池目录顺序及字段、每个指数本地历史文件的存在性/大小/修改时间、覆盖数据。元数据分别写入目录签名、源历史/覆盖签名、生成时间、数据状态计数和维护任务结果 ID。读取时按以下规则返回：

| 条件 | `status` | 返回内容 |
| --- | --- | --- |
| 元数据和输入签名一致 | `ready` | 当前摘要和详情。 |
| 有快照但签名不同 | `stale` | 旧摘要和详情，带当前输入最新日期。 |
| 没有完整三件快照文件 | `missing` | 空的新列结构。 |
| 读取或解析快照失败 | `failed` | 空的新列结构和中文错误信息。 |

移除 `load_index_health_snapshot_cached` 对 `build_index_health_snapshot` 的调用，并用新函数替换其全部页面调用点。遗留 `index_health_snapshot*` 文件不迁移、不复用，避免把估值或趋势数据混入新页面。

- [ ] **Step 4: 运行缓存、目录与页面导入回归。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_state_cache.py tests\test_nicegui_app_import.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-state-green
```

Expected: PASS；读取函数没有构建副作用，且失效快照仍可检查。

- [ ] **Step 5: 提交快照读取层。**

```powershell
git add src/etf_trading/nicegui_app/state.py tests/test_nicegui_state_cache.py tests/test_nicegui_app_import.py
git commit -m "feat: make index atomic snapshots maintenance-only"
```

## Task 3: 增加持久化的“重建指数原子指标”数据维护任务

**Files:**

- Modify: `src/etf_trading/nicegui_app/maintenance_tasks.py`
- Modify: `src/etf_trading/nicegui_app/pages/maintenance.py`
- Modify: `tests/test_nicegui_maintenance_tasks.py`
- Modify: `tests/test_nicegui_app_import.py`

**Interfaces:**

- Add task type: `index_atomic_snapshot_rebuild` with user label `重建指数原子指标`.
- Add runner: `IndexAtomicSnapshotMaintenanceRunner(store, parquet_store, *, build_snapshot=build_index_atomic_snapshot)`.
- Runner `start()` returns a persisted `MaintenanceTaskRun`; `latest()` and `reconcile_interrupted()` use the existing generic maintenance-task storage.

- [ ] **Step 1: 写任务持久化与本地读取边界的失败测试。**

```python
def test_atomic_snapshot_runner_persists_completed_result_and_snapshot_meta(tmp_path):
    runner, store, parquet_store = _atomic_runner(tmp_path, _successful_atomic_builder())

    task = runner.start()
    _wait_for_terminal_task(store, task.task_id)

    completed = store.get_maintenance_task_run(task.task_id)
    assert completed.state == "completed"
    assert completed.result_json
    assert _snapshot_meta(parquet_store)["task_result_id"] == task.task_id


def test_atomic_snapshot_runner_uses_local_builder_without_initialization_service(tmp_path):
    runner, store, _ = _atomic_runner(tmp_path, _successful_atomic_builder())

    task = runner.start()
    _wait_for_terminal_task(store, task.task_id)

    assert store.get_maintenance_task_run(task.task_id).state == "completed"


def test_atomic_snapshot_runner_keeps_previous_snapshot_when_rebuild_fails(tmp_path):
    runner, store, parquet_store = _atomic_runner(tmp_path, _failing_atomic_builder())
    _write_previous_snapshot(parquet_store)

    task = runner.start()
    _wait_for_terminal_task(store, task.task_id)

    assert store.get_maintenance_task_run(task.task_id).state == "failed"
    assert state.load_index_atomic_snapshot_readonly(parquet_store, (_definition("000300"),)).summary.empty is False
```

- [ ] **Step 2: 运行红灯维护任务测试。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_maintenance_tasks.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-maintenance-red
```

Expected: FAIL，因为当前维护中心不存在该任务类型和专用运行器。

- [ ] **Step 3: 实现专用运行器和维护页入口。**

运行器先读取 `index_atomic_snapshot_inputs(store)`，再在 `run.io_bound` 中调用原子计算内核并调用 `write_index_atomic_snapshot`。构建过程只读取本地 SQLite/Parquet，禁止创建 `InitializationService` 或 provider。进度总数设为正式指数总数，按指数更新 `progress_done` 与当前代码；完成结果 JSON 记录总数、成功计算数、数据状态计数、生成时间和快照文件名。异常时记录中文错误文本，不删除先前快照。

在 `数据维护 -> 指数目录与历史` 区增加按钮、最近运行状态和帮助文案：`只读取本地指数历史；初始化、补齐或修复历史后，请手动重建。` 页面重载时从 `latest()` 恢复结果；服务重启遗留运行任务标记为中断，保持现有任务中心的状态语义。

- [ ] **Step 4: 运行维护任务与维护页回归。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_maintenance_tasks.py tests\test_nicegui_app_import.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-maintenance-green
```

Expected: PASS；成功结果可在刷新后读取，失败保留旧快照。

- [ ] **Step 5: 提交维护任务。**

```powershell
git add src/etf_trading/nicegui_app/maintenance_tasks.py src/etf_trading/nicegui_app/pages/maintenance.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_app_import.py
git commit -m "feat: add index atomic snapshot maintenance task"
```

## Task 4: 建立稳定排序、中文状态和详情分组视图模型

**Files:**

- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Modify: `src/etf_trading/nicegui_app/components/tables.py`
- Modify: `tests/test_nicegui_view_models.py`
- Modify: `tests/test_nicegui_table_display.py`

**Interfaces:**

- Add: `IndexAtomicFilters(pool="core", query="")`.
- Add: `build_index_atomic_rows(summary, filters)` and `index_atomic_detail_groups(details, index_code)`.
- Add Chinese snapshot states: `已验证`、`待重建`、`不存在`、`生成失败`.
- Add Chinese indicator states: `已计算`、`历史不足`、`缺少输入字段`、`读取失败`、`计算失败`.

- [ ] **Step 1: 写池、搜索、顺序与分组的失败测试。**

```python
def test_index_atomic_rows_keep_catalog_order_within_each_pool_and_search_only_filters():
    summary = pd.DataFrame([
        {"index_code": "399001", "index_name": "深证成指", "pool": "core", "catalog_order": 2},
        {"index_code": "000300", "index_name": "沪深300", "pool": "core", "catalog_order": 1},
        {"index_code": "801010", "index_name": "农林牧渔", "pool": "research", "catalog_order": 3},
    ])

    core = build_index_atomic_rows(summary, IndexAtomicFilters(pool="core"))
    searched = build_index_atomic_rows(summary, IndexAtomicFilters(pool="core", query="深证"))

    assert [row["index_code"] for row in core] == ["000300", "399001"]
    assert [row["index_code"] for row in searched] == ["399001"]


def test_index_atomic_detail_groups_are_fact_categories_without_strategy_conclusions():
    groups = index_atomic_detail_groups(_atomic_details(), "000300")

    assert [group.title for group in groups] == ["价格与均线", "均线穿越", "区间位置", "收益与回撤", "波动与成交", "数据质量"]
    assert all("趋势" not in item.label and "交易" not in item.label for group in groups for item in group.items)
```

- [ ] **Step 2: 运行红灯视图模型与表格测试。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_view_models.py tests\test_nicegui_table_display.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-view-model-red
```

Expected: FAIL；遗留筛选器按类别/代码排序，且详情仍含估值和趋势条目。

- [ ] **Step 3: 实现行模型、展示映射与固定表格列。**

行模型先按 `pool` 过滤，再对名称或代码执行大小写无关包含匹配，最后只按 `catalog_order` 稳定排序。表格固定使用：`指数`、`分类`、`最新日期`、`相对20日线`、`相对60日线`、`20日区间`、`20日收益`、`数据状态`。相对均线用“高于/低于 + 百分比”显示；区间只显示“20日新高”“20日新低”或“区间内”；空值显示“数据不足”。

详情分组不计算新值，只格式化快照详情。将日期、百分比、布尔交叉、状态码和空值统一转为中文可读文本，并保留原始 `metric_key` 供测试与页面定位。

- [ ] **Step 4: 运行视图模型、表格和全局样式回归。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_view_models.py tests\test_nicegui_table_display.py tests\test_nicegui_theme.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-view-model-green
```

Expected: PASS；核心/研究池顺序和中文状态保持一致。

- [ ] **Step 5: 提交视图模型与表格显示。**

```powershell
git add src/etf_trading/nicegui_app/view_models.py src/etf_trading/nicegui_app/components/tables.py tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py tests/test_nicegui_theme.py
git commit -m "feat: present index atomic indicator rows"
```

## Task 5: 改造指数体检页面为宽弹窗原子指标工作台

**Files:**

- Modify: `src/etf_trading/nicegui_app/pages/market.py`
- Modify: `src/etf_trading/nicegui_app/theme.py`
- Modify: `tests/test_nicegui_app_import.py`
- Modify: `tests/test_nicegui_theme.py`

**Interfaces:**

- `_render_index_health` consumes `load_index_atomic_snapshot_readonly`, `IndexAtomicFilters`, row model, detail groups.
- The row click opens a wide `ui.dialog` with tabs `关键指标`、`全部原子指标`、`数据质量`.
- The reload action calls the same read-only loader and never starts a maintenance run.

- [ ] **Step 1: 写页面结构和禁止遗留文案的失败测试。**

```python
def test_market_page_uses_readonly_atomic_snapshot_and_no_legacy_health_builder():
    source = Path("src/etf_trading/nicegui_app/pages/market.py").read_text(encoding="utf-8")

    assert "load_index_atomic_snapshot_readonly" in source
    assert "load_index_health_snapshot_cached" not in source
    assert "build_index_atomic_snapshot" not in source
    assert "CORE_VALUATION_METRICS" not in source


def test_market_page_declares_pool_search_and_tabbed_detail_dialog():
    source = Path("src/etf_trading/nicegui_app/pages/market.py").read_text(encoding="utf-8")

    for text in ("核心池", "研究池", "搜索指数", "关键指标", "全部原子指标", "数据质量"):
        assert text in source
    for forbidden in ("大趋势", "中趋势", "小趋势", "允许开仓", "估值"):
        assert forbidden not in source
```

- [ ] **Step 2: 运行红灯页面测试。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_app_import.py tests\test_nicegui_theme.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-market-red
```

Expected: FAIL；页面仍读取遗留健康快照并在表格下方显示详情。

- [ ] **Step 3: 实现状态栏、交互表格与三标签详情弹窗。**

动态区域之前创建工具栏。顶部状态栏包含快照状态、生成时间、当前输入最新日期、状态计数和“前往数据维护”入口。状态不是 `ready` 时，使用不可关闭、固定在结果上方的强提醒：

- `stale`：`原子指标快照待重建，当前展示的是上次成功生成的数据。`
- `missing`：`尚未生成指数原子指标快照，不能展示计算指标。请前往数据维护执行“重建指数原子指标”。`
- `failed`：`最近一次原子指标快照生成失败，不能把结果作为最新数据使用。请查看数据维护任务并重新执行。`

核心/研究池为分段控件，搜索框占同一行；表格点击行打开最大宽度约 1120px 的对话框。`关键指标` 只放最新收盘、MA20/60、相对均线、20日区间、20日收益和数据状态；`全部原子指标` 显示六个分组的全部快照详情；`数据质量` 显示生成时间、快照状态、原始历史状态、行数、覆盖信息、数据源及错误。缺失快照时不创建伪造表格行，保留状态栏和维护入口。

在 `theme.py` 为 `.index-atomic-alert`、`.index-atomic-dialog`、`.index-atomic-detail-grid` 编写样式：桌面使用多列网格，390px 宽度折叠为单列，详情表格容器可横向滚动但页面根容器不产生横向滚动。

- [ ] **Step 4: 运行模块测试和浏览器验收。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_app_import.py tests\test_nicegui_theme.py tests\test_nicegui_view_models.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-market-green
```

Then start the local app with an isolated data directory, open `市场地图 -> 指数体检`, and verify at 1440px and 390px:

1. 核心池默认显示，切换研究池后只出现研究池；搜索后相对目录顺序未变。
2. 快照不存在时显示不可关闭的维护提示且无伪造指标。
3. 写入测试快照后，点击一行打开三标签弹窗；六个原子分组、生成时间和数据质量可见。
4. 改动一个本地历史文件后，刷新页面显示“待重建”强提醒且保留旧数据。
5. 控制台没有错误或警告，390px 页面无根级横向滚动。

- [ ] **Step 5: 提交工作台页面。**

```powershell
git add src/etf_trading/nicegui_app/pages/market.py src/etf_trading/nicegui_app/theme.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py
git commit -m "feat: redesign index health as atomic workbench"
```

## Task 6: 进行端到端回归、静态防护和任务记忆更新

**Files:**

- Modify: `docs/task-memory.md`
- Review: changed source and tests from Tasks 1–5.

- [ ] **Step 1: 运行完整自动化回归。**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-workbench-full
```

Expected: PASS；每个用户可见的新增状态均有中文显示测试，历史不足与成交额缺失不会导致无关指标失效。

- [ ] **Step 2: 运行静态边界检查。**

Run:

```powershell
rg -n "CORE_VALUATION_METRICS|build_index_health_snapshot|TrendRegimeClassifier|allows_new_position|大趋势|中趋势|小趋势" src\etf_trading\nicegui_app\pages\market.py src\etf_trading\research\index_health_snapshot.py
rg -n "build_index_atomic_snapshot|InitializationService|AkShare" src\etf_trading\nicegui_app\pages\market.py
git diff --check
```

Expected: 前两条命令无匹配；`git diff --check` 无输出。

- [ ] **Step 3: 复查快照和维护任务的实际行为。**

使用临时 SQLite/Parquet：先运行“重建指数原子指标”，确认三件新快照文件和元数据存在；随后修改一份历史或覆盖输入，确认页面加载返回 `stale` 而不写文件；再让构建器抛错，确认维护记录失败且原快照仍可读取。删除快照三件文件后，确认页面返回 `missing` 而不触发构建。

- [ ] **Step 4: 更新任务记忆并提交验收记录。**

在 `docs/task-memory.md` 追加实施摘要、完整测试命令及结果、浏览器分辨率、关键边界：页面只读、手动重建、旧快照失败保留、核心/研究池顺序、无估值或策略结论。

```powershell
git add docs/task-memory.md
git commit -m "docs: record index atomic workbench verification"
```
