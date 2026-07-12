# 数据可信层实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**目标：** 建立统一的数据就绪评估，使用中文状态展示，并让不可靠的 ETF 数据无法进入机会排名。

**架构：** 新增 etf_trading.data.quality，负责交易日、历史状态、缺失交易日和问题原因。ETF 总览、维护缺口、原子指标、缓存和 NiceGUI 视图模型只消费这一个评估结果；页面通过全局摘要、数据体检页和就地提示三层展示数据状态。

**技术栈：** Python 3.11、pandas、SQLite、Parquet、NiceGUI、pytest。

## 全局约束

- 所有用户可见状态、筛选项、表头和通知使用中文；内部代码可保留稳定英文状态码。
- 不增加外部依赖，不自动拉取外部数据，不迁移 SQLite schema。
- 不修改策略公式、评分或买卖建议。
- 机会列表只显示 is_rank_eligible=True 的 ETF；体检列表可显示全部 ETF。
- 页面快照时间只能标为“页面计算”或“快照生成”。
- 每个生产行为必须先有失败测试。

---

### 任务 1：新增统一历史数据评估模块

**文件：**

- 新建：src/etf_trading/data/quality.py
- 新建：tests/test_data_quality.py

**接口：**

- 产出：HistoryReadiness、HistoryAssessment、expected_latest_trade_date、trading_day_lag、assess_price_history、history_readiness_label。
- 消费者：任务 2 的原子指标构建器和任务 3 的覆盖构建器。

- [ ] **步骤 1：写失败测试**

    def test_assessment_keeps_stale_as_primary_and_short_history_as_reason():
        prices = pd.DataFrame({"trade_date": pd.bdate_range("2026-06-01", periods=40)})
        result = assess_price_history(prices, pd.Timestamp("2026-07-10"), 252)
        assert result.readiness is HistoryReadiness.STALE
        assert result.reason_codes == ("stale", "short_history")
        assert result.trading_day_lag > 0

    def test_expected_latest_trade_date_skips_weekends_and_explicit_holidays():
        holidays = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"]
        assert expected_latest_trade_date("2026-07-05") == pd.Timestamp("2026-07-03")
        assert expected_latest_trade_date("2026-10-08", holidays) == pd.Timestamp("2026-09-30")

    def test_history_readiness_label_is_chinese():
        assert history_readiness_label(HistoryReadiness.READY) == "数据可用"
        assert history_readiness_label(HistoryReadiness.READ_FAILED) == "读取失败"

- [ ] **步骤 2：运行测试，确认失败**

运行：python -m pytest tests/test_data_quality.py -q

预期：因 etf_trading.data.quality 尚不存在而失败。

- [ ] **步骤 3：最小实现**

    class HistoryReadiness(StrEnum):
        READY = "ready"
        STALE = "stale"
        SHORT_HISTORY = "short_history"
        MISSING_HISTORY = "missing_history"
        READ_FAILED = "read_failed"

    @dataclass(frozen=True)
    class HistoryAssessment:
        readiness: HistoryReadiness
        latest_trade_date: str
        expected_trade_date: str
        history_rows: int
        trading_day_lag: int | None
        reason_codes: tuple[str, ...]

assess_price_history 按“读取失败、历史缺失、行情滞后、历史不足、数据可用”的优先级产生主状态，并保留全部原因；标签函数返回固定中文文本。

- [ ] **步骤 4：运行模块测试，确认通过**

运行：python -m pytest tests/test_data_quality.py -q

预期：全部通过。

- [ ] **步骤 5：提交**

    git add src/etf_trading/data/quality.py tests/test_data_quality.py
    git commit -m "feat: add market data readiness assessment"

### 任务 2：让原子指标只为可信数据生成机会排名

**文件：**

- 修改：src/etf_trading/research/atomic_indicators.py
- 修改：src/etf_trading/nicegui_app/state.py
- 修改：tests/test_atomic_indicators.py
- 修改：tests/test_nicegui_state_cache.py

**接口：**

- 消费：任务 1 的 HistoryAssessment。
- 产出：原子快照新增 expected_trade_date、trading_day_lag、history_reason_codes、is_rank_eligible。
- 消费者：任务 4 的视图模型和 ETF 页面。

