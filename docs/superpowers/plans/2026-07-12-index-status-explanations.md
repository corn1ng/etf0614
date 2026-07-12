# 指数数据状态说明 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在数据维护任务中心和指数市场参考中，以中文明确说明每个指数缺少什么数据、当前数据到哪一天，以及为何不能作为交易依据。

**Architecture:** 保留现有 `STALE`、`COMPLETE`、`INCOMPLETE`、`BASELINE_UNVERIFIED` 和 `MISSING_HISTORY` 内部状态作为存储与筛选键；在数据质量层集中生成面向用户的句子。初始化服务把同一说明写入维护任务结果、更新状态和历史覆盖表，NiceGUI 快照与共享表格只渲染这些说明字段，不再以内部状态短语作为主要结论。

**Tech Stack:** Python 3.11、pandas、SQLite、Parquet、NiceGUI、pytest。

## Global Constraints

- 所有新增或修改的用户可见文本必须为中文；内部枚举值不得直接作为主要提示。
- `STALE` 只表达最新行情滞后，不得被表述为历史起点缺失；必须展示本地最新日期和缺少的目标交易日。
- `BASELINE_UNVERIFIED` 必须展示实际本地覆盖区间、缺少官方基日，以及“不作为交易依据”的限制。
- `MISSING_HISTORY` / `EMPTY` 必须明确为数据源未返回历史行情，并展示指数代码与中文数据源类型；不得误称为历史不完整。
- 核心池准入逻辑、历史完整性枚举、数据库结构和策略规则保持不变；本次只增加解释字段和文案。
- 不读取或提交生成的 SQLite、Parquet、日志、报告和临时测试目录；不暂存用户已有的 `docs/superpowers/specs/2026-07-12-index-universe-expansion-design.md` 修改。
- 使用 `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe` 与唯一的 `--basetemp C:\Users\cjj\AppData\Local\Temp\...` 运行测试。

---

## File Structure

| 文件 | 责任 |
| --- | --- |
| `src/etf_trading/data/quality.py` | 将历史完整性和行情滞后事实格式化为可读中文说明。 |
| `src/etf_trading/data/initialization.py` | 在补齐、滞后与空响应路径写入一致的说明，并返回给维护任务。 |
| `src/etf_trading/nicegui_app/state.py` | 为指数市场快照增加行情状态说明，保留完整性说明。 |
| `src/etf_trading/nicegui_app/components/tables.py` | 为状态说明字段提供列标题，并避免把“基日待核验”作为主结论。 |
| `tests/test_index_support.py` | 覆盖完整、起点缺失、基日未知和空历史的中文解释。 |
| `tests/test_storage_and_services.py` | 覆盖补齐服务写入的滞后、空响应和覆盖说明。 |
| `tests/test_nicegui_table_display.py` | 覆盖维护表格的中文列名与状态展示。 |
| `tests/test_nicegui_app_import.py` | 覆盖指数快照的行情缺口说明。 |

## Task 1: 在数据质量层定义统一的指数说明

**Files:**
- Modify: `src/etf_trading/data/quality.py`
- Modify: `tests/test_index_support.py`

**Interfaces:**
- Produces: `index_history_freshness_message(latest_trade_date, expected_trade_date)`。
- Extends: `assess_index_history_completeness(..., index_code=None, source_kind=None)`；既有调用保持兼容。
- Consumes: 本地首日/末日、官方基日、基日来源、指数代码和数据源类型。

- [ ] **Step 1: 写失败测试，固定用户可见的五类说明**

