# 指数历史估值源与估值体检设计

日期：2026-07-05
项目：`etf0614`

## 1. 背景

当前项目已经有指数历史行情、指数趋势状态、市场地图、指数买卖参考和指数 K 线。新的需求不是给指数算一个综合分，而是为每个指数建立一张全面、透明的估值体检表。

核心原则：

- 不计算指数点位本身的历史百分位。
- 不计算任何加权估值分、综合热度分、买卖分或温度计总分。
- 只展示估值原子指标，包括原始值、历史百分位、覆盖年限、数据源和缺失原因。
- 每个原子指标独立计算、独立标记状态，缺失或历史不足时留空并说明原因。
- 估值源要可切换，后续从 iFind、AKShare、Tushare、CSV 之间切换时，不应重写估值体检计算和 UI。

## 2. 目标

第一阶段要完成一个可长期使用的系统功能：

```text
估值源接入与覆盖体检
  -> 本地指数估值缓存
  -> 估值原子指标历史百分位
  -> 市场地图中的指数估值体检页面
```

系统应能回答：

- 每个指数有哪些估值字段：PE、PE_TTM、PB、PS、股息率、盈利收益率、ERP 等。
- 每个估值字段的当前值是多少。
- 当前值分别处在自身历史的什么位置。
- 每个字段有几年历史、来自哪个数据源、最新日期是哪一天。
- 哪些字段缺失、历史不足、日期滞后或不能计算。

## 3. 非目标

第一阶段不做以下内容：

- 不做自动交易。
- 不输出买入、卖出、减仓、目标仓位或账户金额。
- 不计算估值综合分、加权分、中位数汇总分或温度计分。
- 不把 PE/PB/股息率/ERP 混合成一个最终判断。
- 不用指数点位百分位替代估值百分位。
- 不在估值字段缺失时用其它字段补位。
- 不承诺所有指数都有 10 年估值历史；页面要如实展示覆盖差异。
- 不在本轮实现 CAPE，除非数据源已经能稳定提供足够长的 EPS 和 CPI 历史。

## 4. 数据源策略

采用多源适配层，而不是把数据源写死进体检计算逻辑。

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

估值体检模块只读取统一后的本地缓存，不直接调用外部数据源。

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
roe
payout_ratio
forward_pe
data_source
source_quality
source_updated_at
```

字段说明：

- `earnings_yield = 1 / pe_ttm`，仅在 `pe_ttm > 0` 时计算。
- `erp = earnings_yield - bond_yield_10y`，仅在盈利收益率和 10 年国债收益率同时存在时计算。
- `roe`、`payout_ratio`、`forward_pe` 是可选字段，只有数据源稳定提供时才展示。
- `data_source` 保留实际来源，例如 `ifind`、`akshare_legulegu`、`akshare_csindex`、`csv_import`。
- `source_quality` 第一版使用 `primary`、`fallback`、`recent_check`、`manual`。

## 6. 估值覆盖体检

新增覆盖体检表，粒度为“一只指数一行”：

```text
index_code
index_name
primary_source
available_fields
missing_fields
first_date
latest_date
sample_count
has_3y_history
has_5y_history
has_10y_history
coverage_status
coverage_reason
```

`coverage_status` 第一版：

- `complete`：核心估值字段覆盖充分。
- `partial`：有部分估值字段，但覆盖不完整。
- `insufficient_history`：有字段，但历史长度不足。
- `missing_valuation`：完全没有估值数据。
- `stale`：最新估值日期明显滞后于指数行情日期。
- `read_failed`：本地缓存读取失败。

这张表只说明数据健康，不产生估值分数。

## 7. 原子指标规则

这是硬性规则，优先级高于展示美观。

### 7.1 指标级状态

每个估值原子指标都必须有独立状态：

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

`status` 第一版：

- `computed`
- `missing_field`
- `insufficient_history`
- `stale`
- `invalid_value`
- `not_applicable`

如果状态不是 `computed`，`historical_percentile` 留空，页面展示 `reason`。

### 7.2 指标方向

每个原子指标只标记解释方向，不合成为总分：

```text
pe_ttm: 越高通常越贵
pe_static: 越高通常越贵
pb: 越高通常越贵
ps: 越高通常越贵
dividend_yield: 越低通常越贵
earnings_yield: 越低通常越贵
erp: 越低通常风险补偿越低
roe: 越高通常质量越好，但不是越便宜
payout_ratio: 只做分红结构观察
forward_pe: 越高通常越贵，但依赖预测口径
```

页面可以显示“高/中/低百分位”这样的单字段标签，但不能把多个标签合成为一个最终估值结论。

### 7.3 禁止的计算

第一版明确禁止：

- `valuation_hot_pct`
- `综合过热度`
- `估值总分`
- `买卖分`
- PE/PB/股息率/ERP 的加权平均。
- PE/PB/股息率/ERP 的中位数汇总分。
- 用缺失字段的默认值参与任何计算。

## 8. 百分位计算

每个原子指标独立计算历史百分位：

```text
percentile_t = 100 * (count(x_s < x_t) + 0.5 * count(x_s = x_t)) / count(x_s)
```

只允许使用 `date <= t` 的历史数据。

默认窗口：

- 长期窗口：全部可比历史，至少 5 年才标记为可靠。
- 滚动窗口：10 年；历史不足 10 年时显示实际覆盖年数。
- 最低计算门槛：3 年或 756 个交易日左右。字段低于门槛时不计算该字段百分位。

不同指标的百分位不横向混合。沪深300的 PE 百分位、红利指数的 PB 百分位、恒生科技的股息率百分位都只在自身历史里解释。

## 9. 原子指标清单

第一版主表和详情页围绕这些估值原子指标：

```text
pe_ttm
pe_static
pb
ps
dividend_yield
earnings_yield
bond_yield_10y
erp
roe
payout_ratio
forward_pe
```

每个指标展示：

```text
当前值
历史百分位
当前窗口覆盖年数
历史最小值
历史最大值
历史中位数
数据源
最新日期
状态
缺失原因
```

其中历史最小值、最大值、中位数只是该指标自己的描述统计，不参与其它指标的合成。

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

### 10.2 体检流程

```text
ParquetStore.read_index_valuations(index_code)
ParquetStore.read_macro_series(...)
  -> build_index_valuation_healthcheck(...)
  -> build_index_valuation_metric_rows(...)
