# 指数体检快照设计

日期：2026-07-06
项目：`etf0614`

## 1. 背景

当前系统已经有指数历史行情、`TrendRegimeClassifier` 趋势门禁、`市场地图 -> 指数买卖参考` 和 `指数K线`，但还缺一层真正面向“体检”的成品数据。

现在的指数状态主要是页面打开时现算：

- 可以得到 `large_trend / medium_trend / small_trend / allows_new_position`
- 可以展示当前是否允许参与
- 不能稳定回答“这个指数现在为什么是这个状态”
- 不能统一展示趋势原子指标、估值原子指标、历史覆盖、缺失原因和估值分位

项目里已经有一套成熟范式可复用：`ETF数据 -> 原子指标`。它通过“原始行情 -> 原子指标快照 -> 本地缓存 -> NiceGUI 页面”的方式，把 ETF 体检页做成了稳定、可缓存、可筛选、可追因的数据产品。

本次需求不是给指数做综合评分，也不是把指数买卖参考包装成直接交易信号，而是新增一套指数原子快照：

- 同时覆盖趋势体检和估值体检
- 在 `市场地图` 下作为独立二级页 `指数体检`
- 首版就带估值，但页面分层展示，不把趋势和估值混成一个总分
- 保留后续扩充估值源和指标集的接口

## 2. 目标

本阶段完成后，系统应能回答以下问题：

- 每个指数当前的大趋势、中趋势、小趋势是什么
- 每个指数当前允许参与与否，以及对应的体检状态是什么
- 每个指数当前的趋势位置、动量、回撤、过热/回踩状态是什么
- 每个指数当前有哪些估值字段可用，它们的当前值、历史百分位、覆盖年数、数据源和缺失原因是什么
- 每个指数的估值数据是否完整、是否历史不足、是否读取失败
- 页面能否在不阻塞首屏的前提下读取旧快照，并在后台刷新成新快照

## 3. 非目标

本阶段不做以下内容：

- 不输出综合评分、温度分、估值总分、趋势总分
- 不输出买入、卖出、加仓、减仓建议
- 不把估值总览标签解释为交易结论
- 不要求所有估值数据源在第一版全部接入
- 不在页面打开时直接调用外部估值 provider
- 不把趋势体检和估值体检混成一张难以理解的大宽表
- 不在首版实现任意复杂图谱、雷达图、合成热力图

## 4. 信息架构

`市场地图` 调整为以下二级入口顺序：

```text
市场总览
指数体检
指数买卖参考
指数K线
```

四个页面职责如下：

- `市场总览`
  负责看全市场和分类参与情况
- `指数体检`
  负责统一查看每个指数的趋势原子指标、估值原子指标、历史覆盖和缺失原因
- `指数买卖参考`
  继续只承载 `TrendRegimeClassifier` 的门禁结果，不承载诊断宽表
- `指数K线`
  继续只承载单指数行情和均线图

这个边界要求延续现有工作台原则：

- `市场地图` 是指数决策层
- `ETF数据` 是 ETF 资产和载体层
- `指数体检` 属于指数观察与诊断，不迁回 `ETF数据`

## 5. 总体方案

采用与 ETF 原子指标一致的“快照 + 缓存 + 独立页”方案。

数据流如下：

```text
指数行情 parquet
  + 估值原始缓存 parquet
    -> 指数体检快照生成器
      -> data/parquet/cache/index_health_snapshot.parquet
      -> data/parquet/cache/index_health_snapshot.meta.json
        -> NiceGUI 市场地图 -> 指数体检
```

方案分两层缓存：

### 5.1 估值原始缓存

这一层只负责把外部估值数据标准化落盘，不负责 UI 聚合。

建议路径：

```text
data/parquet/index_valuations/{index_code}.parquet
data/parquet/macro/10y_bond_yield.parquet
data/parquet/macro/*.parquet
```

这一层存放按日期展开的原始估值时间序列，比如：

- `pe_ttm`
- `pb`
- `dividend_yield`
- `earnings_yield`
- `bond_yield_10y`
- `erp`
- `data_source`
- `trade_date`

### 5.2 指数体检快照缓存

这一层是页面成品数据，只存当前最新交易日的一行摘要和单指数原子指标明细所需内容。

建议路径：

```text
data/parquet/cache/index_health_snapshot.parquet
data/parquet/cache/index_health_snapshot.meta.json
```

