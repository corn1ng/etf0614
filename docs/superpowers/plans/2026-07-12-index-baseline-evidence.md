# 指数历史起点证据核验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 批量联网核验正式指数的历史起点，优先写入官方基日，记录第三方参考起点，并把证据等级、历史完整性和最新行情可用性清晰展示在页面中。

**Architecture:** 版本化的 configs/index_baseline_evidence.yaml 作为每个指数的证据覆盖层；它覆盖主目录的基日与证据元数据，SQLite 保存同一投影。联网解析器先请求中证官方基础信息接口，再以聚宽公开指数列表的发布日期作为第三方参考起点；无法取得可信日期的指数保留未确认。历史完整性评估只将官方基日覆盖视为 COMPLETE，第三方参考独立为 BASELINE_REFERENCED；最新行情和短周期研究状态不受该等级影响。

**Tech Stack:** Python 3.11、requests、pandas、PyYAML、SQLite、Parquet、NiceGUI、pytest。

## Global Constraints

- 正式范围是当前 180 个 A 股和港股指数；不修改本地 Parquet 历史价格文件。
- 官方来源优先：中证指数官方接口 https://www.csindex.com.cn/csindex-home/indexInfo/index-basic-info/{code} 仅在返回 code 与请求代码一致且 basicDate 有效时写为官方证据。
- 第三方来源只使用聚宽公开指数列表 https://www.joinquant.com/data/dict/indexData；它提供 publish_date 时写为“参考起点（第三方：聚宽，发布日期）”，绝不伪装为官方基日。
- 申万与港股官方接口不可访问或无可核验基日时必须保留未确认，并在任务结果写明拒绝原因；不得用本地首日、发布日期或推测日期冒充官方基日。
- 只有官方基日覆盖本地首日的记录能成为 COMPLETE、进入长周期回测或新开仓；第三方参考和未确认记录仍可用于行情、趋势、原子指标和短周期研究。
- 所有用户可见文案为中文；第三方来源必须放在括号内，保留链接和检索日期。
- 证据覆盖 YAML、源代码、测试和文档可提交；SQLite、Parquet、日志、报告与临时测试目录不得提交。
- 不暂存用户已修改的 docs/superpowers/specs/2026-07-12-index-universe-expansion-design.md。
- 测试使用 H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe，并使用唯一的 C:\Users\cjj\AppData\Local\Temp\ basetemp。

---

## File Structure

| 文件 | 责任 |
| --- | --- |
| configs/index_baseline_evidence.yaml | 每个代码的基日/参考起点、证据等级、来源名、链接、检索日期和说明。 |
| src/etf_trading/data/baseline_evidence.py | 联网来源适配器、日期/身份校验、证据结果模型和覆盖 YAML 读写。 |
| src/etf_trading/data/index_catalog.py | 将证据覆盖层合并到主目录，并扩展目录条目的证据字段。 |
| src/etf_trading/data/indexes.py | 在 IndexDefinition 中保留证据元数据，供市场快照使用。 |
| src/etf_trading/data/storage.py | 为目录投影增加证据字段，并进行向后兼容 SQLite 列迁移。 |
| src/etf_trading/data/quality.py | 区分官方完整、第三方参考和起点未确认，保持行情新鲜度独立。 |
| src/etf_trading/data/initialization.py | 执行证据核验、写入覆盖 YAML、同步目录并重算既有历史覆盖。 |
| src/etf_trading/nicegui_app/maintenance_tasks.py | 新增可恢复的 index_baseline_evidence 维护任务。 |
| src/etf_trading/nicegui_app/pages/maintenance.py | 展示证据任务按钮、摘要、来源链接和拒绝原因。 |
| src/etf_trading/nicegui_app/state.py | 将证据字段合并入指数市场快照，保持行情可用性和新开仓准入分离。 |
| src/etf_trading/nicegui_app/components/tables.py | 提供“起点证据”“证据来源”“证据链接”“检索日期”等中文列名和值标签。 |
| scripts/verify_index_baselines.py | 支持命令行批量核验、写入覆盖 YAML、同步目录和输出可复核汇总。 |
| tests/test_baseline_evidence.py | 证据解析、优先级、拒绝规则和 YAML 覆盖读写。 |
| tests/test_index_catalog.py | 目录覆盖层、证据字段、SQLite 迁移和第三方来源校验。 |
| tests/test_storage_and_services.py | 证据核验后重算历史覆盖但不拉取价格的服务测试。 |
| tests/test_nicegui_maintenance_tasks.py | 新维护任务的持久化、进度和任务结果测试。 |
| tests/test_nicegui_table_display.py | 证据等级和链接列的中文显示测试。 |
| tests/test_nicegui_app_import.py | 市场快照中第三方/未确认起点与行情可用性分离测试。 |