```python
def test_index_history_completeness_explains_unverified_base_with_actual_range():
    assessment = assess_index_history_completeness(
        pd.DataFrame({"trade_date": pd.to_datetime(["1999-12-30", "2026-07-09"])}),
        None,
        baseline_source="unverified",
        index_code="000001",
        source_kind="csi",
    )

    assert assessment.status == "BASELINE_UNVERIFIED"
    assert assessment.message == (
        "已有 1999-12-30 至 2026-07-09 的行情，但缺少官方基日；"
        "暂时无法判断是否从指数起点完整，不作为交易依据。"
    )


def test_index_history_completeness_explains_empty_source_response():
    assessment = assess_index_history_completeness(
        pd.DataFrame(),
        "2014-12-31",
        baseline_source="official_methodology",
        index_code="L11226",
        source_kind="csi",
    )

    assert assessment.status == "MISSING_HISTORY"
    assert assessment.message == "中证数据源未返回 L11226 的历史行情。"


def test_index_history_freshness_message_names_the_missing_trade_date():
    assert index_history_freshness_message("2026-07-09", "2026-07-10") == "已更新至 2026-07-09，缺少 2026-07-10 行情。"
```

同时为 `COMPLETE` 与 `INCOMPLETE` 添加断言：前者包含官方基日与本地覆盖区间，后者为“应从 … 开始，当前仅有 … 起的数据。”

- [ ] **Step 2: 运行测试，确认当前文案不满足要求**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_support.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-quality-red
```

Expected: FAIL，基日未知场景仍返回“基日待核验，不能判定历史完整”，且不存在行情缺口格式化接口。

- [ ] **Step 3: 实现基于事实的中文说明函数**

在 `quality.py` 增加小型纯函数，日期统一格式化为 `YYYY-MM-DD`，并把 `csi`、`shenwan`、`hk` 转换为“中证数据源”“申万数据源”“港股数据源”。实现的语义必须等同于：

```python
def index_history_freshness_message(latest_trade_date, expected_trade_date) -> str:
    return f"已更新至 {latest_trade_date}，缺少 {expected_trade_date} 行情。"


def _missing_history_message(index_code: str | None, source_kind: str | None) -> str:
    if index_code and source_kind:
        return f"{_source_kind_label(source_kind)}未返回 {index_code} 的历史行情。"
    return "数据源未返回该指数的历史行情。"
```

将 `assess_index_history_completeness` 的结果文案更新为：

```python
# BASELINE_UNVERIFIED
f"已有 {first_text} 至 {latest_text} 的行情，但缺少官方基日；"
"暂时无法判断是否从指数起点完整，不作为交易依据。"

# COMPLETE
f"历史从官方基日 {base_text} 开始，当前覆盖 {first_text} 至 {latest_text}，数据完整。"

# INCOMPLETE
f"应从 {base_text} 开始，当前仅有 {first_text} 起的数据。"
```

无 `index_code` 或 `source_kind` 的旧调用必须安全降级为通用空响应说明；读取失败的现有错误说明保持不变。

- [ ] **Step 4: 运行数据质量回归测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_support.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-quality-green
```

Expected: PASS，五种状态都能表达实际日期、范围或数据源事实。

- [ ] **Step 5: 提交数据质量说明**

```powershell
git add src/etf_trading/data/quality.py tests/test_index_support.py
git commit -m "feat: explain index history data status"
```

## Task 2: 把说明持久化到补齐结果与历史覆盖

**Files:**
- Modify: `src/etf_trading/data/initialization.py`
- Modify: `tests/test_storage_and_services.py`

**Interfaces:**
- Consumes: `IndexCatalogEntry` 的 `index_code`、`source_kind`、基日与基日来源。
- Produces: `IndexHistoryResult.error_message`（状态说明）、`IndexHistoryResult.completeness_message` 及 `data_update_state.error_message`。
- Preserves: `IndexHistoryResult.status`、`completeness_status` 与既有 SQLite 表结构。

- [ ] **Step 1: 写失败测试，验证维护任务会保留具体缺口而非技术短语**