- [ ] **步骤 1：写失败测试**

    def test_stale_etf_keeps_diagnostic_values_but_has_no_opportunity_rank():
        frame = build_etf_atomic_indicator_snapshot(master, store, today=pd.Timestamp("2026-07-10"))
        stale = frame.loc[frame["etf_code"] == "510300"].iloc[0]
        assert stale["history_status"] == "stale"
        assert stale["is_rank_eligible"] is False
        assert pd.isna(stale["return_20_rank_all"])
        assert pd.notna(stale["return_20"])

    def test_ready_feature_complete_etf_is_ranked():
        ready = frame.loc[frame["etf_code"] == "512880"].iloc[0]
        assert ready["is_rank_eligible"] is True
        assert ready["return_20_rank_all"] == 1

- [ ] **步骤 2：运行测试，确认失败**

运行：python -m pytest tests/test_atomic_indicators.py -q

预期：现有实现仍给滞后 ETF 计算排名。

- [ ] **步骤 3：最小实现**

用任务 1 的评估替换本地历史判断，将四个评估字段加入 ATOMIC_INDICATOR_COLUMNS。只有 is_rank_eligible 为真的行参与全池和分类收益排名；不合格行的排名字段为 pd.NA，但诊断数值仍保留。将 ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION 加一，拒绝缺少新增列的旧快照。

- [ ] **步骤 4：运行原子指标与缓存测试**

运行：python -m pytest tests/test_atomic_indicators.py tests/test_nicegui_state_cache.py -q

预期：全部通过。

- [ ] **步骤 5：提交**

    git add src/etf_trading/research/atomic_indicators.py src/etf_trading/nicegui_app/state.py tests/test_atomic_indicators.py tests/test_nicegui_state_cache.py
    git commit -m "feat: gate atomic rankings by data readiness"

### 任务 3：统一 ETF/指数覆盖与维护缺口

**文件：**

- 修改：src/etf_trading/ui/data_coverage.py
- 修改：src/etf_trading/nicegui_app/state.py
- 修改：tests/test_data_coverage.py
- 修改：tests/test_nicegui_app_import.py

**接口：**

- 消费：任务 1 的评估和中文状态映射。
- 产出：ETF 总览的中文本地历史状态、维护缺口与指数趋势摘要中的状态、有效日期和缺失交易日。
- 消费者：任务 4 的顶部栏和数据体检页。

- [ ] **步骤 1：写失败测试**

    def test_etf_overview_and_gap_detail_report_same_status():
        overview = build_etf_data_overview(master, watchlist, store, universe, today=pd.Timestamp("2026-07-10"))
        gaps = build_data_gap_detail(master, watchlist, indexes, universe, store, today=pd.Timestamp("2026-07-10"))
        assert overview.loc[overview["ETF代码"] == "510300", "本地历史"].item() == "行情滞后"
        assert gaps.loc[(gaps["数据类型"] == "ETF历史") & (gaps["代码"] == "510300"), "状态"].item() == "行情滞后"

    def test_index_summary_exposes_data_status_and_lag():
        summary = build_index_trend_summary(store, definitions=(definition,))
        assert summary.loc[0, "data_status"] == "行情滞后"
        assert summary.loc[0, "trading_day_lag"] > 0

- [ ] **步骤 2：运行测试，确认失败**

运行：python -m pytest tests/test_data_coverage.py tests/test_nicegui_app_import.py -q

预期：新参数或状态字段尚不存在而失败。

- [ ] **步骤 3：最小实现**

build_etf_data_overview 接受可选 today 和 holidays，以统一评估填入中文“本地历史”、应有日期和缺失交易日。维护缺口直接消费同一评估，不能自行定义状态优先级。指数趋势摘要加入 data_status、expected_trade_date、trading_day_lag。

- [ ] **步骤 4：运行覆盖和应用导入测试**

运行：python -m pytest tests/test_data_coverage.py tests/test_nicegui_app_import.py -q

预期：全部通过。