## Task 1: 建立证据覆盖模型与目录/SQLite 投影

**Files:**
- Create: configs/index_baseline_evidence.yaml
- Modify: src/etf_trading/data/index_catalog.py
- Modify: src/etf_trading/data/indexes.py
- Modify: src/etf_trading/data/storage.py
- Test: tests/test_index_catalog.py
- Test: tests/test_storage_and_services.py

**Interfaces:**
- Produces: BaselineEvidence, load_baseline_evidence(path), apply_baseline_evidence(entries, evidence)。
- Extends: IndexCatalogEntry 与 IndexDefinition，新增 baseline_evidence_kind、baseline_evidence_name、baseline_evidence_url、baseline_checked_at。
- Preserves: index_code、pool、source_kind、既有基日和 YAML groups 格式。

- [ ] **Step 1: 写失败测试，固定三种证据等级和 SQLite 投影**

~~~python
def test_catalog_evidence_overlay_updates_only_named_index(tmp_path):
    overlay = tmp_path / "index_baseline_evidence.yaml"
    overlay.write_text(
        "evidence:\n"
        "  '000300':\n"
        "    reference_date: '2004-12-31'\n"
        "    source: official_api\n"
        "    kind: official_base_date\n"
        "    source_name: 中证指数官方基础信息\n"
        "    source_url: https://www.csindex.com.cn/csindex-home/indexInfo/index-basic-info/000300\n"
        "    checked_at: '2026-07-12'\n",
        encoding="utf-8",
    )

    entries = load_index_catalog(evidence_path=overlay)
    by_code = {entry.index_code: entry for entry in entries}

    assert by_code["000300"].index_base_date == date(2004, 12, 31)
    assert by_code["000300"].baseline_source == "official_api"
    assert by_code["000300"].baseline_evidence_kind == "official_base_date"
    assert by_code["000905"].baseline_source == "unverified"