```python
def test_ensure_index_history_records_exact_missing_latest_trade_date(tmp_path):
    service, store = _service_with_catalog(
        tmp_path,
        _FakeProvider(index_frame=_prices("000300", start="2005-01-04", end="2026-07-09")),
        [_catalog_entry("000300", index_base_date=date(2005, 1, 4))],
    )

    result = service.ensure_index_history("000300", "2026-07-10")

    assert result.status == "STALE"
    assert result.error_message == "已更新至 2026-07-09，缺少 2026-07-10 行情。"
    with store.connect() as conn:
        state = pd.read_sql_query("SELECT error_message FROM data_update_state", conn).iloc[0]
    assert state["error_message"] == result.error_message


def test_ensure_index_history_records_empty_provider_response_with_source(tmp_path):
    service, _ = _service_with_catalog(
        tmp_path,
        _FakeProvider(index_frame=pd.DataFrame()),
        [_catalog_entry("H30533", source_kind="hk", index_base_date=None, baseline_source="unverified")],
    )

    result = service.ensure_index_history("H30533", "2026-07-10")

    assert result.status == "EMPTY"
    assert result.error_message == "港股数据源未返回 H30533 的历史行情。"
    assert result.completeness_message == result.error_message
```

- [ ] **Step 2: 运行服务测试，确认现有空响应没有可解释原因**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-service-red
```

Expected: FAIL，`STALE` 使用“未达到目标交易日”的技术文本，`EMPTY` 的结果没有 `error_message`。

- [ ] **Step 3: 在所有指数历史路径使用同一说明源**

将目录条目的代码和数据源类型传入完整性评估：

```python
completeness = assess_index_history_completeness(
    frame,
    entry.index_base_date,
    baseline_source=entry.baseline_source,
    index_code=entry.index_code,
    source_kind=entry.source_kind,
)
```

在 `_stale_index_result` 中调用 `index_history_freshness_message(last_date, expected_date)`，并将它同时写入 `data_update_state.error_message` 与 `IndexHistoryResult.error_message`。空响应路径将 `completeness.message` 同时写入更新状态和 `IndexHistoryResult.error_message`，确保页面刷新后仍能看到原因。

不要把空响应伪装为 `FAILED`：保留 `EMPTY`，因为这代表数据源已成功调用但未返回可用历史；网络或解析异常继续走既有 `FAILED` 路径并保留短截断的原始错误。

- [ ] **Step 4: 运行初始化和存储回归测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py tests\test_index_support.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-service-green
```

Expected: PASS，任务结果、更新状态和历史覆盖表中的说明一致。

- [ ] **Step 5: 提交补齐结果解释**

```powershell
git add src/etf_trading/data/initialization.py tests/test_storage_and_services.py
git commit -m "feat: persist index history status explanations"
```

## Task 3: 在任务中心和市场参考页显示缺口说明

**Files:**
- Modify: `src/etf_trading/nicegui_app/state.py`
- Modify: `src/etf_trading/nicegui_app/components/tables.py`
- Modify: `tests/test_nicegui_table_display.py`
- Modify: `tests/test_nicegui_app_import.py`

**Interfaces:**
- Produces: 指数快照字段 `data_status_message`，以及表格列“行情状态说明”“历史完整性说明”“状态说明”。
- Consumes: `HistoryAssessment` 的 `latest_trade_date`、`expected_trade_date`、`readiness` 和已持久化的 `completeness_message`。
- Preserves: `data_status`、`history_completeness_status`、表格的内部值映射和 `allows_new_position` 准入逻辑。

- [ ] **Step 1: 写失败测试，覆盖维护结果与市场行的显示文案**

```python
def test_table_columns_name_maintenance_detail_as_status_explanation():
    labels = [column["label"] for column in table_columns([{"error_message": "已更新至 2026-07-09，缺少 2026-07-10 行情。"}])]

    assert labels == ["状态说明"]


def test_table_rows_do_not_use_baseline_pending_verification_as_the_primary_conclusion():
    display = table_rows([{
        "completeness_status": "BASELINE_UNVERIFIED",
        "completeness_message": "已有 1999-12-30 至 2026-07-09 的行情，但缺少官方基日；暂时无法判断是否从指数起点完整，不作为交易依据。",
    }])

    assert display[0]["completeness_status"] == "历史起点无法确认"
    assert "基日待核验" not in " ".join(str(value) for value in display[0].values())


def test_build_index_trend_summary_exposes_exact_stale_gap_message(tmp_path):
    summary = build_index_trend_summary(_parquet_with_last_date(tmp_path, "000300", "2026-07-09"), today="2026-07-10")

    assert summary.iloc[0]["data_status_message"] == "已更新至 2026-07-09，缺少 2026-07-10 行情。"
```

