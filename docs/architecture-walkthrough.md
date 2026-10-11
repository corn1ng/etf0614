# etf0614 项目架构梳理

面向对象：接手/复核本项目的开发者。本文件描述**代码实际行为**，不是设计意图。
每条结论标注来源（`path:line`），实测数据标注为"实测"。

仓库根：`H:\pythonproject\etf0614\etf0614`（外层 `H:\pythonproject\etf0614` 只是父目录）
当前 HEAD：`f98eed9 Merge branch 'feature/unified-index-profile'`

---

## 0. 一句话概述

本地运行的 **A 股 ETF 交易指引 + 回测研究工作台**，无自动下单。链路是：

```
数据抓取(Tushare→AkShare 回退) → SQLite 元数据 + Parquet 行情
  → 技术指标 → ETF 趋势策略 / 指数趋势 V1 策略
  → 回测(T 日信号、T+1 开盘成交) → 有效性闸门 → 报告与 UI
```

规模（实测）：156 个 `.py`，约 2.8 万行；SQLite 12 张表；Parquet 431 MB / 1719 文件。

---

## 1. 运行入口

| 命令 | 作用 | 地址 |
|---|---|---|
| `python scripts/run_nicegui.py` | **主 UI**（NiceGUI） | `127.0.0.1:8502` |
| `python -m streamlit run app.py` | 回退 UI（Streamlit） | `127.0.0.1:8501` |
| `python scripts/update_data.py` | 初始化 ETF 主表 + 补 watchlist 历史 | — |
| `python scripts/run_research.py --limit 20` | ETF 级候选策略研究 | — |
| `python scripts/run_index_research.py` | 指数趋势 V1 全量回测并发布证据包 | — |

- NiceGUI 路由：`/`、`/page/{page_slug}`、`/page/{page_slug}/{section}`（`nicegui_app/main.py:18-28`），`reconnect_timeout=60s`。
- Streamlit 端口在 `scripts/run_streamlit_server.py:22` 写死为 8501。

---

## 2. 数据层（`src/etf_trading/data`）

### 2.1 Provider 契约

`DataProvider(ABC)`（`data/provider.py:17`）。契约核心：**Provider 必须先把列名规范化**，策略/存储/图表不感知供应商差异（`provider.py:20-22`）。

| 方法 | 返回关键列 |
|---|---|
| `fetch_etf_list()` | `etf_code, name, exchange, category, tracking_index, fund_company, listing_date, is_active, tradability_status, data_source` |
| `fetch_etf_daily(code, start, end, adjust="qfq")` | `etf_code, trade_date, open, high, low, close, volume, amount, data_source`；空结果返回**固定 9 列**空表 |
| `fetch_etf_nav(...)` | `etf_code, trade_date, unit_nav, accumulated_nav, iopv, premium_rate`；**AkShare 恒返回空表**（`akshare_provider.py:74-77`） |
| `fetch_index_daily(...)` | `index_code, trade_date, open, high, low, close, volume, amount, data_source` |
| `fetch_index_official_valuations(...)` | 基类抛 `ProviderCapabilityError`（`provider.py:51-57`） |
| `fetch_trade_calendar(market, start, end)` | `market, trade_date, is_open` |

### 2.2 路由与回退语义

- 唯一构造点 `create_data_provider()`（`providers/factory.py:13-15`）：**硬编码** Tushare 主 + AkShare 备；YAML 里的 `primary_provider`/`fallback_provider` 只被读取存储，**从不被使用**。
- `_dispatch`（`providers/fallback_provider.py:28-36`）：主源成功即返回；主源抛**任何** `Exception` → 记 `ProviderNotice` → 试备源；都失败抛 `CombinedProviderError`。所以回退触发条件是"主源抛异常"，包含网络/权限/参数错误，也包含 schema 与 `ValueError`。
- **`fetch_index_official_valuations` 绕过 `_dispatch`**（`fallback_provider.py:43`），直接调主源：官方估值**永不回退 AkShare**，不支持就是明确失败。这是有意设计。
- `data_source` 由实际产出数据的适配器写入，路由器不写。注意 AkShare 的 `_normalize_eastmoney_daily` **不加** `data_source` 列（`akshare_provider.py:246-261`）。
- 回退告警是**进程内缓冲**，不落库：`consume_provider_notices` + `summarize_provider_notices`（`provider_runtime.py:68-74, 107-117`），汇总形如 `Tushare 异常后已使用 AkShare：{n} 次；示例：{≤5 codes}；原因：{categories}`。持久化任务把它写进 `maintenance_task_run.error_message` 并把 `state` 置为 `warning`，UI 显示"已完成（已回退）"。

### 2.3 密钥与限流

- Token **只从环境变量** `TUSHARE_TOKEN` 读取（`provider_runtime.py:77-93`），YAML 中永不存放；`ProviderSettings.token` 用 `repr=False` 隐藏（`provider_runtime.py:20-29`）。
- 代理地址：`TUSHARE_API_URL` → YAML `tushare.api_url` → `https://ts.gyzcloud.top/api`。实现方式是覆写 tushare 私有属性 `client._DataApi__http_url`（`tushare_provider.py:42`）——依赖该库的内部命名，若上游改名会静默失效。
- `redact_provider_text(text, secrets=)`（`provider_runtime.py:96-104`）：把非空 secret（最长优先）替换为 `[REDACTED]`，并正则抹掉 `token=`/`authorization=`。只把 token 当 secret，**代理 URL 不会被脱敏**。
- `RequestRateLimiter`（`provider_runtime.py:120-146`）：全局共享锁，`interval = 60/rpm`（默认 120 → 0.5s）；AkShare 无限流，只有每次调用的重试。

### 2.4 存储

`SQLiteStore`（`storage.py:31-39`），实测 12 张表：

