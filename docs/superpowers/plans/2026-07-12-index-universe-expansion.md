# 指数主目录扩容 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 A 股和港股指数范围从 49 个静态白名单升级为约 180 个经验证的指数主目录，并将约 100 个有 ETF 映射的指数作为核心交易池。

**Architecture:** 版本化 YAML 候选目录是唯一的目录定义来源，SQLite 保存其本地投影、ETF 映射覆盖和历史完整性，Parquet 继续保存逐指数历史。数据源验证、从 1990 年起的全历史补齐和日常增量更新均由持久化维护任务执行；平台快照从 SQLite 目录读取，而不再由 `DEFAULT_INDEXES` 限制。

**Tech Stack:** Python 3.11、pandas、PyYAML、SQLite、Parquet、AkShare、NiceGUI、pytest。

## Global Constraints

- 第一阶段只覆盖 A 股和港股；不增加付费数据源、境外市场、商品或债券指数。
- 正式目录目标为 180 个经验证指数：核心池 100 个、研究池 80 个；配置保留约 30 个候补。
- 首次历史补齐必须从 `1990-01-01` 请求；不得用十年窗口代替全历史。
- 核心池必须同时满足历史完整、最新行情正常和至少一个活跃 ETF 映射；研究池不得进入研究回测、策略或买卖建议输入。
- 历史完整性、行情新鲜度和数据源可读性必须分别存储和显示；所有用户可见状态为中文。
- 生成的 SQLite、Parquet、日志、报告和临时测试目录不得提交。
- 使用 `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe` 与唯一的 `--basetemp C:\Users\cjj\AppData\Local\Temp\...` 运行测试。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `configs/index_universe.yaml` | 约 210 个经过人工审阅的 A 股、港股候选指数；包含核心、研究和候补层级及数据源元数据。 |
| `src/etf_trading/data/index_catalog.py` | YAML 解析、字段校验、目录条目模型、历史完整性评估。 |
| `src/etf_trading/data/indexes.py` | 保留兼容接口，将旧 49 条静态目录迁移为从 YAML 加载的默认目录。 |
| `src/etf_trading/data/storage.py` | SQLite 指数目录、历史覆盖和 ETF 映射覆盖表及读写接口。 |
| `src/etf_trading/data/provider.py` | 将指数历史拉取接口扩展为接收目录条目。 |
| `src/etf_trading/data/providers/akshare_provider.py` | 依据目录的数据源类型调用中证、申万、港股端点并标准化日线。 |
| `src/etf_trading/data/initialization.py` | 目录同步、数据源验证、全历史补齐、完整性状态更新。 |
| `src/etf_trading/nicegui_app/maintenance_tasks.py` | 可恢复的目录同步、数据源验证、全历史、历史重补和增量更新后台任务。 |
| `src/etf_trading/nicegui_app/state.py` | 从 SQLite 目录构建指数快照，合并历史完整性和 ETF 映射。 |
| `src/etf_trading/research/index_etf_universe.py` | 只为核心池生成可交易 ETF 样本，并记录映射来源。 |
| `src/etf_trading/nicegui_app/view_models.py` | 核心/研究筛选、完整性摘要和中文展示数据。 |
| `src/etf_trading/nicegui_app/pages/maintenance.py` | 指数目录健康摘要与五类持久化维护操作。 |
| `src/etf_trading/nicegui_app/pages/market.py` | 核心池默认展示、研究池显式切换和完整性列。 |
| `src/etf_trading/nicegui_app/pages/research.py` | 回测入口只提供核心池指数。 |
| `tests/test_index_catalog.py` | 目录配置、数量边界、完整性评估和 ETF 准入单测。 |
| `tests/test_storage_and_services.py` | SQLite 目录/覆盖读写、服务同步及历史补齐单测。 |
| `tests/test_akshare_provider_fallback.py` | 中证、申万、港股数据源选择和标准化单测。 |
| `tests/test_nicegui_maintenance_task_runner.py` | 新维护任务持久化、恢复和快照失效单测。 |
| `tests/test_nicegui_maintenance_tasks.py` | 数据维护摘要、中文状态与操作按钮单测。 |
| `tests/test_nicegui_view_models.py`、`tests/test_nicegui_navigation.py` | 核心/研究筛选和研究页准入单测。 |