这一层与 ETF 原子指标缓存保持一致的行为：

- 页面优先读取本地缓存
- 缓存与源数据签名一致时直接返回 `ready`
- 签名不一致时先返回旧缓存并标记 `stale`
- 无缓存时返回 `building`
- 刷新失败时返回 `failed`

## 6. 数据模型

本次设计分成两类数据产物：

- 主表用的“指数体检快照”
- 单指数详情用的“原子指标明细行”

### 6.1 指数体检快照

快照按“一只指数一行”组织，建议至少包含以下字段：

```text
index_code
index_name
market
category
latest_date
history_rows

large_trend
medium_trend
small_trend
allows_new_position
trend_health_status
trend_health_reason

valuation_overview_label
valuation_health_status
valuation_health_reason

valuation_latest_date
valuation_coverage_years
valuation_primary_source

detail_payload_key
```

字段解释：

- `trend_health_status`
  用于主表快速表示趋势体检结果，例如 `normal / watch / missing / read_failed`
- `valuation_overview_label`
  用于主表显示 `低分位 / 中分位 / 高分位 / 缺失 / 历史不足`
- `valuation_health_status`
  用于主表表示估值数据健康度，例如 `complete / partial / insufficient_history / missing / read_failed`
- `detail_payload_key`
  指向详情区所需的单指数原子指标数据

### 6.2 单指数趋势原子指标明细

趋势详情按“一项指标一行”或“单指数定长宽表”均可，但 NiceGUI 展示层必须能稳定输出以下概念：

- `close`
- `ma20 / ma51 / ma120 / ma250 / ma850`
- `close_above_ma20 / ma51 / ma120 / ma250 / ma850`
- `ma51_slope`
- `ma120_slope`
- `ma250_slope`
- `momentum_20`
- `momentum_60`
- `momentum_120`
- `drawdown_120`
- `distance_to_ma20_pct`
- `distance_to_ma51_pct`
- `small_trend_extension`
- `right_side_state`
- `pullback_state`
- `extended_state`
- `broken_state`

每个趋势原子指标至少要能展示：

```text
metric_name
current_value
status
reason
display_direction
```

### 6.3 单指数估值原子指标明细

估值详情按“一项估值指标一行”组织。每行至少包含：

```text
metric_name
current_value
historical_percentile
window_years
first_date
latest_date
sample_count
data_source
status
reason
```

首版核心估值指标：

- `pe_ttm`
- `pb`
- `dividend_yield`
- `earnings_yield`
- `bond_yield_10y`
- `erp`

可选扩展指标：

- `pe_static`
- `ps`
- `roe`
- `payout_ratio`
- `forward_pe`

这些可选字段只在数据源稳定提供时展示，不用伪造空值补齐。

## 7. 估值总览标签

主表中的 `估值总览` 只做摘要标签，不做综合评分。

第一版推荐使用三个核心字段作为候选：

- `pe_ttm`
- `pb`
- `erp`

聚合规则如下：

1. 如果这三个字段大部分缺失或历史不足，则显示 `缺失` 或 `历史不足`
2. 如果有效字段里大部分百分位落在低位区间，则显示 `低分位`
3. 如果有效字段里大部分百分位落在高位区间，则显示 `高分位`
4. 其他情况显示 `中分位`

该标签的约束：

- 不能命名为“估值分”
- 不能表示买卖信号
- 不能替代单指标明细
- 只能用于主表快速扫视

## 8. 百分位与状态规则

### 8.1 估值百分位

每个估值指标独立计算历史百分位，不跨字段聚合。

公式沿用独立百分位思想：

```text
percentile_t = 100 * (count(x_s < x_t) + 0.5 * count(x_s = x_t)) / count(x_s)
```

约束如下：

- 只使用该指标自身的历史序列
- 默认使用可比历史全窗口
- 历史不足时不给百分位，直接标记 `insufficient_history`
- 不把 `PE` 和 `PB` 的百分位合成一个新的数值

### 8.2 趋势体检状态

趋势体检不计算百分位，主要看当前原子指标是否完整、是否可解释。

建议状态：

- `normal`
- `watch`
- `missing_history`
- `missing_features`
- `read_failed`

### 8.3 估值体检状态

估值体检建议使用：

