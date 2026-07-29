# 指数趋势基准策略 V1 实施计划

> **供智能代理执行：** 必须使用 `subagent-driven-development`（推荐）或 `executing-plans` 技能逐项实施。以下步骤使用复选框跟踪，严格执行测试驱动开发和逐任务提交。

**目标：** 建立可每日重复运行的指数趋势回测系统，用全部合格指数历史检验固定的“MA60 上下 2% 缓冲带＋3 倍 ATR20 紧急退出”策略，并从页面发现数据过期、启动后台重算和查看完整证据。

**架构：** 在现有 ETF 研究模块旁增加指数专用流水线：分层数据准入、固定 V1 状态机、严格 T+1 成交、全历史与五年滚动验证、版本化原子发布、后台任务和只读结果页面。第一阶段只验证指数理论信号；ETF 实际执行验证在指数策略通过标准后另行设计。

**技术栈：** Python 3.11、pandas 2.2+、NumPy 1.26+、PyArrow/Parquet、PyYAML、NiceGUI 3.14+、pytest 8.2+

## 全局约束

- 正式策略名称固定为 `index_trend_v1`，锁定日期为 `2026-07-30`。
- 入场上轨固定为 `MA60 × 1.02`，正常退出下轨固定为 `MA60 × 0.98`。
- 紧急退出固定为持仓最高收盘价减去 `3 × ATR20`。
- 不测试 MA50、MA70、ATR 2.5、ATR 3.5，不使用动量、强弱排名、MA20 排列或通道突破。
- 0% 和 3% 缓冲版本只用于解释 2% 是否减少假突破，不能替换 V1。
- 每个指数只允许 0% 或 100% 仓位，不做空、不加杠杆、不轮动。
- T 日收盘产生信号，下一有效交易日开盘成交；买卖滑点均为 0.02%，手续费为成交金额的 0.015%。
- 空仓收益为 0；双倍费用仅用于压力测试。
- 主结论只使用官方基日样本；第三方基日样本单列；出版日和未核验基日样本排除。
- 官方基日后至少需要 1,000 个有效交易日。
- 使用全部有效历史、逐年和五年滚动窗口；不使用历史数据拟合参数。
- 锁定日之后首次获得的新交易日才标记为真正的 `prospective_oos`。
- 结果写入 `reports/index_research/`，不得提交生成数据。
- 现有 ETF 回测行为和测试不得改变。
- 自动化测试不得调用网络数据源。

---

## 文件结构

- 创建 `configs/index_research.yaml`：V1 规则、成本、历史窗口、门槛和锁定日期。
- 创建 `src/etf_trading/research/index_models.py`：配置、准入、交易、结果、任务状态模型。
- 创建 `src/etf_trading/research/index_data.py`：指数数据分层准入、质量检查和 MA60/ATR20 特征。
- 创建 `src/etf_trading/research/index_trend_v1.py`：固定策略状态机，不提供通用策略插件机制。
- 创建 `src/etf_trading/research/index_backtest.py`：严格 T+1 成交、买入持有和交易审计。
- 创建 `src/etf_trading/research/index_metrics.py`：收益、回撤、交易质量和假突破指标。
- 创建 `src/etf_trading/research/index_validation.py`：全历史、年度、五年滚动、缓冲带消融、费用压力和六项门槛。
- 创建 `src/etf_trading/research/index_report.py`：版本化结果目录、原子 latest 指针和中文报告。
- 创建 `src/etf_trading/research/index_jobs.py`：后台运行、互斥、进度、取消和过期判断。
- 创建 `scripts/run_index_research.py`：与页面共用的命令行入口。
- 修改 `src/etf_trading/nicegui_app/navigation.py` 和 `src/etf_trading/nicegui_app/pages/research.py`：新增“指数趋势回测”。
- 创建对应的 `tests/test_index_research_*.py` 聚焦测试。
- 修改 `docs/task-memory.md`：记录最终证据、限制和运行方法。

---

### 任务1：锁定配置、数据分层准入与指标

**文件：**

- 创建：`configs/index_research.yaml`
- 创建：`src/etf_trading/research/index_models.py`
- 创建：`src/etf_trading/research/index_data.py`
- 测试：`tests/test_index_research_data.py`

