# ETF 原子指标与全量场内 ETF 数据基建设计

日期：2026-07-05
项目：`etf0614`

## 1. 背景

相对强度策略最初来自创新药 ETF 讨论，但用户已经确认它不应是创新药专用策略，而应成为统一 ETF 选择框架。不过当前阶段不实现该策略本体，也不输出最终加权分数或买卖指令。

本阶段目标是先打牢平台基础能力：扩大 ETF 覆盖，确认交易对象边界，补齐历史行情和技术特征，并提供一个能展示各个原子指标的地方。后续任何趋势、相对强度、轮动或风控策略，都应优先复用这些基础数据和指标，而不是各自重复计算。

## 2. 已确认决策

1. 第一阶段只覆盖沪深交易所场内可交易 ETF。
2. 可交易 ETF 主池以 AkShare `fund_etf_spot_em` 为准。
3. `fund_name_em` 只能作为辅助发现源，不直接进入可交易 ETF 主池。
4. 不把 ETF 联接基金、LOF、普通场外指数基金混入策略池。
5. 先展示原子指标，不做最后的加权总分。
6. 不生成正式 `BUY`、`SELL`、`REDUCE` 交易指令。
7. 不判断“策略是否有效”，只保证基础数据完整、可解释、可追踪。

## 3. 本地数据质量观察

本次检查使用本地 SQLite/Parquet 和 AkShare 当前接口结果。

### 3.1 场内 ETF 主表

当前实时 `fund_etf_spot_em` 返回 1528 只 ETF，字段包含代码、名称、最新价、IOPV 实时估值、基金折价率、成交量、成交额、最新份额、流通市值、总市值、数据日期和更新时间。

本地 `etf_master` 当前有 1507 只 ETF。和实时列表对账：

- 实时有、本地没有：21 只，主要是近期新发或新上市 ETF。
- 本地有、实时没有：0 只。
- 实时列表中 ETF 联接：0 条。
- 实时列表中 LOF：0 条。
- 实时列表中名称不含 ETF：0 条。

这说明当前本地主表接近场内 ETF 全量，但需要刷新到实时主表。

### 3.2 当前 Provider 混入风险

项目当前 `AkShareProvider.fetch_etf_list()` 会把 `fund_etf_spot_em` 和 `fund_name_em` 合并。联网检查显示，合并后会返回 1647 条，其中有 119 条不在实时 ETF 交易列表中，并混入：

- ETF 联接：25 条。
- LOF：5 条。
- 多数额外记录没有最新价、成交额和成交量。

因此第一阶段应调整 provider 边界：可交易主表只使用 `fund_etf_spot_em`；辅助基金名称库可以单独保留，但必须带 `tradability_status` 或类似字段，不能默认进入交易池、评分池或历史补齐任务。

### 3.3 历史行情覆盖

本地当前有 120 只 ETF 历史行情文件，明显少于 1528 只实时场内 ETF。多数 ETF 历史最新日期为 2026-06-18；指数历史已经更新到 2026-07-03。当前历史覆盖不足以支持全量 ETF 原子指标看板。

旧 ETF 历史文件里已有 OHLCV、成交额、MA51、MA120、MA250、MA850、20/60 日动量和 20 日平均成交额，但普遍缺少：

- `ma20`
- `ma60`
- `momentum_120`
- `momentum_60_skip5`
- `momentum_120_skip5`
- `ma60_slope_20`
- `atr20`
- `distance_ma20_atr`

这些字段现有 `add_technical_features()` 已经支持，但旧缓存需要重算或回填。

## 4. 目标

本阶段完成后，系统应能回答：

- 当前场内可交易 ETF 主池有多少只。
- 本地 ETF 主表和实时 ETF 主池差多少。
- 每只 ETF 是否有历史行情。
- 每只 ETF 的历史行情是否足够长、是否更新到最近交易日。
- 每只 ETF 是否具备计算趋势、相对强度、成交活跃和过热指标所需的字段。
- 每只 ETF 的原子指标当前值是什么。
- 哪些 ETF 无法计算，以及原因是什么。