## Task 1: 建立版本化指数候选目录与模型

**Files:**
- Create: `configs/index_universe.yaml`
- Create: `src/etf_trading/data/index_catalog.py`
- Modify: `src/etf_trading/data/indexes.py`
- Test: `tests/test_index_catalog.py`

**Interfaces:**
- Produces: `IndexCatalogEntry`、`load_index_catalog(path)`、`default_index_catalog()`、`catalog_definitions(entries, pool=None, include_reserve=False)`。
- Consumes: YAML 配置和现有 `IndexDefinition` 使用方。

- [ ] **Step 1: 写失败测试，明确 YAML 校验、目录层级与数量边界**

```python
def test_default_catalog_has_target_pool_boundaries():
    entries = default_index_catalog()

    assert len(entries) == 210
    assert sum(entry.pool == "core" for entry in entries) == 100
    assert sum(entry.pool == "research" for entry in entries) == 80
    assert sum(entry.pool == "reserve" for entry in entries) == 30
    assert {entry.market for entry in entries} == {"A股", "港股"}


def test_catalog_rejects_duplicate_codes_and_missing_base_date(tmp_path):
    path = tmp_path / "index_universe.yaml"
    path.write_text(
        "entries:\n"
        "  - index_code: '000300'\n    name: 沪深300\n    market: A股\n"
        "    pool: core\n    source_kind: csi\n    provider_symbol: '000300'\n"
        "  - index_code: '000300'\n    name: 重复\n    market: A股\n"
        "    pool: core\n    source_kind: csi\n    provider_symbol: '000300'\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate index_code"):
        load_index_catalog(path)
```

- [ ] **Step 2: 运行测试，确认当前没有目录加载接口**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_catalog.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-catalog-red
```

Expected: FAIL，提示 `default_index_catalog` 或 `load_index_catalog` 不存在。

- [ ] **Step 3: 实现目录模型和 YAML 加载**

```python
@dataclass(frozen=True)
class IndexCatalogEntry:
    index_code: str
    name: str
    market: str
    category_level_1: str
    category_level_2: str
    index_type: str
    pool: Literal["core", "research", "reserve"]
    index_base_date: date
    published_at: date | None
    source_kind: Literal["csi", "shenwan", "hk"]
    provider_symbol: str
    aliases: tuple[str, ...] = ()


def load_index_catalog(path: str | Path) -> tuple[IndexCatalogEntry, ...]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entries = tuple(_entry_from_mapping(item) for item in raw.get("entries", []))
    _validate_catalog(entries)
    return entries


def catalog_definitions(
    entries: Sequence[IndexCatalogEntry],
    *,
    pool: str | None = None,
    include_reserve: bool = False,
) -> tuple[IndexDefinition, ...]:
    selected = [entry for entry in entries if (pool is None or entry.pool == pool)]
    if not include_reserve:
        selected = [entry for entry in selected if entry.pool != "reserve"]
    return tuple(entry.to_index_definition() for entry in selected)
```

Populate `configs/index_universe.yaml` with exactly 210 records. Use the existing 49 records as migration seeds, all 31 rows returned by `ak.sw_index_first_info()` as A 股行业覆盖，人工筛选的申万二级行业和 ETF 覆盖主题补足 A 股 143 条，以及经过港股端点验证的宽基、行业和中国资产指数补足港股 37 条。每条记录必须有实际代码、指数基日、数据源类型和提供者代码；不得以名称猜测代替代码。

Keep compatibility in `indexes.py`:

```python
DEFAULT_INDEXES = catalog_definitions(default_index_catalog())


def get_index_definition(index_code: str) -> IndexDefinition:
    return next(item for item in DEFAULT_INDEXES if item.index_code == str(index_code))
```

- [ ] **Step 4: 运行目录测试，确认加载、边界和兼容选择器**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_catalog.py tests\test_index_support.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-catalog-green
```

Expected: PASS，且已有 49 个指数的兼容测试不回归。

- [ ] **Step 5: 提交目录模型与候选目录**

```powershell
git add configs/index_universe.yaml src/etf_trading/data/index_catalog.py src/etf_trading/data/indexes.py tests/test_index_catalog.py tests/test_index_support.py
git commit -m "feat: add versioned index universe catalog"
```

