# 指数趋势策略回测实施计划（中文版）

> 执行本计划时，必须使用 `subagent-driven-development`（推荐）或 `executing-plans` 技能，严格按照任务顺序实施，并使用测试驱动开发。

**目标：** 建立一套可重复运行的单指数趋势研究流程，对本地指数库分别回测“MA60＋ATR”“MA250”“通道突破”三种择时策略，并与各指数的买入持有结果比较，最终判断主策略是否达到预先约定的有效性标准。

**总体结构：** 在现有ETF研究框架旁新增独立的指数研究流程，包括指数数据准入、趋势信号生成、T+1成交模拟、历史与样本外验证、结果发布和策略实验室展示。指数研究使用独立模型和模块，不改变现有ETF回测行为。

**技术环境：** Python 3.11、pandas、NumPy、PyArrow/Parquet、PyYAML、NiceGUI、pytest。

## 一、全局约束

- 每个指数单独回测，只允许全仓持有或空仓。
- 不做空、不加杠杆、不进行指数轮动，也不使用跨指数强弱排名。
- 当日收盘后产生信号，下一有效交易日开盘成交。
- 买入滑点为0.02%，卖出滑点为0.02%，手续费为成交金额的0.015%。
- 压力测试同时将手续费和滑点提高到默认值的两倍。
- 空仓资金收益按0计算。
- 主结论只纳入具有官方基日证据、且官方基日后至少有1000个有效交易日的指数。
- 固定样本外区间从2019年1月1日开始；指数必须在此前已有足够指标预热数据，才能进入完整样本外总体统计。
- 默认参数固定为MA60和3倍ATR。MA50/60/70与2.5/3.0/3.5倍ATR只用于稳定性检查，不能根据回测收益挑选最优参数替换默认值。
- 研究结果写入 `reports/`，不提交到Git。
- 自动化测试不得访问Tushare、AkShare或互联网。

## 二、文件与模块划分

新增以下文件：

- `configs/index_research.yaml`：锁定策略参数、费用、验证区间和有效性门槛。
- `src/etf_trading/research/index_models.py`：配置、数据准入、研究输出和有效性判断模型。
- `src/etf_trading/research/index_data.py`：指数数据加载、官方基日校验、质量检查和指标计算。
- `src/etf_trading/research/index_signals.py`：三种趋势策略的纯信号生成逻辑。
- `src/etf_trading/research/index_backtest.py`：指数专用T+1成交、买入持有基准、交易审计和绩效指标。
- `src/etf_trading/research/index_validation.py`：全历史、样本外、年度、市场阶段、参数邻域和费用压力验证。
- `src/etf_trading/research/index_report.py`：CSV、Parquet和中文Markdown报告发布。
- `scripts/run_index_research.py`：命令行研究入口。
- 六个对应的 `tests/test_index_research_*.py` 测试文件。

修改以下文件：

- `src/etf_trading/nicegui_app/navigation.py`：在策略实验室增加“指数趋势回测”。
- `src/etf_trading/nicegui_app/pages/research.py`：读取并展示已经生成的研究结果。
- `tests/test_nicegui_navigation.py`：验证新增导航。
- `docs/task-memory.md`：记录最终验证结果和研究限制。

## 三、任务1：配置、模型与数据准入

### 实现内容

建立 `configs/index_research.yaml`，固定以下默认值：

- 主趋势均线：60日；
- 快速均线：20日；
- 均线斜率窗口：20日；
- 动量窗口：60日和120日，跳过最近5日；
- 最大追涨距离：2倍ATR；
- ATR移动止损：3倍；
- 手续费：0.00015；
- 滑点：0.0002；
- 压力倍数：2；
- 最少有效交易日：1000；
- 样本外开始日：2019-01-01。

数据加载器逐个读取指数目录和Parquet文件。每个指数只能得到两种结果之一：成功纳入，或者产生一条明确的排除记录。

排除情形包括：

- 没有官方基日证据；
- 缺少基日；
- 文件不存在；
- 缺少OHLC或交易日期；
- 日期无效或重复；
- OHLC存在非正数；
- 官方基日后的有效历史不足1000日。

缺失开盘价暂不在数据层删除，交给成交引擎处理。计算MA20、MA50、MA60、MA70、MA250、相应20日斜率、跳过最近5日的60/120日动量、ATR20、距离MA20的ATR倍数，以及不包含当日的60日最高和20日最低收盘价。

