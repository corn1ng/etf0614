# 指数先行投资决策系统改造设计

研究与设计时点：2026-07-04  
目标项目：`etf0614`

## 1. 这版文档解决什么问题

上一版文档更像目标蓝图，没有区分“现有项目已经具备”和“还需要改造”。本版改成差异化设计：先盘点现状，再列出真正要新增或重构的部分。

结论先说清楚：项目不是从零开始。当前已经有指数数据、指数观察、趋势状态、ETF 研究和部分指数过滤能力。真正缺的是把这些能力组织成一个稳定闭环：

```text
指数数据健康
  -> 指数强弱与市场状态
  -> 指数组合级回测
  -> 每日指数决策建议
  -> ETF执行工具映射
  -> 后续真实账户建议
```

第一阶段不应大改所有东西，而应补齐“指数决策闭环”缺口。

## 2. 现有项目已经有的能力

### 2.1 指数数据定义和抓取已有

已有文件：

- `src/etf_trading/data/indexes.py`
- `src/etf_trading/data/providers/akshare_provider.py`
- `src/etf_trading/data/initialization.py`
- `src/etf_trading/data/storage.py`

现状：

- `DEFAULT_INDEXES` 已经内置一批 A 股和港股指数。
- `AkShareProvider.fetch_index_daily()` 已支持 A 股、港股指数抓取。
- `normalize_index_daily()` 已能把不同数据源规范成统一字段。
- `InitializationService.ensure_index_history()` 已支持指数历史增量补齐。
- `ParquetStore.write_index_prices()` / `read_index_prices()` 已支持指数 Parquet 缓存。

因此第一阶段不需要重写指数数据抓取框架。

### 2.2 技术指标已有

已有文件：

- `src/etf_trading/strategy/features.py`
- `src/etf_trading/research/regime.py`

现状：

- 已有 MA20、MA51、MA60、MA120、MA250、MA850。
- 已有 momentum_20、momentum_60、momentum_120。
- 已有 skip-5 动量、MA60 斜率、ATR20、距离 MA20 的 ATR 乖离。
- `add_trend_regime_features()` 已能补充趋势状态所需斜率字段。

因此第一阶段不需要再设计一套新指标库，只需要复用和整理指标口径。

### 2.3 Streamlit 里已有指数页面和数据中心入口

已有文件：

- `src/etf_trading/ui/app.py`

现状：

- 有“指数观察”页面，可以选择指数并查看 K 线。
- 有“数据中心”的指数历史拉取和一键补齐入口。
- 研究页里已经出现“指数过滤”概念。
- ETF 研究运行前可以按指数趋势过滤 ETF 范围。

因此第一阶段 UI 不是从零做，而是把指数相关散点整合成更清晰的“指数决策页”。

### 2.4 ETF 策略研究已有

已有文件：

- `configs/research.yaml`
- `src/etf_trading/research/models.py`
- `src/etf_trading/research/signals.py`
- `src/etf_trading/research/runner.py`
- `src/etf_trading/research/experiment.py`
- `src/etf_trading/backtest/engine.py`

现状：

- 已有候选策略配置。
- 已有单 ETF 信号生成。
- 已有 T 日收盘信号、T+1 开盘成交的单 ETF 回测。
- 已有候选策略 ranking。
- 已有横截面 RS 排名函数 `attach_relative_strength_rank()`。

但这部分目前更偏“ETF 单品研究”，还不是账户级或指数级组合决策。

## 3. 现有能力的主要缺口

### 缺口 1：指数定义写死在代码里

现状：

- 指数池在 `src/etf_trading/data/indexes.py` 的 `DEFAULT_INDEXES` 中硬编码。

问题：

- 调整指数池需要改代码。
- 无法区分核心指数、观察指数、风险代理、ETF 映射基准。
- 后续很难让用户按配置启用/禁用指数。

需要修改：

- 新增 `configs/indexes.yaml`。
- 改造 `data/indexes.py`，让它从配置加载指数，保留内置默认值作为 fallback。

### 缺口 2：已有指数状态，但没有“指数决策模型”

现状：

- `TrendRegimeClassifier` 能判断单个指数或 ETF 的趋势状态。
- UI 能展示部分指数状态。

问题：

- 还没有一个统一对象表达“市场状态、仓位上限、强势方向、风险方向”。
- 指数状态目前偏展示和过滤，还没有成为每日建议的核心输入。