## Task 2: 持久化指数目录、覆盖与 ETF 映射状态

**Files:**
- Modify: `src/etf_trading/data/storage.py`
- Test: `tests/test_storage_and_services.py`

**Interfaces:**
- Consumes: `Sequence[IndexCatalogEntry]`。
- Produces: `SQLiteStore.upsert_index_catalog(entries)`、`list_index_catalog(pool=None, include_reserve=False)`、`upsert_index_history_coverage(...)`、`list_index_history_coverage()`、`replace_index_etf_mappings(frame)`、`list_index_etf_mappings()`。

- [ ] **Step 1: 写失败测试，明确目录和完整性状态必须可跨进程读取**

```python
def test_sqlite_store_persists_catalog_coverage_and_etf_mappings(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    entry = _catalog_entry("801010", pool="core", source_kind="shenwan")

    store.upsert_index_catalog([entry])
    store.upsert_index_history_coverage(
        "801010",
        index_base_date="1999-12-30",
        local_first_trade_date="1999-12-30",
        source_first_trade_date="1999-12-30",
        latest_trade_date="2026-07-10",
        history_rows=6408,
        completeness_status="complete",
        completeness_message="历史完整",
    )
    store.replace_index_etf_mappings(pd.DataFrame([{
        "index_code": "801010", "etf_code": "516300", "mapping_source": "data_source",
        "confidence": "high", "is_tradable": 1,
    }]))

    assert store.list_index_catalog(pool="core").iloc[0]["index_code"] == "801010"
    assert store.list_index_history_coverage().iloc[0]["completeness_status"] == "complete"
    assert store.list_index_etf_mappings().iloc[0]["is_tradable"] == 1
```

- [ ] **Step 2: 运行测试，确认数据库尚无这些接口和表**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py::test_sqlite_store_persists_catalog_coverage_and_etf_mappings -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-storage-red
```

Expected: FAIL，提示 `upsert_index_catalog` 不存在。

- [ ] **Step 3: 为目录事实、历史覆盖和 ETF 映射增加 SQLite 模型**

在 `initialize_schema()` 中加入三个表：

```sql
CREATE TABLE IF NOT EXISTS index_catalog (
    index_code TEXT PRIMARY KEY, name TEXT NOT NULL, market TEXT NOT NULL,
    category_level_1 TEXT NOT NULL, category_level_2 TEXT NOT NULL,
    index_type TEXT NOT NULL, pool TEXT NOT NULL,
    index_base_date TEXT NOT NULL, published_at TEXT,
    source_kind TEXT NOT NULL, provider_symbol TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]', updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS index_history_coverage (
    index_code TEXT PRIMARY KEY, index_base_date TEXT NOT NULL,
    local_first_trade_date TEXT, source_first_trade_date TEXT,
    latest_trade_date TEXT, history_rows INTEGER NOT NULL DEFAULT 0,
    completeness_status TEXT NOT NULL, completeness_message TEXT NOT NULL,
    validated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS index_etf_mapping (
    index_code TEXT NOT NULL, etf_code TEXT NOT NULL, mapping_source TEXT NOT NULL,
    confidence TEXT NOT NULL, is_tradable INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (index_code, etf_code)
);
```

Each read method must return a stable DataFrame with all expected columns even when its table is empty. `replace_index_etf_mappings` deletes and rewrites only the supplied index codes inside one transaction, so a new mapping calculation does not erase unrelated indexes.

- [ ] **Step 4: 运行存储和服务回归测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py tests\test_index_catalog.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-storage-green
```

Expected: PASS。

- [ ] **Step 5: 提交持久化目录状态**

```powershell
git add src/etf_trading/data/storage.py tests/test_storage_and_services.py
git commit -m "feat: persist index catalog coverage and mappings"
```

## Task 3: 支持中证、申万和港股目录条目的历史拉取

**Files:**
- Modify: `src/etf_trading/data/provider.py`
- Modify: `src/etf_trading/data/providers/akshare_provider.py`
- Modify: `src/etf_trading/data/indexes.py`
- Test: `tests/test_akshare_provider_fallback.py`
- Test: `tests/test_index_support.py`