- [ ] **步骤 5：提交**

    git add src/etf_trading/ui/data_coverage.py src/etf_trading/nicegui_app/state.py tests/test_data_coverage.py tests/test_nicegui_app_import.py
    git commit -m "feat: unify data readiness in coverage views"

### 任务 4：接入中文健康摘要、全局状态与就地提示

**文件：**

- 修改：src/etf_trading/nicegui_app/view_models.py
- 修改：src/etf_trading/nicegui_app/layout.py
- 修改：src/etf_trading/nicegui_app/pages/etf_data.py
- 修改：src/etf_trading/nicegui_app/pages/maintenance.py
- 修改：src/etf_trading/nicegui_app/pages/market.py
- 修改：tests/test_nicegui_view_models.py
- 修改：tests/test_nicegui_maintenance_tasks.py
- 修改：tests/test_nicegui_navigation.py

**接口：**

- 消费：任务 2 的 is_rank_eligible 与任务 3 的中文数据状态字段。
- 产出：atomic_data_health_summary、platform_data_status_summary 和准确的机会/体检筛选。

- [ ] **步骤 1：写失败测试**

    def test_atomic_health_summary_counts_unique_assets():
        summary = atomic_data_health_summary(frame)
        assert summary.total == 5
        assert summary.issue_count == 4
        assert summary.primary_status_counts["行情滞后"] == 1

    def test_opportunity_rows_exclude_non_rank_eligible_but_health_rows_keep_them():
        assert [row["ETF代码"] for row in atomic_indicator_rows(frame, view_mode="机会特征")] == ["510300"]
        assert len(atomic_indicator_rows(frame, view_mode="体检特征")) == 2

    def test_platform_status_separates_snapshot_time_and_source_date():
        summary = platform_data_status_summary(snapshot)
        assert summary.etf_label == "ETF：1/2 数据可用"
        assert summary.latest_trade_date == "2026-07-03"
        assert summary.generated_label == "页面计算 2026-07-05 10:00"

- [ ] **步骤 2：运行测试，确认失败**

运行：python -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_navigation.py -q

预期：当前页面仍累加重叠问题，并在机会表中展示未就绪 ETF。

- [ ] **步骤 3：最小实现**

atomic_data_health_summary 使用主状态计算唯一问题数；原因标签只用于明细。机会视图固定过滤 is_rank_eligible=True，体检视图不过滤。移除原子表格和详情选项中的 300 行硬上限，让 NiceGUI 分页处理完整筛选集。

顶部栏显示“ETF：可用/总数”和源行情最新有效日期，并把 generated_at 标为“页面计算”。数据维护首个页签改为“数据体检”；ETF 与市场页面在数据不可靠时显示中文提示和“前往数据体检”链接。

- [ ] **步骤 4：运行视图模型和页面测试**

运行：python -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_navigation.py -q

预期：全部通过。

- [ ] **步骤 5：提交**

    git add src/etf_trading/nicegui_app/view_models.py src/etf_trading/nicegui_app/layout.py src/etf_trading/nicegui_app/pages/etf_data.py src/etf_trading/nicegui_app/pages/maintenance.py src/etf_trading/nicegui_app/pages/market.py tests/test_nicegui_view_models.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_navigation.py
    git commit -m "feat: surface trusted data status in workbench"

### 任务 5：完整验证与运行记录

**文件：**

- 修改：docs/task-memory.md

- [ ] **步骤 1：运行完整测试**

运行：python -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-data-trust-final

预期：全部通过。

- [ ] **步骤 2：运行 NiceGUI 冒烟检查**

启动：python -c "from etf_trading.nicegui_app.main import run; run(port=8511)"

检查桌面和 390px 视口的“ETF数据 → 原子指标”“市场地图 → 指数体检”“数据维护 → 数据体检”：顶部应区分页面计算与行情有效日期，机会表不含未就绪 ETF，体检表可筛选全部中文状态，控制台没有应用错误。

- [ ] **步骤 3：记录任务记忆并提交**

在 docs/task-memory.md 追加中文条目，记录统一评估入口、验证命令和三条提醒：状态代码/中文标签分离；机会排名必须依赖 is_rank_eligible；数据体检页是权威来源。

    git add docs/task-memory.md
    git commit -m "docs: record data trust layer verification"
