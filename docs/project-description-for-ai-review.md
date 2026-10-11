# ETF 交易指引与回测研究工作台 —— 项目描述（供外部 AI 评审）

> **本文用途**：把本项目完整地"投喂"给一个**无法访问代码库**的外部评审者（例如网页版 GPT），使其能够做出有依据的技术评审，并产出一份可执行的后续迭代计划。
>
> **自包含声明**：本文不依赖任何其他文件。所有数字要么标注"实测"（作者在本机对源码、SQLite、Parquet、报告产物逐项核对得到），要么明确标注为"声明/未接线"。
>
> **证据口径**：本文区分四种完成度标记 —— **【已实现】/【部分实现】/【已声明未接线】/【未实现】**。请勿把"配置里有"当成"功能可用"。
>
> 版本锚点：Git HEAD `f98eed9`（`Merge branch 'feature/unified-index-profile'`）；仓库根 `H:\pythonproject\etf0614\etf0614`。

---

## 0. 给评审 AI 的指令（请先读这一节）

**你的角色**：同时具备量化研究经验与 Python 工程经验的资深评审。不要复述本文，不要赞美，直接给判断。

**请按以下顺序输出**：

1. **一句话诊断**：这个项目当前最核心的矛盾是什么（一句话，不要铺垫）。
2. **事实核对与质疑**：本文中哪些结论你认为证据不足、口径可疑或存在自欺（例如指标定义、闸门阈值、回测假设、样本量）。指出具体条目编号。
3. **问题清单**：按"阻断性问题 / 重要问题 / 可延后问题"三档，每条给出：现象 → 后果 → 证据位置。
4. **迭代路线图**：给出**分批**计划（建议 3~4 批），每批包含：
   - 目标（一句话）
   - 具体任务清单（可执行粒度，指明改哪个模块）
   - 验收标准（可度量，例如"闸门 X 由 failed 变为 passed"且不得放宽阈值）
   - 预计工作量（人日）与风险
   - 前置依赖
5. **当前建议**：在**不做大改**的前提下，这个项目这周应该做什么、不该做什么（各 3 条）。
6. **需要我补充的信息**：列出为把建议落到可执行，你必须知道但本文未提供的信息（最多 10 条，按重要性排序）。
7. **反面清单**：明确说出你认为**不应该做**的事及理由（防止过度工程）。

**约束**：
- 不得建议"通过放宽阈值/更换指标口径"来让有效性闸门通过；本项目明确禁止用措辞或口径调整把失败结论包装成成功。
- 建议必须与"本地单机、无券商接口、单用户、数据只在本机"的现状相容，除非你明确论证要打破该边界。
- 涉及新增数据源、交易日历、成本模型的建议，必须说明它如何影响**已有历史回测结论的可比性**。

---

## 1. 项目是什么

**一句话**：一个**本地运行、单机单用户**的 A 股 ETF「交易指引 + 回测研究工作台」——把"指数/ETF 数据 → 技术指标 → 策略信号 → 历史回测与有效性验证 → 每日人工操作建议"串成闭环，但**不连接券商、不自动下单**，产出的是给人看的决策依据。

**三句话版本**：
1. 它要解决的是"个人投资者在 A 股 ETF 上有想法但缺少可复核证据"的问题：所有结论必须能被独立重算，不能只是曲线好看。
2. 它由两条腿组成：**ETF 级**（对 1500+ 只 ETF 出每日建议与候选策略对比）与**指数级**（对 210 个指数做趋势策略的严格回测与六道有效性闸门验证，这是当前的主战场）。
3. 它在工程质量上投入很重（55 个测试文件、原子化的证据包发布、严格复核链），但在**策略有效性上目前是失败结论**：指数趋势 V1 六道闸门只过四道，且**没有任何前瞻样本外证据**。

**明确的非目标**：不接券商、不做自动下单、不做多用户/登录、不做云端部署、不做参数网格搜索式调优、不做分钟级/日内交易。

---

## 2. 背景、目标与使用场景

### 2.1 背景（为什么要做）

- A 股 ETF 数量极大（实测 `etf_master` 1544 条），分类混杂（宽基/行业/主题/跨境/债券/商品/货币），普通投资者难以系统化地"看指数、买 ETF"。
- 常见做法（追热点、跟大 V、看单一均线）无法回答三个问题：这个信号历史上到底有没有效？回撤能不能接受？成本翻倍后还成立吗？
- 于是本项目的核心命题被设定为：**先把证据链做扎实，再谈收益**。宁可得出"策略没通过"的结论，也不接受"看起来很赚"的曲线。

### 2.2 目标（按优先级）

| 优先级 | 目标 | 当前状态 |
|---|---|---|
| P0 | 结论可被独立复核：任何发布的策略结论都能从结构化数据重算出来 | 【已实现】指数级 |
| P0 | 数据来源可溯源、可回退、不泄密 | 【已实现】 |
| P1 | 对指数趋势策略给出"是否值得继续"的判定 | 【已实现】，结论当前为 `failed` |
| P1 | 对 ETF 出每日可执行的建议（买/卖/减/持/禁） | 【部分实现】，且当前计算池为空 → 实际无输出 |
| P2 | 组合级资金管理与风控（多标的共享现金、组合上限、回撤 overlay） | 【未实现】 |
| P3 | 自动化调度、实盘对接 | 【未实现】 |

### 2.3 典型使用场景

1. **日常（设计意图）**：早盘打开本机页面 → 「今日行动」看计算池每只 ETF 的信号 → 手工在券商 App 下单。
2. **研究（真实高频）**：跑 `run_index_research.py` → 看六道闸门与分期/滚动结果 → 判断策略是否需要重构。
3. **数据维护**：数据体检 → 看缺口 → 点"补齐任务"→ 任务中心看进度（可跨刷新/重启恢复）。
4. **单标的复盘**：策略实验室 → ETF 复盘 → 看买卖点标记与逐笔交易。

---

## 3. 系统全貌

### 3.1 分层结构

