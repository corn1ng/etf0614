# 指数历史估值源与温度计设计

日期：2026-07-05
项目：`etf0614`

## 1. 背景

当前项目已经有指数历史行情、指数趋势状态、市场地图、指数买卖参考和指数 K 线。新的目标是在所有指数上做历史位置分析，用来辅助买卖判断。核心原则已经确认：

- 不计算指数点位本身的历史百分位。
- 必须计算可解释指标的历史百分位，包括估值、趋势、波动和回撤。
- 估值数据不能缺失后静默降级；如果字段或历史长度不足，页面必须明确显示缺失情况。
- 估值源要可切换，后续从 iFind、AKShare、Tushare、CSV 之间切换时，不应重写温度计计算和 UI。

## 2. 目标

第一阶段要完成一个可长期使用的系统功能：

```text
估值源接入与覆盖体检
  -> 本地指数估值缓存
  -> 四维历史百分位计算
  -> 市场地图中的指数温度计页面
```

系统应能回答：

- 每个指数有没有 PE、PB、股息率、ERP 等估值历史。
- 每个估值字段的历史长度是否足够计算 3 年、5 年或 10 年百分位。
- 当前指数是估值偏贵、趋势偏强、波动偏高，还是处在深回撤状态。
- 哪些结果因为数据缺失没有计算，缺的是哪个字段或哪个时间段。

## 3. 非目标

第一阶段不做以下内容：

- 不做自动交易。
- 不把温度计分数直接变成账户买卖金额。
- 不用指数点位百分位替代估值百分位。
- 不在估值字段缺失时用其它字段强行凑出完整估值热度。
- 不承诺所有指数都有 10 年估值历史；页面要如实展示覆盖差异。
- 不在本轮实现 CAPE，除非数据源已经能稳定提供足够长的 EPS 和 CPI 历史。

## 4. 数据源策略

采用多源适配层，而不是把数据源写死进计算逻辑。

### 4.1 数据源优先级

1. `iFind`：主源。优先用于指数 PE、PB、股息率、指数历史估值、10 年国债收益率和 CPI。
2. `AKShare 乐咕乐股`：免费长历史 fallback。主要覆盖常用宽基指数 PE/PB，例如沪深300、中证500等。
3. `AKShare 中证官网估值`：近期官方校验源。适合校验最新 PE、股息率，不适合作为长历史百分位主源。
4. `CSV/Parquet 导入`：兜底源。用于手工补齐或未来替换专业数据源。

### 4.2 Provider 边界

新增统一接口：

```text
IndexValuationProvider
  fetch_index_valuation(index_code, start_date, end_date) -> DataFrame
  fetch_macro_series(series_name, start_date, end_date) -> DataFrame
  source_name -> str
```

第一版候选实现：

```text
IFindIndexValuationProvider
AkshareLeguleguValuationProvider
AkshareCsindexRecentValuationProvider
CsvIndexValuationProvider
```

温度计计算模块只读取统一后的本地缓存，不直接调用外部数据源。

## 5. 本地缓存模型

新增本地缓存路径：

```text
data/parquet/index_valuations/{index_code}.parquet
data/parquet/macro/10y_bond_yield.parquet
data/parquet/macro/cpi.parquet
```

指数估值统一字段：

```text
index_code
trade_date
pe_ttm
pe_static
pb
ps
dividend_yield
earnings_yield
bond_yield_10y
erp
data_source
source_quality
source_updated_at
```

字段说明：

- `earnings_yield = 1 / pe_ttm`，仅在 `pe_ttm > 0` 时计算。
- `erp = earnings_yield - bond_yield_10y`，仅在盈利收益率和 10 年国债收益率同时存在时计算。
- `data_source` 保留实际来源，例如 `ifind`、`akshare_legulegu`、`akshare_csindex`、`csv_import`。
- `source_quality` 第一版使用 `primary`、`fallback`、`recent_check`、`manual`。

## 6. 估值覆盖体检

新增覆盖体检表，粒度为“一只指数一行”：

```text
index_code
index_name
primary_source
available_fields
first_date
latest_date
sample_count
has_3y_history
has_5y_history
has_10y_history
field_gaps
coverage_status
coverage_reason
```

`coverage_status` 第一版：