| 表 | 实测行数 | 用途 |
|---|---|---|
| `etf_master` | **1544** | ETF 主列表 |
| `index_catalog` | **210** | 版本化指数目录（含 baseline evidence 4 列） |
| `index_etf_mapping` | **800** | 指数↔ETF 映射 |
| `index_history_coverage` | **180** | 每指数历史完整性证据 |
| `data_update_state` | **1715** | 每资产数据集新鲜度（`etf_daily_price` / `index_daily_price` / `index_source_validation`） |
| `maintenance_task_run` | **17** | 长任务持久化（进度/结果/失败原因） |
| `user_etf_watchlist` | 0 | 每日计算池（**当前为空**） |
| `strategy_signal` / `daily_trade_advice` | 0 | 策略输出/建议日志（**当前为空**） |
| `data_quality_log` | 0 | **全代码库从不写入**，仅旧 Streamlit 页读取 |
| `data_fetch_job` | 0 | 任务队列日志 |

唯一迁移：给 `index_catalog` 补 4 个 `baseline_evidence_*` 列（`storage.py:182-191`）。

`ParquetStore`（`storage.py:508-559`，构造时即 `mkdir`）：

| 路径 | 状态（实测） |
|---|---|
| `data/parquet/prices/<etf_code>.parquet` | 1535 文件 |
| `data/parquet/indexes/<index_code>.parquet` | 179 文件 |
| `data/parquet/index_valuations/<index_code>.parquet` | **目录不存在** |
| `data/parquet/macro/<series>.parquet` | **目录不存在** |
| `data/parquet/cache/*.parquet` | 5 文件（原子指标与指数快照） |

### 2.5 指数目录与"官方基日"门槛

- `IndexCatalogEntry`（`index_catalog.py:81-98`）；`pool ∈ {core, research, reserve}`，`source_kind ∈ {csi, shenwan, hk}`，`baseline_source` 决定能否作为可交易基准。
- **`catalog_order` 不落库**：SQLite 读出来是按 code 排序的，消费者必须用 `default_index_catalog()` 的 YAML 顺序重新排序，未知 code 排最后（`nicegui_app/state.py:309-322`）。
- `SQLiteStore.list_index_catalog()` 默认**隐藏 `pool='reserve'`**。
- 允许新开仓的唯一闸门 `allows_new_index_position`（`quality.py:196-213`）：需**同时**满足 `regime_allows` + `pool == "core"` + 官方基日 + `completeness_status == "COMPLETE"` + 数据就绪。
- 未知基日**故意不算完整**，即使供应商返回了很长历史（`quality.py:226-231`）——防止研究用目录行因"虚假完整"变成可交易。
- 官方估值只支持 **6 个**指数（`data/index_valuations.py:8-15`）：`000001→000001.SH`、`000016→000016.SH`、`000300→000300.SH`、`000905→000905.SH`、`399001→399001.SZ`、`399006→399006.SZ`；其余一律 `ProviderCapabilityError`。

### 2.6 数据质量

- **`data_quality_score` 在整个仓库里从未被计算**。全代码库仅 5 处出现：UI 页写死 `= 1.0`（`ui/app.py:2759`、`ui/app.py:2894`、`nicegui_app/pages/action.py:93`），策略侧按 1.0 默认值读取（`strategy/trend.py:41, 152`）。也就是说"数据质量不足 → FORBID"这条规则在实际数据流中**永远不触发**。
- 真实质量逻辑在 `data/quality.py`：`HistoryReadiness` 枚举（`ready/stale/short_history/missing_history/read_failed`）、`expected_latest_trade_date`、`trading_day_lag`、`assess_price_history`（`STALE` 优先于 `SHORT_HISTORY`）、`assess_index_history_completeness`（状态阶梯到 `COMPLETE`/`INCOMPLETE`）。
- 完整性/缺口统计在 `ui/data_coverage.py` 组装（`build_data_gap_detail`、`build_data_coverage_summary`）。

### 2.7 配置键

`configs/data_sources.yaml`：`tushare.api_url`、`tushare.requests_per_minute: 120`、`tushare.attempts: 3` 生效；`primary_provider`/`fallback_provider`/`storage.*`/`update.*` **无任何代码读取**（只是与代码默认值字面相同的文档）。

`configs/index_universe.yaml`（308 行）：`groups:` 列表，组级 `market`/`category_level_1`/`category_level_2`/`index_type`/`pool`/`source_kind`，行 `[code, name, aliases?]`。含 9 个 core A 股组、2 个 research 组、1 个 reserve 组（30 项）、2 个 core 港股组、3 个 research 港股组。

`configs/index_baseline_evidence.yaml`（625 行）：逐 code 的 `reference_date/source/kind/source_name/source_url/checked_at/detail`。除 `399001`/`399006` 为 `third_party_publication`（聚宽，注明"第三方仅提供发布日期，不能视为官方基日"）外，其余均为 `official_api`。证据写入**永不**把已确认的官方记录降级为第三方（`baseline_evidence.py:161-163, 185-187`）。

---

## 3. 实测环境状态（重要）

| 项 | 实测结果 | 含义 |
|---|---|---|
| 官方指数估值缓存 | `data/parquet/index_valuations/` **不存在**；`task_id=14`（`official_index_valuation_sync`）虽报 `success`，但最后一项 `399006 FAILED` | **6 个官方指数的 PE-TTM/PB 全部未同步**，"指数估值"页与估值分位原子处于"未同步"状态；该同步只能走 Tushare，无回退 |
| Tushare 可用性 | `task_id=9/11/13` 的 `error_message` 均为 `Tushare 异常后已使用 AkShare：180 次` | 本机 Tushare 侧不可用（`TUSHARE_TOKEN` 未配置或代理失败），指数历史实际由 AkShare 提供 |
| 每日计算池 | `user_etf_watchlist` 0 行 | "今日行动/每日建议"当前无内容可出 |
| ETF 研究样本 | `reports/research_latest/candidate_ranking.csv` 仅 2 个样本 | 该报告是冒烟运行，不构成策略结论 |

---

## 4. 指数趋势 V1：六道闸门与真实结果

锁定配置 `configs/index_research.yaml`：`version=index_trend_v1`，`locked_at=2026-07-30`，`ma_window=60`、`slope_lookback=20`、`buffer_rate=0.02`、`atr_window=20`、`atr_multiple=3.0`，缓冲消融 `[0.0, 0.02, 0.03]`，成本 `commission=0.00015`/`slippage=0.0002`/`stress_multiplier=2.0`。该 YAML 会先规范化 UTF-8+LF 再算 SHA-256，作为审计身份（跨 LF/CRLF 检出保持一致）。