**Interfaces:**
- Consumes: `IndexCatalogEntry` 或兼容的 `IndexDefinition`。
- Produces: `DataProvider.fetch_index_daily(index, start_date, end_date)`，每次返回标准列 `index_code, trade_date, open, high, low, close, volume, amount, data_source`。

- [ ] **Step 1: 写失败测试，覆盖申万全历史和港股备用端点**

```python
def test_fetch_index_daily_uses_shenwan_history_for_shenwan_catalog_entry(fake_akshare):
    entry = _catalog_entry("801010", source_kind="shenwan", provider_symbol="801010")
    provider = AkShareProvider(ak=FakeAkShare(index_hist_sw=_shenwan_frame()))

    result = provider.fetch_index_daily(entry, "1990-01-01", "2026-07-10")

    assert result["index_code"].eq("801010").all()
    assert result["data_source"].eq("akshare_shenwan").all()
    assert result["trade_date"].min() == pd.Timestamp("1999-12-30")


def test_fetch_index_daily_returns_empty_frame_after_all_configured_hk_sources_fail():
    entry = _catalog_entry("H30533", source_kind="hk", provider_symbol="H30533")
    provider = AkShareProvider(ak=AlwaysFailAkShare())

    result = provider.fetch_index_daily(entry, "1990-01-01", "2026-07-10")

    assert list(result.columns) == INDEX_DAILY_COLUMNS
    assert result.empty
```

- [ ] **Step 2: 运行测试，确认申万条目尚不被支持**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_akshare_provider_fallback.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-provider-red
```

Expected: FAIL，提示 `fetch_index_daily` 不能使用 `IndexCatalogEntry` 或没有 `index_hist_sw` 路径。

- [ ] **Step 3: 实现按目录条目选择数据源**

```python
def fetch_index_daily(
    self,
    index: str | IndexCatalogEntry,
    start_date: date | str,
    end_date: date | str,
) -> pd.DataFrame:
    entry = _resolve_catalog_entry(index)
    if entry.source_kind == "shenwan":
        raw = _call_with_retries(
            self.ak.index_hist_sw,
            f"AkShare 申万行业指数行情 {entry.index_code}",
            symbol=entry.provider_symbol,
            period="day",
        )
        frame = normalize_index_daily(raw, entry.index_code, "akshare_shenwan")
    elif entry.source_kind == "hk":
        frame = self._fetch_hk_index_daily(entry)
    else:
        frame = self._fetch_csi_index_daily(entry)
    return _filter_index_dates(frame, start_date, end_date)
```

`_resolve_catalog_entry` accepts old string callers through `get_index_definition`, so existing tests and scripts remain operational. `DataProvider` must document the new union type. Do not call a provider at module import time.

- [ ] **Step 4: 运行数据源与指数历史回归测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_akshare_provider_fallback.py tests\test_index_support.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-provider-green
```

Expected: PASS。

- [ ] **Step 5: 提交多源指数历史支持**

```powershell
git add src/etf_trading/data/provider.py src/etf_trading/data/providers/akshare_provider.py src/etf_trading/data/indexes.py tests/test_akshare_provider_fallback.py tests/test_index_support.py
git commit -m "feat: support catalog index history sources"
```

## Task 4: 同步目录、验证数据源并按全历史评估完整性

**Files:**
- Modify: `src/etf_trading/data/initialization.py`
- Modify: `src/etf_trading/data/quality.py`
- Test: `tests/test_storage_and_services.py`
- Test: `tests/test_index_support.py`

**Interfaces:**
- Consumes: `SQLiteStore`、`ParquetStore`、`DataProvider`、`Sequence[IndexCatalogEntry]`。
- Produces: `InitializationService.sync_index_catalog()`、`validate_index_sources()`、`ensure_index_history()`、`ensure_all_index_history()` 和 `IndexHistoryResult.completeness_status`。

- [ ] **Step 1: 写失败测试，区分历史不完整、历史缺失和行情滞后**