def test_sqlite_catalog_round_trips_third_party_publication_evidence(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    entry = _catalog_entry(
        "000300",
        index_base_date=date(2005, 4, 8),
        baseline_source="third_party_publication",
        baseline_evidence_kind="publication_date",
        baseline_evidence_name="聚宽",
        baseline_evidence_url="https://www.joinquant.com/data/dict/indexData",
        baseline_checked_at=date(2026, 7, 12),
    )

    store.initialize_schema()
    store.upsert_index_catalog([entry])

    row = store.list_index_catalog(include_reserve=True).iloc[0]
    assert row["baseline_evidence_kind"] == "publication_date"
    assert row["baseline_evidence_name"] == "聚宽"
~~~

- [ ] **Step 2: 运行测试，确认覆盖层和证据列尚不存在**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_catalog.py tests\test_storage_and_services.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-model-red
~~~

Expected: FAIL，提示 evidence_path、证据字段或 SQLite 列不存在。

- [ ] **Step 3: 实现覆盖层、证据字段和可迁移 SQLite 投影**

创建覆盖文件：

~~~yaml
evidence: {}
~~~

在 index_catalog.py 中定义：

~~~python
BaselineSource = Literal[
    "official_methodology",
    "official_factsheet",
    "official_api",
    "third_party_reference",
    "third_party_publication",
    "unverified",
]
BaselineEvidenceKind = Literal["official_base_date", "third_party_base_date", "publication_date", "unresolved"]


@dataclass(frozen=True)
class BaselineEvidence:
    index_code: str
    reference_date: date | None
    source: BaselineSource
    kind: BaselineEvidenceKind
    source_name: str
    source_url: str
    checked_at: date | None
    detail: str = ""
~~~

load_index_catalog 默认读取主目录与 configs/index_baseline_evidence.yaml；证据条目只覆盖同代码的 index_base_date、baseline_source 及证据字段。若 source 不是 unverified，reference_date 必须存在；publication_date 只能搭配 third_party_publication；official_base_date 只能搭配 official_*。

在 storage.py 的 initialize_schema 后使用 PRAGMA table_info(index_catalog)，为既有数据库逐个执行：

~~~sql
ALTER TABLE index_catalog ADD COLUMN baseline_evidence_kind TEXT NOT NULL DEFAULT 'unresolved';
ALTER TABLE index_catalog ADD COLUMN baseline_evidence_name TEXT NOT NULL DEFAULT '';
ALTER TABLE index_catalog ADD COLUMN baseline_evidence_url TEXT NOT NULL DEFAULT '';
ALTER TABLE index_catalog ADD COLUMN baseline_checked_at TEXT;
~~~

新建表定义也必须包含同四列；upsert_index_catalog 与 catalog_entries_from_frame 全量读写它们。IndexDefinition 将四个字段追加在现有尾部并设置安全默认值，避免现有位置参数构造失效。

- [ ] **Step 4: 运行模型、目录和存储测试**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_catalog.py tests\test_storage_and_services.py tests\test_index_support.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-model-green
~~~

Expected: PASS，旧目录仍能加载，证据覆盖层只影响明确代码，旧 SQLite 可迁移并返回完整列。

- [ ] **Step 5: 提交目录证据模型**

~~~powershell
git add configs/index_baseline_evidence.yaml src/etf_trading/data/index_catalog.py src/etf_trading/data/indexes.py src/etf_trading/data/storage.py tests/test_index_catalog.py tests/test_storage_and_services.py
git commit -m "feat: persist index baseline evidence"
~~~

## Task 2: 联网解析官方与第三方起点证据

**Files:**
- Create: src/etf_trading/data/baseline_evidence.py
- Create: tests/test_baseline_evidence.py

**Interfaces:**
- Produces: BaselineEvidenceResolver.collect(entries, as_of) -> pandas.DataFrame。
- Consumes: Sequence[IndexCatalogEntry] 与可注入 HTTP getter。
- Result columns: index_code, evidence_status, reference_date, baseline_source, baseline_evidence_kind, baseline_evidence_name, baseline_evidence_url, checked_at, detail。

- [ ] **Step 1: 写失败测试，锁定官方优先、身份校验和第三方发布日期**

~~~python
def test_resolver_prefers_matching_csindex_basic_date_over_third_party_publication():
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get({
            "https://www.csindex.com.cn/csindex-home/indexInfo/index-basic-info/000300":
                {"code": "200", "data": {"indexCode": "000300", "basicDate": "2004-12-31"}},
        }),
        third_party_index_list=pd.DataFrame(
            [{"index_code": "000300", "display_name": "沪深300", "publish_date": "2005-04-08"}],
        ),
    )

    result = resolver.collect([_entry("000300", "沪深300", source_kind="csi")], as_of=date(2026, 7, 12))

    row = result.iloc[0]
    assert row["evidence_status"] == "OFFICIAL"
    assert row["reference_date"] == "2004-12-31"
    assert row["baseline_source"] == "official_api"


def test_resolver_records_joinquant_publication_only_when_official_api_has_no_basic_date():
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get({}),
        third_party_index_list=pd.DataFrame(
            [{"index_code": "000905", "display_name": "中证500", "publish_date": "2007-01-15"}],
        ),
    )

    result = resolver.collect([_entry("000905", "中证500", source_kind="csi")], as_of=date(2026, 7, 12))

    row = result.iloc[0]
    assert row["evidence_status"] == "THIRD_PARTY_PUBLICATION"
    assert row["baseline_evidence_kind"] == "publication_date"
    assert row["detail"] == "第三方仅提供发布日期，不能视为官方基日"