### 4.1 六道闸门与实测值

最新已发布运行：`20260730T191223407974Z-eb8fad0d41`，数据截止 `2026-07-28`，官方/参考/排除 = `25/0/185`。总体状态 **`failed`**。

| 闸门 | 实测值 | 阈值 | 结果 |
|---|---|---|---|
| `drawdown_win_rate` | 0.96 | ≥ 0.60 | ✅ 通过 |
| `median_drawdown_reduction` | 0.5358 | ≥ 0.20 | ✅ 通过 |
| `median_calmar_improves` | V1 0.054743 vs 买入持有 0.084631 | V1 高于买入持有 | ❌ 失败 |
| `median_return_is_retained` | V1 0.02528 vs 下限 0.031598（买入持有中位 0.051598 − 0.02） | ≥ 买入持有减 0.02 | ❌ 失败 |
| `buffer_reduces_whipsaw_rate_and_trades` | 假突破率 0.7380→0.4916；交易/年 6.2631→3.8301 | 2% 缓冲两项均严格更低 | ✅ 通过 |
| `stress_keeps_first_four_gates` | 双倍费用下前四项：前两项 True，后两项 False | 四项全通过 | ❌ 失败 |

> 注意上表两个"中位数"是**25 个指数横截面的中位数**，不是某个指数的值。所以正确读法是：**策略把中位回撤压掉了约 53.6%，但代价是中位年化从 5.16% 掉到 2.53%，且 Calmar 反而更差**——典型的"减了波动、也减了收益"。

五年滚动窗口：31 个合格窗口中 10 个通过（通过率 0.3226）。
全历史最好/最差（按 V1 年化）：最好 `000819` 有色金属 `+6.41%`，最差 `000688` 科创50 `-5.03%`。
排除原因分布：`unresolved` 131、`non_positive_ohlc` 51、`publication_date` 2、缺文件 1。
前瞻样本：25 个官方指数**全部** `no_prospective_sample`（`no_data_strictly_after_locked_at`）。注意 `data_cutoff=2026-07-28` **早于** `locked_at=2026-07-30`，所以锁定日之后确实还没有任何数据；报告明确写了"不得将历史切分表述为 prospective OOS"。这也意味着**当前没有任何前瞻样本外证据**，历史表现与前瞻证据不能混为一谈。

严格复核已由独立的一次端到端复跑确认：`load_latest_index_research('reports/index_research')` 通过，且锁定配置的实际哈希与运行元数据中的 `config_sha256` 一致（`74ae521e…34ba`）。

三个容易踩的运维细节：

- **可评估起点需要 79 根 K 线**（MA60 本身 60 根 + `ma60_slope_20` 再 20 根），而数据准入只要求 `min_valid_rows = 1000`。不足 79 根时整个区间被跳过，该指数记为 `no_evaluable_history`。
- **`ma60_slope_20` 是 MA60 的 20 行比值变化**（`ma60/ma60.shift(20) - 1`），不是逐日回归斜率；且 `add_index_trend_features` 里的 `60/20/20` 是**硬编码**的——配置项的 `ma_window`/`slope_lookback`/`atr_window` 只被用于与锁定值比对，并没有接进特征构建器。改这三个值会先因锁定校验失败。
- 每个区间都**从空仓重新开始**，并额外前置一根区间开始前的观测，只为让"新鲜上轨突破"在首日可判定；切片 NAV 随后丢弃这一行。

### 4.2 发布物与证据链

每次运行产出固定 10 个文件到 `reports/index_research/runs/<run_id>/`：`index_backtest_results.csv`、`index_backtest_trades.csv`、`index_strategy_summary.csv`、`index_strategy_yearly.csv`、`index_strategy_buffer_comparison.csv`、`index_strategy_exclusions.csv`、`index_strategy_rolling_5y.csv`、`index_strategy_nav.parquet`、`index_trend_strategy_report.md`、`index_trend_strategy_run.json`，并用 `latest.json` 指向最新运行。

严格复核（`index_validation.py`，435 行）不信任任何摘要：从加载后的结构化表**重新计算**六道闸门，校验运行元数据计数与截止日，用锁定配置的 SHA-256 对齐，检测孤立的 trade/NAV 序列，并禁止 CSV/JSON/Markdown 中出现字面 `NaN`/`Infinity`（缺失单元格渲染为 `—`）。失败结论会被原样保留，不被"解释性措辞"包装成有效。

## 5. 策略、风控与回测

### 5.1 指标口径（`strategy/features.py`）

`add_technical_features(prices)` 需要 `trade_date` + `close`，先按日期排序。`MA_WINDOWS=(20,51,60,120,250,850)`（`min_periods=窗口`，**不产生部分窗口**），`MOMENTUM_WINDOWS=(20,60,120)`。

| 列 | 公式 |
|---|---|
| `ma20/51/60/120/250/850` | `close.rolling(w).mean()` |
| `momentum_{20,60,120}` | `close/close.shift(w) - 1`；`return_{w}` 是它的**别名** |
| `momentum_60_skip5` / `momentum_120_skip5` | `close.shift(5)/close.shift(65) - 1` / `.../shift(125) - 1` |
| `ma60_slope_20` | `ma60/ma60.shift(20) - 1` |
| `avg_amount_5` / `avg_amount_20` / `amount_ratio_5_20` | 成交额均值（`min_periods=1`）；无 `amount` 列时全为 `pd.NA` |
| `distance_ma20_pct` / `distance_ma20_atr` | `close/ma20-1` / `(close-ma20)/atr20` |
| `atr20` | 真实波幅 `max(high-low, |high-prev_close|, |low-prev_close|)` 的 20 日均值；缺 OHLC 则 `pd.NA` |
| `rolling_high_close_60` / `is_60d_close_breakout` | 60 日最高收盘 / 是否创 60 日新高 |
| `volatility_20` / `drawdown_120` | 日收益 20 日标准差 / 相对 120 日最高的回撤 |