**接口：**

- 输入：`default_index_catalog()`、`ParquetStore.read_index_prices(code)`。
- 输出：`load_index_research_config(path) -> IndexResearchConfig`。
- 输出：`load_index_frames(parquet_root, catalog, config) -> IndexAdmissionResult`。
- 输出：`add_index_trend_features(frame) -> pd.DataFrame`。

- [ ] **步骤1：编写失败的配置和准入测试**

```python
def test_config_locks_v1_without_parameter_grid():
    config = load_index_research_config("configs/index_research.yaml")
    assert config.strategy_version == "index_trend_v1"
    assert config.locked_at == date(2026, 7, 30)
    assert config.ma_window == 60
    assert config.buffer_rate == 0.02
    assert config.atr_window == 20
    assert config.atr_multiple == 3.0
    assert config.buffer_ablation == (0.0, 0.02, 0.03)
    assert not hasattr(config, "sensitivity_ma_windows")


def test_official_and_reference_base_dates_are_separate(tmp_path):
    store = ParquetStore(tmp_path)
    store.write_index_prices("OFFICIAL", valid_prices(1100))
    store.write_index_prices("REFERENCE", valid_prices(1100))
    result = load_index_frames(
        tmp_path,
        (
            catalog_entry("OFFICIAL", "official_base_date"),
            catalog_entry("REFERENCE", "third_party_base_date"),
        ),
        test_config(),
    )
    assert result.metadata.set_index("index_code").loc["OFFICIAL", "cohort"] == "official"
    assert result.metadata.set_index("index_code").loc["REFERENCE", "cohort"] == "reference"


def test_duplicate_dates_are_excluded_not_silently_deduplicated(tmp_path):
    frame = valid_prices(1100)
    ParquetStore(tmp_path).write_index_prices("TEST", pd.concat([frame, frame.iloc[[5]]]))
    result = load_index_frames(tmp_path, (catalog_entry("TEST", "official_base_date"),), test_config())
    assert result.exclusions.iloc[0]["reason_code"] == "duplicate_trade_date"
```

- [ ] **步骤2：运行测试确认失败**

运行：

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_data.py -q
```

预期：因模块尚不存在而在收集阶段失败。

- [ ] **步骤3：创建不可变配置和模型**

`configs/index_research.yaml` 使用以下固定内容：

```yaml
strategy:
  version: index_trend_v1
  locked_at: 2026-07-30
  ma_window: 60
  slope_lookback: 20
  buffer_rate: 0.02
  atr_window: 20
  atr_multiple: 3.0
  buffer_ablation: [0.0, 0.02, 0.03]
costs:
  commission_rate: 0.00015
  slippage_rate: 0.0002
  stress_multiplier: 2.0
validation:
  min_valid_rows: 1000
  rolling_years: 5
  rolling_step_years: 1
  whipsaw_max_holding_days: 20
  stage_years: [2015, 2018, 2020, 2022]
effectiveness:
  min_drawdown_win_rate: 0.60
  min_median_drawdown_reduction: 0.20
  max_median_annual_return_lag: 0.02
```

`IndexResearchConfig` 必须显式包含上述值；`IndexAdmissionResult` 包含 `frames`、`metadata`、`exclusions` 三个字段。

- [ ] **步骤4：实现严格数据准入和最少指标**

```python
REQUIRED_COLUMNS = {"trade_date", "open", "high", "low", "close"}