```python
def test_ensure_index_history_marks_complete_history_only_when_base_date_is_covered(tmp_path):
    entry = _catalog_entry("801010", index_base_date=date(1999, 12, 30), source_kind="shenwan")
    provider = FakeProvider(index_frame=_prices("801010", start="2005-01-04", end="2026-07-10"))
    service, store = _service_with_catalog(tmp_path, provider, [entry])

    result = service.ensure_index_history("801010", "2026-07-10")

    assert result.status == "INITIALIZED"
    assert result.completeness_status == "INCOMPLETE"
    coverage = store.list_index_history_coverage().iloc[0]
    assert coverage["local_first_trade_date"] == "2005-01-04"
    assert coverage["completeness_message"] == "应从 1999-12-30 开始，本地仅从 2005-01-04 开始"
```

- [ ] **Step 2: 运行测试，确认结果对象尚无完整性字段**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py::test_ensure_index_history_marks_complete_history_only_when_base_date_is_covered -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-history-red
```

Expected: FAIL，提示 `completeness_status` 不存在。

- [ ] **Step 3: 实现同步、验证和全历史完整性状态**

```python
def sync_index_catalog(self, entries: Sequence[IndexCatalogEntry] | None = None) -> pd.DataFrame:
    catalog = tuple(entries or default_index_catalog())
    self.store.upsert_index_catalog(catalog)
    return self.store.list_index_catalog(include_reserve=True)


def ensure_index_history(self, index_code: str, through: date | str) -> IndexHistoryResult:
    entry = self._catalog_entry(index_code)
    existing = self.parquet_store.read_index_prices(index_code)
    fetch_start = INDEX_HISTORY_AUTO_START if existing.empty else _next_trade_day(existing)
    fetched = self.provider.fetch_index_daily(entry, fetch_start, through)
    featured = _merge_index_history(existing, fetched, entry.index_code)
    self.parquet_store.write_index_prices(entry.index_code, featured)
    completeness = assess_index_history_completeness(featured, entry.index_base_date)
    self.store.upsert_index_history_coverage(entry.index_code, **completeness.to_storage_values())
    return IndexHistoryResult.from_frame(entry.index_code, featured, completeness)
```

`validate_index_sources()` must request only the latest ten calendar days, write source validation metadata, and return one result row per catalog entry. `ensure_all_index_history()` defaults to SQLite formal entries (`core` and `research`, not `reserve`), catches each exception independently, and emits progress for every entry. When an existing file is fresh but incomplete, do not skip it: request history again from `1990-01-01` when the caller chose the historical-repair operation.

- [ ] **Step 4: 运行服务、质量和指数支持测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py tests\test_index_support.py tests\test_data_coverage.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-history-green
```

Expected: PASS，覆盖完整、缺失、滞后和读取失败互不混淆。

- [ ] **Step 5: 提交目录服务与完整性评估**

```powershell
git add src/etf_trading/data/initialization.py src/etf_trading/data/quality.py tests/test_storage_and_services.py tests/test_index_support.py
git commit -m "feat: validate index history completeness"
```

## Task 5: 将 ETF 映射和策略研究限制在核心池

**Files:**
- Modify: `src/etf_trading/research/index_etf_universe.py`
- Modify: `src/etf_trading/nicegui_app/state.py`
- Modify: `src/etf_trading/nicegui_app/pages/research.py`
- Test: `tests/test_index_etf_universe.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Consumes: SQLite 目录、ETF 主列表、Parquet ETF 历史和 `IndexCatalogEntry.pool`。
- Produces: 带 `pool`、`is_tradable`、`mapping_source` 和 `confidence` 列的 ETF 映射；研究回测入口只接受核心指数。

- [ ] **Step 1: 写失败测试，研究池即使有 ETF 也不能进入回测样本**

```python
def test_build_index_etf_universe_excludes_research_pool_from_tradeable_samples(tmp_path):
    entries = (
        _catalog_entry("000300", pool="core", aliases=("沪深300",)),
        _catalog_entry("801010", pool="research", aliases=("农林牧渔",)),
    )
    universe = build_index_etf_universe(_master_with_two_indexes(), ParquetStore(tmp_path), entries=entries)

    assert set(universe["index_code"]) == {"000300"}
    assert universe.iloc[0]["is_tradable"] is True
```

- [ ] **Step 2: 运行测试，确认现有函数会处理所有传入定义**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_etf_universe.py::test_build_index_etf_universe_excludes_research_pool_from_tradeable_samples -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-etf-red
```