`relative_strength_rank` **不在这里算**：由 `research/runner.py:80-100` 横截面生成，`momentum_60.rank(ascending=False, pct=True)`，即 **0.0 = 最强、1.0 = 最弱**，并列取平均名次。

另有 `add_weekly_trend_features`（周线 MA10/MA30 及斜率，前向填充到日线）**在 `src` 中无任何调用方**，以及 `add_trend_regime_features`（在基础特征上追加 `ma51/120_slope_20`、`ma250_slope_60`）。

### 5.2 `TrendStrategy` 判定级联（`strategy/trend.py:14`，自上而下第一个命中即返回）

默认参数：`min_trade_interval_days=10`、`min_avg_amount_20=3e7`、`max_abs_premium_rate=0.005`、`high_volatility_20=0.04`。

| # | 条件 | 结果 | 行 |
|---|---|---|---|
| 1 | `data_quality_score < 0.9` | `FORBID` w=0，`["data_quality"]` | `:41-43` |
| 2 | 港股跨境 且 `underlying_market_open is False` | `FORBID` w=0，`["hk_market_closed"]` | `:45-46` |
| 3 | `avg_amount_20 < 3e7` | `FORBID` w=0，`["liquidity"]` | `:48-50` |
| 4 | `|premium_rate| > 0.005` | `FORBID` w=0，`["premium"]` | `:52-54` |
| 5 | 非 risk_on 且 `current_weight > 0` | `REDUCE` w=`current_weight*0.5` | `:64-66` |
| 6 | 非 risk_on 且 `current_weight == 0` | `HOLD` w=0 | `:67` |
| 7 | `close < ma120` 且 `current_weight > 0` | `SELL` w=0，`["close_below_MA120"]` | `:69-70` |
| 8 | **全部**：`close>ma51`、`close>ma120`、`momentum_20>0`、`momentum_60>0`、`relative_strength_rank<=0.30` | 见下方 BUY 子流程 | `:72-97` |
| 9 | `close < ma51` 且 `momentum_20 < 0` 且 `current_weight > 0` | `REDUCE` w=`current_weight*0.5` | `:99-100` |
| 10 | 其他 | `HOLD` w=`current_weight`，`["no_action"]` | `:102` |

BUY 子流程：低频约束（距上次动作 < 10 天 → `HOLD`）→ `risk_multiplier = 0.5 if volatility_20 > 0.04 else 1.0` → `target = sizer.recommend_buy_percentage(category, current_weight, target_weight=single_etf_cap(category), risk_multiplier)`。

### 5.3 `TrendV1Strategy` 判定级联（`:125`）

| # | 条件 | 结果 | 行 |
|---|---|---|---|
| 1-4 | 数据质量 / 港股市休市 / `avg_amount_20 < 1e8` / `|premium| > 0.005` | `FORBID` | `:152-165` |
| 5 | `close` 或 `ma60` 缺失 | `HOLD`，`["required_indicator_missing"]` | `:167-179` |
| 6 | `current_weight > 0` 且 `close < ma60` | `SELL`，`["close_below_MA60"]` | `:183-184` |
| 7-8 | 非 risk_on（有仓 → `REDUCE` 半仓；无仓 → `HOLD`） | `:186-189` |
| 9 | `ma20`/`ma60_slope_20`/`momentum_60_skip5`/`momentum_120_skip5`/`relative_strength_rank`/`distance_ma20_atr` 任一缺失 | `HOLD`，`["required_indicator_missing"]` | `:191-216` |
| 10 | `close < ma20` 且 `momentum_20 < 0` 且有仓 | `REDUCE` 半仓 | `:218-219` |
| 11 | `distance_ma20_atr > 2.0` | `HOLD`，`["no_new_buy"]` | `:221-222` |
| 12 | **全部**：`close>ma60`、`ma20>ma60`、`ma60_slope_20>0`、`momentum_60_skip5>0`、`momentum_120_skip5>0`、`rs<=0.30` | 低频约束 → `BUY` | `:224-257` |
| 13 | 其他 | `HOLD`，`["no_action"]` | `:259` |

两版的关键差异：**判定顺序不同**（TrendV1 先查跌破均线再查 risk_off，`TrendStrategy` 相反——所以非 risk_on 且跌破 MA 时，V1 会 `SELL`，旧版只 `REDUCE`）；TrendV1 **无波动率半仓**、BUY 的 `trigger_rules` 是固定 7 条静态列表；`TrendStrategy` 用 `_safe_float` 把 NaN 当 0（缺失 `ma120` 会被当成暴跌 → `SELL`），TrendV1 用 `_required_float` 宁可 `HOLD`。

> **`TrendV1Strategy` 在 `src/` 中从未被实例化**，只有测试调用。研究用的 `etf_trend_v1_*` 候选是用 `StrategyCandidate` 参数**重新实现**了这套规则，而非调用该类，二者并不等价（例如跟踪止损只存在于研究路径）。

### 5.4 仓位计算（`risk/position_sizing.py`）

```
cap           = single_etf_cap(category)
capped_target = min(target_weight, cap) * clamp(risk_multiplier, 0, 1)
add_weight    = min(max(capped_target - current_weight, 0), single_trade_add_cap(category))
final_target  = current_weight + add_weight        # 4 位小数
```

- `SINGLE_ETF_CAPS`：A股宽基 0.15 / A股行业 0.08 / A股主题 0.06 / 港股宽基 0.10 / 港股科技 0.06 / 港股医药 0.06 / 港股高股息红利 0.08 / 债券 0.20 / 商品 0.10 / 货币现金 0.50（未知 → 0.06）。
- `SINGLE_TRADE_ADD_CAPS`：单次加仓上限，如 A股宽基 0.05、A股行业 0.03（未知 → 0.02）。
- 含义：BUY 的 `target_weight` 是**交易后绝对权重**；已达上限时 BUY 是"零动作"；`risk_multiplier > 1` 无法放大仓位。
- **`HK_TOTAL_CAPS`、`THEME_GROUP_CAPS`、`AGGREGATE_CAPS`、`RISK_BUDGETS`、`DRAWDOWN_EQUITY_MULTIPLIERS` 五张表在 `src/` 中无任何调用方**（仅有单测）。因此**组合级仓位上限、风险预算、回撤分层减仓全部未生效**。