需要新增：

- `src/etf_trading/indexes/__init__.py`
- `src/etf_trading/indexes/models.py`
- `src/etf_trading/indexes/signals.py`
- 定义 `IndexSignal` 和 `IndexDecision`。
- 把单指数趋势状态、RS 排名、市场环境汇总成决策输出。

### 缺口 3：没有指数级组合回测

现状：

- `BacktestEngine.run_single_etf()` 是单标的回测。
- `StrategyExperimentRunner` 对每个 ETF 单独跑，再聚合指标。

问题：

- 真实决策不是“每个指数单独买卖”，而是从指数池里选前 1 到 3 个方向。
- 现在无法回答“如果按指数轮动规则交易，组合净值和最大回撤是多少”。
- 也无法输出组合持仓日志。

需要新增：

- `src/etf_trading/backtest/index_portfolio_engine.py`

第一版只做指数组合：

- 周频调仓。
- 每期最多持有 1 到 3 个指数。
- 市场弱时降低总权益仓位。
- T 日收盘信号，T+1 开盘成交。

### 缺口 4：没有真正的“每日指数建议”

现状：

- `src/etf_trading/report/daily_report.py` 有买入/卖出建议报告结构。
- UI 有“每日建议”区域。
- `strategy_signal` 和 `daily_trade_advice` 表结构存在。

问题：

- 这些还没有围绕指数策略形成稳定输出。
- 现在更像信号展示，不是完整的每日决策摘要。

需要新增：

- `src/etf_trading/advice/index_advice.py`

需要修改：

- `src/etf_trading/report/daily_report.py`
- `src/etf_trading/ui/app.py`

每日指数建议至少输出：

```text
市场状态
权益仓位上限
可参与指数
强势指数排名
禁止追高指数
风险指数
建议动作：WATCH / BUY / REDUCE / SELL / HOLD
规则解释
数据是否滞后
```

### 缺口 5：ETF 只是被指数过滤，还没有“指数到 ETF 执行工具映射”

现状：

- ETF master 中有 `tracking_index` 字段。
- ETF 分类已有。
- 研究页能按指数趋势过滤 ETF 类别或范围。

问题：

- 还没有显式维护“指数方向 -> 可交易 ETF”映射。
- 也没有对同一指数下多个 ETF 做优先级排序。
- 指数层建议和 ETF 执行工具之间还没打通。

需要新增：

- `configs/index_etf_map.yaml`
- `src/etf_trading/universe/index_etf_mapping.py`

第一版规则：

- 一个指数可映射多个 ETF。
- 优先选择成交额高、上市时间长、数据质量好、折溢价正常的 ETF。
- 没有合适 ETF 时，只输出指数方向，不输出 ETF 买入建议。

### 缺口 6：现有 UI 文件过大，指数闭环应拆模块

现状：

- `src/etf_trading/ui/app.py` 很大，指数、ETF、研究、数据中心逻辑混在一起。

问题：

- 继续往 `app.py` 塞每日建议和组合回测，会让文件更难维护。

需要修改：

- 不做大规模 UI 重构。
- 新增小的业务模块承载逻辑。
- `ui/app.py` 只负责调用和渲染。

## 4. 第一阶段真正要改什么

第一阶段名称：指数决策闭环 MVP。

目标不是“新增指数功能”，而是把现有指数能力串成可辅助决策的闭环。

### 工作包 1：指数配置外置

新增：

- `configs/indexes.yaml`

修改：

- `src/etf_trading/data/indexes.py`
- `tests/test_index_support.py`

验收：

- 仍能使用现有 `DEFAULT_INDEXES`。
- 可以从 YAML 加载指数池。
- 每个指数有 `role` 字段：`core`、`satellite`、`risk_proxy`、`disabled`。

### 工作包 2：指数横截面强弱排名

复用：

- `attach_relative_strength_rank()`

新增：

- `src/etf_trading/indexes/ranking.py`

修改：

- `src/etf_trading/research/runner.py` 继续保留 ETF 研究入口，不承载指数排名新逻辑。

验收：

- 对所有已缓存指数按日期计算 RS20、RS60、RS120 排名。
- 输出最近一日指数强弱表。

### 工作包 3：指数决策信号

新增：

- `src/etf_trading/indexes/models.py`
- `src/etf_trading/indexes/signals.py`

复用：

- `TrendRegimeClassifier`
- `add_technical_features`