Expected: FAIL，研究池 ETF 被包含或函数不接受 `entries`。

- [ ] **Step 3: 实现核心池 ETF 准入与目录驱动快照**

```python
def build_index_etf_universe(
    master: pd.DataFrame,
    parquet_store: ParquetStore,
    entries: Sequence[IndexCatalogEntry],
    config: IndexEtfSampleConfig | None = None,
) -> pd.DataFrame:
    core_entries = [entry for entry in entries if entry.pool == "core"]
    # 对 core_entries 做显式跟踪指数、配置别名和 ETF 名称三层匹配。
    # 映射的 is_tradable 只在 ETF 活跃且历史行数达到阈值时为 True。
```

In `load_snapshot`, load formal catalog entries from SQLite, pass all formal entries to `build_index_trend_summary`, pass core entries to `build_index_etf_universe`, then persist current mapping coverage with `replace_index_etf_mappings`. In the research page, filter `index_choice_options` to `pool == "core"` before calling `selected_etf_codes`.

- [ ] **Step 4: 运行 ETF 映射、研究页和快照回归测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_etf_universe.py tests\test_nicegui_view_models.py tests\test_nicegui_state_cache.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-etf-green
```

Expected: PASS，研究池只能显示研究信息，不能构成回测 ETF 样本。

- [ ] **Step 5: 提交核心池策略边界**

```powershell
git add src/etf_trading/research/index_etf_universe.py src/etf_trading/nicegui_app/state.py src/etf_trading/nicegui_app/pages/research.py tests/test_index_etf_universe.py tests/test_nicegui_view_models.py
git commit -m "feat: restrict index ETF research to core pool"
```

## Task 6: 目录驱动平台快照与指数体检缓存

**Files:**
- Modify: `src/etf_trading/nicegui_app/state.py`
- Modify: `src/etf_trading/research/index_health_snapshot.py`
- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Test: `tests/test_index_health_snapshot.py`
- Test: `tests/test_nicegui_state_cache.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Consumes: SQLite 目录和覆盖 DataFrame。
- Produces: 带 `pool`、`history_completeness_status`、`history_completeness_message`、`index_base_date` 和 ETF 映射数的 `PlatformSnapshot.index_summary`。

- [ ] **Step 1: 写失败测试，快照必须展示覆盖状态但不能把研究池当作可交易指数**

```python
def test_index_trend_summary_includes_history_completeness_and_pool(tmp_path):
    definitions = (_definition("801010", pool="research", index_base_date="1999-12-30"),)
    coverage = pd.DataFrame([{
        "index_code": "801010", "completeness_status": "incomplete",
        "completeness_message": "应从 1999-12-30 开始，本地仅从 2005-01-04 开始",
    }])

    summary = build_index_trend_summary(ParquetStore(tmp_path), definitions=definitions, coverage=coverage)

    assert summary.iloc[0]["pool"] == "research"
    assert summary.iloc[0]["history_completeness_status"] == "incomplete"
    assert summary.iloc[0]["allows_new_position"] is False
```

- [ ] **Step 2: 运行测试，确认旧快照没有目录覆盖字段**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_health_snapshot.py tests\test_nicegui_state_cache.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-snapshot-red
```

Expected: FAIL，提示 `coverage` 参数或完整性列不存在。

- [ ] **Step 3: 合并目录状态并扩大缓存签名**

```python
def build_index_trend_summary(
    parquet_store: ParquetStore,
    definitions: Sequence[IndexDefinition],
    *,
    coverage: pd.DataFrame | None = None,
    today: date | pd.Timestamp | None = None,
) -> pd.DataFrame:
    # 为每条定义读取 Parquet，随后按 index_code 左连接 coverage。
    # 只有 pool == "core"、完整历史、数据可用且趋势通过时 allows_new_position 才为 True。
```

`_index_health_snapshot_source_signature` must hash `index_code`, `pool`, `index_base_date`, Parquet file signatures and coverage update times. Cache schema version must increment so a prior 49-index snapshot cannot be reused. `index_health_summary` and `market_overview` must separately report core, research and incomplete-history counts.

- [ ] **Step 4: 运行指数快照与视图模型测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_health_snapshot.py tests\test_nicegui_state_cache.py tests\test_nicegui_view_models.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-snapshot-green
```