### 5.5 回测引擎（`backtest/engine.py`）

- 契约：**T 日收盘信号 → T+1 开盘成交**（类文档字符串明示）。
- 成交价 `open*(1±slippage)`，佣金 `|delta_value| * 0.00015` 另计；NAV 以当根 K 线收盘价计。
- 只有 `BUY/SELL/REDUCE` 会交易，**`HOLD`/`FORBID` 是空事件**；`_target_weight_for_signal` 把 `REDUCE` 也当作绝对目标权重。
- 输出 `BacktestResult(trades, nav, metrics)`；指标 `total_return`、`max_drawdown`、`volatility`，港股跨境额外记 `max_hk_cross_market_exposure`。
- 已知局限：
  - **单标的引擎**，不在多 ETF 间共享现金 → 4.4 里的所有组合级上限都无从执行；
  - 信号日期必须**恰好等于上一根 K 线的日期**，否则被静默丢弃；同日重复信号只保留最后一个；
  - `open`/`close` 无 NaN 校验；无最小变动单位/印花税/最低佣金；无止损止盈（`StrategySignal.stop_loss`/`take_profit` 字段声明了但引擎不读）；
  - 无保证金检查，现金可为负；年化固定按 252 天。

### 5.6 ETF 级研究（`research/`）

- **不是参数网格**：`configs/research.yaml` 的一个条目 = 一个 `StrategyCandidate` = 每只 ETF 一行结果。该文件是**唯一被代码读取的配置**（`research/config.py:15-23`）。
- `configs/research.yaml` 含 9 个候选：`balanced_breakout`、`regime_balanced_breakout`、`early_breakout_tight_heat_filter`、`regime_early_breakout_tight_heat_filter`、`relative_strength_momentum`、`regime_relative_strength_momentum`、`etf_trend_v1_standard`、`etf_trend_v1_width_filtered`、`etf_trend_v1_tight_heat_filter`（全部 `min_trade_interval_days=10`、`target_weight=1.0`、`status=experimental`）。
- 流程：`load_price_frames`（`min_rows=252`，不足则计入 `skipped_count`）→ 可选横截面 RS 排名 → 逐 ETF × 逐候选生成信号并回测 → `rank_candidates` 排序。
- `generate_candidate_signals` 是**有状态单仓位循环**，不产出 `HOLD`：持仓时按 `trailing_ATR_stop` 或 `close < exit_ma` 卖出；空仓时按 `close>entry_ma`、`close>trend_ma`、各动量>0、`required_ma_relations`、`slope_field>0`、`rs<=rs_rank_max`、`max_distance_from_entry_ma`、`max_recent_return_20`、`max_atr_distance_from_ma` 全部通过才买入。
- 输出：`reports/research/{research_results.csv,candidate_ranking.csv}`；`score = mean_total_return + clip(median_annualized_return,±1) + 0.1*clip(median_sharpe,±3) + 0.05*clip(median_calmar,±3) + worst_max_drawdown`。
- 市场风险开关的"研究版"是 `StrategyCandidate.require_trend_regime` → `TrendRegimeClassifier.allows_new_position`（大级别 ∈ {UP, RECOVERY} 且中级别 ∈ {UP, TURNING_UP} 且小级别 ∈ {RIGHT_SIDE_START, PULLBACK}；`EXTENDED` 与 `REBOUND` 明确不允许开仓）。

### 5.7 ETF 分类（`universe/classification.py`）

10 个类别：`A股宽基/A股行业/A股主题/港股宽基/港股科技/港股医药/港股高股息红利/债券/商品/货币现金替代`。`classify_etf` 把 `代码+名称+跟踪指数` 拼接后按 `RULES` **顺序做子串匹配**（前 4 条港股规则需先命中港股语境词 `港股/恒生/H股/中概/中国企业`），默认 `A股主题`。`is_hk_cross_market(category)` = `startswith("港股")`。注意匹配是**大小写敏感的子串**，`红利` 若无港股语境词会落到 `A股主题`。

### 5.8 ⚠️ 三个"声明了但未接线"的关键项

1. **`market_risk_on` 从未被计算**：它是两个 `evaluate` 的必需入参，但仓库内所有调用方都硬编码 `True`（`nicegui_app/pages/action.py:95`、`ui/app.py:2761`、`ui/app.py:2896`）。策略里的"大盘风险过滤"分支在当前接线下**不可达**。日报的 `market_state` 同样由调用方硬编码为 `"震荡"`。
2. **`configs/strategy.yaml` 与 `configs/risk.yaml` 没有任何加载器**：全仓库 grep 只找到描述性 UI 字符串。它们只是 Python 默认值的镜像文档，**改这两个文件不影响运行时**。
3. **风控表大面积死代码**：见 4.4 末尾。组合级上限、风险预算、回撤 overlay 都只存在于声明与单测中。

## 6. 应用层与 UI

### 6.1 启动路径

| 命令 | 入口 | UI |
|---|---|---|
| `python scripts/run_nicegui.py` | `nicegui_app/main.py:run()` | **主 UI（NiceGUI）** `127.0.0.1:8502`，`title="ETF 工作台"`，`reconnect_timeout=60s` |
| `python -m streamlit run app.py` | `etf_trading.ui.app.main` | 回退 UI（Streamlit）8501 |
| `python scripts/run_streamlit_server.py` | 同上，headless，日志写 `logs/streamlit.*.log` | Streamlit 8501 |
| `python scripts/start_streamlit_win.py`（或双击 `.cmd`） | 同上，脱离进程组 | Streamlit 8501 |
| `python scripts/run_daily.py` | `etf_trading.ui.app.main` | **名字有误导性**：它只是 Streamlit 面板的别名，不是无头日更任务 |

NiceGUI 路由：`/`、`/page/{page_slug}`、`/page/{page_slug}/{section}`（section 会 URL 解码）。

**所有运行期路径都是相对路径**，两个 UI 都必须在仓库根目录下启动：`database/etf_system.sqlite`、`data/parquet`、`reports/*`、`configs/*`、`data/ui_preferences.json`。