### 验证

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_data.py tests\test_index_catalog.py -q
```

通过后提交：

```powershell
git commit -m "feat: admit index histories for trend research"
```

## 四、任务2：趋势策略信号

### MA60＋ATR主策略

空仓时必须同时满足：

- 收盘价高于MA60；
- MA20高于MA60；
- MA60过去20日斜率为正；
- 60日和120日跳过最近5日的动量均为正；
- 价格距离MA20不超过2倍ATR。

持仓时满足任意一项即卖出：

- 收盘价低于MA60；
- 收盘价不高于持仓以来最高收盘价减去3倍ATR。

### MA250对照策略

- 收盘价高于MA250时买入；
- 收盘价低于MA250时卖出。

### 通道突破对照策略

- 收盘价突破此前60个交易日的最高收盘价时买入；
- 收盘价跌破此前20个交易日的最低收盘价或触发3倍ATR移动止损时卖出。

滚动最高和最低必须排除当日，防止未来数据或当日数据泄漏。信号生成模块不处理资金和成交，只输出信号日期、动作、原因和触发规则。

### 验证

重点测试买入条件边界、均线退出、ATR退出、等于均线时不卖出、指标缺失时不产生信号，以及通道窗口不包含当日。

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_signals.py tests\test_research_signals.py -q
```

通过后提交：

```powershell
git commit -m "feat: generate locked index trend signals"
```

## 五、任务3：严格T+1成交与绩效指标

指数研究使用独立回测引擎，避免改变现有ETF回测行为。

### 成交规则

- 收盘后产生的目标仓位在下一有效开盘执行；
- 缺失或无效开盘价时，信号保持待执行；
- 等待期间如果出现更新的目标信号，以最新信号替换旧信号，并记录旧信号被替换；
- 回测结束仍没有有效开盘价时，记录为无法成交；
- 跳空退出使用真实开盘价，不能使用理论止损价；
- 买卖方向分别计入滑点和手续费。

### 买入持有基准

在评价区间内第一个有效开盘全仓买入，使用与策略相同的买入费用，持有到最后一个有效收盘，不虚构期末卖出。

### 输出指标

- 总收益、年化收益、年化波动率、夏普；
- 最大回撤、回撤开始日、谷底日、恢复日和从前高到恢复的天数；
- Calmar、平均持仓比例；
- 交易次数、完整交易次数、胜率、平均单笔收益和平均持有天数。

### 验证

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_backtest.py tests\test_backtest.py tests\test_research_metrics.py -q
```

通过后提交：

```powershell
git commit -m "feat: execute strict index timing backtests"
```

## 六、任务4：验证矩阵与有效性门槛

### 回测矩阵

对每个成功纳入的指数执行：

1. 确定所有策略共同可计算的首日，确保四种方案起点一致；
2. 运行全历史的三种策略和买入持有；
3. 运行2019年至今的完整样本外回测；
4. 2019年后才满足条件的指数标记为“后进入样本”，不混入完整样本外总体统计；
5. 生成逐年结果和2015、2018、2020、2022年阶段结果；
6. 运行MA50/60/70与ATR 2.5/3.0/3.5组成的九组参数邻域；
7. 使用双倍费用重复默认主策略。

### 六项有效性标准

主策略必须同时满足：

1. 完整样本外指数中，至少60%的最大回撤优于买入持有；
2. 最大回撤绝对值的中位数相对买入持有减少至少20%；
3. Calmar中位数高于买入持有；
4. 年化收益中位数高于买入持有，或落后不超过2个百分点；
5. 默认参数不是参数邻域中的孤立峰值；
6. 双倍费用下前四项结论不发生反转。

全部通过标记为“通过”，前四项通过但稳定性或费用测试失败标记为“部分通过”，其他情况标记为“未通过”。不得因为最终结果不好而修改标准。

配对统计以同一指数的“策略减买入持有”为单位，输出平均数、中位数、25%和75%分位数、最差十个指数，以及固定随机种子、2000次重采样的描述性区间。报告必须说明指数之间高度相关，该区间不能解释为独立样本置信区间。

### 验证

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_validation.py tests\test_index_research_data.py tests\test_index_research_signals.py tests\test_index_research_backtest.py -q
```

通过后提交：

```powershell
git commit -m "feat: validate index trend effectiveness"
```

## 七、任务5：结果文件、中文报告和命令行入口

研究任务以原子方式发布以下八个文件：