Expected: PASS。

- [ ] **Step 5: 提交目录驱动快照**

```powershell
git add src/etf_trading/nicegui_app/state.py src/etf_trading/research/index_health_snapshot.py src/etf_trading/nicegui_app/view_models.py tests/test_index_health_snapshot.py tests/test_nicegui_state_cache.py tests/test_nicegui_view_models.py
git commit -m "feat: expose catalog coverage in index snapshots"
```

## Task 7: 扩展持久化维护任务与数据维护页面

**Files:**
- Modify: `src/etf_trading/nicegui_app/maintenance_tasks.py`
- Modify: `src/etf_trading/nicegui_app/pages/maintenance.py`
- Modify: `src/etf_trading/nicegui_app/components/tables.py`
- Test: `tests/test_nicegui_maintenance_task_runner.py`
- Test: `tests/test_nicegui_maintenance_tasks.py`
- Test: `tests/test_nicegui_table_display.py`

**Interfaces:**
- Produces: 五类任务 `index_catalog_sync`、`index_source_validation`、`index_history_full`、`index_history_repair`、`index_history_incremental`；每类任务均可恢复查看。

- [ ] **Step 1: 写失败测试，任务类型、历史不完整摘要和中文状态都必须持久化**

```python
def test_catalog_validation_runner_persists_per_index_history_incomplete_result(monkeypatch, tmp_path):
    runner = IndexCatalogMaintenanceRunner(_store(tmp_path), ParquetStore(tmp_path / "parquet"), service_factory=_fake_service)
    task = runner.start("index_history_repair", through="2026-07-10")

    asyncio.run(_run_scheduled_task(monkeypatch, runner, task.task_id))

    persisted = runner.store.get_maintenance_task_run(task.task_id)
    assert persisted.state == "success"
    assert "INCOMPLETE" in persisted.result_json
    assert _task_status_from_run(persisted).message == "已检查 1 个指数：历史不完整 1"
```

- [ ] **Step 2: 运行测试，确认现有 runner 仅支持全量历史任务**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_maintenance_task_runner.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-maintenance-red
```

Expected: FAIL，提示 `IndexCatalogMaintenanceRunner` 或任务类型不支持。

- [ ] **Step 3: 实现多操作持久化 runner 与数据维护摘要**

```python
INDEX_MAINTENANCE_TASK_TYPES = {
    "index_catalog_sync": "同步指数目录",
    "index_source_validation": "验证指数数据源",
    "index_history_full": "补齐全部指数历史",
    "index_history_repair": "仅补历史不完整",
    "index_history_incremental": "仅更新最新行情",
}


class IndexCatalogMaintenanceRunner:
    def start(self, task_type: str, *, through: str) -> MaintenanceTaskRun:
        if task_type not in INDEX_MAINTENANCE_TASK_TYPES:
            raise ValueError(f"unsupported index maintenance task: {task_type}")
        # 同类运行任务去重，创建持久化 task，按 task_type 调用服务方法。
```

The maintenance page must render a catalog summary with formal/core/research/reserve counts and Chinese counts for `历史完整`、`历史不完整`、`行情仍滞后`、`历史缺失`、`读取失败`. Add five buttons corresponding exactly to the task type labels. Keep old single-index fetch action; it uses the selected catalog entry.

Add these display labels:

```python
VALUE_LABELS.update({
    "COMPLETE": "历史完整",
    "INCOMPLETE": "历史不完整",
    "SOURCE_LIMITED": "数据源历史不完整",
    "index_catalog_sync": "同步指数目录",
    "index_source_validation": "验证指数数据源",
    "index_history_repair": "仅补历史不完整",
    "index_history_incremental": "仅更新最新行情",
})
```

Every successful operation calls `invalidate_snapshot_cache(store, parquet_store)`.

- [ ] **Step 4: 运行维护任务和中文表格测试**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_maintenance_task_runner.py tests\test_nicegui_maintenance_tasks.py tests\test_nicegui_table_display.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-maintenance-green
```

Expected: PASS，刷新页面可恢复任一最新同类任务，且不显示内部状态码。

- [ ] **Step 5: 提交指数维护工作流**