## 5. 非目标

本阶段不做以下内容：

- 不实现相对强度策略本体。
- 不计算综合加权分数。
- 不输出买卖建议或目标仓位。
- 不接入自动交易。
- 不把名称推断的 ETF-指数映射当成官方跟踪关系。
- 不覆盖场外 ETF 联接基金、LOF、普通指数基金。
- 不做全市场个股宽度或成分股扩散度。

## 6. 数据源边界

### 6.1 场内可交易 ETF 主池

新增或调整 provider 能力：

```text
fetch_exchange_traded_etf_spot()
```

返回粒度为“一只当前可交易场内 ETF”。规范字段建议：

```text
etf_code
name
exchange
latest_price
iopv
premium_rate
volume
amount
latest_share
float_market_value
total_market_value
data_date
updated_at
is_active
tradability_status
data_source
```

`tradability_status` 第一版可使用：

- `exchange_traded`
- `not_in_spot_list`
- `auxiliary_only`
- `excluded_link_fund`
- `excluded_lof`

可交易主池只允许 `exchange_traded` 进入。

### 6.2 辅助基金名称库

`fund_name_em` 仍可用于补充名称、识别联接基金或未来做映射辅助，但它的记录不能直接进入可交易 ETF 池。若保存到本地，必须和交易主池分开，或者在同表中标记为 `auxiliary_only` 且默认排除。

## 7. 数据模型

### 7.1 ETF 主表扩展

现有 `etf_master` 可扩展字段：

```text
tradability_status
spot_source
spot_data_date
spot_updated_at
iopv
premium_rate
latest_share
float_market_value
total_market_value
excluded_reason
```

如果不想立即改数据库 schema，第一版也可以在 UI 计算时动态生成这些字段，但 provider 输出和内部 DataFrame 需要先统一。

### 7.2 ETF 历史覆盖表

新增纯函数或服务输出每只 ETF 的历史覆盖情况：

```text
etf_code
name
category
is_exchange_traded
has_history
history_rows
first_trade_date
latest_trade_date
expected_latest_trade_date
missing_trade_days
is_history_sufficient
is_fresh
history_status
history_reason
```

`history_status` 第一版：

- `complete`
- `missing_history`
- `stale`
- `short_history`
- `read_failed`

### 7.3 特征健康表

新增特征健康检查，不直接计算策略结果：

```text
etf_code
trade_date
has_ohlcv
has_amount
has_ma20
has_ma60
has_ma120
has_atr20
has_weekly_features
can_compute_trend_atoms
can_compute_relative_strength_atoms
can_compute_liquidity_atoms
can_compute_overheat_atoms
missing_feature_names
```

## 8. 原子指标定义

第一版不输出综合分，只展示原子指标。

### 8.1 数据完整性

- 是否在实时场内 ETF 主池。
- 是否有历史行情。
- 历史行数。
- 最新交易日。
- 缺失交易日数量。
- 是否缺 OHLCV。
- 是否缺成交额。
- 是否缺 MA20、MA60、ATR20、周线字段。

### 8.2 趋势结构

- `close > ma20`
- `ma20 > ma60`
- `close > ma60`
- `ma60_slope_20`
- `weekly_close > weekly_ma10`
- `weekly_close > weekly_ma30`
- `weekly_ma10_slope`
- `weekly_ma30_slope`

### 8.3 相对强度

- `return_20`
- `return_60`
- `return_20_rank_all`
- `return_60_rank_all`
- `return_20_rank_category`
- `return_60_rank_category`
- 是否跑赢沪深300 20 日收益。
- 是否跑赢沪深300 60 日收益。

若沪深300指数数据缺失，基准比较字段显示缺失，不阻塞全池排名。