def test_resolver_rejects_csindex_response_with_another_index_code():
    resolver = BaselineEvidenceResolver(
        http_get=_fake_http_get({
            "https://www.csindex.com.cn/csindex-home/indexInfo/index-basic-info/000300":
                {"code": "200", "data": {"indexCode": "000905", "basicDate": "2004-12-31"}},
        }),
        third_party_index_list=pd.DataFrame(),
    )

    row = resolver.collect([_entry("000300", "沪深300", source_kind="csi")], as_of=date(2026, 7, 12).iloc[0]

    assert row["evidence_status"] == "UNRESOLVED"
    assert "代码不一致" in row["detail"]
~~~

- [ ] **Step 2: 运行解析测试，确认解析器不存在**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_baseline_evidence.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-resolver-red
~~~

Expected: FAIL，提示 BaselineEvidenceResolver 不存在。

- [ ] **Step 3: 实现来源优先级、拒绝规则和覆盖文件写入**

~~~python
CSINDEX_BASIC_INFO_URL = "https://www.csindex.com.cn/csindex-home/indexInfo/index-basic-info/{index_code}"
JOINQUANT_INDEX_LIST_URL = "https://www.joinquant.com/data/dict/indexData"


class BaselineEvidenceResolver:
    def collect(self, entries: Sequence[IndexCatalogEntry], as_of: date) -> pd.DataFrame:
        third_party = self._third_party_index_list()
        rows = [self._collect_one(entry, third_party, as_of) for entry in entries]
        return pd.DataFrame(rows)

    def _collect_one(self, entry, third_party, as_of):
        official = self._csindex_evidence(entry, as_of)
        if official is not None:
            return official
        publication = self._joinquant_publication_evidence(entry, third_party, as_of)
        return publication or _unresolved_evidence(entry, as_of, "未取得可核验的官方基日或第三方发布日期")
~~~

官方请求只对 source_kind 为 csi 或 index_code 以 H 开头的目录条目尝试；请求异常、非 200 业务码、空 basicDate、无效日期、代码不一致都写为拒绝细节，不抛出并终止批量。第三方列表读取 index_code、display_name、publish_date；代码相同且名称与目录名称或别名规范化匹配时才接受，来源名固定“聚宽”，来源链接固定 JOINQUANT_INDEX_LIST_URL。

实现 write_baseline_evidence(path, frame)：只将 OFFICIAL、THIRD_PARTY_BASE_DATE、THIRD_PARTY_PUBLICATION 结果写入 evidence 映射；UNRESOLVED 不覆盖旧的官方记录。YAML 输出按 index_code 排序，日期为 ISO 格式，保留 detail。

- [ ] **Step 4: 运行解析测试和网络隔离回归**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_baseline_evidence.py tests\test_index_catalog.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-resolver-green
~~~

Expected: PASS；测试完全使用注入响应，不产生真实网络调用。

- [ ] **Step 5: 提交证据解析器**

~~~powershell
git add src/etf_trading/data/baseline_evidence.py tests/test_baseline_evidence.py
git commit -m "feat: collect index baseline evidence"
~~~

## Task 3: 将证据等级接入完整性重算和持久化维护任务

**Files:**
- Modify: src/etf_trading/data/quality.py
- Modify: src/etf_trading/data/initialization.py
- Modify: src/etf_trading/nicegui_app/maintenance_tasks.py
- Modify: tests/test_storage_and_services.py
- Modify: tests/test_nicegui_maintenance_task_runner.py
- Modify: tests/test_nicegui_maintenance_tasks.py

**Interfaces:**
- Produces: InitializationService.verify_index_baseline_evidence(through, write_evidence=True) -> pandas.DataFrame。
- Adds: index_baseline_evidence to INDEX_MAINTENANCE_TASK_TYPES。
- Preserves: index_history_full、index_history_repair、index_history_incremental 和价格历史下载行为。

- [ ] **Step 1: 写失败测试，区分官方完整、第三方参考和起点未确认**

~~~python
def test_assess_history_marks_third_party_reference_without_claiming_complete():
    assessment = assess_index_history_completeness(
        _prices("000300", start="2004-12-31", end="2026-07-10"),
        "2004-12-31",
        baseline_source="third_party_publication",
        evidence_name="聚宽",
        evidence_kind="publication_date",
    )

    assert assessment.status == "BASELINE_REFERENCED"
    assert assessment.message == "参考起点 2004-12-31（第三方：聚宽，发布日期）；不用于长周期回测或新开仓。"


def test_verify_baseline_evidence_recomputes_existing_coverage_without_fetching_prices(tmp_path):
    service, store = _service_with_catalog_and_cached_index_prices(tmp_path, "000300")
    service.evidence_resolver = _FakeEvidenceResolver(_official_evidence("000300", "2004-12-31"))

    result = service.verify_index_baseline_evidence("2026-07-10")

    assert result.iloc[0]["evidence_status"] == "OFFICIAL"
    assert store.list_index_history_coverage().iloc[0]["completeness_status"] == "COMPLETE"
    assert service.provider.index_calls == []
~~~

- [ ] **Step 2: 运行服务测试，确认第三方证据尚被误判为完整**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py tests\test_nicegui_maintenance_task_runner.py tests\test_nicegui_maintenance_tasks.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-maintenance-red
~~~

Expected: FAIL，提示 BASELINE_REFERENCED 或 verify_index_baseline_evidence 不存在。

- [ ] **Step 3: 实现完整性规则与可恢复维护任务**

在 quality.py 中增加官方来源判定：

~~~python
_OFFICIAL_BASELINE_SOURCES = frozenset({"official_methodology", "official_factsheet", "official_api"})


def has_official_baseline(source: str, base_date: object) -> bool:
    return source in _OFFICIAL_BASELINE_SOURCES and _parse_date(base_date) is not None
~~~

assess_index_history_completeness 仅在 has_official_baseline 为真时返回 COMPLETE 或 INCOMPLETE。third_party_reference 与 third_party_publication 均返回 BASELINE_REFERENCED，文案根据 evidence_kind 使用“参考基日”或“参考起点（第三方：聚宽，发布日期）”；unverified 继续返回 BASELINE_UNVERIFIED。

在 InitializationService 中执行以下顺序：

~~~python
def verify_index_baseline_evidence(self, through: date | str, *, write_evidence: bool = True) -> pd.DataFrame:
    entries = self._formal_catalog_entries()
    evidence = self.evidence_resolver.collect(entries, pd.Timestamp(through).date())
    if write_evidence:
        write_baseline_evidence(DEFAULT_INDEX_BASELINE_EVIDENCE_PATH, evidence)
    self.sync_index_catalog()
    refreshed = self._formal_catalog_entries()
    return self._recompute_index_history_coverage(refreshed, evidence)
~~~

_recompute_index_history_coverage 只读取 read_index_prices，调用 _persist_index_history_coverage，并把 evidence 的状态、来源、链接和拒绝原因合并到结果行；不得调用 fetch_index_daily。maintenance task runner 为 index_baseline_evidence 复用既有持久化进度、结果 JSON 和快照失效逻辑。

- [ ] **Step 4: 运行服务、维护任务和完整性回归**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py tests\test_index_support.py tests\test_nicegui_maintenance_task_runner.py tests\test_nicegui_maintenance_tasks.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-maintenance-green
~~~

Expected: PASS；第三方日期不进入 COMPLETE，维护任务不发起价格下载。

- [ ] **Step 5: 提交证据维护任务**

~~~powershell
git add src/etf_trading/data/quality.py src/etf_trading/data/initialization.py src/etf_trading/nicegui_app/maintenance_tasks.py tests/test_storage_and_services.py tests/test_nicegui_maintenance_task_runner.py tests/test_nicegui_maintenance_tasks.py
git commit -m "feat: verify index baseline evidence"
~~~

## Task 4: 在数据维护与市场参考显示证据等级

**Files:**
- Modify: src/etf_trading/nicegui_app/components/tables.py
- Modify: src/etf_trading/nicegui_app/pages/maintenance.py
- Modify: src/etf_trading/nicegui_app/state.py
- Modify: src/etf_trading/nicegui_app/view_models.py
- Modify: tests/test_nicegui_table_display.py
- Modify: tests/test_nicegui_app_import.py
- Modify: tests/test_nicegui_view_models.py

**Interfaces:**
- Produces: 起点证据、证据来源、证据链接、检索日期和证据说明的中文表格字段。
- Preserves: data_status、data_status_message、history_completeness_status 与 allows_new_position 的独立含义。

- [ ] **Step 1: 写失败测试，锁定行情可用与第三方起点并存**

~~~python
def test_market_snapshot_keeps_ready_quotes_for_third_party_baseline_reference(tmp_path):
    definition = IndexDefinition(
        "000300", "沪深300", "A股", "A股宽基", "000300",
        index_base_date=date(2005, 4, 8),
        baseline_source="third_party_publication",
        baseline_evidence_kind="publication_date",
        baseline_evidence_name="聚宽",
    )
    summary = build_index_trend_summary(
        _parquet_with_last_date(tmp_path, "000300", "2026-07-10"),
        definitions=(definition,),
        today="2026-07-10",
    )

    row = summary.iloc[0]
    assert row["data_status"] == "数据可用"
    assert row["history_completeness_status"] == "BASELINE_REFERENCED"
    assert row["history_completeness_message"] == "参考起点 2005-04-08（第三方：聚宽，发布日期）；不用于长周期回测或新开仓。"
    assert bool(row["allows_new_position"]) is False


def test_table_rows_translate_baseline_reference_to_chinese():
    display = table_rows([{"history_completeness_status": "BASELINE_REFERENCED"}])

    assert display[0]["history_completeness_status"] == "第三方参考起点"
~~~

- [ ] **Step 2: 运行页面测试，确认新证据字段和标签未展示**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_table_display.py tests\test_nicegui_app_import.py tests\test_nicegui_view_models.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-ui-red
~~~

Expected: FAIL，提示 BASELINE_REFERENCED 或证据字段不存在。

- [ ] **Step 3: 实现中文展示、任务摘要和市场快照字段**

在 tables.py 添加字段标签：

~~~python
COLUMN_LABELS.update({
    "baseline_evidence_kind": "起点证据",
    "baseline_evidence_name": "证据来源",
    "baseline_evidence_url": "证据链接",
    "baseline_checked_at": "检索日期",
    "evidence_status": "核验结果",
})
VALUE_LABELS["BASELINE_REFERENCED"] = "第三方参考起点"
VALUE_LABELS["OFFICIAL"] = "官方已核验"
VALUE_LABELS["THIRD_PARTY_PUBLICATION"] = "第三方参考起点"
VALUE_LABELS["UNRESOLVED"] = "起点无法确认"
~~~

在 maintenance.py 添加 index_baseline_evidence 的中文标题“核验指数起点证据”，摘要固定为“已核验 N，第三方参考 N，仍未确认 N，拒绝 N”。在 market snapshot 行保留目录证据字段；view_models 将 BASELINE_REFERENCED 与 BASELINE_UNVERIFIED 计入非官方完整起点，且不得把 data_status 从“数据可用”改为不可用。证据链接作为 table 行的可点击外链或可复制完整 URL，不隐藏第三方来源。

- [ ] **Step 4: 运行 UI 与维护页回归**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_table_display.py tests\test_nicegui_app_import.py tests\test_nicegui_view_models.py tests\test_nicegui_maintenance_tasks.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-ui-green
~~~

Expected: PASS；第三方参考记录同时显示“数据可用”和“第三方参考起点”，新开仓仍为否。

- [ ] **Step 5: 提交页面证据展示**

~~~powershell
git add src/etf_trading/nicegui_app/components/tables.py src/etf_trading/nicegui_app/pages/maintenance.py src/etf_trading/nicegui_app/state.py src/etf_trading/nicegui_app/view_models.py tests/test_nicegui_table_display.py tests/test_nicegui_app_import.py tests/test_nicegui_view_models.py
git commit -m "feat: show index baseline evidence"
~~~

## Task 5: 执行一次真实核验、审查结果并完成验证

**Files:**
- Create or Modify: configs/index_baseline_evidence.yaml
- Create: scripts/verify_index_baselines.py
- Modify: docs/task-memory.md

**Interfaces:**
- Command: python scripts/verify_index_baselines.py --through 2026-07-10 --write-evidence。
- Produces: 逐指数证据结果、更新后的覆盖 YAML、SQLite 目录投影和维护任务可见结果。

- [ ] **Step 1: 写命令行集成测试，确保真实网络调用可以替换为固定解析器**

~~~python
def test_verify_index_baselines_cli_writes_only_verified_or_reference_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "etf_trading.data.baseline_evidence.BaselineEvidenceResolver.collect",
        lambda self, entries, as_of: pd.DataFrame([
            _official_row("000300", "2004-12-31"),
            _unresolved_row("801010", "申万官方站点不可访问"),
        ]),
    )

    exit_code = main([
        "--through", "2026-07-10",
        "--evidence-path", str(tmp_path / "evidence.yaml"),
        "--formal",
    ])

    saved = yaml.safe_load((tmp_path / "evidence.yaml").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "000300" in saved["evidence"]
    assert "801010" not in saved["evidence"]
~~~

- [ ] **Step 2: 运行命令行测试，确认入口尚不存在**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_baseline_evidence.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-cli-red
~~~

Expected: FAIL，提示 scripts.verify_index_baselines.main 不存在。

- [ ] **Step 3: 实现命令行入口并执行真实批量核验**

命令行入口必须：
- 只选择 pool 为 core 或 research 的目录条目；
- 输出 OFFICIAL、THIRD_PARTY_PUBLICATION、UNRESOLVED 三类计数和逐代码结果；
- write-evidence 时只写可信官方或明确第三方参考；
- exit code 为 0，除非配置/YAML 写入失败；单条网络失败是 UNRESOLVED，不中断批次。

执行：

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' scripts\verify_index_baselines.py --through 2026-07-10 --write-evidence --formal
~~~

Expected: 每条正式指数都有一行结果；中证官方接口返回 basicDate 的记录为 OFFICIAL；聚宽仅返回 publish_date 的记录为 THIRD_PARTY_PUBLICATION；无可信日期的记录为 UNRESOLVED。

审查 configs/index_baseline_evidence.yaml：每条 official_api 记录的 source_url 必须为对应中证接口，reference_date 必须为 ISO 日期；每条 third_party_publication 记录必须包含“聚宽”与“发布日期”语义。

- [ ] **Step 4: 运行完整测试、同步本地目录并验证页面数据**

Run:

~~~powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-full
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' scripts\verify_index_baselines.py --through 2026-07-10 --write-evidence --formal
~~~

Expected: PASS；市场参考和数据维护重启后显示官方、第三方和未确认三类证据；官方完整性重算不产生新的指数价格下载。

- [ ] **Step 5: 检查提交范围、记录工作记忆并提交**

Run:

~~~powershell
git status --short
rg -n "TODO|FIXME|XXX|HACK" src/etf_trading/data/baseline_evidence.py src/etf_trading/data/index_catalog.py src/etf_trading/data/storage.py src/etf_trading/data/quality.py src/etf_trading/data/initialization.py src/etf_trading/nicegui_app/maintenance_tasks.py src/etf_trading/nicegui_app/pages/maintenance.py src/etf_trading/nicegui_app/state.py
~~~

Expected: 只暂存本计划列出的代码、测试、覆盖 YAML 与 docs/task-memory.md；无生成 SQLite、Parquet、日志、报告、临时目录或用户未提交设计文档。

向 docs/task-memory.md 追加来源限制、真实核验命令及结果计数，然后提交：

~~~powershell
git add configs/index_baseline_evidence.yaml scripts/verify_index_baselines.py tests/test_baseline_evidence.py docs/task-memory.md
git commit -m "feat: refresh index baseline evidence"
~~~