无任何启动脚本依赖 `pwsh`（唯一 shell 产物是 `scripts/start_streamlit_win.cmd`），README 里的 `$env:VAR=...` 在 Windows PowerShell 5.1 下同样有效。

### 6.2 NiceGUI 页面/分区与"快照生命周期策略"

外壳 `layout.py:render_shell()`：应用主题 → 解析页面/分区 → **选择快照模式** → 建 store → 载入快照 → 渲染侧栏/顶栏/页头分区标签 → 分发。

| 快照模式 | 触发的页面/分区 | 载入器 | 行为 |
|---|---|---|---|
| `full` | 其余全部（行动/*、市场 市场总览/指数买卖参考/指数K线、ETF数据 ETF总览/指数样本池、策略实验室/*） | `load_snapshot_cached`（TTL 600s） | 完整 `PlatformSnapshot`；会重建指数样本池并 **`replace_index_etf_mappings` 写库**——即**渲染期就写** |
| `maintenance_tasks` | 数据维护 补齐任务/日志与设置；ETF数据 原子指标/ETF行情/搜索加入/每日计算池 | `load_maintenance_task_snapshot` | 只读 SQLite；`universe`/`gaps`/`coverage` 为空 |
| `atomic_index` | 市场 指数体检 | 同上（廉价外壳） | 页面本身再以只读方式读已发布的 Parquet 快照 |
| `index_valuation_readonly` | 市场 指数估值 | `load_index_atomic_shell_snapshot_readonly` | `store = None`，`parquet_store` 换成只读的 `IndexAtomicSnapshotReader`——**完全没有 SQLite 句柄**，无从写起 |

五个页面与分区：

1. **今日行动**（行动摘要/每日建议/计算池明细）：指标条 + 允许开仓的分类 + 日报 markdown + 计算池明细。日报由 `TrendStrategy` 对 watchlist 逐只评估生成。
2. **市场地图**（市场总览/指数体检/指数估值/指数买卖参考/指数K线）：
   - 指数体检：设计上只读，读本地原子快照，含 5 标签页**指数画像**对话框（画像总览/估值详情/趋势与风险/全部指标/数据质量），行点击只开对话框、不触发任何计算或写入。
   - 指数估值：只展示已发布统一快照中的官方估值与独立分位，"不计算、不排序评分，也不作交易结论"。
   - 指数买卖参考：研究池在 UI 层被**强制** `allows_new_position = False`。
3. **ETF数据**（ETF总览/原子指标/ETF行情/搜索加入/每日计算池/指数样本池）：原子指标页带多种筛选、体检徽章、右侧 ETF 检查器与"刷新快照"。唯一页面级写入是"搜索加入"→ `set_watchlist` → 随后失效缓存。
4. **策略实验室**（策略库/新建策略/运行回测/策略比较/ETF复盘/指数过滤实验/指数趋势回测）：
   - 运行回测：写 `reports/research_dashboard/{research_results,candidate_ranking,index_trend_summary,research_universe}.csv`。
   - 单 ETF 手动回测：明确"**不写入**研究结果文件"。
   - 指数趋势回测：读**已发布证据包**，页面**不会自动计算**；后台重跑用 `IndexResearchJobManager`，有 1 秒轮询定时器且**在客户端断开时取消**。
5. **数据维护**（数据体检/缺口明细/补齐任务/日志与设置）：补齐任务页含**任务中心**（从 `maintenance_task_run` 恢复）+ 1 秒定时刷新 + 五个展开面板（主列表/ETF历史/指数历史/指数目录与完整性/批量任务）。页面脚注明确"补齐任务只在点击后执行，避免打开页面自动触发耗时操作"。

### 6.3 状态层（`nicegui_app/state.py`）

- 快照：进程内 dict + `RLock`，`SNAPSHOT_CACHE_TTL_SECONDS = 600`，key = SQLite 路径 + Parquet 根。
- `load_snapshot` 在 catalog 为空时会用 `default_index_catalog()` 播种，并写 `index_etf_mappings`（渲染期写入的另一个来源）。
- 原子指标缓存：schema v2，内存 + 磁盘 `data/parquet/cache/atomic_indicators.parquet` + `.meta.json`；签名变化时保留上一代并在**子进程**里重建，UI 显示 `ready/stale/building/failed`。
- 指数原子快照：schema v3，文件 `index_atomic_snapshot.parquet` / `_details.parquet` / `.meta.json`；发布为 临时写→校验→备份→原子替换（失败回滚），且要求 `expected_input_signature` 与发布锁内重新计算的签名一致，否则报"本地输入已变化，拒绝发布快照"。文档字符串明示这是**进程内**协议，"不声称跨进程事务"。
- 只读语义：`IndexAtomicSnapshotReader` 是"只带路径、**绝不创建**目录"的句柄；`load_index_atomic_snapshot_readonly` 读取时"不计算、不抓取"；`invalidate_index_health_snapshot_cache` 是**故意的空实现**（"维护负责写入，页面不保留指数缓存"）。
- 容错：缓存读失败返回 `failed` 结果而不是抛异常；"重新读取快照"失败时保留当前可见快照，避免页面变空白。
- 持久化任务：4 个 runner（指数目录 / 指数原子快照 / 官方指数估值 / 指数历史批处理），各有 `start/latest/reconcile_interrupted`；任务身份是 `(db路径, task_type, task_id)`。已持久化但**不属于本进程**的 `running` 行会被降级为 `interrupted`（"服务器已重启，任务未继续执行"）——这正是重启/刷新到新进程后的行为。成功写入会失效快照缓存。

### 6.4 视图模型与图表

- `view_models.py`（1771 行）是 **UI 中立的纯函数层**：框架 dataclass（`PlatformSnapshot`、`IndexProfileView`、`IndexAtomicOverview`…）、固定列契约（`INDEX_ATOMIC_DISPLAY_COLUMNS`、`INDEX_PROFILE_ALL_GROUPS`）、状态→中文映射表，以及一批 `build_*` 构造器。页面从不自己拼列名。
- `_row_value(row, *keys)` 同时接受中文展示列名与 snake_case，这正是轻量快照（原始 `etf_master`）也能在这些分区工作的原因。
- **图表用 Apache ECharts**（`ui.echart`），payload 形状沿用 TradingView Lightweight Charts 风格，由 **NiceGUI 与 Streamlit 共享**的 `ui/chart_renderer.py` 生成：K 线/线、MA 叠加（ma51/120/250/850 固定配色）、成交量副图、成交标记、价格轴模式 `normal|logarithmic|percent|log_return|drawdown|downside`。区间预设 `近3月/近6月/近1年/近2年/全部/自定义`，默认近 2 年。
- 遗留未用代码：`build_chart_html` 及其 CDN 版 Lightweight Charts、`build_static_chart_html` 及 SVG 兜底——**无任何页面调用**。
- Streamlit 侧改用 `streamlit-lightweight-charts` + Altair。

### 6.5 主题与响应式

`theme.py` 是一整段 CSS（`WORKBENCH_CSS`，约 930 行），按功能前缀组织：

| 前缀 | 范围 |
|---|---|
| `workbench-*` | 外壳与通用件（侧栏 188px 深色渐变、顶栏、页头、分区标签、指标条、表格、任务中心、图表容器…） |
| `atomic-*` | ETF 原子指标工作台 |
| `index-atomic-*` | 指数体检工作台及其对话框（MA 阶梯、区间轨道、事件时间线、证据组） |
| `index-profile-*` | 5 标签页指数画像对话框 |
| `tone-*` | 语义文字色（neutral/info/success/warning/danger） |

断点：`max-width: 960px` 双列网格降为单列；`max-width: 720px` 侧栏收成 58px 图标栏（用 `content: attr(data-short)`）、对话框近全屏、画像网格与标签改单列/可滚动。

中文化约定：所有面向用户的字符串均为中文；表头经 `COLUMN_LABELS`（约 200 条）本地化，枚举经 `VALUE_LABELS`，布尔列经 `BOOLEAN_COLUMN_LABELS` 渲染为 是/否，日期 `%Y-%m-%d`；`render_table` 还装好 Quasar 的"每页行数/暂无数据/没有匹配结果/加载中"文案。反例：Streamlit 的研究表是**中英双语**，且 `ui/components/charts.py` 把中文写成 `\uXXXX` 转义。

### 6.6 Streamlit 回退版差异

同一套五个页面标签，但分区更少：市场地图**没有**指数体检/指数估值，ETF数据**没有**原子指标，策略实验室**没有**指数趋势回测，数据维护首个分区叫"数据总览"而非"数据体检"。

本质差异：Streamlit 每次交互**重跑整个脚本**（只有资源级缓存），长任务多数**同步 + `st.spinner`**（只有趋势研究有可取消的后台 manager）；**没有快照策略/只读纪律**——指数体检与指数估值的只读保证只存在于 NiceGUI 路径。`ui/app.py:65` 的 `WORKFLOW_TABS` 是导航已不使用的遗留常量（`PAGE_SPECS` 才是权威）。共享模块：`ui/chart_renderer.py`、`ui/data_coverage.py`、`ui/state.py`、`ui/components/status.py`。

### 6.7 ⚠️ 一个容易误判的顶栏现象

在 `maintenance_tasks` / `atomic_index` 路由下，`snapshot.master` 是**原始 `etf_master` 表**，没有 `本地历史`/`最新日期` 列。于是 `platform_data_status_summary` 在这些页面上无法统计 ETF 就绪数与最新日期，顶栏 ETF 计数会退化为 `0/N`，而指数计数仍然正确。排查顶栏数字不一致时先想到这一点。

### 6.8 脚本清单

| 脚本 | 作用 | 参数 |
|---|---|---|
| `run_nicegui.py` | 启动主 UI | 无（127.0.0.1:8502） |
| `run_streamlit_server.py` | headless 启动 Streamlit | 无 |
| `start_streamlit_win.py` / `.cmd` | 分离进程启动 Streamlit | 无 |
| `run_daily.py` | 实为 Streamlit 面板别名 | 无 |
| `init_db.py` | 建/升级 SQLite schema 并打印路径 | 无 |
| `update_data.py` | 空则初始化主表，然后补齐 watchlist 中 **enabled** 的 ETF 约 5 年历史 | 无 |
| `run_research.py` | ETF 候选策略研究并写 CSV | `--config --parquet-root --sqlite-path --output-dir --limit --min-rows --no-relative-strength` |
| `run_index_research.py` | 运行并发布指数趋势 V1 证据包 | `--config --parquet-root --report-root --limit` |
| `run_backtest.py` | 交互式单 ETF 回测（首根 K 线当 BUY，打印指标与前 5 笔） | stdin 提示 |
| `fetch_all_etf_history.py` | 批量抓全量 ETF 历史，跳过已新鲜者，可续跑/切片/分片，写 JSON 汇总 | `--years --sleep --limit --start-index --end-index --shard-count --shard-index --summary --no-refresh-master` |
| `verify_index_baselines.py` | 核验正式指数目录的基日证据（可选写回 YAML） | `--through`（必填）`--formal`（必填）`--write-evidence --evidence-path --sqlite-path` |

## 7. 关键"名不副实"清单（复核时优先看）

这些是本轮梳理中**最值得注意**的发现——文档/配置声明的能力与代码实际执行的能力不一致：

| # | 现象 | 证据 |
|---|---|---|
| 1 | `data_quality_score` 从未被计算，永远为 1.0 → "数据质量不足"分支不可达 | `strategy/trend.py:41,152` 读取；仅 3 处 UI 写死 1.0 |
| 2 | `market_risk_on` 从未被计算，所有调用方硬编码 `True` → "大盘风险过滤"分支不可达 | `trend.py:32,145`；`pages/action.py:95`、`ui/app.py:2761,2896` |
| 3 | `configs/strategy.yaml`、`configs/risk.yaml` **无任何加载器**，改它们不影响运行 | 全仓库 grep 仅命中 UI 文案 |
| 4 | 5 张风控表（港股总仓/主题组/合计/风险预算/回撤 overlay）**无调用方** | `position_sizing.py:31-60` 仅单测引用 |
| 5 | 折溢价/流动性/港股休市三个 FORBID 闸门在"每日建议"路径被常量绕过 | `pages/action.py:88-95` |
| 6 | `TrendV1Strategy` 在生产代码中**从未实例化**；研究候选是另写的近似实现 | `src/` 无引用，仅 `tests/test_strategy.py` |
| 7 | 官方指数估值（PE-TTM/PB 分位）在本机**完全未同步**，目录不存在 | `data/parquet/index_valuations/` 不存在；`task_id=14` 末项 `FAILED` |
| 8 | Tushare 在本机不可用，指数历史实际全部由 AkShare 回退提供 | `maintenance_task_run` 告警"已使用 AkShare：180 次" |
| 9 | `data_sources.yaml` 的 `primary_provider`/`fallback_provider`/`storage.*`/`update.*` 均无代码读取 | `providers/factory.py:13-15` 硬编码 |
| 10 | `data_quality_log` 表全代码库从不写入 | 仅被两处 UI 读取 |
| 11 | 每日计算池为空 → "今日行动/每日建议"当前无内容 | `user_etf_watchlist` 0 行 |
| 12 | `reports/research_latest` 只是 2 样本冒烟结果，不构成策略结论 | `candidate_ranking.csv` 仅 3 行 |

## 8. 指数趋势 V1 规则与验证链（细节）

### 8.1 规则本体（`research/index_trend_v1.py`）

`IndexTrendV1` 是**无状态**的：每次只评估一个收盘价，持仓状态由回测持有。构造函数校验 `buffer_rate >= 0` 有限、`atr_multiple > 0` 有限；任一必需输入非有限则直接返回 `None`（不出信号）。

必需输入：`close`、`ma60`、`ma60_slope_20`、`atr20`。带 `buffer_rate=0.02` 的上下轨：`upper = ma60*(1+b)`、`lower = ma60*(1-b)`。

**持仓中（卖出优先级从上到下）**
1. `close <= highest_close - atr_multiple * atr20` → `SELL`，`atr_emergency_exit`，规则 `["atr_emergency_stop"]`
2. `close < lower_band` → `SELL`，`lower_band_exit`，规则 `["price_below_lower_band"]`

**空仓时（买入）**
- 必须存在 `previous` 且其 `close`/`ma60` 有限；
- 条件：`previous_close <= previous_upper_band` **且** `close > upper_band` **且** `slope > 0` → `BUY`，`fresh_upper_band_breakout`，规则 `["fresh_upper_band_cross","ma60_slope_20_positive"]`。

即：**只在缓冲带上轨被新鲜突破（且 MA60 斜率为正）时买入**，跌破下轨或触发 3×ATR 跟踪止损时卖出。BUY 目标仓位 1.0，SELL 0.0。

`entry_is_valid(current)` 用于信号未成交时确认/否决/推迟：返回 `True`（`close > upper_band and slope > 0`）、`False`，或输入缺失时 `None`（推迟）。

### 8.2 指标与成本

`research/index_metrics.py` 的 `summarize_index_result` = NAV 指标 + 交易指标：

- NAV：`total_return`、`annualized_return`、`annualization_periods`、`volatility`、`sharpe`、`max_drawdown`、`calmar`（`max_drawdown == 0` 时取 0）、`avg_exposure`（`weight` 均值）。
- 回撤族：`drawdown_start/trough/recovery`、`drawdown_recovered`、`recovery_trading_days`（按交易日计数）。
- 交易族：`trade_count`、`closed_trade_count`(=`complete_trade_count`)、`win_rate`、`avg_trade_return`、`avg_holding_days`、`annualized_trade_count`(=`trades_per_year`)、`cost_drag`(=`explicit_transaction_cost`=`commission_cost + slippage_cost`)、`atr_exit_count`、`reentry_count`(=`atr_reentry_count`)、`whipsaw_trade_count` 与 `whipsaw_trade_rate`（分母为已平仓数）。
- 成本按锁定的 `commission_rate=0.00015` / `slippage_rate=0.0002`；压力测试 `stress_multiplier=2.0` 即整组翻倍。

### 8.3 六道闸门的确切口径

| 闸门 | 判定 | 阈值文本（`index_gate_evidence.py`） |
|---|---|---|
| `drawdown_win_rate` | 回撤改善的指数占比 ≥ 0.60 | 至少 0.60 |
| `median_drawdown_reduction` | 回撤中位改善 ≥ 0.20 | 至少 0.20 |
| `median_calmar_improves` | V1 中位 Calmar > 买入持有中位 Calmar | V1 中位 Calmar 高于买入持有 |
| `median_return_is_retained` | V1 中位年化 ≥ 买入持有中位年化 − 0.02 | V1 中位年化收益不低于买入持有减 0.02 |
| `buffer_reduces_whipsaw_rate_and_trades` | 2% 缓冲的假突破率**与**交易/年**均严格低于** 0% 缓冲 | 2% 两项均严格低于 0% |
| `stress_keeps_first_four_gates` | 双倍费用下前四项全部通过 | 双倍费用下前四项均通过 |

总体状态由六项聚合（当前为 `failed`）。`format_gate_evidence` 是**报告与 UI 共用**的唯一格式化入口，保证 Markdown 与页面不会各自表述（值、阈值、原因三件套）。

### 8.4 严格复核链（`research/index_validation.py`，435 行）

不信任任何摘要文本，改为从加载后的结构化表**重新计算**：解析元数据 → 按 `config` 的 SHA-256 对齐锁定配置 → 重算 `evaluate_effectiveness`（含缓冲与压力证据）→ 比对状态、六道闸门、全部数值与全部原因 → 检查 `latest.json` 指针 → 交叉引用 → 拒绝无法解析到结果序列的孤立 trade/NAV 键 → 断言 CSV/JSON/Markdown 中不含字面 `NaN`/`Infinity`。

配套约束：`index_data.py` 的准入要求所有必需 OHLC 值有限且为正（`NaN` 与 `<=0` 检查都拦不住正无穷，必须显式判定有限正数）；滚动窗口由 `build_rolling_windows(years=5, step_years=1)` 生成，`summarize_rolling_gates` 汇总通过率；配置哈希前会把 YAML 规范化为 UTF-8 + LF，使 LF/CRLF 检出共享同一审计身份。