### 8.4 成交活跃

- `avg_amount_5`
- `avg_amount_20`
- `amount_ratio_5_20`
- 是否达到最低成交额阈值。
- 是否 `amount_ratio_5_20 > 1.0`
- 是否 `amount_ratio_5_20 > 1.2`

### 8.5 过热与位置

- `distance_ma20_pct`
- `distance_ma20_atr`
- `rolling_high_close_60`
- 是否突破 60 日收盘新高。
- 是否距离 20 日线超过 8%。
- 是否距离 20 日线超过 10%。
- 是否超过 20 日线加 2 倍 ATR。

## 9. 特征计算

### 9.1 日线特征

扩展现有 `add_technical_features()` 或新增兼容包装，确保所有 ETF 历史重算后至少包含：

```text
ma20
ma60
ma120
ma250
ma850
return_20
return_60
momentum_20
momentum_60
momentum_120
avg_amount_5
avg_amount_20
amount_ratio_5_20
ma60_slope_20
atr20
distance_ma20_atr
distance_ma20_pct
rolling_high_close_60
is_60d_close_breakout
```

`return_20` 和 `momentum_20` 可先保持同义，但建议显式保留 `return_*` 字段，便于 UI 展示“收益排名”，保留 `momentum_*` 给已有研究逻辑。

### 9.2 周线特征

新增周线特征计算函数：

```text
add_weekly_trend_features(prices)
```

输出回填到日线最后一个交易日或每个交易日可见的字段：

```text
weekly_close
weekly_ma10
weekly_ma30
weekly_ma10_slope
weekly_ma30_slope
weekly_close_above_ma10
weekly_close_above_ma30
```

第一版按周五或该周最后一个交易日收盘聚合，不预测未完成周。

## 10. 每日原子指标快照

新增每日快照生成能力：

```text
build_etf_atomic_indicator_snapshot(...)
```

输入：

- 场内 ETF 主池。
- 本地 ETF 历史。
- ETF 分类。
- 基准指数行情。
- 特征健康检查结果。

输出粒度为“一只 ETF 在一个交易日的一行”：

```text
trade_date
etf_code
name
category
exchange
history_status
feature_status
latest_trade_date
return_20
return_60
return_20_rank_all
return_60_rank_all
return_20_rank_category
return_60_rank_category
close_above_ma20
ma20_above_ma60
close_above_ma60
ma60_slope_20
weekly_close_above_ma10
weekly_close_above_ma30
avg_amount_5
avg_amount_20
amount_ratio_5_20
distance_ma20_pct
distance_ma20_atr
is_60d_close_breakout
missing_feature_names
```

快照可先保存到 Parquet：

```text
data/parquet/atomic_indicators/YYYY-MM-DD.parquet
```

后续如果需要查询历史变化，再考虑落 SQLite 或建立分区索引。

## 11. UI 设计

在 `ETF 数据` 下新增或替换一个子页：

```text
原子指标
```

第一版不显示综合分，不显示“买入”字样。表格默认按相对强度排名、成交额或用户选择排序。

### 11.1 顶部概览

指标卡：

- 实时场内 ETF 数量。
- 本地主表数量。
- 主表缺口数量。
- 已有历史 ETF 数量。
- 历史完整 ETF 数量。
- 可计算趋势指标 ETF 数量。
- 可计算相对强度 ETF 数量。

### 11.2 筛选器

- 分类。
- 是否只看场内可交易 ETF。
- 历史状态。
- 特征状态。
- 最新交易日是否完整。
- 最低 20 日平均成交额。
- 是否突破 60 日高点。
- 是否周线站上 10 周线。

### 11.3 表格字段

建议默认列：

```text
ETF代码
ETF名称
分类
最新交易日
历史状态
特征状态
20日收益
60日收益
20日全池排名
60日全池排名
20日同类排名
60日同类排名
收盘>MA20
MA20>MA60
收盘>MA60
周收盘>10周线
周收盘>30周线
5日/20日成交额
距20日线
距20日线ATR
突破60日高点
缺失字段
```