- [ ] **Step 2: 运行前端显示测试，确认当前表格只显示内部短语**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_table_display.py tests\test_nicegui_app_import.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-ui-red
```

Expected: FAIL，表格列名仍为“错误信息”，“基日待核验”仍是状态主文案，市场快照没有 `data_status_message`。

- [ ] **Step 3: 为共享表格和市场快照接入说明字段**

在 `tables.py` 执行以下定向显示调整：

```python
COLUMN_LABELS.update({
    "error_message": "状态说明",
    "data_status_message": "行情状态说明",
})
VALUE_LABELS["BASELINE_UNVERIFIED"] = "历史起点无法确认"
```

在 `build_index_trend_summary` 的默认行、读取失败分支和正常评估分支写入 `data_status_message`：滞后时复用 `index_history_freshness_message`；数据可用时说明“已更新至 {expected}，行情可用。”；空历史或读取失败时复用已有的中文状态并说明其无法作为趋势或买卖依据。将 `data_status_message` 加入指数健康快照缓存的文本列，防止缓存读写丢失该字段。

市场参考页已经直接渲染 `snapshot.index_summary`，因此不单独复制格式化逻辑；维护任务中心继续渲染 `IndexHistoryResult.error_message`，但列标题改为“状态说明”。

- [ ] **Step 4: 运行前端显示与快照回归测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_table_display.py tests\test_nicegui_app_import.py tests\test_nicegui_view_models.py tests\test_nicegui_maintenance_tasks.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-ui-green
```

Expected: PASS，任务中心、市场参考、健康快照均保留中文说明，且核心池准入没有回归。

- [ ] **Step 5: 提交页面状态说明**

```powershell
git add src/etf_trading/nicegui_app/state.py src/etf_trading/nicegui_app/components/tables.py tests/test_nicegui_table_display.py tests/test_nicegui_app_import.py
git commit -m "feat: show index data gaps in Chinese"
```

## Task 4: 全量验证与人工验收

**Files:**
- Modify: `docs/task-memory.md`

- [ ] **Step 1: 运行完整测试套件**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-full
```

Expected: PASS；不得因为新的中文说明改变核心交易池或策略准入结果。

- [ ] **Step 2: 启动应用并进行最小人工验收**

打开“数据维护 → 补齐任务”，检查任意 `STALE` 行是否显示“已更新至 …，缺少 … 行情。”；检查任意 `BASELINE_UNVERIFIED` 行是否显示实际覆盖区间、官方基日缺失和“不作为交易依据”；检查 `H30533` 或 `L11226` 等空响应行是否显示中文数据源与代码。再打开“市场参考”，确认同一指数显示一致的行情状态说明和历史完整性说明。

- [ ] **Step 3: 检查提交范围与计划自检**

Run:

```powershell
git status --short
git log --oneline -3
rg -n "TODO|FIXME|XXX|HACK" src/etf_trading/data/quality.py src/etf_trading/data/initialization.py src/etf_trading/nicegui_app/state.py src/etf_trading/nicegui_app/components/tables.py tests/test_index_support.py tests/test_storage_and_services.py tests/test_nicegui_table_display.py tests/test_nicegui_app_import.py
```

Expected: 只存在本计划列出的源代码、测试和工作记忆改动；最后一条命令无匹配；保留用户的未提交设计文档和无关临时目录。

- [ ] **Step 4: 记录工作记忆并提交收尾文档**

向 `docs/task-memory.md` 追加本次状态说明的实现范围、完整测试结果和人工验收结果，然后只暂存该记忆文件：

```powershell
git add docs/task-memory.md
git commit -m "docs: record index status explanation verification"
```