- `complete`
- `partial`
- `insufficient_history`
- `missing_valuation`
- `stale`
- `read_failed`

所有非正常状态必须带明确原因。

## 9. Provider 边界

估值源要做成可替换 provider，但页面永远不直接读 provider。

建议接口：

```text
IndexValuationProvider
  fetch_index_valuation(index_code, start_date, end_date) -> DataFrame
  fetch_macro_series(series_name, start_date, end_date) -> DataFrame
  source_name -> str
```

本次实现约束：

- 页面层不知道外部数据源细节
- 体检快照层只读取标准化后的本地 parquet
- provider 的切换不影响 NiceGUI 页面接口

第一版不要求所有 provider 都落地，但数据结构和缓存路径必须为后续接入保留稳定边界。

## 10. NiceGUI 页面设计

页面采用“摘要卡 + 主表 + 详情区”的结构，延续 ETF 原子指标的工作台节奏。

### 10.1 顶部摘要卡

显示 4-6 个摘要指标：

- 指数总数
- 趋势可判定数
- 估值完整数
- 估值缺失数
- 允许参与数
- 快照最新时间

### 10.2 主表

主表默认列：

- `指数代码`
- `指数名称`
- `分类`
- `趋势状态`
- `可参与`
- `趋势体检`
- `估值总览`
- `估值体检`
- `最新日期`
- `历史行数`

主表支持：

- 按指数代码/名称搜索
- 按分类筛选
- 按趋势状态筛选
- 按估值状态筛选

主表不显示大宽表形式的所有原子指标列。

### 10.3 详情区

选中一个指数后，页面下半区显示两块：

- `趋势原子指标表`
- `估值原子指标表`

要求：

- 两块独立展示，不混成一张总表
- 每一行都能解释“当前值、状态、原因”
- 估值表额外显示历史百分位、覆盖年数和数据源

## 11. 刷新与性能

刷新逻辑沿用 ETF 原子指标页：

- 打开页面时优先读快照缓存
- 点击刷新时，如果已有缓存则触发后台重建
- 后台重建时页面继续可用
- 成功、后台刷新中、失败三种状态都要有提示

性能边界：

- 冷启动不能因为全量体检重算而阻塞页面
- 主表必须可以在已有缓存条件下快速打开
- 单指数详情不能再次触发全量重算

## 12. 代码分层

本次设计要求遵循现有 NiceGUI 分层习惯：

- `research/*`
  负责指数体检快照和原子指标构建逻辑
- `nicegui_app/state.py`
  负责缓存读取、签名、后台刷新和快照状态返回
- `nicegui_app/view_models.py`
  负责把快照和明细转成 UI 中立行结构
- `nicegui_app/pages/market.py`
  负责 `指数体检` 页面渲染
- `nicegui_app/navigation.py`
  负责新增 `指数体检` 二级入口

不要把快照计算逻辑直接写进页面函数。

## 13. 测试要求

第一版至少需要覆盖以下验证：

- 导航测试：`市场地图` 包含 `指数体检`
- 快照生成测试：趋势摘要、估值摘要、缺失原因稳定输出
- 缓存测试：本地缓存、过期缓存、无缓存、失败状态
- view model 测试：主表行和详情行格式稳定
- 页面测试：`指数体检` 可在无缓存、旧缓存、刷新中三种状态下正常渲染
- 回归测试：现有 `指数买卖参考` 和 `ETF数据 -> 原子指标` 不被破坏

## 14. 验收标准

满足以下条件即视为第一版完成：

1. `市场地图` 新增 `指数体检` 二级入口
2. 页面可读取指数体检快照缓存并展示主表
3. 主表能同时显示趋势体检、估值总览和估值体检状态
4. 选中单个指数后，可同时看到趋势原子指标表和估值原子指标表
5. 估值总览标签只做位置摘要，不是综合分，也不是买卖建议
6. 非正常状态都带明确原因
7. 页面在冷启动和后台刷新时保持可用

## 15. 后续扩展

本设计为下一步保留以下扩展点：

- 接入更多估值 provider
- 增加更多估值字段
- 给单估值指标补历史时间序列小图
- 增加更细的趋势诊断解释行
- 在研究模块复用指数体检快照作为过滤因子输入

第一版重点不是做漂亮的结论，而是把指数体检快照做成可信、可缓存、可扩展的数据层。