### 11.4 缺失原因展示

对不可计算 ETF，表格不隐藏。状态列直接说明原因，例如：

- 未拉历史。
- 历史不足 252 日。
- 最新数据滞后。
- 缺成交额。
- 缺 ATR。
- 周线数据不足。

## 12. 数据补齐流程

新增一个全量场内 ETF 历史补齐流程，和当前 watchlist-only 更新分开。

### 12.1 主表刷新

```text
fund_etf_spot_em
  -> normalize_exchange_traded_etf_spot
  -> upsert_etf_master
  -> mark exchange_traded
```

刷新后记录主表缺口和新增 ETF。

### 12.2 历史补齐

对 `exchange_traded` ETF 分批拉取历史：

- 已有历史：从本地最后日期向后滚动补齐。
- 无历史：按默认起始日期拉取，例如 5 年或上市以来可得历史。
- 新上市 ETF：允许历史不足，但状态标为 `short_history`。
- 拉取失败：写入 `data_update_state`，不阻塞其他 ETF。

### 12.3 特征回填

历史拉取后统一重算技术特征。旧 Parquet 中缺新字段时，即使没有新行情，也要允许只重算特征并覆盖写回。

## 13. 错误处理

- AkShare 主表拉取失败：保留本地旧主表，并在页面显示实时主表刷新失败。
- 单只 ETF 历史失败：记录失败状态，继续处理其他 ETF。
- 历史文件损坏：该 ETF 标为 `read_failed`，不参与指标计算。
- 指数基准缺失：基准跑赢字段为空，全池和同类排名继续计算。
- 缺成交额：成交活跃指标为空，不用 0 代替。
- 周线历史不足：周线字段为空，日线指标继续展示。

## 14. 测试设计

新增或更新测试：

- Provider 归一化测试：
  - `fund_etf_spot_em` 记录进入 `exchange_traded`。
  - `fund_name_em` 中 ETF 联接和 LOF 不进入可交易池。
  - 缺最新价和成交额的辅助记录不进入可交易池。
- 数据覆盖测试：
  - 主表数量、历史缺失、历史不足、最新日期滞后能正确标记。
  - 读文件失败不会中断整张表。
- 特征测试：
  - 计算 `avg_amount_5`、`amount_ratio_5_20`、`rolling_high_close_60`、`distance_ma20_pct`。
  - 周线特征按周最后交易日聚合。
- 排名测试：
  - 20 日和 60 日全池排名正确。
  - 同分类排名只在同一分类内计算。
  - 指数基准缺失时排名仍可生成。
- UI 数据帧测试：
  - 原子指标表不包含综合分字段。
  - 不出现正式买卖建议字段。
  - 缺失字段以原因展示。

## 15. 验收标准

1. 可交易 ETF 主池来自 `fund_etf_spot_em`，不混入 ETF 联接和 LOF。
2. 页面能显示实时主池数量、本地主表数量和差异。
3. 页面能显示全量 ETF 的历史覆盖状态。
4. 页面能显示原子指标，不显示综合加权分数。
5. 不生成任何正式交易动作。
6. 旧的 120 只 ETF 历史可以重算出新特征字段。
7. 新增全量历史补齐入口可以按场内 ETF 主池分批执行。
8. 单只 ETF 数据失败不会阻塞整批任务或页面渲染。

## 16. 后续扩展

基础能力稳定后，再考虑：

- 相对强度策略读取原子指标并定义组合规则。
- 策略实验室使用原子指标快照做回测因子输入。
- ETF 官方跟踪指数映射接入。
- 场外基金和 ETF 联接基金另建独立观察池。
- 更严格的交易所交易日历。
- 分批任务进度、失败重试和断点续跑 UI。