def add_index_trend_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values("trade_date").copy()
    close = pd.to_numeric(result["close"], errors="coerce")
    result["ma60"] = close.rolling(60, min_periods=60).mean()
    result["ma60_slope_20"] = result["ma60"] / result["ma60"].shift(20) - 1.0
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            result["high"] - result["low"],
            (result["high"] - previous_close).abs(),
            (result["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["atr20"] = true_range.rolling(20, min_periods=20).mean()
    return result
```

官方基日进入 `official`，第三方基日进入 `reference`，出版日和未核验记录进入 exclusions。拒绝文件缺失、列缺失、无效日期、重复日期、非正 OHLC 和基日后不足 1,000 行。开盘价缺失保留为 `NaN` 供成交层处理。

- [ ] **步骤5：运行聚焦测试并提交**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_data.py tests\test_index_catalog.py -q
git add configs/index_research.yaml src/etf_trading/research/index_models.py src/etf_trading/research/index_data.py tests/test_index_research_data.py
git commit -m "feat: admit index data for locked trend research"
```

预期：全部通过。

---

### 任务2：V1 状态机与严格成交

**文件：**

- 创建：`src/etf_trading/research/index_trend_v1.py`
- 创建：`src/etf_trading/research/index_backtest.py`
- 测试：`tests/test_index_trend_v1.py`
- 测试：`tests/test_index_research_backtest.py`

**接口：**

- 输出：`IndexTrendV1(buffer_rate=0.02, atr_multiple=3.0)`。
- 输出：`run_index_backtest(index_code, frame, strategy, costs) -> IndexBacktestResult`。
- 输出：`run_buy_hold(index_code, frame, costs) -> IndexBacktestResult`。

- [ ] **步骤1：编写失败的缓冲轨和重入测试**

```python
def test_buy_requires_fresh_cross_above_two_percent_upper_band():
    strategy = IndexTrendV1(buffer_rate=0.02, atr_multiple=3.0)
    previous = row(close=101.9, ma60=100.0, slope=0.01, atr20=2.0)
    current = row(close=102.1, ma60=100.0, slope=0.01, atr20=2.0)
    signal = strategy.evaluate_close(previous, current, in_position=False)
    assert signal.action == "BUY"
    assert signal.reason == "fresh_upper_band_breakout"


def test_price_inside_hysteresis_band_keeps_position():
    strategy = IndexTrendV1()
    signal = strategy.evaluate_close(
        row(close=103.0, ma60=100.0, slope=0.01, atr20=2.0),
        row(close=99.0, ma60=100.0, slope=0.01, atr20=2.0),
        in_position=True,
        highest_close=105.0,
    )
    assert signal is None


def test_atr_exit_requires_new_upper_cross_before_reentry():
    strategy = IndexTrendV1()
    assert strategy.evaluate_close(
        row(close=103.0, ma60=100.0, slope=0.01, atr20=2.0),
        row(close=104.0, ma60=100.0, slope=0.01, atr20=2.0),
        in_position=False,
    ) is None
```

- [ ] **步骤2：编写失败的 T+1、跳空和缺失开盘测试**

```python
def test_signal_executes_at_next_valid_open():
    prices = prices_with_opens([10.0, float("nan"), 12.0])
    result = run_index_backtest("000300", prices, always_buy_strategy(), default_costs())
    trade = result.trades[0]
    assert trade.trade_date == pd.Timestamp("2024-01-04")
    assert trade.execution_price == pytest.approx(12.0 * 1.0002)
    assert trade.delay_days == 2


def test_gap_exit_uses_actual_open_not_lower_band_or_atr_stop():
    result = run_index_backtest("000300", gap_down_prices(), fixed_exit_strategy(), default_costs())
    assert result.trades[-1].execution_price == pytest.approx(80.0 * 0.9998)


def test_pending_buy_is_cancelled_when_entry_condition_invalidates():
    result = run_index_backtest(
        "000300",
        prices_with_missing_open_then_lower_band_close(),
        IndexTrendV1(),
        default_costs(),
    )
    assert result.trades == []
    assert result.cancelled_signals.iloc[0]["reason"] == "entry_invalidated_before_execution"
```

- [ ] **步骤3：运行测试确认失败**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_trend_v1.py tests\test_index_research_backtest.py -q
```

预期：缺少新模块和接口。

- [ ] **步骤4：实现固定状态机**

```python
class IndexTrendV1:
    def __init__(self, buffer_rate: float = 0.02, atr_multiple: float = 3.0) -> None:
        self.buffer_rate = buffer_rate
        self.atr_multiple = atr_multiple

    def evaluate_close(
        self,
        previous: pd.Series,
        current: pd.Series,
        *,
        in_position: bool,
        highest_close: float | None = None,
    ) -> StrategySignal | None:
        current_close = float(current["close"])
        current_ma = float(current["ma60"])
        upper = current_ma * (1.0 + self.buffer_rate)
        lower = current_ma * (1.0 - self.buffer_rate)
        if in_position:
            atr_stop = float(highest_close) - self.atr_multiple * float(current["atr20"])
            if current_close <= atr_stop:
                return sell_signal(current, "trailing_atr_exit")
            if current_close < lower:
                return sell_signal(current, "lower_band_breakdown")
            return None
        previous_upper = float(previous["ma60"]) * (1.0 + self.buffer_rate)
        fresh_cross = float(previous["close"]) <= previous_upper and current_close > upper
        if fresh_cross and float(current["ma60_slope_20"]) > 0:
            return buy_signal(current, "fresh_upper_band_breakout")
        return None
```

实际实现必须在成交后更新持仓状态和持仓最高收盘价。卖出后只有新的上轨交叉才能重入。指标缺失时不产生信号。

- [ ] **步骤5：实现指数专用成交循环**

成交循环顺序固定为：开盘执行待处理目标、更新实际持仓、收盘估值、更新持仓最高收盘价、调用 V1 产生新目标。等待开盘期间出现更新目标时记录 `replaced_before_execution`。尚未成交的买入目标若收盘时已经不再高于上轨或 MA60 斜率不再为正，则记录 `entry_invalidated_before_execution`；已经产生的卖出目标不因反弹撤销。区间结束仍待执行时记录 `no_future_valid_open`。

交易记录包含信号日、成交日、实际成交价、滑点、手续费、延迟天数、前后仓位、原因和规则。买入持有使用首个有效开盘和相同买入费用，不虚构期末卖出。

- [ ] **步骤6：运行回归测试并提交**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_trend_v1.py tests\test_index_research_backtest.py tests\test_backtest.py -q
git add src/etf_trading/research/index_trend_v1.py src/etf_trading/research/index_backtest.py tests/test_index_trend_v1.py tests/test_index_research_backtest.py
git commit -m "feat: execute buffered index trend v1"
```

预期：新测试及现有 ETF 回测测试全部通过。

---

### 任务3：绩效、回撤和假突破指标

**文件：**

- 创建：`src/etf_trading/research/index_metrics.py`
- 测试：`tests/test_index_research_metrics.py`

**接口：**

- 输入：`IndexBacktestResult`。
- 输出：`summarize_index_result(result, whipsaw_max_holding_days=20) -> dict[str, object]`。
- 输出：`summarize_nav_by_year(nav) -> pd.DataFrame`。

- [ ] **步骤1：编写失败的回撤与假突破测试**

```python
def test_drawdown_episode_reports_peak_trough_and_recovery():
    metrics = summarize_index_result(result_with_nav([1.0, 1.2, 0.9, 1.2]))
    assert metrics["max_drawdown"] == -0.25
    assert metrics["drawdown_start"] == "2024-01-03"
    assert metrics["drawdown_trough"] == "2024-01-04"
    assert metrics["drawdown_recovery"] == "2024-01-05"
    assert metrics["drawdown_recovered"] is True


def test_losing_round_trip_within_twenty_trading_days_is_whipsaw():
    result = result_with_round_trip(entry_index=2, exit_index=12, entry_price=100, exit_price=97)
    metrics = summarize_index_result(result, whipsaw_max_holding_days=20)
    assert metrics["whipsaw_trade_count"] == 1
    assert metrics["whipsaw_trade_rate"] == 1.0
```

- [ ] **步骤2：运行测试确认失败**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_metrics.py -q
```

- [ ] **步骤3：实现完整指标**

返回总收益、年化收益、年化波动、夏普、最大回撤及日期、恢复天数、Calmar、平均持仓、交易次数、完整交易次数、胜率、平均交易收益、平均持有日、成本损耗、ATR 退出次数、重入次数和假突破指标。

假突破使用交易日索引差而不是自然日：完整买卖交易持有不超过 20 个交易日且扣费后亏损。没有完整交易时，假突破率为 0，并保留分母字段。

- [ ] **步骤4：运行测试并提交**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_metrics.py tests\test_research_metrics.py -q
git add src/etf_trading/research/index_metrics.py tests/test_index_research_metrics.py
git commit -m "feat: measure index trend risk and whipsaws"
```

---

### 任务4：全历史、五年滚动和六项门槛

**文件：**

- 扩展：`src/etf_trading/research/index_models.py`
- 创建：`src/etf_trading/research/index_validation.py`
- 测试：`tests/test_index_research_validation.py`

**接口：**

- 输出：`run_index_research(admission, config, progress=None, should_stop=None) -> IndexResearchOutput`。
- 输出：`evaluate_effectiveness(results, buffer_comparison, stress_results, config) -> EffectivenessAssessment`。

- [ ] **步骤1：编写失败的全历史和滚动窗口测试**

```python
def test_every_admitted_index_gets_full_history_v1_and_buy_hold_rows():
    output = run_index_research(two_index_admission(), test_config())
    full = output.results[output.results["period_type"] == "full_history"]
    assert set(full["index_code"]) == {"000300", "000905"}
    assert set(full["strategy_name"]) == {"index_trend_v1", "buy_hold"}


def test_five_year_windows_advance_one_calendar_year():
    windows = build_rolling_windows(long_frame("2005-01-01", "2020-12-31"), years=5, step_years=1)
    assert windows[0].start.year == 2005
    assert windows[0].end.year == 2009
    assert windows[1].start.year == 2006
    assert windows[1].end.year == 2010


def test_only_post_lock_rows_are_prospective_oos():
    output = run_index_research(admission_around_lock_date(), test_config())
    prospective = output.nav[output.nav["period_type"] == "prospective_oos"]
    assert (pd.to_datetime(prospective["trade_date"]).dt.date > date(2026, 7, 30)).all()
```

- [ ] **步骤2：编写失败的六项门槛测试**

```python
def test_effectiveness_fails_when_buffer_does_not_reduce_whipsaws():
    assessment = evaluate_effectiveness(
        passing_results(),
        buffer_comparison(rate_0=0.10, rate_2=0.10, trades_0=4.0, trades_2=3.0),
        passing_stress_results(),
        test_config(),
    )
    assert assessment.status == "failed"
    assert assessment.gates["buffer_reduces_whipsaw_rate_and_trades"] is False
```

- [ ] **步骤3：运行测试确认失败**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_validation.py -q
```

- [ ] **步骤4：实现确定性研究矩阵**

每个纳入指数执行：

1. 正式 2% V1 和买入持有的全历史回测；
2. 每次前移一年的五年滚动回测；
3. 逐自然年及 2015、2018、2020、2022 年结果；
4. 0%、2%、3% 缓冲版本的全历史解释性消融；
5. 正式 2% V1 的双倍费用回测；
6. 锁定日后已有数据时生成 `prospective_oos`，否则保存“尚无前瞻样本”状态。

正式和扩展样本都运行，但总体主结论只聚合 `cohort == "official"`。进度回调签名固定为 `progress(done: int, total: int, index_code: str, phase: str) -> None`，每个指数边界检查取消状态。

- [ ] **步骤5：实现六项门槛**

```python
drawdown_reduction = (
    1.0
    - official_v1["max_drawdown"].abs().median()
    / official_buy_hold["max_drawdown"].abs().median()
)
gates = {
    "drawdown_win_rate": drawdown_win_rate >= config.min_drawdown_win_rate,
    "median_drawdown_reduction": drawdown_reduction >= config.min_median_drawdown_reduction,
    "median_calmar_improves": median_calmar_v1 > median_calmar_buy_hold,
    "median_return_is_retained": median_return_v1 >= median_return_buy_hold - config.max_median_annual_return_lag,
    "buffer_reduces_whipsaw_rate_and_trades": whipsaw_rate_2 < whipsaw_rate_0 and trades_per_year_2 < trades_per_year_0,
    "stress_keeps_first_four_gates": all(stress_first_four.values()),
}
```

只有六项全部通过才是 `passed`。五年窗口通过前四项的比例单独报告，不增加事后阈值。输出官方、扩展、市场和指数类型分组的平均、中位、25%/75% 分位及最差十个指数。

- [ ] **步骤6：运行聚焦测试并提交**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_validation.py tests\test_index_research_data.py tests\test_index_trend_v1.py tests\test_index_research_backtest.py tests\test_index_research_metrics.py -q
git add src/etf_trading/research/index_models.py src/etf_trading/research/index_validation.py tests/test_index_research_validation.py
git commit -m "feat: validate locked index trend v1"
```

---

### 任务5：版本化原子发布、中文报告和 CLI

**文件：**

- 创建：`src/etf_trading/research/index_report.py`
- 创建：`scripts/run_index_research.py`
- 测试：`tests/test_index_research_report.py`

**接口：**

- 输出：`publish_index_research(output, report_root, run_meta) -> PublishedIndexResearch`。
- 输出：`load_latest_index_research(report_root) -> LoadedIndexResearch`。
- 输出：`render_index_research_markdown(output, run_meta) -> str`。

- [ ] **步骤1：编写失败的完整发布和旧结果保留测试**

```python
def test_publish_creates_versioned_run_and_atomic_latest_pointer(tmp_path):
    published = publish_index_research(sample_output(), tmp_path, sample_run_meta())
    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["run_id"] == published.run_id
    assert (tmp_path / "runs" / published.run_id / "index_backtest_results.csv").exists()
    assert (tmp_path / "runs" / published.run_id / "index_strategy_nav.parquet").exists()


def test_failed_publish_preserves_previous_latest_pointer(tmp_path, monkeypatch):
    first = publish_index_research(sample_output(), tmp_path, sample_run_meta("first"))
    monkeypatch.setattr(pd.DataFrame, "to_parquet", raise_disk_error)
    with pytest.raises(OSError):
        publish_index_research(sample_output(), tmp_path, sample_run_meta("second"))
    assert load_latest_index_research(tmp_path).run_id == first.run_id
```

- [ ] **步骤2：运行测试确认失败**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py -q
```

- [ ] **步骤3：发布十项完整结果**

每次运行写入 `runs/<run_id>.staging/`，验证后重命名为 `runs/<run_id>/`，最后通过 `os.replace` 更新 `latest.json`。运行目录包含：

- `index_backtest_results.csv`
- `index_backtest_trades.csv`
- `index_strategy_summary.csv`
- `index_strategy_yearly.csv`
- `index_strategy_rolling_5y.csv`
- `index_strategy_buffer_comparison.csv`
- `index_strategy_exclusions.csv`
- `index_strategy_nav.parquet`
- `index_trend_strategy_report.md`
- `index_trend_strategy_run.json`

运行元数据包含策略版本、配置 SHA-256、锁定日期、最新数据日、运行时间、官方/扩展/排除数量、状态和六项门槛。

- [ ] **步骤4：生成结论优先的中文报告**

顺序固定为：历史有效性结论、六项门槛、全历史配对结果、五年滚动稳定性、0/2/3% 缓冲诊断、双倍费用、年度/阶段、最好与最差指数、扩展样本、排除项、前瞻样本状态、研究限制。必须醒目标记指数结果不是 ETF 可实现收益。

- [ ] **步骤5：创建复用同一入口的 CLI**

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="运行指数趋势基准策略 V1 回测")
    parser.add_argument("--config", default="configs/index_research.yaml")
    parser.add_argument("--parquet-root", default="data/parquet")
    parser.add_argument("--report-root", default="reports/index_research")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    published = run_and_publish_index_research(
        config_path=args.config,
        parquet_root=args.parquet_root,
        report_root=args.report_root,
        limit=args.limit,
    )
    print(f"指数趋势回测完成：run_id={published.run_id}，截止日={published.data_cutoff}")
```

- [ ] **步骤6：运行测试、两个指数冒烟和提交**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py tests\test_index_research_validation.py -q
.venv-win\Scripts\python.exe scripts\run_index_research.py --limit 2 --report-root reports\index_research_smoke
git add src/etf_trading/research/index_report.py scripts/run_index_research.py tests/test_index_research_report.py
git commit -m "feat: publish versioned index trend evidence"
```

预期：测试通过，冒烟运行产生完整运行目录和 `latest.json`，生成结果保持未跟踪。

---

### 任务6：后台重算、过期检测与策略页面

**文件：**

- 创建：`src/etf_trading/research/index_jobs.py`
- 修改：`src/etf_trading/nicegui_app/navigation.py`
- 修改：`src/etf_trading/nicegui_app/pages/research.py`
- 测试：`tests/test_index_research_jobs.py`
- 测试：`tests/test_index_research_page.py`
- 修改：`tests/test_nicegui_navigation.py`

**接口：**

- 输出：`IndexResearchJobManager.start() -> str`、`cancel() -> None`、`snapshot() -> IndexResearchJobSnapshot`。
- 输出：`index_research_is_stale(latest_meta, parquet_root) -> bool`。
- 输出：`render_index_trend_research(report_root, parquet_store, job_manager)`。

- [ ] **步骤1：编写失败的过期和互斥测试**

```python
def test_newer_index_data_marks_result_stale(tmp_path):
    write_latest_meta(tmp_path, data_cutoff="2026-07-28")
    write_index_price(tmp_path, latest_date="2026-07-29")
    assert index_research_is_stale(load_meta(tmp_path), tmp_path) is True


def test_job_manager_rejects_second_concurrent_run():
    manager = IndexResearchJobManager(blocking_runner())
    manager.start()
    with pytest.raises(IndexResearchAlreadyRunning):
        manager.start()
```

- [ ] **步骤2：编写失败的导航和页面状态测试**

```python
def test_research_navigation_contains_index_trend_backtest():
    assert "指数趋势回测" in get_page_by_slug("research").sections


def test_page_source_contains_required_run_and_result_states():
    source = Path("src/etf_trading/nicegui_app/pages/research.py").read_text(encoding="utf-8")
    for label in (
        "重新回测", "结果已过期", "策略版本", "数据截止日", "总体结论",
        "五年滚动", "缓冲带诊断", "交易记录", "排除原因", "指数理论回测",
    ):
        assert label in source
```

- [ ] **步骤3：运行测试确认失败**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_jobs.py tests\test_index_research_page.py tests\test_nicegui_navigation.py -q
```

- [ ] **步骤4：实现单任务后台管理器**

管理器使用一个后台工作线程和互斥锁，状态为 `idle`、`queued`、`running`、`completed`、`failed`、`cancelled`。进度包含当前阶段、已完成指数数、总指数数和当前代码。取消只在指数边界生效；失败或取消不更新 `latest.json`。

过期判断读取 latest 的数据截止日，并扫描本地指数 Parquet 的最新日期。页面打开只读，不自动运行。

- [ ] **步骤5：实现页面层级和重新回测按钮**

页面顺序：

1. 策略版本、锁定日期、数据截止日、运行时间和过期状态；
2. “重新回测”按钮、进度和取消按钮；
3. 六项门槛及总体结论；
4. 官方样本的 V1 与买入持有比较；
5. 指数选择器、净值和回撤曲线；
6. 年度、五年滚动和交易记录；
7. 0/2/3% 缓冲诊断和双倍费用；
8. 扩展样本、排除原因、前瞻样本状态和限制。

结果缺失、不完整、无效、运行中和可用状态必须有不同提示。页面通过 `latest.json` 读取一个完整运行目录，不在展示阶段重算指标。

- [ ] **步骤6：运行 UI 测试和真实浏览器检查**

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_jobs.py tests\test_index_research_page.py tests\test_nicegui_navigation.py tests\test_nicegui_app_import.py tests\test_nicegui_theme.py -q
```

启动 NiceGUI，在 1440px 和 390px 下检查无结果、过期、运行中、完成和失败状态。使用真实冒烟结果确认选择器、净值、回撤、滚动窗口和交易表正常，控制台无错误，页面无整体横向溢出。

- [ ] **步骤7：提交页面和任务管理器**

```powershell
git add src/etf_trading/research/index_jobs.py src/etf_trading/nicegui_app/navigation.py src/etf_trading/nicegui_app/pages/research.py tests/test_index_research_jobs.py tests/test_index_research_page.py tests/test_nicegui_navigation.py
git commit -m "feat: rerun index trend research from strategy lab"
```

---

### 任务7：全指数运行、交叉校验和项目记忆

**文件：**

- 扩展：`tests/test_index_research_report.py`
- 修改：`docs/task-memory.md`
- 只生成：`reports/index_research/runs/*` 和 `reports/index_research/latest.json`

- [ ] **步骤1：增加跨文件一致性测试**

```python
def test_summary_gate_values_recalculate_from_published_rows(tmp_path):
    published = publish_index_research(deterministic_output(), tmp_path, sample_run_meta())
    loaded = load_latest_index_research(tmp_path)
    expected = recalculate_drawdown_win_rate(loaded.results)
    row = loaded.summary[loaded.summary["metric"] == "drawdown_win_rate"].iloc[0]
    assert float(row["value"]) == pytest.approx(expected)
    assert loaded.run_meta["config_sha256"] == published.config_sha256
```

- [ ] **步骤2：运行全量自动化测试**

```powershell
.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-full
```

预期：全部通过；实时 Tushare 冒烟测试在未显式启用时保持跳过。

- [ ] **步骤3：运行全部本地指数**

```powershell
.venv-win\Scripts\python.exe scripts\run_index_research.py --report-root reports\index_research
```

预期：每个目录指数都有官方结果、扩展结果或明确排除原因，正式运行目录包含十项文件，`latest.json` 指向该目录。

- [ ] **步骤4：只读核对关键结果**

```powershell
@'
from pathlib import Path
import json
import pandas as pd
root = Path("reports/index_research")
latest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
run = root / "runs" / latest["run_id"]
required = {
    "index_backtest_results.csv", "index_backtest_trades.csv",
    "index_strategy_summary.csv", "index_strategy_yearly.csv",
    "index_strategy_rolling_5y.csv", "index_strategy_buffer_comparison.csv",
    "index_strategy_exclusions.csv", "index_strategy_nav.parquet",
    "index_trend_strategy_report.md", "index_trend_strategy_run.json",
}
assert required == {p.name for p in run.iterdir()}
summary = pd.read_csv(run / "index_strategy_summary.csv")
gates = summary[summary["row_type"] == "effectiveness_gate"]
assert len(gates) == 6
print(gates[["metric", "value", "threshold", "passed"]].to_string(index=False))
'@ | .venv-win\Scripts\python.exe -
```

预期：打印六项门槛，无断言失败。不得在门槛未全部通过时声称策略有效。

- [ ] **步骤5：用真实全量结果完成浏览器验收**

检查总体结论、一个表现较好的指数、一个失败指数、0/2/3% 诊断、扩展样本和排除表。核对页面数字与 CSV、Markdown 一致，并保存桌面与移动截图。

- [ ] **步骤6：更新任务记忆并提交**

在 `docs/task-memory.md` 写入实现摘要、完整测试命令与结果、运行 ID、数据截止日、官方/扩展/排除数量、六项门槛、浏览器检查，以及官方基日、存续偏差、指数相关性和 ETF 不可直接实现的限制。

```powershell
git add tests/test_index_research_report.py docs/task-memory.md
git commit -m "test: verify full index trend v1 research"
git status --short
```

预期：生成报告保持忽略，不暂存用户原有的无关修改。

---

## 最终验收清单

- V1 只包含 MA60 上下 2% 缓冲、MA60 20 日方向和 3 倍 ATR20。
- 只有新上轨突破才能买入，ATR 卖出后不会在没有新突破时立即重入。
- 0%/3% 仅作消融解释，没有参数寻优或赢家替换。
- 主结论使用全部官方有效历史，并有逐年和五年滚动证据。
- 2026-07-30 后新增数据单独标记为真正前瞻样本。
- 每个指数都有官方结果、扩展结果或明确排除原因。
- 所有信号严格在下一有效开盘成交，跳空和费用正确。
- 六项历史有效性标准无论通过或失败都完整发布。
- 页面能够发现数据过期、互斥启动后台重算、显示进度并保留上一套成功结果。
- 结果目录版本化，`latest.json` 只指向完整校验后的运行。
- CSV、Parquet、Markdown和页面数字一致。
- 全量测试通过且现有 ETF 行为不变。
- 报告明确说明第一阶段是指数理论回测；ETF 执行验证尚未完成。