```

体检模块必须返回原子指标行和状态，不允许只返回数字。

## 11. UI 设计

在 `市场地图` 新增子页：

```text
指数估值体检
```

建议二级入口顺序：

```text
市场总览
指数估值体检
指数买卖参考
指数K线
```

### 11.1 顶部概览

展示 4-6 个紧凑指标：

- 指数总数。
- 估值数据完整指数数。
- 估值部分缺失指数数。
- 估值历史不足指数数。
- 最新估值日期。
- 主数据源状态。

### 11.2 全指数覆盖表

默认列：

```text
指数代码
指数名称
分类
估值覆盖状态
可用字段
缺失字段
估值源
估值最早日期
估值最新日期
覆盖年数
缺失说明
```

这张表不显示综合分。

### 11.3 单指数原子指标表

选择指数后展示该指数的估值原子指标表：

```text
指标
当前值
历史百分位
覆盖年数
历史最小值
历史中位数
历史最大值
数据源
最新日期
状态
说明
```

缺失字段必须直接可见。表格不能把缺失指标显示为 0、50 或其它默认值。

### 11.4 单指标历史图

第一版可以为选中的原子指标展示历史曲线和当前百分位位置：

- PE_TTM 历史曲线。
- PB 历史曲线。
- 股息率历史曲线。
- ERP 历史曲线。

图表只展示单指标历史，不叠加综合评分。

## 12. 错误处理

- 外部源失败：保留本地缓存，页面显示源失败和缓存最新日期。
- 单指数估值缺失：该指数覆盖状态为 `missing_valuation`。
- 单字段缺失：该字段状态为 `missing_field`，百分位留空。
- 宏观数据缺失：ERP 不计算，并显示 `bond_yield_10y missing`。
- 估值日期滞后：相关字段状态为 `stale`。
- 负 PE 或 0 PE：盈利收益率不计算；PE 字段是否展示由字段质量规则决定。
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
  - 单指标经验分布百分位处理相等值。
  - 滚动窗口不使用未来数据。
- 缺失规则测试：
  - 字段不足时该字段百分位为空。
  - 缺失字段不会被格式化成 0、50 或 `0.0%`。
  - 不存在 `valuation_hot_pct`、综合估值分或买卖分字段。
- UI view-model 测试：
  - 覆盖表包含可用字段、缺失字段和缺失说明。
  - 原子指标表包含每个字段的状态和说明。
  - 不出现正式买入、卖出、目标仓位字段。
- 导航测试：
  - `市场地图` 包含 `指数估值体检`。
  - `ETF数据` 不出现指数估值体检入口。

## 14. 验收标准

第一阶段完成时必须满足：

1. 可以配置并切换指数估值源。
2. 可以将指数估值历史写入本地 Parquet 缓存。
3. 可以生成全指数估值覆盖体检表。
4. 可以生成单指数估值原子指标表。
5. 每个原子指标独立展示当前值、历史百分位、覆盖年数、数据源和状态。
6. 数据缺失、历史不足、值无效或日期滞后时，该指标百分位为空并显示原因。
7. 不计算任何估值综合分、加权分、中位数汇总分或买卖分。
8. 页面明确显示缺失字段、历史长度、数据源和最新日期。
9. 所有百分位计算只使用当前日期及之前的数据。
10. 后续新增数据源只需实现 provider，不需要重写估值体检计算和 UI。

## 15. 实施顺序

1. 新增估值 provider 接口和归一化函数。
2. 新增 Parquet 读写能力。
3. 新增估值覆盖体检。
4. 新增单指标百分位和估值原子指标体检模块。
5. 接入 AKShare 乐咕和中证近期估值 fallback。
6. 预留 iFind provider 接口，等 MCP 工具可用后补实际调用。
7. 新增 NiceGUI `市场地图 -> 指数估值体检` 页面。
8. 补充测试并运行目标测试和全量测试。

## 16. 结论

第一版的重点不是给指数一个漂亮分数，而是建立可信的数据源、覆盖体检和估值原子指标表。

每个估值字段单独展示、单独解释、单独标记缺失。系统只告诉用户这个指数的 PE、PB、股息率、ERP 等指标当前处在自身历史什么位置，不把它们合成为一个貌似精确的买卖判断。