- `index_backtest_results.csv`：逐指数、策略和区间指标；
- `index_backtest_trades.csv`：交易明细和退出原因；
- `index_strategy_summary.csv`：总体统计和六项门槛；
- `index_strategy_yearly.csv`：逐年和市场阶段结果；
- `index_strategy_sensitivity.csv`：参数邻域与费用压力结果；
- `index_strategy_exclusions.csv`：排除指数及原因；
- `index_strategy_nav.parquet`：绘图使用的逐日净值；
- `index_trend_strategy_report.md`：中文研究报告。

所有文件先写入临时路径，全部成功且结构验证通过后才替换正式结果。任何一步失败都不能留下半套新结果，也不能破坏上一套完整结果。

中文报告按照以下顺序组织：

1. 最终结论；
2. 六项门槛的实际值和判断；
3. 样本外配对比较；
4. 全历史参考；
5. 双倍费用结果；
6. 参数稳定性；
7. 最好、最差和无效指数；
8. 年度与市场阶段；
9. 排除项、数据覆盖和研究限制。

运行命令：

```powershell
.venv-win\Scripts\python.exe scripts\run_index_research.py --output-dir reports\index_research
```

先使用两个指数进行冒烟验证：

```powershell
.venv-win\Scripts\python.exe scripts\run_index_research.py --limit 2 --output-dir reports\index_research_smoke
```

通过后提交：

```powershell
git commit -m "feat: publish index trend research reports"
```

## 八、任务6：策略实验室展示

在“策略实验室”中新增“指数趋势回测”栏目。页面只读取已经发布的结果，打开页面时不得重新计算策略，也不得覆盖结果文件。

页面按照以下层级展示：

1. 总体结论和六项有效性门槛；
2. 完整样本外的策略比较；
3. 指数代码和名称选择器；
4. 单指数策略与买入持有净值曲线；
5. 回撤曲线；
6. 年度收益和交易记录；
7. 参数稳定性和双倍费用结果；
8. 排除原因、数据覆盖和限制说明。

结果加载状态必须明确区分：结果不存在、文件不完整、文件结构无效、结果可用。表格需要分页，移动端不能产生页面级横向溢出。

### 验证

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_page.py tests\test_nicegui_navigation.py tests\test_nicegui_app_import.py tests\test_nicegui_theme.py -q
```

随后启动应用，在1440像素和390像素宽度下检查真实结果页面，确认选择器、净值图、回撤图和表格正常，浏览器控制台没有错误。

通过后提交：

```powershell
git commit -m "feat: show index trend research in strategy lab"
```

## 九、任务7：全指数运行与最终验证

### 自动化验证

```powershell
.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-backtest-full
```

必须保证全部测试通过，并且现有ETF回测行为没有变化。

### 全指数研究

```powershell
.venv-win\Scripts\python.exe scripts\run_index_research.py --output-dir reports\index_research
```

必须满足：

- 指数目录中的每个指数都有回测结果或明确排除原因；
- 八个结果文件全部存在且可读取；
- 没有遗留临时文件；
- 汇总文件中恰好保存六项有效性判断；
- 页面、CSV和Markdown报告中的数字一致；
- 只有六项门槛全部通过时，才能对用户表述为“通过预设有效性标准”。

使用真实全量结果再次完成桌面端和移动端页面检查。最后在 `docs/task-memory.md` 记录：

- 实现内容；
- 完整测试命令与结果；
- 纳入和排除指数数量；
- 六项门槛的最终状态；
- 浏览器验证结果；
- 官方基日、存续偏差、指数相关性以及指数信号映射ETF时的风险。

## 十、最终验收标准

- 三种策略规则与确认后的设计完全一致；
- 主结果没有混入官方基日前历史或基日证据不足的指数；
- 所有成交严格发生在信号后的下一有效开盘；
- 跳空交易使用实际开盘价，费用方向正确；
- 全历史、完整样本外、后进入样本、逐年、市场阶段、九组参数和双倍费用结果均可识别；
- 六项门槛无论通过或失败都完整展示；
- 每个指数都有结果或排除原因；
- CSV、Markdown和页面使用同一套持久化结果；
- 全量自动化测试通过，现有ETF逻辑不受影响；
- 页面经过真实结果的桌面端和移动端验证；
- 最终结论明确区分历史证据与未来收益，并披露存续偏差、指数相关性和ETF执行差异。

## 十一、执行方式

实施时可以选择：

1. **子代理分任务执行（推荐）**：七个任务依次交给独立子代理，每个任务完成后进行规格符合性和代码质量审查，再进入下一项。
2. **当前会话直接执行**：在当前会话使用 `executing-plans` 技能分批实施，在固定检查点汇报测试和结果。

英文逐步执行清单保留在：`docs/superpowers/plans/2026-07-29-index-trend-backtest.md`。