```
┌──────────────────────────────────────────────────────────────────┐
│ 表现层  NiceGUI 主 UI（127.0.0.1:8502） / Streamlit 回退（8501）   │
│         view_models.py（UI 中立纯函数层） + theme.py（CSS）        │
├──────────────────────────────────────────────────────────────────┤
│ 编排层  scripts/*（研究/维护/建库）  +  持久化任务管理（SQLite）    │
├──────────────────────────────────────────────────────────────────┤
│ 领域层  strategy/（信号） risk/（仓位） backtest/（撮合）          │
│         research/（候选实验 + 指数趋势 V1 + 证据包）               │
│         universe/（ETF 分类） report/（日报）                      │
├──────────────────────────────────────────────────────────────────┤
│ 数据层  data/  Provider 契约 → Tushare(主)/AkShare(备) → 规范化    │
│         SQLiteStore（元数据/状态）  ParquetStore（行情/快照）      │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 端到端数据流

```
Tushare(主) ──异常──> AkShare(备)      ← 回退会记一条告警（进程内缓冲）
      │
      ├─> 列名规范化（etf_code/trade_date/open/high/low/close/volume/amount/data_source）
      │
      ├─> SQLite：etf_master / index_catalog / index_etf_mapping /
      │           index_history_coverage / data_update_state / maintenance_task_run
      └─> Parquet：data/parquet/prices/<etf>.parquet（日线 + 全指标）
                    data/parquet/indexes/<idx>.parquet
                    data/parquet/index_valuations/<idx>.parquet（当前不存在）
                    data/parquet/cache/*.parquet（原子指标/指数快照 + 签名 meta）
      │
      ├─> 指标 add_technical_features / add_index_trend_features
      │
      ├─> 策略：TrendStrategy(v0) / TrendV1Strategy(v1，仅测试调用)
      │         / IndexTrendV1（指数趋势，锁定版）
      │
      ├─> 回测引擎：T 日收盘信号 → T+1 开盘成交 + 佣金 0.015% + 滑点 0.02%
      │
      ├─> 有效性验证：六道闸门 + 全历史/逐年/关键阶段/5 年滚动/缓冲消融/双倍成本
      │
      └─> 发布：reports/index_research/runs/<run_id>/（10 文件，原子替换 + latest.json 指针）
              → UI 只读该证据包，不自动计算
```

### 3.3 两个典型请求的流转

**A. 出每日建议（今日行动 → 每日建议）**
1. 读自选池 `user_etf_watchlist`（**实测 0 行** → 当前该页无内容可出）。
2. 逐只读 `prices/<code>.parquet`，现算技术指标，取最后一行。
3. **硬编码填充入参**：`relative_strength_rank=0.2`、`premium_rate=0.0`、`data_quality_score=1.0`、`underlying_market_open=True`、`market_risk_on=True`（`nicegui_app/pages/action.py:88-95`）。
   → **后果：折溢价、数据质量、港股市休市、大盘风险四道否决闸门在这一路径上被绕过。**
4. 调 `TrendStrategy.evaluate` 得 BUY/SELL/REDUCE/HOLD/FORBID。
5. 渲染中文 Markdown 日报（市场状态硬编码为"震荡"、风险偏好硬编码为"平衡偏保守"）。

**B. 指数趋势研究（策略实验室 → 指数趋势回测 / CLI）**
1. 读 `configs/index_research.yaml`，逐字段与冻结锁定值比对，并对 YAML 文本算 SHA-256 作为审计身份。
2. 从 `indexes/*.parquet` 载入本地指数历史，按 "官方基日 + 完整性 + OHLC 有限且为正" 准入，其余写入排除清单。
3. 对每个指数跑 `index_trend_v1` 与 `buy_hold` 两条腿，覆盖全历史/逐年/关键阶段/5 年滚动/三档缓冲/双倍成本。
4. 计算六道闸门 → 汇总总体状态。
5. 先写暂存目录（10 个产物）→ **用与加载时同一个严格校验器校验** → 原子替换 → 换 `latest.json` 指针。
6. UI 只读该证据包；后台重跑走 `IndexResearchJobManager`（单飞 + 协作式取消 + 客户端断开即取消）。

---

## 4. 技术栈与运行形态

| 项目 | 内容 |
|---|---|
| 语言 | Python ≥ 3.11（本机用 `.venv-win`，Python 3.11） |
| 包 | `etf-trading-system` 0.1.0，`pip install -e ".[dev]"` |
| 依赖 | `akshare>=1.14.0`、`tushare>=1.4.24`、`duckdb>=1.0.0`（**当前未使用**）、`numpy>=1.26.0`、`pandas>=2.2.0`、`pyarrow>=15.0.0`、`pydantic>=2.7.0`、`pyyaml>=6.0.0`、`nicegui>=3.14.0`、`streamlit>=1.36.0`、`streamlit-lightweight-charts>=0.7.20`；dev 仅 `pytest>=8.2.0` |
| 主 UI | NiceGUI，`127.0.0.1:8502`，图表 **Apache ECharts** |
| 回退 UI | Streamlit，`127.0.0.1:8501`，图表 `streamlit-lightweight-charts` + Altair |
| 存储 | SQLite（元数据/状态/任务；实测 1.19 MB）+ Parquet（行情/快照；实测 431 MB / 1719 文件） |
| 配置 | YAML（`configs/`，7 个文件） |
| 测试 | pytest，55 个测试文件，`pythonpath=["src"]`，`testpaths=["tests"]` |
| 网络 | 仅两个数据源 SDK；无自建服务端；无云依赖 |

**启动命令（实测有效）**

```powershell
Set-Location 'H:\pythonproject\etf0614\etf0614'
$env:PYTHONPATH=(Resolve-Path '.\src').Path
.\.venv-win\Scripts\python.exe scripts\run_nicegui.py        # 主 UI :8502
.\.venv-win\Scripts\python.exe -m streamlit run app.py       # 回退 UI :8501
.\.venv-win\Scripts\python.exe scripts\init_db.py            # 建/升级 SQLite
.\.venv-win\Scripts\python.exe scripts\update_data.py        # 补数据
.\.venv-win\Scripts\python.exe scripts\run_research.py --limit 20
.\.venv-win\Scripts\python.exe scripts\run_index_research.py
```

**硬约束**：所有运行期路径都是**相对路径**（`database/`、`data/parquet`、`reports/`、`configs/`、`data/ui_preferences.json`），因此**必须在仓库根目录启动**，否则会读到空库或新建错误位置的文件。

**密钥约定**：Tushare Token **只从环境变量 `TUSHARE_TOKEN` 读取**，永不写入 YAML 或数据库；代理地址优先 `TUSHARE_API_URL`，其次 YAML，再次默认。异常文本中的 token / `authorization=` / `token=` 会被替换为 `[REDACTED]` 后再进入日志与 UI。

---

## 5. 代码结构与模块职责

实测规模：`src/` **90 个文件 / 23,975 行**；`tests/` **55 个文件 / 16,283 行**；`scripts/` **11 个文件 / 607 行**。

### 5.1 `src/etf_trading/data/`（数据层）

| 文件 | 职责 |
|---|---|
| `provider.py` | `DataProvider(ABC)` 契约；要求 Provider 自己把列名规范化；官方估值默认抛 `ProviderCapabilityError` |
| `providers/tushare_provider.py` | Tushare 实现；覆写 `client._DataApi__http_url` 以支持代理（依赖上游私有属性，脆弱） |
| `providers/akshare_provider.py` | AkShare 实现（ETF 列表/行情、指数行情 A股/港股/申万、交易日历）；`fetch_etf_nav` **恒返回空表** |
| `providers/fallback_provider.py` | 主备路由 `_dispatch`；主源抛**任何** `Exception` → 记 `ProviderNotice` → 试备源；官方估值**绕过**回退 |
| `providers/factory.py` | 唯一构造点，**硬编码** Tushare 主 + AkShare 备（YAML 的 `primary_provider` 等无代码读取） |
| `provider_runtime.py` | Token/代理设置（`token` 字段 `repr=False`）、脱敏 `redact_provider_text`、令牌桶限流 `RequestRateLimiter`（默认 120 次/分，全局共享）、回退告警缓冲 |
| `storage.py`（559 行） | `SQLiteStore`（12 表建表 + 1 次字段迁移）与 `ParquetStore`（构造即 `mkdir`） |
| `quality.py`（398 行） | `HistoryReadiness` 枚举、`expected_latest_trade_date`、`trading_day_lag`、`assess_price_history`、`assess_index_history_completeness`、**可交易闸门 `allows_new_index_position`** |
| `index_catalog.py` | `IndexCatalogEntry`（含 4 个 baseline evidence 字段）、目录校验与持久化 |
| `indexes.py` / `index_data*` / `index_valuations.py` / `index_valuation_service.py` | 指数目录与官方估值（仅 6 个硬编码指数） |
| `baseline_evidence.py` | 官方基日证据自动核验与写回；**永不**把已确认的官方记录降级为第三方 |
| `initialization.py` / `update_state.py` | 初始化主表、逐资产数据集新鲜度记录 |

### 5.2 `src/etf_trading/strategy/`、`risk/`、`backtest/`

| 文件 | 行数 | 职责 |
|---|---|---|
| `strategy/features.py` | 107 | `add_technical_features`（日线指标）、`add_weekly_trend_features`（**无调用方**）、`add_trend_regime_features` |
| `strategy/trend.py` | 286 | `TrendStrategy`（v0，判定级联 10 级）与 `TrendV1Strategy`（v1，13 级；**生产代码从未实例化**） |
| `strategy/models.py` | — | `StrategySignal`（含声明但无人读取的 `stop_loss`/`take_profit`） |
| `risk/position_sizing.py` | 115 | `PositionSizer`：单 ETF 分类上限、单次加仓上限 + 5 张**无调用方**的组合级风控表 |
| `backtest/engine.py` | 124 | 单标的回测：T 日信号 → T+1 开盘成交、佣金/滑点、NAV 与逐笔交易 |
| `universe/classification.py` | — | 10 类 ETF 分类，`代码+名称+跟踪指数` 拼接后按规则**顺序子串匹配**（大小写敏感） |

### 5.3 `src/etf_trading/research/`（研究层，项目重心）

| 文件 | 行数 | 职责 |
|---|---|---|
| `index_trend_v1.py` | 110 | 锁定版指数趋势策略（无状态，一次只判一个收盘价） |
| `index_data.py` | 162 | 指数历史准入、滚动窗口生成、排除原因归类 |
| `index_metrics.py` | — | NAV 指标 + 交易指标（含回撤族、成本、假突破率） |
| `index_gate_evidence.py` | 81 | 六道闸门的统一格式化出口（报告与 UI 共用） |
| `index_validation.py` | 509 | **严格复核链**：不信任摘要，从结构化表重算闸门并逐字节校验发布物 |
| `index_backtest.py` / `index_jobs.py` / `index_report.py` | — | 指数回测执行、后台任务管理、报告生成 |
| `index_valuation_atoms.py` / `index_health_snapshot.py` | — | 估值分位原子、指数体检原子快照 |
| `runner.py` | 132 | ETF 级候选实验主循环 + 横截面 RS 排名 |
| `signals.py` / `experiment.py` / `comparison.py` / `config.py` / `models.py` / `metrics.py` | — | 有状态信号生成、候选定义与排名、实验结果对比 |
| `atomic_indicators.py` / `regime.py` | — | ETF 原子指标、市场状态三级分类器 |

### 5.4 `src/etf_trading/nicegui_app/`（主 UI，与 `ui/` Streamlit 回退）

| 文件 | 行数 | 职责 |
|---|---|---|
| `main.py` | — | 路由 `/`、`/page/{slug}`、`/page/{slug}/{section}`，`reconnect_timeout=60s` |
| `layout.py` | — | 外壳：选快照模式 → 建 store → 载快照 → 渲染侧栏/顶栏/分区标签 |
| `navigation.py` | 76 | **5 个页面、25 个分区**的权威定义 |
| `state.py` | 1165 | 进程内快照缓存（TTL 600s）、原子指标缓存（schema v2）、指数原子快照（schema v3）、只读 reader、4 个持久化任务 runner |
| `view_models.py` | 1771 | UI 中立纯函数层：dataclass 视图模型、固定列契约、状态→中文映射、`build_*` 构造器 |
| `theme.py` | 947 | 一整段 CSS（`workbench-*` / `atomic-*` / `index-atomic-*` / `index-profile-*` / `tone-*` 前缀）+ 响应式断点 |
| `maintenance_tasks.py` | 491 | 长任务持久化、恢复、`reconcile_interrupted` |
| `pages/*`、`components/*` | — | 五个页面与表格/图表/告警/状态组件 |
| `ui/app.py` | 3738 | Streamlit 回退版（**缺乏**指数体检/指数估值/原子指标/指数趋势回测，且无只读保护与任务持久化） |

### 5.5 `scripts/`（可运行工作流）

`run_nicegui.py`、`run_streamlit_server.py`、`start_streamlit_win.py`/`.cmd`、`run_daily.py`（**名字误导：实为 Streamlit 面板别名**）、`init_db.py`、`update_data.py`、`run_research.py`、`run_index_research.py`、`run_backtest.py`、`fetch_all_etf_history.py`（可续跑/切片/分片、跳过已新鲜者）、`verify_index_baselines.py`（基日证据核验，可写回 YAML）。

---

## 6. 数据层细节

### 6.1 Provider 契约（关键列）

| 方法 | 返回的关键列 |
|---|---|
| `fetch_etf_list()` | `etf_code, name, exchange, category, tracking_index, fund_company, listing_date, is_active, tradability_status, data_source` |
| `fetch_etf_daily(code,start,end,adjust="qfq")` | `etf_code, trade_date, open, high, low, close, volume, amount, data_source`（空结果返回固定 9 列空表） |
| `fetch_etf_nav(...)` | `unit_nav, accumulated_nav, iopv, premium_rate`（**AkShare 恒空**） |
| `fetch_index_daily(...)` | `index_code, trade_date, open, high, low, close, volume, amount, data_source` |
| `fetch_index_official_valuations(...)` | 基类抛 `ProviderCapabilityError`，**不回退** |
| `fetch_trade_calendar(market,start,end)` | `market, trade_date, is_open`（Tushare 真实日历；AkShare 为"工作日"近似） |

### 6.2 回退语义与其代价

- 触发条件极宽：主源抛**任何**异常（网络/权限/参数/schema 不一致/`ValueError`）都会回退，因此"数据正常返回"不等于"主源正常"。
- 回退告警是**进程内缓冲**，只在一次任务结束时汇总成一条（形如 `Tushare 异常后已使用 AkShare：180 次；示例：000001、000015…；原因：configuration`），写进 `maintenance_task_run.error_message` 并把状态置为 `warning`（UI 显示"已完成（已回退）"）。**服务重启后未消费的告警丢失，无法事后审计某段历史行情到底来自哪个源。**
- `data_source` 列由实际产出数据的适配器写入；注意 AkShare 的东方财富日线规范化路径**不加** `data_source` 列。

### 6.3 SQLite 实测状态（12 张表）

| 表 | 实测行数 | 用途 |
|---|---|---|
| `etf_master` | 1544 | ETF 名录（含 `amount`/`volume`/`latest_price`） |
| `index_catalog` | 210 | 指数目录（含 4 个基日证据列） |
| `index_etf_mapping` | 800 | 指数↔ETF 映射（**置信度实测全部为 `medium`**） |
| `index_history_coverage` | 180 | 每指数历史完整度证据 |
| `data_update_state` | 1715 | 逐资产数据集新鲜度 |
| `maintenance_task_run` | 17 | 长任务持久化 |
| `user_etf_watchlist` | **0** | 每日计算池（**空**） |
| `strategy_signal` | **0** | 策略信号 |
| `daily_trade_advice` | **0** | 每日建议日志 |
| `data_quality_log` | **0** | **全代码库从不写入**，仅有界面读取 |
| `data_fetch_job` | **0** | 抓取任务队列日志 |
| `sqlite_sequence` | 1 | SQLite 内部表 |

**实测分布（供判断目录治理质量）**
- `index_catalog.pool`：`core` 100 / `research` 80 / `reserve` 30。
- `market`：A股 173 / 港股 37。
- `source_kind`：`shenwan` 128 / `csi` 78 / `hk` 4。
- `baseline_source`：`unverified` **131** / `official_api` 76 / `official_methodology` 1 / `third_party_publication` 2。
  → 即 **210 个指数里只有 77 个有官方基日**，另外 131 个是 `unverified`。
- `index_history_coverage.completeness_status`：`BASELINE_UNVERIFIED` 101 / `COMPLETE` 56 / `INCOMPLETE` 20 / `BASELINE_REFERENCED` 2 / `MISSING_HISTORY` 1。
- `data_update_state`：`etf_daily_price` SUCCESS 1532 / FAILED 3；`index_daily_price` SUCCESS 176 / STALE 3 / EMPTY 1。

### 6.4 Parquet 实测状态

| 路径 | 内容 | 实测 |
|---|---|---|
| `data/parquet/prices/<etf_code>.parquet` | ETF 日线 + 全部技术指标 | **1535 文件 / 261.0 MB** |
| `data/parquet/indexes/<index_code>.parquet` | 指数日线 + 指标 | **179 文件 / 169.8 MB** |
| `data/parquet/index_valuations/<index_code>.parquet` | 官方估值历史（PE/PB） | **目录不存在** |
| `data/parquet/macro/<series>.parquet` | 宏观序列（预留） | **目录不存在** |
| `data/parquet/cache/*` | 原子指标 / 指数原子 / 指数体检快照 + 签名 meta | 5 个 parquet + 3 个 meta.json / 0.4 MB |

### 6.5 增量更新与新鲜度判定

- ETF 历史需**同时**满足"19 个必需特征列齐全" **且** "数据已到最近应有交易日"才算新鲜，否则重新抓取。
- **已知缺陷**：`fetch_and_store_history` 以请求区间**整体覆盖**文件（不合并）。传入较短的起始日会**静默截短**已存历史。

### 6.6 数据质量体系

- `HistoryReadiness`：`ready / stale / short_history / missing_history / read_failed`（中文标签，UI 展示）。
- `assess_price_history`：`STALE` 优先于 `SHORT_HISTORY`。
- `assess_index_history_completeness`：状态阶梯到 `COMPLETE`/`INCOMPLETE`；**未知基日故意不判为完整**（即使供应商返回很长历史），防止研究用指数因"虚假完整"变成可交易。
- 覆盖率与缺口明细在 `ui/data_coverage.py` 组装（`build_data_coverage_summary`、`build_data_gap_detail`）。
- **名不副实项**：`data_quality_score` 全库**从未被计算**，仅 3 处 UI 写死为 `1.0`，策略按默认 1.0 读取 → "数据质量不足 → FORBID"分支**永不触发**。

---

## 7. 领域模型与目录治理

| 概念 | 含义（含实测） |
|---|---|
| ETF 主列表 `etf_master` | 全市场 ETF 名录，1544 条；分类实测：A股主题 905 / A股宽基 233 / A股行业 211 / 货币现金替代 53 / 商品 40 / 港股科技 39 / 港股高股息红利 30 / 港股宽基 28 / 港股医药 5 |
| 自选/每日计算池 `user_etf_watchlist` | 用户挑选的每日出建议标的，**实测 0 行** |
| 指数目录 `index_catalog` | 项目关注并回测的指数清单，210 条，带市场/两级分类/类型/池/基日证据 |
| 三类池 `pool` | `core`（可参与交易与统计，100）/ `research`（研究用，UI 强制禁止开新仓，80）/ `reserve`（候补，默认对所有用户可见集合与批量任务隐藏，30） |
| 官方基日 `baseline_source` | 可交易基准的前提。只有 `official_api / official_methodology / official_factsheet` + 可解析日期才算官方；`third_party_publication` 仅"发布日期"，**明确不算官方基日** |
| 指数↔ETF 映射 `index_etf_mapping` | 800 条，两级匹配（跟踪指数精确 > 名称/别名子串），按成交额排序、每指数上限 10 |
| 数据源溯源 `data_source` | 每行行情由哪个适配器产出 |
| **可交易闸门** `allows_new_index_position` | 允许新开仓需**同时**满足：趋势 regime 允许 + `pool=core` + 有官方基日 + `completeness_status=COMPLETE` + 数据就绪 |

**目录治理的实现特点**：`configs/index_universe.yaml` 用**分组 + 组级继承**（组级声明 market/分类/类型/池/source_kind，行只写 `[code, name, aliases?]`），校验代码唯一与枚举合法后同步进 SQLite。注意 `catalog_order` **不落库**，消费者必须用 YAML 顺序重新排序（未知 code 排最后）。

---

## 8. 技术指标口径（`strategy/features.py`）

输入需含 `trade_date` + `close`，内部先按日期排序。`MA_WINDOWS=(20,51,60,120,250,850)`，全部 `min_periods=窗口`，**不产生部分窗口值**；`MOMENTUM_WINDOWS=(20,60,120)`。

| 列 | 公式 / 口径 |
|---|---|
| `ma20/51/60/120/250/850` | `close.rolling(w).mean()` |
| `momentum_{20,60,120}` | `close/close.shift(w) - 1`（`return_{w}` 是别名） |
| `momentum_60_skip5` / `momentum_120_skip5` | `close.shift(5)/close.shift(65) - 1` / `close.shift(5)/close.shift(125) - 1`（跳过近 5 日，规避短期反转） |
| `ma60_slope_20` | `ma60/ma60.shift(20) - 1`（**是 20 行比值变化，不是逐日回归斜率**） |
| `avg_amount_5` / `avg_amount_20` / `amount_ratio_5_20` | 成交额均值（`min_periods=1`）；无 `amount` 列时全为 `pd.NA` |
| `distance_ma20_pct` / `distance_ma20_atr` | `close/ma20 - 1` / `(close-ma20)/atr20` |
| `atr20` | 真实波幅 `max(high-low, |high-prev_close|, |low-prev_close|)` 的 20 日均值；缺 OHLC 则为 `pd.NA` |
| `rolling_high_close_60` / `is_60d_close_breakout` | 60 日最高收盘价 / 是否创 60 日新高 |
| `volatility_20` / `drawdown_120` | 日收益的 20 日标准差 / 相对 120 日最高价的回撤 |
| `relative_strength_rank` | **不在此处计算**：由 `research/runner.py:80-100` 横截面生成，`momentum_60.rank(ascending=False, pct=True)` → **0.0 = 最强、1.0 = 最弱**，并列取平均名次 |
| 周线特征 `add_weekly_trend_features` | 周线 MA10/MA30 及斜率，已实现但 **`src/` 中无任何调用方**（死代码） |
| `add_trend_regime_features` | 在基础特征上追加 `ma51/120_slope_20`、`ma250_slope_60` |

**声明但未生效的指标相关字段**：`StrategySignal.stop_loss` / `take_profit` 在信号模型里声明，**两个回测引擎都不读取**。

---

## 9. 策略层

### 9.1 `TrendStrategy`（v0，ETF 日频，`strategy/trend.py:14`）

默认参数：`min_trade_interval_days=10`、`min_avg_amount_20=3e7`（3000 万）、`max_abs_premium_rate=0.005`、`high_volatility_20=0.04`。
判定是**自上而下第一个命中即返回**的级联：

| # | 条件 | 结果 |
|---|---|---|
| 1 | `data_quality_score < 0.9` | `FORBID`，权重 0，规则 `data_quality` |
| 2 | 港股跨境 且 `underlying_market_open is False` | `FORBID`，规则 `hk_market_closed` |
| 3 | `avg_amount_20 < 3000 万` | `FORBID`，规则 `liquidity` |
| 4 | `abs(premium_rate) > 0.5%` | `FORBID`，规则 `premium` |
| 5 | 非 risk_on 且有仓 | `REDUCE` 至 `current_weight × 0.5` |
| 6 | 非 risk_on 且空仓 | `HOLD` 0 |
| 7 | `close < ma120` 且有仓 | `SELL` 0 |
| 8 | **全部满足**：`close>ma51`、`close>ma120`、`momentum_20>0`、`momentum_60>0`、`rs_rank<=0.30` | 进入 BUY 子流程（见下） |
| 9 | `close < ma51` 且 `momentum_20 < 0` 且有仓 | `REDUCE` 至 `current_weight × 0.5` |
| 10 | 其他 | `HOLD`，保持当前权重，规则 `no_action` |

BUY 子流程：低频约束（距上次动作 < 10 天 → `HOLD`）→ `risk_multiplier = 0.5 if volatility_20 > 4% else 1.0` → 目标权重 = `PositionSizer.recommend_buy_percentage(category, current_weight, single_etf_cap(category), risk_multiplier)`。
技术实现注意：v0 用 `_safe_float` 把 NaN 当 0，**缺失 `ma120` 会被当成"跌破"从而触发 SELL**（已知脆弱点）。

### 9.2 `TrendV1Strategy`（v1，`strategy/trend.py:125`）

| # | 条件 | 结果 |
|---|---|---|
| 1-4 | 数据质量 / 港股市休市 / `avg_amount_20 < 1 亿` / `abs(premium) > 0.5%` | `FORBID` |
| 5 | `close` 或 `ma60` 缺失 | `HOLD`，`required_indicator_missing` |
| 6 | 有仓且 `close < ma60` | `SELL`，`close_below_MA60` |
| 7-8 | 非 risk_on（有仓 → 半仓 `REDUCE`；空仓 → `HOLD`） | — |
| 9 | `ma20`/`ma60_slope_20`/`momentum_60_skip5`/`momentum_120_skip5`/`rs_rank`/`distance_ma20_atr` 任一缺失 | `HOLD`（宁可不动，不用 NaN 当 0） |
| 10 | `close<ma20` 且 `momentum_20<0` 且有仓 | `REDUCE` 半仓 |
| 11 | `distance_ma20_atr > 2.0` | `HOLD`，`no_new_buy`（离均线太远不追） |
| 12 | **全部满足**：`close>ma60`、`ma20>ma60`、`ma60_slope_20>0`、`momentum_60_skip5>0`、`momentum_120_skip5>0`、`rs<=0.30` | 低频约束后 `BUY` |
| 13 | 其他 | `HOLD`，`no_action` |

v0 与 v1 的实质差异：判定顺序不同（非 risk_on 且跌破均线时，v1 会 `SELL`、v0 只 `REDUCE`）；v1 无波动率半仓、BUY 的 `trigger_rules` 是固定 7 条静态列表；v1 更保守地处理缺失值。
**关键事实：`TrendV1Strategy` 在生产代码中从未被实例化**（`src/` 内无引用，仅测试调用）。研究用的 `etf_trend_v1_*` 候选是用 `StrategyCandidate` 参数**重新实现**了这套规则，二者**不等价**（例如跟踪止损只存在于研究路径）。

---

## 10. 风控与仓位

### 10.1 生效的部分（`risk/position_sizing.py`）

```
cap           = single_etf_cap(category)
capped_target = min(target_weight, cap) × clamp(risk_multiplier, 0, 1)
add_weight    = min(max(capped_target − current_weight, 0), single_trade_add_cap(category))
final_target  = current_weight + add_weight     # 保留 4 位小数
```

- `SINGLE_ETF_CAPS`：A股宽基 0.15 / A股行业 0.08 / A股主题 0.06 / 港股宽基 0.10 / 港股科技 0.06 / 港股医药 0.06 / 港股高股息红利 0.08 / 债券 0.20 / 商品 0.10 / 货币现金替代 0.50（未知分类 → 0.06）。
- `SINGLE_TRADE_ADD_CAPS`：单次加仓上限，如 A股宽基 0.05、A股行业 0.03（未知 → 0.02）。
- 语义：BUY 的 `target_weight` 是**交易后的绝对权重**；已达上限时 BUY 退化为"零动作"；`risk_multiplier > 1` 无法放大仓位。
- 波动率减半只存在于 v0（`volatility_20 > 4%` → 目标仓位 ×0.5）。

### 10.2 **声明了但完全没有调用方**的组合级风控（死代码）

| 表 / 机制 | 设计意图 | 现状 |
|---|---|---|
| `HK_TOTAL_CAPS` | 港股跨境总仓上限 | 无调用方 |
| `THEME_GROUP_CAPS` | 主题组上限（科技高相关 25%、港股跨境 20%） | 无调用方 |
| `AGGREGATE_CAPS` | 行业+主题合计 50% | 无调用方 |
| `RISK_BUDGETS` | 按波动分配风险预算 | 无调用方 |
| `DRAWDOWN_EQUITY_MULTIPLIERS` | 回撤 8% → ×0.75、12% → 上限 30%、15% → 清仓 | 无调用方 |
| `minimum_cash_bond_weight = 25%` | 最低现金/债券仓位 | 无代码强制 |

**根因**：回测引擎是**单标的**引擎，不在多 ETF 之间共享现金，因此上述组合级约束即使接线也**无处执行**。

---

## 11. 回测引擎（`backtest/engine.py`）

**契约**：T 日收盘产生信号 → **T+1 开盘成交**（明确避免前视）。
**成本**：成交价 `open × (1 ± slippage)`，佣金 `|delta_value| × 0.00015` 另计；NAV 按当根 K 线收盘价计。
**行为**：只有 `BUY / SELL / REDUCE` 会交易，`HOLD / FORBID` 是空事件；`REDUCE` 也被当作**绝对目标权重**。
**输出**：`BacktestResult(trades, nav, metrics)`，指标含 `total_return`、`max_drawdown`、`volatility`，港股跨境额外记 `max_hk_cross_market_exposure`。

**已知局限（评审时请注意这些假设）**
1. 单标的引擎，无共享资金池、无再平衡、无组合层风控。
2. 信号日期必须**恰好等于上一根 K 线的日期**，否则被静默丢弃；同日重复信号只保留最后一个。
3. `open`/`close` 无 NaN 校验；无最小变动单位、无印花税、无最低佣金。
4. 无止损/止盈读取（字段声明但引擎不读）。
5. 无保证金检查，现金可为负；年化固定按 252 天。

---

## 12. ETF 级研究流水线（`configs/research.yaml`，9 个候选）

- **不是参数网格**：一个 YAML 条目 = 一个 `StrategyCandidate`，对每只 ETF 产出一行结果。该文件是**唯一被代码读取的策略配置**。
- 9 个候选：`balanced_breakout`、`regime_balanced_breakout`、`early_breakout_tight_heat_filter`、`regime_early_breakout_tight_heat_filter`、`relative_strength_momentum`、`regime_relative_strength_momentum`、`etf_trend_v1_standard`、`etf_trend_v1_width_filtered`、`etf_trend_v1_tight_heat_filter`（全部 `min_trade_interval_days=10`、`target_weight=1.0`、`status=experimental`；`regime_` 前缀 = 加市场状态过滤的对照组）。
- 流程：`load_price_frames`（`min_rows=252`，不足计入 `skipped_count`）→ 可选横截面 RS 排名 → 逐 ETF × 逐候选生成信号并回测 → `rank_candidates` 排序。
- 信号生成 `generate_candidate_signals` 是**有状态单仓位循环**，不产出 `HOLD`：持仓时按 `trailing_ATR_stop` 或 `close < exit_ma` 卖出；空仓时需 `close>entry_ma`、`close>trend_ma`、各动量 > 0、`required_ma_relations`、`slope_field>0`、`rs<=rs_rank_max`、`max_distance_from_entry_ma`、`max_recent_return_20`、`max_atr_distance_from_ma` **全部通过**才买入。
- 排名分：`score = mean_total_return + clip(median_annualized_return, ±1) + 0.1×clip(median_sharpe, ±3) + 0.05×clip(median_calmar, ±3) + worst_max_drawdown`。
- 输出：`reports/research/{research_results.csv, candidate_ranking.csv}`。
- **市场风险开关的"研究版"**：`StrategyCandidate.require_trend_regime` → `TrendRegimeClassifier.allows_new_position`（大级别 ∈ {UP, RECOVERY} 且中级别 ∈ {UP, TURNING_UP} 且小级别 ∈ {RIGHT_SIDE_START, PULLBACK}；`EXTENDED` 与 `REBOUND` 明确不允许开仓）。
- 研究**只读本地 Parquet 缓存**，不联网取数；缺数据必须先到数据维护页补齐。

---

## 13. 指数级研究流水线（当前项目主战场）

### 13.1 锁定配置（`configs/index_research.yaml`，逐字段校验）

```
strategy:   version=index_trend_v1   locked_at=2026-07-30
            ma_window=60  slope_lookback=20  buffer_rate=0.02
            atr_window=20  atr_multiple=3.0  buffer_ablation=[0.0, 0.02, 0.03]
costs:      commission_rate=0.00015  slippage_rate=0.0002  stress_multiplier=2.0
validation: min_valid_rows=1000  rolling_years=5  rolling_step_years=1
            whipsaw_max_holding_days=20  stage_years=[2015, 2018, 2020, 2022]
effectiveness: min_drawdown_win_rate=0.60
               min_median_drawdown_reduction=0.20
               max_median_annual_return_lag=0.02
```

配置**逐字段与冻结值比对**，并对 YAML 文本算 SHA-256 作为审计身份（规范化 UTF-8 + LF，使 LF/CRLF 检出共享同一身份；改一个换行都会导致历史运行无法加载）。

### 13.2 策略规则（`research/index_trend_v1.py`，110 行，无状态）

必需输入：`close`、`ma60`、`ma60_slope_20`、`atr20` —— **任一非有限则直接返回 `None`（不出信号）**。
上下轨：`upper = ma60×(1+b)`、`lower = ma60×(1−b)`，`b = 0.02`。

**持仓中（卖出优先级从上到下）**
1. `close <= highest_close − 3.0×atr20` → `SELL`（`atr_emergency_exit`，3×ATR 跟踪止损）
2. `close < lower_band` → `SELL`（`lower_band_exit`）

**空仓时（买入）**：需存在 `previous` 且其 `close`/`ma60` 有限；条件为
`previous_close <= previous_upper_band` **且** `close > upper_band` **且** `slope > 0` → `BUY`（`fresh_upper_band_breakout`）。
即：**只在缓冲带上轨被"新鲜"突破且 MA60 斜率为正时买入**；BUY 目标权重 1.0、SELL 0.0。
`entry_is_valid(current)` 用于信号尚未成交时的确认/否决/推迟（缺输入返回 `None` 表示推迟）。

### 13.3 数据准入与可评估起点

- 准入：要求指数有**官方基日**、完整度满足要求、且所有必需 OHLC **有限且为正**（`NaN` 与 `<=0` 检查都拦不住正无穷，因此必须显式判有限正数）。
- `min_valid_rows = 1000`，但**可评估起点实际需要 79 根 K 线**（MA60 需 60 根 + `ma60_slope_20` 再需 20 根）。不足 79 根时整段区间被跳过，该指数记为 `no_evaluable_history`。
- **硬编码风险**：`add_index_trend_features` 里的 `60/20/20` 是硬编码，配置项 `ma_window`/`slope_lookback`/`atr_window` 只用于与锁定值比对，**并未接进特征构建器**。改这三个值会先因锁定校验失败。
- 每个区间都**从空仓重新开始**，并额外前置一根区间开始前的观测（只为让"新鲜突破"在首日可判定），切片 NAV 随后丢弃该行。

### 13.4 多周期验证维度

全历史 + 逐年 + 关键阶段（2015/2018/2020/2022）+ **5 年滚动窗口**（`build_rolling_windows(years=5, step_years=1)`）+ **缓冲带消融**（0% / 2% / 3%）+ **双倍成本压力**。每条腿都有 `buy_hold` 对照（买入持有基准）。

### 13.5 六道有效性闸门（口径）

| 闸门 | 判定 | 阈值文本 |
|---|---|---|
| `drawdown_win_rate` | 回撤得到改善的指数占比 ≥ 0.60 | 至少 0.60 |
| `median_drawdown_reduction` | 回撤中位改善 ≥ 0.20 | 至少 0.20 |
| `median_calmar_improves` | V1 中位 Calmar **高于** 买入持有中位 Calmar | V1 中位 Calmar 高于买入持有 |
| `median_return_is_retained` | V1 中位年化 ≥ 买入持有中位年化 − 0.02 | 不低于买入持有减 0.02 |
| `buffer_reduces_whipsaw_rate_and_trades` | 2% 缓冲的假突破率**与**交易/年**均严格低于** 0% 缓冲 | 2% 两项均严格低于 0% |
| `stress_keeps_first_four_gates` | 双倍费用下**前四项全部**通过 | 双倍费用下前四项均通过 |

总体状态由六项聚合。`format_gate_evidence` 是**报告与 UI 共用**的唯一格式化入口，保证 Markdown 与页面不会各自表述（统一给"值 / 阈值 / 原因"三件套）。

### 13.6 指标与成本口径（`research/index_metrics.py`）

- NAV 族：`total_return`、`annualized_return`、`annualization_periods`、`volatility`、`sharpe`、`max_drawdown`、`calmar`（`max_drawdown == 0` 时取 0）、`avg_exposure`（`weight` 均值）。
- 回撤族：`drawdown_start/trough/recovery`、`drawdown_recovered`、`recovery_trading_days`（按交易日计）。
- 交易族：`trade_count`、`closed_trade_count`、`win_rate`、`avg_trade_return`、`avg_holding_days`、`annualized_trade_count`、`cost_drag`（= `commission_cost + slippage_cost`）、`atr_exit_count`、`reentry_count`、`whipsaw_trade_count`、`whipsaw_trade_rate`（分母为已平仓数）。

### 13.7 证据包发布（每次运行固定 10 个文件）

`reports/index_research/runs/<run_id>/` 下：
`index_backtest_results.csv`、`index_backtest_trades.csv`、`index_strategy_summary.csv`、`index_strategy_yearly.csv`、`index_strategy_buffer_comparison.csv`、`index_strategy_exclusions.csv`、`index_strategy_rolling_5y.csv`、`index_strategy_nav.parquet`、`index_trend_strategy_report.md`、`index_trend_strategy_run.json`，并用 `latest.json`（一行 `{"run_id": "..."}`）指向最新运行。
发布方式：写暂存目录 → **用与加载时同一个严格校验器校验** → 原子替换；取消时**不发布半成品**。

### 13.8 严格复核链（`research/index_validation.py`，509 行）

不信任任何摘要文本，改为：
1. 解析元数据 → 按 `config_sha256` 对齐锁定配置；
2. 从加载后的结构化表**重新计算**六道闸门（含缓冲与压力证据）；
3. 比对状态、六道闸门、全部数值与全部原因；
4. 检查 `latest.json` 指针与交叉引用；
5. **拒绝孤立交易/NAV 键**（无法解析到结果序列的键）；
6. 断言 CSV/JSON/Markdown 中不含字面 `NaN` / `Infinity`（缺失单元格渲染为 `—`）；
7. 校验 Markdown 与结构化证据**逐字节一致**。

失败结论被原样保留，**不得**用解释性措辞包装成有效。发布物在加载时会**重新哈希配置**并用锁定配置的 SHA-256 校验。

---

## 14. UI 层（NiceGUI 为主，Streamlit 为回退）

### 14.1 五个页面 / 25 个分区（`nicegui_app/navigation.py`，权威定义）

| 页面（slug） | 分区 |
|---|---|
| 今日行动 `action` | 行动摘要 / 每日建议 / 计算池明细 |
| 市场地图 `market` | 市场总览 / 指数体检 / 指数估值 / 指数买卖参考 / 指数K线 |
| ETF数据 `etf-data` | ETF总览 / 原子指标 / ETF行情 / 搜索加入 / 每日计算池 / 指数样本池 |
| 策略实验室 `research` | 策略库 / 新建策略 / 运行回测 / 策略比较 / ETF复盘 / 指数过滤实验 / 指数趋势回测 |
| 数据维护 `maintenance` | 数据体检 / 缺口明细 / 补齐任务 / 日志与设置 |

### 14.2 快照生命周期策略（本项目的关键设计）

外壳 `layout.py:render_shell()` 先解析页面/分区，再**按页选择快照模式**，避免"渲染即写库"和"打开页面触发重活"：

| 模式 | 触发页面/分区 | 行为 |
|---|---|---|
| `full` | 其余全部 | 完整 `PlatformSnapshot`，`load_snapshot_cached`（TTL 600s）；会重建指数样本池并 **`replace_index_etf_mappings` 写库**（渲染期写入） |
| `maintenance_tasks` | 数据维护（补齐任务/日志与设置）、ETF数据（原子指标/ETF行情/搜索加入/每日计算池） | 只读 SQLite；`universe`/`gaps`/`coverage` 为空 |
| `atomic_index` | 市场 → 指数体检 | 廉价外壳 + 页面自己只读读取已发布 Parquet 快照 |
| `index_valuation_readonly` | 市场 → 指数估值 | `store = None`，只给只读 `IndexAtomicSnapshotReader`——**完全没有 SQLite 句柄**，无从写起 |

### 14.3 状态层与缓存（`nicegui_app/state.py`，1165 行）

- 快照缓存：进程内 dict + `RLock`，key = SQLite 路径 + Parquet 根，TTL 600 秒。
- 原子指标缓存：schema v2，内存 + 磁盘 `data/parquet/cache/atomic_indicators.parquet` + `.meta.json`；签名变化时保留上一代并在**子进程**里重建；UI 状态 `ready/stale/building/failed`。
- 指数原子快照：schema v3，发布为"临时写 → 校验 → 备份 → 原子替换（失败回滚）"，要求 `expected_input_signature` 与锁内重算签名一致，否则报"本地输入已变化，拒绝发布快照"；文档明示这是**进程内**协议，不声称跨进程事务。
- 只读纪律：`IndexAtomicSnapshotReader` **绝不创建目录**；`load_index_atomic_snapshot_readonly` 读取时"不计算、不抓取"；`invalidate_index_health_snapshot_cache` 是**故意的空实现**（"维护负责写入，页面不保留指数缓存"）。
- 容错：缓存读失败返回 `failed` 结果而非抛异常；"重新读取快照"失败时保留当前可见快照，避免页面变空白。
- 持久化任务：4 个 runner（指数目录 / 指数原子快照 / 官方指数估值 / 指数历史批处理），各有 `start/latest/reconcile_interrupted`；任务身份 = `(db路径, task_type, task_id)`；已持久化但不属于本进程的 `running` 行会被降级为 `interrupted`（"服务器已重启，任务未继续执行"）。

### 14.4 视图模型与图表

- `view_models.py`（1771 行）是 **UI 中立的纯函数层**：视图 dataclass、固定列契约、状态→中文映射表、`build_*` 构造器；页面从不自己拼列名。
- 图表用 **Apache ECharts**（`ui.echart`），payload 形状沿用 TradingView Lightweight Charts 风格，由 NiceGUI 与 Streamlit **共享**的 `ui/chart_renderer.py` 生成：K线/线、MA 叠加（ma51/120/250/850 固定配色）、成交量副图、成交标记、价格轴模式 `normal|logarithmic|percent|log_return|drawdown|downside`；区间预设 近3月/近6月/近1年/近2年/全部/自定义，默认近 2 年。
- 遗留未用代码：`build_chart_html`（CDN 版 Lightweight Charts）、`build_static_chart_html`（SVG 兜底）**无任何页面调用**。
- 中文化：表头经 `COLUMN_LABELS`，枚举经 `VALUE_LABELS`，布尔经 `BOOLEAN_COLUMN_LABELS` 渲染为 是/否，日期 `%Y-%m-%d`；`render_table` 还装好 Quasar 的"每页行数/暂无数据/没有匹配结果/加载中"文案。

### 14.5 主题与响应式

`theme.py`（947 行）是一整段 CSS，按功能前缀组织：`workbench-*`（外壳与通用件，侧栏 188px 深色渐变）、`atomic-*`（ETF 原子指标）、`index-atomic-*`（指数体检及对话框）、`index-profile-*`（5 标签页指数画像）、`tone-*`（语义文字色）。断点：`max-width:960px` 双列网格降单列；`max-width:720px` 侧栏收成 58px 图标栏、对话框近全屏、画像网格改单列可滚动。

### 14.6 Streamlit 回退版差异（一致性风险）

同五个页面标签，但**缺少**：指数体检、指数估值、原子指标、指数趋势回测（数据维护首分区叫"数据总览"）。
本质差异：Streamlit 每次交互**重跑整个脚本**（只有资源级缓存），长任务多数**同步 + `st.spinner`**（只有趋势研究有可取消后台 manager），**没有快照策略与只读纪律**——"指数体检/指数估值只读"的保证只存在于 NiceGUI 路径。

---

## 15. 工程质量与实践

### 15.1 测试

- 55 个测试文件（16,283 行），覆盖数据源回退、指标、策略、风控、回测、研究流水线各环节、UI 视图模型与导航、任务持久化、严格复核链。
- 网络访问必须 mock（含 AkShare/Tushare）；有可选的真实代理冒烟测试 `tests/test_tushare_smoke.py`（需 `RUN_TUSHARE_SMOKE=1`）。
- 仓库记录的基线：**695 passed / 1 skipped**。
- 作者本次复跑得到的数字与注意事项见 §16.3。

### 15.2 约定

- 4 空格缩进；公开函数带类型标注；领域规则写简短 docstring；`snake_case` 模块/函数、`PascalCase` 类；优先 `pathlib.Path`。
- **参数放 `configs/` 而非硬编码**（当前有明显违例，见 §18）。
- `data/`、`database/`、`logs/`、`reports/` 是**生成的本地状态，不入库**（含 SQLite、行情、日志、报告、截图）。
- 提交用 Conventional Commit 风格（如 `fix: handle missing ETF history`）。

### 15.3 证据文化与项目记忆（本项目的特色，也是评审重点）

- `docs/task-memory.md`（约 90 KB / 779 行量级）：每条实质性改动都记录"改了什么、用什么命令验证、下次要注意什么"。
- 结论必须**可被独立重算复核**；失败结论不得用措辞包装成成功；报告中明确写了"**不得将历史切分表述为前瞻样本外**"。
- 因此本项目呈现一个反直觉特征：**工程质量高，但策略结论是失败的**——这正是它想展示的诚实性。

---

## 16. 实测运行状态（决定"哪些功能现在其实是空的"）

### 16.1 数据与产物

| 项 | 实测 | 影响 |
|---|---|---|
| ETF 行情 Parquet | 1535 文件 / 261.0 MB | 研究有料可用 |
| 指数行情 Parquet | 179 文件 / 169.8 MB | 指数研究有料可用 |
| 官方指数估值缓存 | `data/parquet/index_valuations/` **不存在** | PE/PB 分位、估值对比、"指数估值"页**全部无数据**。`task_id=14` 的 6 个指数**全部 FAILED**（原因 `TUSHARE_TOKEN is not configured`），但该任务 `state` 仍被记为 `success`（状态判定缺陷，见 §18 #21） |
| 宏观序列 | `data/parquet/macro/` **不存在** | 预留未用 |
| 指数原子快照缓存 | 5 个 parquet + 3 个 meta | 指数体检页可用 |

### 16.2 任务历史（`maintenance_task_run` 17 条）

| task_id | 类型 | 状态 | 备注（实测） |
|---|---|---|---|
| 9 / 11 / 13 | `index_history_batch` | warning | 均为 `Tushare 异常后已使用 AkShare：180 次；示例：000001、000015、000016、000029、000300；原因：configuration、unsupported`（progress 180/180） |
| 4 / 5 | `index_history_batch` | failed | `No module named 'akshare'`（环境缺依赖时真实触发过） |
| 8 | `index_history_batch` | success 但带中断信息 | `服务器已重启，任务未继续执行`（死进程遗留被降级，progress 180/180 已跑完） |
| 14 | `official_index_valuation_sync` | success（**判定错误**） | `progress_detail = 399006 FAILED`；`result_json` 显示 **6/6 全部 FAILED**，原因均为 `TUSHARE_TOKEN is not configured` → 估值缓存至今为空 |
| 16 | `index_atomic_snapshot_rebuild` | failed | `重建指数原子指标失败：本地输入已变化，拒绝发布快照`（并发保护真实生效） |
| 其余 | `index_history_batch`/`index_atomic_snapshot_rebuild` | success | — |

**结论**：Tushare 在本机**不可用**（Token 未配置或代理失败），指数历史实际全部由 AkShare 回退提供；官方估值因设计上**不允许回退**而直接失败。

### 16.3 测试复跑（本次核对）

- 在本机受限环境直接跑 `pytest` 会得到 `491 passed / 1 skipped / 204 errors`，错误全部是 `PermissionError: ...Temp\dsh-*\pytest-of-cjj`（pytest 临时目录被环境拒绝），**属环境问题而非仓库缺陷**。
- 指定工作区内 basetemp 后复跑结果：见本文件末尾"核验记录"一节。

### 16.4 ETF 级研究产物（实测）

| 目录 | 样本 | 说明 |
|---|---|---|
| `reports/research_latest/` | 2 个 ETF × 3 候选（结果 7 行，其中多数指标为 0） | **属冒烟运行，不构成策略结论** |
| `reports/research_latest_120/` | **113 个 ETF** | 较大样本的历史运行：`early_breakout_tight_heat_filter` 得分最高（mean_total_return 0.475、median_annualized 0.0718、median_calmar 0.265），但 `worst_max_drawdown = −0.839` |
| `reports/research_latest_120_rs/` | 113 个 ETF | 加 RS 排名过滤后整体变差（median_annualized 0.031 / 0.0034 / 0.0092） |
| `reports/research_dashboard/` | — | UI 运行回测的输出 + 40 余张 UI 审计截图 |

注意：`research_latest_120` 中 `balanced_breakout` 与 `relative_strength_momentum` 的中位年化完全相同（0.071271），说明该批次未启用横截面 RS（否则不应相同）——**两批结果口径不同，不能混用**。

---

## 17. 最新策略结论（判断"策略值不值得继续"的唯一依据）

最新已发布运行：`run_id = 20260730T191223407974Z-eb8fad0d41`，`run_at = 2026-07-30T19:12:23Z`，`data_cutoff = 2026-07-28`，`locked_at = 2026-07-30`，官方指数 **25** 个、参考 0 个、排除 **185** 个，`config_sha256 = 74ae521e…34ba`，总体状态 **`failed`**。

| 闸门 | 实测值 | 阈值 | 结果 |
|---|---|---|---|
| `drawdown_win_rate` | 0.96（24/25 指数回撤更浅） | ≥ 0.60 | ✅ 通过 |
| `median_drawdown_reduction` | 0.5358（中位回撤压掉 53.6%） | ≥ 0.20 | ✅ 通过 |
| `median_calmar_improves` | V1 0.054743 vs 买入持有 0.084631 | V1 更高 | ❌ **失败** |
| `median_return_is_retained` | V1 0.02528 vs 下限 0.031598（买入持有 0.051598 − 0.02） | ≥ 下限 | ❌ **失败** |
| `buffer_reduces_whipsaw_rate_and_trades` | 假突破率 0.7380 → 0.4916；交易/年 6.2631 → 3.8301 | 两项严格更低 | ✅ 通过 |
| `stress_keeps_first_four_gates` | 双倍成本下：前两项 True，后两项 False | 四项全过 | ❌ **失败** |

其他实测结论：
- **5 年滚动窗口**：31 个合格窗口中通过 10 个（通过率 0.3226）。
- **全历史最好/最差**（按 V1 年化）：最好 `000819` 有色金属 **+6.41%/年**；最差 `000688` 科创50 **−5.03%/年**。
- **排除原因分布**：`unresolved` 131、`non_positive_ohlc` 51、`publication_date` 2、缺文件 1（合计 185）。
- **前瞻样本外**：25 个指数**全部** `no_prospective_sample`，原因 `no_data_strictly_after_locked_at`。注意 `data_cutoff = 2026-07-28` **早于** `locked_at = 2026-07-30`，因此锁定日之后确实还没有任何数据 → **当前没有任何前瞻样本外证据**。
- **一句话诊断**：这套策略能**显著降低回撤**（回撤中位压缩 53.6%，24/25 指数改善），但代价是**收益掉得更多**（中位年化 5.16% → 2.53%），导致**风险调整后收益（Calmar）反而更差**（0.055 vs 0.085）；在双倍成本下这个劣势依旧存在。典型的"减了波动、也减了收益"。
- 严格复核已由一次端到端复跑确认：`load_latest_index_research('reports/index_research')` 通过，锁定配置实际哈希与运行元数据一致。

---

## 18. 已知缺口与未接线清单（**评审应优先从这里找迭代点**）

| # | 问题 | 性质 | 影响 |
|---|---|---|---|
| 1 | `data_quality_score` 从未计算，恒为 1.0（仅 3 处 UI 写死） | 未接线 | "数据质量不足 → FORBID"分支不可达 |
| 2 | `market_risk_on` 从未计算，所有调用方硬编码 `True` | 未接线 | "大盘风险过滤"减仓分支不可达；日报 `market_state` 同样硬编码为"震荡" |
| 3 | `configs/strategy.yaml`、`configs/risk.yaml` **无任何加载器** | 未接线 | 改这两个文件不影响运行时，易误导 |
| 4 | 5 张组合级风控表无调用方；最低现金债券仓位无强制 | 未接线 | 组合上限/风险预算/回撤 overlay 全未生效 |
| 5 | 回测为单标的、不共享资金 | 架构缺口 | 组合级风控即使接线也无处执行 |
| 6 | 今日行动页硬编码乐观入参（折溢价/数据质量/港股休市/大盘风险） | 实现取巧 | 该页建议**绕过了四道否决闸门** |
| 7 | `TrendV1Strategy` 从未被生产调用，研究候选是另写的近似实现 | 重复实现 | 策略类与研究逻辑两套代码易漂移 |
| 8 | `fetch_and_store_history` 整体覆盖不合并 | 缺陷 | 短窗口请求会**静默截短**已存历史 |
| 9 | 官方估值仅 6 个硬编码指数且**不回退**；本机缓存目录不存在 | 覆盖不足 | 估值能力几乎不可用 |
| 10 | 回退告警不落库、进程重启即丢 | 可观测性 | 数据来源质量无法事后审计 |
| 11 | `data_quality_log` 表从不写入 | 死表 | 质量历史无处追溯 |
| 12 | 无前瞻样本外验证（锁定日后无数据） | 方法论缺口 | 有效性结论仅基于历史 |
| 13 | 配置哈希基于 YAML 文本（改一个换行即失效） | 脆弱 | 历史运行可能无法加载 |
| 14 | 无调度器/无自动更新数据 | 运维缺口 | 数据新鲜度靠人工点击 |
| 15 | 无实盘对接、无持仓账本、无多用户 | 未实现 | 距"可执行闭环"还差一层 |
| 16 | Streamlit 回退版缺 4 个分区且无只读保护 | 一致性 | 两套 UI 能力不同步 |
| 17 | 周线特征函数无调用方；`build_chart_html`/静态图无调用方 | 死代码 | 维护成本 |
| 18 | 止损/止盈字段声明但两个引擎都不读 | 未接线 | 信号层无法表达止损 |
| 19 | `configs/data_sources.yaml` 的 `primary_provider`/`fallback_provider`/`storage.*`/`update.*` 无代码读取 | 未接线 | 配置与实现脱节 |
| 20 | `index_etf_mapping` 实测 800 条**置信度全为 medium** | 质量存疑 | 两级匹配的"高置信"分支实际未产出结果 |
| 21 | `official_index_valuation_sync` **6/6 项全部 FAILED 却把 `state` 记为 `success`** | 状态判定缺陷 | 只看任务状态无法发现估值同步实际全部失败（只有 `progress_detail` 露出 `399006 FAILED`） |
| 22 | `TUSHARE_TOKEN` 未配置 → 主数据源整体不可用，且官方估值**设计上不回退** | 环境/配置缺口 | 指数历史实际全部由 AkShare 提供（回退 180 次）；官方估值能力当前为零 |

---

## 19. 我要的迭代计划（结构化模板）与核心待答问题

### 19.1 期望输出模板

```
一、一句话诊断
二、事实质疑（列出你认为证据不足/口径可疑的条目编号与理由）
三、问题清单（阻断 / 重要 / 可延后）
四、迭代路线图
   批次 1：目标 → 任务 → 验收标准 → 工作量 → 风险 → 依赖
   批次 2：…
   批次 3：…
五、本周该做 / 不该做（各 3 条）
六、需要我补充的信息（≤10 条）
七、反面清单（明确不该做的事 + 理由）
```

### 19.2 我认为最需要你回答的问题

1. 策略目标到底是"降低回撤"还是"风险调整后收益更优"？当前 V1 只满足前者。**应该改闸门定义，还是改策略规则？**（注意：本项目禁止用放宽阈值来"通过"闸门）
2. 在**没有任何前瞻样本外证据**的情况下，是否应优先建"锁定后追踪"机制（锁定日 + 定期追加数据、只做样本外记录），而不是继续调参？
3. 优先补哪个缺口：(a) 接线已声明的风控（组合上限 / 回撤 overlay）、(b) 补齐 `data_quality_score` 与 `market_risk_on`、(c) 建组合级多标的回测引擎？
4. **组合级风控与单标的回测的矛盾**如何解？是否必须先做"多标的共享资金 + 再平衡"引擎，否则 (a) 永远无处执行？
5. ETF 层与指数层两套策略是否需要统一（`TrendV1Strategy` 与研究候选的重复实现）？统一的方向应该是"研究用生产类"还是"生产用研究实现"？
6. 官方估值只有 6 个指数且无回退 —— 是扩展硬编码列表，还是引入其他估值来源（并说明对历史可比性的影响）？
7. `configs/*.yaml` 与实际生效参数脱节 —— 应该"让配置真正生效"还是删掉这些误导性配置？
8. `index_trend_v1` 的买入条件（新鲜突破缓冲带上轨 + MA60 斜率 > 0）与卖出条件（3×ATR 跟踪止损 / 跌破下轨）是否存在**结构性缺陷**导致"砍掉了趋势的大部分收益"？请给出具体的规则修改假设与**可验证的预测**（不要只给方向）。
9. 闸门 `median_return_is_retained` 用"中位年化 − 0.02"作为容忍带，是否合理？2 个百分点相对于 A 股 ETF 的长期年化是什么量级？
10. 若你要给出"这个项目值不值得继续投入"的判断，你需要哪些额外信息？

---

## 20. 术语表与关键文件索引

| 术语 | 含义 |
|---|---|
| 三类池 `pool` | `core` 核心（可交易）/ `research` 研究（UI 禁止开新仓）/ `reserve` 候补（默认隐藏） |
| 官方基日 | 由官方渠道（中证接口/官方方法论/官方 Factsheet）确认的指数基准日；只有它才能当可交易基准 |
| 完整度 `completeness_status` | 本地历史相对官方基日是否完整：`COMPLETE`/`INCOMPLETE`/`BASELINE_UNVERIFIED`/`BASELINE_REFERENCED`/`MISSING_HISTORY` |
| 新鲜度 `HistoryReadiness` | `ready`/`stale`/`short_history`/`missing_history`/`read_failed` |
| 闸门（gate） | 六道有效性判定的每一项，全部通过才算策略有效 |
| 假突破率 `whipsaw_rate` | 已平仓交易中**持有期 ≤ 20 天且净收益为负**的那部分占比（分母为已平仓数，`index_metrics.py:251-255`） |
| 证据包 | 一次指数研究运行发布的 10 个产物 + `latest.json` 指针 |
| 严格复核 | 从结构化数据重算结论、拒绝 NaN/Infinity、校验 Markdown 逐字节一致的加载期验证 |

| 关键文件 | 为什么关键 |
|---|---|
| `src/etf_trading/research/index_trend_v1.py` | 唯一的策略规则本体（110 行，改动风险最集中） |
| `src/etf_trading/research/index_validation.py` | 严格复核链（509 行），决定"结论可信"的边界 |
| `src/etf_trading/research/index_gate_evidence.py` | 六道闸门唯一口径出口 |
| `src/etf_trading/research/runner.py` | ETF 级候选实验主循环 + 横截面 RS |
| `src/etf_trading/backtest/engine.py` | 撮合与成本假设（124 行，回测可信度的根） |
| `src/etf_trading/risk/position_sizing.py` | 仓位与组合上限（含死代码） |
| `src/etf_trading/nicegui_app/state.py` | 快照缓存、只读纪律、持久化任务 |
| `configs/index_research.yaml` | 锁定配置（改它会让历史运行无法加载） |
| `configs/research.yaml` | 唯一被代码读取的策略配置 |
| `docs/task-memory.md` | 项目记忆：每条改动的验证命令与踩坑 |

---

## 核验记录（作者本次实测）

- 核对时间锚点：Git HEAD `f98eed9`；仓库根 `H:\pythonproject\etf0614\etf0614`。
- 代码规模：`src/` 90 文件 23,975 行；`tests/` 55 文件 16,283 行；`scripts/` 11 文件 607 行。
- 数据库：`database/etf_system.sqlite` 1.19 MB，12 张表，行数见 §6.3。
- Parquet：prices 1535 / 261.0 MB，indexes 179 / 169.8 MB，cache 5 / 0.4 MB，`index_valuations` 与 `macro` 目录不存在。
- 指数研究：`reports/index_research/latest.json` → `20260730T191223407974Z-eb8fad0d41`（10 个产物齐全）；六道闸门数值与 `index_trend_strategy_report.md`、`index_trend_strategy_run.json` 一致。
- 全量测试复跑：**未能取得有效汇总行**。本机受限环境下 pytest 的临时目录被 Windows 文件权限拒绝访问（`WinError 5` / `scandir` 失败），导致 **204 个依赖 `tmp_path` 的用例在 setup 阶段报错**（同一原因也使仓库内历史遗留的 `.pytest-basetemp-*` 目录无法被列出）。已确认与仓库代码无关，属本工作区的文件权限问题。
- 因此**测试基线仍以仓库记录的 `695 passed / 1 skipped` 为准，本次未能在本环境复核**。需要可信基线时，应在一个能正常创建/清理临时目录的环境中重跑 `python -m pytest -q`。
- 附带发现（工程风险）：该权限问题本身会阻断 AGENTS.md 要求的"提交前跑全量 pytest"流程，值得作为独立运维项处理。