```powershell
git add src/etf_trading/nicegui_app/maintenance_tasks.py src/etf_trading/nicegui_app/pages/maintenance.py src/etf_trading/nicegui_app/components/tables.py tests/test_nicegui_maintenance_task_runner.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_table_display.py
git commit -m "feat: add catalog index maintenance workflows"
```

## Task 8: 在市场与研究页面分层展示，并完成真实数据验收

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/market.py`
- Modify: `src/etf_trading/nicegui_app/pages/research.py`
- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Modify: `tests/test_nicegui_navigation.py`
- Modify: `tests/test_nicegui_view_models.py`
- Modify: `tests/test_nicegui_maintenance_tasks.py`

**Interfaces:**
- Consumes: `PlatformSnapshot.index_summary` 的 `pool` 和完整性列。
- Produces: 核心池默认视图、显式研究池切换、历史不完整提示和核心池研究回测选择器。

- [ ] **Step 1: 写失败测试，市场页默认核心池且研究页无法选择研究池**

```python
def test_index_choice_options_default_to_core_pool_and_can_include_research():
    frame = pd.DataFrame([
        {"index_code": "000300", "index_name": "沪深300", "pool": "core"},
        {"index_code": "801010", "index_name": "农林牧渔", "pool": "research"},
    ])

    assert index_choice_options(frame) == ["000300 沪深300"]
    assert index_choice_options(frame, include_research=True) == ["000300 沪深300", "801010 农林牧渔"]
```

- [ ] **Step 2: 运行测试，确认选项函数当前没有池边界**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_view_models.py tests\test_nicegui_navigation.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-pages-red
```

Expected: FAIL，研究池仍出现在默认选项或函数没有 `include_research` 参数。

- [ ] **Step 3: 实现页面池选择和完整性提示**

```python
def index_choice_options(index_summary: pd.DataFrame, *, include_research: bool = False) -> list[str]:
    frame = index_summary.copy()
    if "pool" in frame and not include_research:
        frame = frame[frame["pool"].eq("core")]
    return _choice_options_from_frame(frame)
```

In `market.py`, add a `ui.toggle({"core": "核心交易池", "research": "研究池"}, value="core")`; research-pool rows show `仅研究` and no `允许新开仓`. Add a compact column with `历史完整性` and a message from `history_completeness_message`. In `research.py`, call `index_choice_options(snapshot.index_summary)` without `include_research=True`; show a Chinese explanation when a selected index has no eligible ETF sample.

- [ ] **Step 4: 按顺序执行真实目录初始化和浏览器验收**

Run these operations only after unit tests pass, with the local server running and no page-load automation:

1. `数据维护 → 同步指数目录`，确认目录摘要显示 210 候选、180 正式、100 核心、80 研究、30 候补；
2. `验证指数数据源`，记录所有失败候选与端点错误；
3. `补齐全部指数历史`，从 1990 年起逐条运行至结束；
4. 重新打开页面，确认任务状态、历史完整性和数据源异常仍显示；
5. 检查市场地图默认核心池，切换研究池后不出现策略买卖入口；
6. 在 1440px 和 390px 视口检查没有英文状态、遮挡或横向溢出。

- [ ] **Step 5: 运行全量测试并提交页面分层**

Run:

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-universe-full-final
```

Expected: PASS。

```powershell
git add src/etf_trading/nicegui_app/pages/market.py src/etf_trading/nicegui_app/pages/research.py src/etf_trading/nicegui_app/view_models.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_nicegui_maintenance_tasks.py
git commit -m "feat: show core and research index pools"
```

## Plan Self-Review

- Spec coverage: Tasks 1–2 implement the versioned directory and persistent metadata; Tasks 3–4 implement all-history data validation; Task 5 enforces ETF and strategy boundaries; Tasks 6–8 implement snapshots, tasks, pages, Chinese statuses and live acceptance.
- Type consistency: `IndexCatalogEntry` is the source model; SQLite exposes DataFrames; `IndexDefinition` stays the compatibility view for existing classifiers and health snapshots; provider calls accept either model during migration.
- Scope: The plan does not redesign strategies, add markets, purchase data, or automatically trigger bulk downloads during page load.
- Placeholder scan: this plan contains no unfinished markers or unspecified implementation steps.