验收：

- 单个指数能输出 `WATCH`、`BUY`、`REDUCE`、`SELL`、`FORBID`。
- 信号包含规则解释和风险标签。
- 数据缺失或滞后时不输出 `BUY`。

### 工作包 4：指数组合回测

新增：

- `src/etf_trading/backtest/index_portfolio_engine.py`
- `tests/test_index_portfolio_backtest.py`

不替代：

- 不删除现有 `BacktestEngine.run_single_etf()`。

验收：

- 每周从指数池选择前 N 个可买指数。
- T 日信号，T+1 开盘成交。
- 输出组合净值、持仓日志、交易日志。
- 能设置总权益仓位上限。

### 工作包 5：每日指数建议

新增：

- `src/etf_trading/advice/index_advice.py`
- `tests/test_index_advice.py`

修改：

- `src/etf_trading/report/daily_report.py`
- `src/etf_trading/ui/app.py`

验收：

- 输出一张每日指数建议表。
- 明确区分“模型建议”和“账户建议”。
- 未录入持仓时，不输出买卖金额。

### 工作包 6：指数到 ETF 映射雏形

新增：

- `configs/index_etf_map.yaml`
- `src/etf_trading/universe/index_etf_mapping.py`
- `tests/test_index_etf_mapping.py`

验收：

- 每个指数方向可列出候选 ETF。
- ETF 候选按流动性和数据质量排序。
- 无可用 ETF 时给出明确提示，不强推交易工具。

## 5. 哪些暂时不改

第一阶段不改这些：

- 不重写 AkShare provider。
- 不重写现有 ETF 单标的回测。
- 不删除现有 `TrendStrategy` 和 `TrendV1Strategy`。
- 不做全 ETF 池组合回测。
- 不做真实账户持仓录入。
- 不做自动交易。
- 不做大规模 UI 架构重构。

这样可以减少改动面，先把指数闭环跑通。

## 6. 第一阶段完成后的系统变化

完成前：

```text
指数数据和展示已经有
ETF 研究已经有
但指数判断、组合回测、每日建议之间没有稳定闭环
```

完成后：

```text
指数池可配置
指数强弱可排名
指数策略可生成每日建议
指数策略可做组合级回测
指数方向可映射 ETF 执行工具
```

这时系统才真正能回答：

```text
今天市场是否允许参与？
哪些指数方向最强？
模型建议观察、买入、减仓还是空仓？
如果要用 ETF 表达，有哪些候选工具？
这套指数规则历史组合表现如何？
```

## 7. 推荐实施顺序

1. 指数配置外置。
2. 指数 RS 排名。
3. 指数决策信号。
4. 指数组合回测。
5. 每日指数建议。
6. 指数到 ETF 映射。
7. UI 整合。

理由：

- 配置外置是后续所有指数功能的入口。
- RS 排名和趋势状态是决策信号的输入。
- 先有信号，再做组合回测。
- 先有模型建议，再接 ETF 执行工具。
- UI 最后整合，避免先改界面后补逻辑。

## 8. 成功标准

第一阶段完成时必须满足：

- 本地可以加载配置化指数池。
- 可以同步并读取指数历史数据。
- 可以输出最近交易日指数趋势和 RS 排名。
- 可以生成每日指数建议。
- 可以运行指数级组合回测。
- UI 中能看到指数决策页。
- 建议中明确显示规则解释、风险标签和数据日期。
- ETF 建议只作为执行工具候选，不直接替代指数方向判断。

## 9. 风险和约束

- 港股指数和 A 股交易日不同，需要在建议里显示数据日期。
- 部分指数数据源可能缺成交额，成交额不能作为指数策略硬条件。
- 如果指数历史数据滞后，系统只能输出观察或风险提示。
- 指数组合回测不是 ETF 实盘回测，结果不能直接等同于 ETF 可成交收益。
- ETF 映射第一版应人工配置为主，自动匹配为辅。

## 10. 结论

现有项目已经有不少指数基础能力，不需要推倒重来。

真正要做的是补三块：

1. **指数决策层**：把趋势、强弱、市场状态变成统一建议。
2. **组合回测层**：从单标的研究升级到指数池组合回测。
3. **执行映射层**：把指数方向映射到可交易 ETF 候选。

第一阶段的重点不是“多写几个指标”，而是把已有指数数据和研究能力接成一条可解释、可回测、可每日使用的决策链。