- `complete`：至少一个核心估值字段满足最低历史要求，且可计算估值热度。
- `partial`：有部分估值字段，但不能完整计算推荐的估值热度。
- `insufficient_history`：有字段，但历史长度不足。
- `missing_valuation`：完全没有估值数据。
- `stale`：最新估值日期明显滞后于指数行情日期。
- `read_failed`：本地缓存读取失败。

## 7. 缺失数据规则

这是硬性规则，优先级高于展示美观和综合分完整性。

### 7.1 维度级缺失

四维温度计的每个维度独立给出状态：

```text
valuation_status
trend_status
volatility_status
drawdown_status
```

状态值：

- `computed`
- `missing_field`
- `insufficient_history`
- `stale`
- `not_applicable`

如果某个维度不是 `computed`，该维度分数显示为空，并展示原因。

### 7.2 估值热度缺失

估值热度不能因为部分字段缺失而无提示地计算。

第一版规则：

- 至少需要 `pe_ttm` 或 `pb` 中一个字段满足最低历史要求。
- 推荐估值热度使用 `pe_ttm_pct`、`pb_pct`、`100 - dividend_yield_pct`、`100 - earnings_yield_pct`、`100 - erp_pct` 的中位数。
- 每个参与字段必须在详情中列出。
- 每个缺失字段也必须在详情中列出。
- 如果只有一个估值字段可用，页面显示 `partial`，并标记“单字段估值热度，谨慎使用”。
- 如果没有任何核心估值字段满足最低历史要求，`valuation_hot_pct` 为空。

### 7.3 综合显示规则

全指数表中不能只显示一个总分。默认显示四维分数和四维状态。

如果未来增加综合过热度，必须满足：

- 只用 `computed` 的维度。
- 明确显示参与维度数量。
- 当估值维度缺失时，综合分不命名为“估值温度”或“买卖分”。
- 第一版不输出综合买卖动作。

## 8. 百分位计算

百分位采用经验分布口径：

```text
percentile_t = 100 * (count(x_s < x_t) + 0.5 * count(x_s = x_t)) / count(x_s)
```

只允许使用 `date <= t` 的历史数据。

默认窗口：

- 长期窗口：全部可比历史，至少 5 年才显示为可靠。
- 滚动窗口：10 年；历史不足 10 年时显示实际覆盖年数。
- 最低计算门槛：3 年或 756 个交易日左右。估值字段低于门槛不参与估值热度。

## 9. 四维温度计指标

### 9.1 估值热度

候选字段：

```text
pe_ttm_pct
pe_static_pct
pb_pct
ps_pct
100 - dividend_yield_pct
100 - earnings_yield_pct
100 - erp_pct
```

解释方向：

```text
越高 = 越贵 / 越热 / 未来收益补偿越低
```

### 9.2 趋势强度

复用指数行情缓存：

```text
ret_6m_pct
ret_12m_pct
ma200_gap_pct
ma756_gap_pct
```

第一版可先使用 `ret_6m_pct`、`ret_12m_pct`、`ma200_gap_pct` 的中位数。

### 9.3 波动风险

基于日收益率：

```text
vol_20d_pct
vol_60d_pct
downside_vol_pct
```

第一版可先使用 `vol_20d_pct`、`vol_60d_pct` 的中位数。

### 9.4 回撤压力

基于指数历史行情：

```text
drawdown_stress = -current_drawdown
drawdown_stress_pct
drawdown_duration_pct
```

解释方向：

```text
越高 = 跌得越深或修复越慢，不代表越贵
```

## 10. 数据流

### 10.1 同步流程

```text
IndexValuationProvider
  -> normalize_index_valuation(...)
  -> ParquetStore.write_index_valuations(...)
  -> build_index_valuation_coverage(...)
```

宏观数据：

```text
IFind / CSV / other macro provider
  -> normalize_macro_series(...)
  -> ParquetStore.write_macro_series(...)
  -> merge bond_yield_10y into valuation cache
```

### 10.2 计算流程

```text
ParquetStore.read_index_prices(index_code)
ParquetStore.read_index_valuations(index_code)
ParquetStore.read_macro_series(...)
  -> build_index_temperature_frame(...)
  -> build_index_temperature_coverage(...)
```

温度计模块必须返回分数和状态，不允许只返回数字。

## 11. UI 设计

在 `市场地图` 新增子页：

```text
指数温度计
```

建议二级入口顺序：

```text
市场总览
指数温度计
指数买卖参考
指数K线
```

### 11.1 顶部概览

展示 4-6 个紧凑指标：

- 指数总数。
- 可计算估值热度指数数。
- 估值缺失指数数。
- 估值历史不足指数数。
- 最新估值日期。
- 数据源状态。

### 11.2 主表

默认列：

```text
指数代码
指数名称
分类
估值热度
估值状态
趋势强度
趋势状态
波动风险
波动状态
回撤压力
回撤状态
估值源
估值最早日期
估值最新日期
覆盖年数
缺失说明
```

缺失字段必须直接可见。表格不能把缺失维度显示为 0、50 或其它默认值。

### 11.3 单指数详情

选择指数后展示：

- 四维温度计。
- 每个估值字段的当前值、百分位、历史窗口、数据源。
- 未参与计算的字段及原因。
- 行情指标：6 月收益、12 月收益、MA200 偏离、波动、回撤。
- 数据日期对齐提示：估值日期、行情日期、宏观日期。

## 12. 错误处理

- 外部源失败：保留本地缓存，页面显示源失败和缓存最新日期。
- 单指数估值缺失：该指数估值维度为空，不影响趋势、波动、回撤。
- 宏观数据缺失：ERP 不计算，并在估值详情中显示 `bond_yield_10y missing`。
- 估值日期滞后：估值状态为 `stale`，不参与最新估值热度。
- 负 PE 或 0 PE：不计算盈利收益率；PE 百分位是否参与由字段质量规则决定。
- 多源冲突：保留主源值，同时记录校验源差异，第一版只展示差异提示，不自动混合。

## 13. 测试设计

新增或更新测试：

- Provider 归一化测试：
  - iFind、乐咕、中证近期估值能归一到统一字段。
  - 缺列、中文列名、日期倒序能正常处理。
- 缓存测试：
  - `ParquetStore` 能读写指数估值和宏观序列。
- 覆盖体检测试：
  - 完整、部分、历史不足、缺失、滞后状态能正确标记。
- 百分位测试：
  - 经验分布百分位处理相等值。
  - 滚动窗口不使用未来数据。
- 缺失规则测试：
  - 估值字段不足时 `valuation_hot_pct` 为空。
  - 单字段估值状态为 `partial`。
  - 趋势、波动、回撤可在估值缺失时单独计算，但必须显示估值缺失。
- UI view-model 测试：
  - 主表包含四维状态和缺失说明。
  - 缺失分数不会被格式化成 0、50 或 `0.0%`。
  - 不出现正式买入、卖出、目标仓位字段。
- 导航测试：
  - `市场地图` 包含 `指数温度计`。
  - `ETF数据` 不出现指数估值温度计入口。

## 14. 验收标准

第一阶段完成时必须满足：

1. 可以配置并切换指数估值源。
2. 可以将指数估值历史写入本地 Parquet 缓存。
3. 可以生成估值覆盖体检表。
4. 可以计算四维温度计，并且每个维度带状态和缺失原因。
5. 估值数据缺失或历史不足时，不计算估值热度。
6. 页面明确显示缺失字段、历史长度、数据源和最新日期。
7. 趋势、波动、回撤不会因为估值缺失而被阻断。
8. 全指数表不显示单一买卖分，不输出正式交易动作。
9. 所有百分位计算只使用当前日期及之前的数据。
10. 后续新增数据源只需实现 provider，不需要重写温度计计算和 UI。

## 15. 实施顺序

1. 新增估值 provider 接口和归一化函数。
2. 新增 Parquet 读写能力。
3. 新增估值覆盖体检。
4. 新增百分位和四维温度计计算模块。
5. 接入 AKShare 乐咕和中证近期估值 fallback。
6. 预留 iFind provider 接口，等 MCP 工具可用后补实际调用。
7. 新增 NiceGUI `市场地图 -> 指数温度计` 页面。
8. 补充测试并运行目标测试和全量测试。

## 16. 结论

第一版的重点不是尽快给每个指数一个漂亮分数，而是建立可信的数据源、覆盖体检和缺失显示机制。

只有当估值字段和历史长度达标时，系统才计算估值热度。否则页面必须直接告诉用户缺什么、缺多久、来自哪个源。这样温度计才能用于辅助买卖，而不是用不完整数据制造错误信号。
