# Index Trend Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible single-index trend research workflow that compares MA60+ATR, MA250, and channel-breakout timing with buy-and-hold across the local index universe and reports whether the locked strategy passes its predefined effectiveness criteria.

**Architecture:** Add an index-only research pipeline beside the existing ETF research pipeline: catalog-aware data admission, pure signal generation, strict T+1 execution, paired validation, durable report artifacts, and a read-only NiceGUI results surface. Preserve the existing ETF strategy and backtest contracts; index-specific models and orchestration live under `etf_trading.research`.

**Tech Stack:** Python 3.11, pandas 2.2+, NumPy 1.26+, PyArrow/Parquet, PyYAML, NiceGUI 3.14+, pytest 8.2+

## Global Constraints

- Research is single-index, long-or-cash, target weight 1.0, with no leverage, shorting, cross-index ranking, or portfolio rotation.
- Signals use information available at T close and execute at the next valid open; buy slippage is +0.02%, sell slippage is -0.02%, and commission is 0.015% of changed notional.
- The stress run doubles both commission and slippage; idle cash earns 0%.
- Main conclusions use only official-base-date histories with at least 1,000 valid trading days; pre-base histories and unresolved base dates never enter the main result.
- The locked primary strategy is MA60 + 3.0 ATR; MA50/60/70 and ATR 2.5/3.0/3.5 are sensitivity evidence only and cannot replace the default.
- The complete out-of-sample cohort begins on 2019-01-01 and must already have enough warm-up history before that date.
- All generated market results stay under `reports/` and must not be committed.
- Existing ETF backtest behavior and tests must remain unchanged.
- Use deterministic local fixtures in tests; do not access Tushare, AkShare, or the network.

---

## File Structure

- Create `configs/index_research.yaml`: locked strategy, cost, cohort, and sensitivity settings.
- Create `src/etf_trading/research/index_models.py`: immutable settings, admission, run-output, and effectiveness-result models.
- Create `src/etf_trading/research/index_data.py`: catalog-aware index loading, validation, feature calculation, and exclusions.
- Create `src/etf_trading/research/index_signals.py`: pure MA60+ATR, MA250, channel, and buy-hold signal generation.
- Create `src/etf_trading/research/index_backtest.py`: strict T+1 execution, benchmark execution, trade audit, drawdown episodes, and index metrics.
- Create `src/etf_trading/research/index_validation.py`: full-history/OOS/year/stage/sensitivity/stress orchestration and paired effectiveness gates.
- Create `src/etf_trading/research/index_report.py`: atomic CSV/Parquet publication and Chinese Markdown report rendering.
- Create `scripts/run_index_research.py`: reproducible CLI entry point.
- Modify `src/etf_trading/nicegui_app/navigation.py`: add the `指数趋势回测` strategy-lab section.
- Modify `src/etf_trading/nicegui_app/pages/research.py`: load and render stored index-research artifacts without recalculating them.
- Create focused tests `tests/test_index_research_data.py`, `tests/test_index_research_signals.py`, `tests/test_index_research_backtest.py`, `tests/test_index_research_validation.py`, `tests/test_index_research_report.py`, and `tests/test_index_research_page.py`.
- Modify `docs/task-memory.md`: record verification and reusable research cautions after the implementation is complete.

---

### Task 1: Locked Configuration, Models, and Catalog-Aware Data Admission

**Files:**
- Create: `configs/index_research.yaml`
- Create: `src/etf_trading/research/index_models.py`
- Create: `src/etf_trading/research/index_data.py`
- Test: `tests/test_index_research_data.py`

**Interfaces:**
- Consumes: `IndexCatalogEntry`, `default_index_catalog()`, and `ParquetStore.read_index_prices(index_code)`.
- Produces: `load_index_research_config(path) -> IndexResearchConfig`, `load_index_frames(parquet_root, catalog, config) -> IndexAdmissionResult`, and `add_index_research_features(frame, trend_window=60) -> pd.DataFrame`.

- [ ] **Step 1: Write failing configuration and admission tests**

```python
def test_load_config_locks_primary_and_stress_costs():
    config = load_index_research_config("configs/index_research.yaml")
    assert config.primary_ma == 60
    assert config.trailing_atr_multiple == 3.0
    assert config.commission_rate == 0.00015
    assert config.slippage_rate == 0.0002
    assert config.stress_multiplier == 2.0
    assert config.oos_start == date(2019, 1, 1)


def test_admission_rejects_unofficial_base_date(tmp_path):
    store = ParquetStore(tmp_path)
    store.write_index_prices("TEST", valid_prices(1005))
    entry = catalog_entry(
        "TEST", index_base_date=date(2010, 1, 1),
        baseline_evidence_kind="third_party_base_date",
    )
    admitted = load_index_frames(tmp_path, (entry,), test_config(min_rows=1000))
    assert admitted.frames == {}
    assert admitted.exclusions.iloc[0]["reason_code"] == "official_base_date_required"


def test_admission_rejects_duplicate_dates_without_silent_deduplication(tmp_path):
    frame = valid_prices(1005)
    ParquetStore(tmp_path).write_index_prices("TEST", pd.concat([frame, frame.iloc[[5]]]))
    admitted = load_index_frames(tmp_path, (official_entry("TEST"),), test_config())
    assert admitted.exclusions.iloc[0]["reason_code"] == "duplicate_trade_date"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_data.py -q`

Expected: collection fails because `index_models` and `index_data` do not exist.

- [ ] **Step 3: Add the locked YAML and immutable models**

```yaml
primary:
  ma_window: 60
  fast_ma_window: 20
  slope_lookback: 20
  momentum_windows: [60, 120]
  momentum_skip_days: 5
  max_atr_distance: 2.0
  trailing_atr_multiple: 3.0
costs:
  commission_rate: 0.00015
  slippage_rate: 0.0002
  stress_multiplier: 2.0
validation:
  min_valid_rows: 1000
  oos_start: 2019-01-01
  sensitivity_ma_windows: [50, 60, 70]
  sensitivity_atr_multiples: [2.5, 3.0, 3.5]
  stage_years: [2015, 2018, 2020, 2022]
effectiveness:
  min_drawdown_win_rate: 0.60
  min_median_drawdown_reduction: 0.20
  max_median_annual_return_lag: 0.02
```

```python
@dataclass(frozen=True)
class IndexResearchConfig:
    primary_ma: int
    fast_ma: int
    slope_lookback: int
    momentum_windows: tuple[int, int]
    momentum_skip_days: int
    max_atr_distance: float
    trailing_atr_multiple: float
    commission_rate: float
    slippage_rate: float
    stress_multiplier: float
    min_valid_rows: int
    oos_start: date
    sensitivity_ma_windows: tuple[int, ...]
    sensitivity_atr_multiples: tuple[float, ...]
    stage_years: tuple[int, ...]
    min_drawdown_win_rate: float
    min_median_drawdown_reduction: float
    max_median_annual_return_lag: float


@dataclass(frozen=True)
class IndexAdmissionResult:
    frames: dict[str, pd.DataFrame]
    metadata: pd.DataFrame
    exclusions: pd.DataFrame
```

- [ ] **Step 4: Implement strict admission and features**

Implement `load_index_frames` so each catalog entry becomes either one admitted frame or one exclusion row. Require `baseline_evidence_kind == "official_base_date"`, require `index_base_date`, reject missing files/columns, invalid dates, duplicate dates, nonpositive OHLC, and fewer than `min_valid_rows` rows after the base date. Preserve missing opens for the execution engine.

```python
REQUIRED_PRICE_COLUMNS = {"trade_date", "open", "high", "low", "close"}


def add_index_research_features(frame: pd.DataFrame, trend_window: int = 60) -> pd.DataFrame:
    result = frame.sort_values("trade_date").copy()
    close = pd.to_numeric(result["close"], errors="coerce")
    for window in (20, 50, 60, 70, 250):
        result[f"ma{window}"] = close.rolling(window, min_periods=window).mean()
    result["ma60_slope_20"] = result["ma60"] / result["ma60"].shift(20) - 1.0
    result["ma50_slope_20"] = result["ma50"] / result["ma50"].shift(20) - 1.0
    result["ma70_slope_20"] = result["ma70"] / result["ma70"].shift(20) - 1.0
    result["momentum_60_skip5"] = close.shift(5) / close.shift(65) - 1.0
    result["momentum_120_skip5"] = close.shift(5) / close.shift(125) - 1.0
    previous_close = close.shift(1)
    true_range = pd.concat([
        result["high"] - result["low"],
        (result["high"] - previous_close).abs(),
        (result["low"] - previous_close).abs(),
    ], axis=1).max(axis=1)
    result["atr20"] = true_range.rolling(20, min_periods=20).mean()
    result["distance_ma20_atr"] = (close - result["ma20"]) / result["atr20"]
    result["prior_high_close_60"] = close.shift(1).rolling(60, min_periods=60).max()
    result["prior_low_close_20"] = close.shift(1).rolling(20, min_periods=20).min()
    return result
```

- [ ] **Step 5: Run focused tests and commit**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_data.py tests\test_index_catalog.py -q`

Expected: all tests pass.

```powershell
git add configs/index_research.yaml src/etf_trading/research/index_models.py src/etf_trading/research/index_data.py tests/test_index_research_data.py
git commit -m "feat: admit index histories for trend research"
```

---

### Task 2: Pure Strategy Signal Generators

**Files:**
- Create: `src/etf_trading/research/index_signals.py`
- Test: `tests/test_index_research_signals.py`

**Interfaces:**
- Consumes: admitted, featured `pd.DataFrame` values from Task 1 and `StrategySignal`.
- Produces: `generate_index_signals(index_code, frame, strategy_name, ma_window=60, atr_multiple=3.0) -> list[StrategySignal]`.

- [ ] **Step 1: Write failing boundary and look-ahead tests**

```python
def test_primary_entry_requires_all_locked_conditions():
    frame = signal_frame(close=110, ma20=105, ma60=100, slope=0.01,
                         mom60=0.08, mom120=0.12, atr_distance=1.5)
    signals = generate_index_signals("000300", frame, "ma60_atr")
    assert signals[-1].action == "BUY"
    assert set(signals[-1].trigger_rules) == {
        "close_above_ma60", "ma20_above_ma60", "ma60_slope_positive",
        "momentum_60_skip5_positive", "momentum_120_skip5_positive",
        "not_overextended_2ATR",
    }


def test_primary_exit_uses_close_and_trailing_atr():
    frame = entry_then_prices([100, 110, 104], atr20=2.0, ma60=90.0)
    signals = generate_index_signals("000300", frame, "ma60_atr", atr_multiple=3.0)
    assert signals[-1].action == "SELL"
    assert signals[-1].reason == "trailing_atr_exit"


def test_channel_breakout_excludes_current_close_from_window():
    frame = channel_frame(prior_closes=[100] * 60, current_close=101)
    signals = generate_index_signals("000300", frame, "channel_60_20")
    assert signals[-1].action == "BUY"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_signals.py -q`

Expected: import fails because `index_signals.py` does not exist.

- [ ] **Step 3: Implement the dispatcher and three state machines**

```python
STRATEGY_NAMES = ("ma60_atr", "ma250", "channel_60_20")


def generate_index_signals(
    index_code: str,
    frame: pd.DataFrame,
    strategy_name: str,
    *,
    ma_window: int = 60,
    atr_multiple: float = 3.0,
) -> list[StrategySignal]:
    if strategy_name == "ma60_atr":
        return _ma_atr_signals(index_code, frame, ma_window, atr_multiple)
    if strategy_name == "ma250":
        return _ma250_signals(index_code, frame)
    if strategy_name == "channel_60_20":
        return _channel_signals(index_code, frame, atr_multiple)
    raise ValueError(f"unknown index strategy: {strategy_name}")
```

For the primary strategy, maintain `in_position` and `highest_close_since_entry`. Do not emit HOLD rows. Exit has precedence over entry, `close < trend_ma` has precedence in the reason text when both exits fire, and every signal includes exact trigger rules. For sensitivity MA50/MA70, calculate the selected MA and its 20-day slope using columns `ma50`/`ma70` and `ma50_slope_20`/`ma70_slope_20` created by Task 1.

- [ ] **Step 4: Add explicit missing-indicator and no-look-ahead cases**

```python
def test_missing_required_indicator_never_creates_signal():
    frame = signal_frame(close=110, ma20=105, ma60=100, slope=float("nan"),
                         mom60=0.08, mom120=0.12, atr_distance=1.5)
    assert generate_index_signals("000300", frame, "ma60_atr") == []


def test_ma_exit_is_strictly_below_not_equal():
    frame = entry_then_equal_ma_frame()
    assert [s.action for s in generate_index_signals("000300", frame, "ma60_atr")] == ["BUY"]
```

- [ ] **Step 5: Run focused tests and commit**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_signals.py tests\test_research_signals.py -q`

Expected: all tests pass.

```powershell
git add src/etf_trading/research/index_signals.py tests/test_index_research_signals.py
git commit -m "feat: generate locked index trend signals"
```

---

### Task 3: Strict T+1 Index Execution and Extended Metrics

**Files:**
- Create: `src/etf_trading/research/index_backtest.py`
- Test: `tests/test_index_research_backtest.py`

**Interfaces:**
- Consumes: price frames and `list[StrategySignal]` from Task 2.
- Produces: `run_index_backtest(index_code, prices, signals, *, commission_rate=0.00015, slippage_rate=0.0002) -> IndexBacktestResult`, `run_buy_hold(index_code, prices, *, commission_rate=0.00015, slippage_rate=0.0002) -> IndexBacktestResult`, and `summarize_index_result(result) -> dict[str, object]`.

- [ ] **Step 1: Write failing execution tests**

```python
def test_index_signal_executes_at_next_valid_open_with_costs():
    prices = prices_with_opens([10.0, float("nan"), 12.0])
    signal = buy_signal("2024-01-02")
    result = run_index_backtest("000300", prices, [signal], commission_rate=0.00015, slippage_rate=0.0002)
    trade = result.trades[0]
    assert trade.signal_date == pd.Timestamp("2024-01-02")
    assert trade.trade_date == pd.Timestamp("2024-01-04")
    assert trade.execution_price == pytest.approx(12.0 * 1.0002)
    assert trade.delay_days == 2


def test_later_target_replaces_unexecuted_pending_signal():
    prices = prices_with_opens([10.0, float("nan"), 9.0])
    signals = [buy_signal("2024-01-02"), sell_signal("2024-01-03")]
    result = run_index_backtest("000300", prices, signals)
    assert result.trades == []
    assert result.cancelled_signals.iloc[0]["reason"] == "replaced_before_execution"


def test_gap_exit_uses_actual_next_open_not_stop_level():
    result = run_index_backtest("000300", gap_down_prices(), entry_and_atr_exit_signals())
    assert result.trades[-1].execution_price == pytest.approx(80.0 * (1 - 0.0002))
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_backtest.py -q`

Expected: import fails because `index_backtest.py` does not exist.

- [ ] **Step 3: Implement an index-only result and execution loop**

```python
@dataclass(frozen=True)
class IndexTrade:
    index_code: str
    signal_date: pd.Timestamp
    trade_date: pd.Timestamp
    action: str
    execution_price: float
    weight_before: float
    weight_after: float
    commission: float
    delay_days: int
    reason: str
    trigger_rules: tuple[str, ...]


@dataclass
class IndexBacktestResult:
    trades: list[IndexTrade]
    nav: pd.DataFrame
    cancelled_signals: pd.DataFrame
```

The loop stores a pending target after each close. A later signal replaces an unexecuted pending target and records the replaced signal. On a finite positive open, execute the pending target with directional slippage and commission. Mark NAV at every finite close. At the final row, record any still-pending target as `no_future_valid_open`. Keep this implementation separate from `BacktestEngine` so ETF behavior is unchanged.

- [ ] **Step 4: Implement buy-and-hold and drawdown episode metrics**

```python
def drawdown_episode(nav: pd.DataFrame) -> dict[str, object]:
    values = nav.set_index("trade_date")["nav"].astype(float)
    peaks = values.cummax()
    drawdown = values / peaks - 1.0
    trough_date = drawdown.idxmin()
    peak_date = values.loc[:trough_date].idxmax()
    recovered = values.loc[trough_date:]
    recovered = recovered[recovered >= values.loc[peak_date]]
    recovery_date = recovered.index[0] if len(recovered) else pd.NaT
    return {
        "max_drawdown": float(drawdown.min()),
        "drawdown_start": peak_date,
        "drawdown_trough": trough_date,
        "drawdown_recovery": recovery_date,
        "recovery_days": None if pd.isna(recovery_date) else int((recovery_date - peak_date).days),
        "drawdown_recovered": not pd.isna(recovery_date),
    }
```

`run_buy_hold` buys at the first finite positive open in the evaluation interval, applies the same buy cost, never fabricates an ending sale, and values the final position at the last finite close. `summarize_index_result` returns total/annualized return, volatility, Sharpe, max drawdown episode, Calmar, average exposure, trade counts, win rate, average trade return, and average holding days.

- [ ] **Step 5: Run focused and ETF regression tests, then commit**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_backtest.py tests\test_backtest.py tests\test_research_metrics.py -q`

Expected: all tests pass and existing ETF semantics remain green.

```powershell
git add src/etf_trading/research/index_backtest.py tests/test_index_research_backtest.py
git commit -m "feat: execute strict index timing backtests"
```

---

### Task 4: Validation Matrix and Predeclared Effectiveness Gates

**Files:**
- Extend: `src/etf_trading/research/index_models.py`
- Create: `src/etf_trading/research/index_validation.py`
- Test: `tests/test_index_research_validation.py`

**Interfaces:**
- Consumes: `IndexAdmissionResult`, `IndexResearchConfig`, signal generators, and index backtest results.
- Produces: `run_index_research(...) -> IndexResearchOutput` and `evaluate_effectiveness(results, config) -> EffectivenessAssessment`.

- [ ] **Step 1: Write failing matrix and cohort tests**

```python
def test_run_builds_full_and_complete_oos_rows():
    output = run_index_research(admission_for_two_indices(), test_config())
    assert {"full_history", "oos_complete"}.issubset(set(output.results["period_type"]))
    assert set(output.results["strategy_name"]) == {
        "ma60_atr", "ma250", "channel_60_20", "buy_hold"
    }


def test_post_2019_index_is_not_mixed_into_complete_oos_cohort():
    output = run_index_research(admission_starting("2020-01-02"), test_config())
    assert "oos_complete" not in set(output.results["period_type"])
    assert "oos_late_entry" in set(output.results["period_type"])


def test_effectiveness_requires_every_predeclared_gate():
    assessment = evaluate_effectiveness(effectiveness_fixture(drawdown_win_rate=0.59), test_config())
    assert assessment.status == "failed"
    assert assessment.gates["drawdown_win_rate"] is False
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_validation.py -q`

Expected: import or symbol failures for the new validation interfaces.

- [ ] **Step 3: Add output and assessment models**

```python
@dataclass(frozen=True)
class EffectivenessAssessment:
    status: Literal["passed", "partial", "failed"]
    gates: dict[str, bool]
    values: dict[str, float]
    explanations: tuple[str, ...]


@dataclass(frozen=True)
class IndexResearchOutput:
    results: pd.DataFrame
    trades: pd.DataFrame
    yearly: pd.DataFrame
    sensitivity: pd.DataFrame
    summary: pd.DataFrame
    exclusions: pd.DataFrame
    nav: pd.DataFrame
    assessments: tuple[EffectivenessAssessment, ...]
```

- [ ] **Step 4: Implement the deterministic validation matrix**

For every admitted index:

1. Define the common full-history performance start as the first row on which MA250 and every primary/channel input are finite, then run all four strategies from that same date.
2. If warm-up indicators exist before 2019-01-01, start empty at the first 2019 trading day and label `oos_complete`; otherwise label the available post-2019 run `oos_late_entry`.
3. Produce calendar-year rows and the explicitly configured 2015/2018/2020/2022 stage rows.
4. Run the nine primary sensitivity combinations at default costs.
5. Run the locked primary strategy at doubled costs.
6. Attach `index_code`, name, pool, market, actual start/end, row count, cost scenario, and parameter values to every row.

Use a helper with this exact boundary:

```python
def _run_one(
    index_code: str,
    frame: pd.DataFrame,
    strategy_name: str,
    *,
    period_type: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    ma_window: int,
    atr_multiple: float,
    commission_rate: float,
    slippage_rate: float,
) -> tuple[dict[str, object], list[dict[str, object]], pd.DataFrame]:
    evaluation = frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)].copy()
    signals = generate_index_signals(
        index_code,
        evaluation,
        strategy_name,
        ma_window=ma_window,
        atr_multiple=atr_multiple,
    )
    result = (
        run_buy_hold(
            index_code, evaluation,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
        )
        if strategy_name == "buy_hold"
        else run_index_backtest(
            index_code, evaluation, signals,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
        )
    )
    metrics = summarize_index_result(result)
    metrics.update({
        "index_code": index_code,
        "strategy_name": strategy_name,
        "period_type": period_type,
        "actual_start": evaluation["trade_date"].min(),
        "actual_end": evaluation["trade_date"].max(),
        "ma_window": ma_window,
        "atr_multiple": atr_multiple,
    })
    trades = [asdict(trade) | {"period_type": period_type} for trade in result.trades]
    nav = result.nav.assign(
        index_code=index_code,
        strategy_name=strategy_name,
        period_type=period_type,
    )
    return metrics, trades, nav
```

- [ ] **Step 5: Implement paired summaries and all six gates**

Pivot only the `oos_complete` default-cost/default-parameter rows by `index_code`. Compute strategy-minus-buy-hold annualized return, max-drawdown improvement, and Calmar difference. Set status to `passed` only when all six specification gates pass, `partial` when the first four pass but sensitivity or stress fails, and `failed` otherwise.

For the parameter gate, default MA60/3ATR is non-isolated when its median Calmar is at or above the 25th percentile of all nine neighbors and at least one orthogonally adjacent combination is within 10% of its median Calmar. Store the exact formula and result in `summary`; do not substitute the best neighbor.

Use percentile bootstrap over paired index rows with `numpy.random.default_rng(20260729)` and 2,000 resamples for descriptive 95% intervals. Label the interval `correlated_index_descriptive_ci` so it is not presented as an independent-sample confidence claim.

- [ ] **Step 6: Run focused tests and commit**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_validation.py tests\test_index_research_data.py tests\test_index_research_signals.py tests\test_index_research_backtest.py -q`

Expected: all tests pass.

```powershell
git add src/etf_trading/research/index_models.py src/etf_trading/research/index_validation.py tests/test_index_research_validation.py
git commit -m "feat: validate index trend effectiveness"
```

---

### Task 5: Atomic Artifacts, Chinese Research Report, and CLI

**Files:**
- Create: `src/etf_trading/research/index_report.py`
- Create: `scripts/run_index_research.py`
- Test: `tests/test_index_research_report.py`

**Interfaces:**
- Consumes: `IndexResearchOutput` from Task 4.
- Produces: `publish_index_research(output, output_dir) -> tuple[Path, ...]`, `render_index_research_markdown(output) -> str`, and the CLI command `python scripts/run_index_research.py`.

- [ ] **Step 1: Write failing publication and report tests**

```python
def test_publish_writes_complete_named_artifact_set_atomically(tmp_path):
    paths = publish_index_research(sample_output(), tmp_path)
    assert {path.name for path in paths} == {
        "index_backtest_results.csv", "index_backtest_trades.csv",
        "index_strategy_summary.csv", "index_strategy_yearly.csv",
        "index_strategy_sensitivity.csv", "index_strategy_exclusions.csv",
        "index_strategy_nav.parquet",
        "index_trend_strategy_report.md",
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_report_leads_with_failed_gate_instead_of_hiding_it():
    markdown = render_index_research_markdown(sample_output(status="failed"))
    assert "结论：未通过预设有效性标准" in markdown
    assert "最大回撤改善比例" in markdown
    assert "存续偏差" in markdown
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py -q`

Expected: import fails because `index_report.py` does not exist.

- [ ] **Step 3: Implement atomic publication**

Write every artifact to `.<name>.tmp`, validate that each required DataFrame has its identifying columns and at least one row where required, then replace final paths only after every temporary write succeeds. On failure, delete temporary files and preserve the prior complete artifact set.

```python
ARTIFACT_FRAMES = {
    "index_backtest_results.csv": "results",
    "index_backtest_trades.csv": "trades",
    "index_strategy_summary.csv": "summary",
    "index_strategy_yearly.csv": "yearly",
    "index_strategy_sensitivity.csv": "sensitivity",
    "index_strategy_exclusions.csv": "exclusions",
}
NAV_ARTIFACT = ("index_strategy_nav.parquet", "nav")
```

- [ ] **Step 4: Render an answer-first Chinese Markdown report**

The report order is: verdict; six gate values; OOS paired comparison; full-history context; stress result; sensitivity neighborhood; best/worst and failed indices; yearly/stage behavior; exclusions; data coverage; limitations. Include actual run timestamp, configuration values, admitted/excluded counts, and the warning that historical evidence is not a future-return promise.

- [ ] **Step 5: Add the reproducible CLI**

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="运行指数单标的趋势策略研究")
    parser.add_argument("--config", default="configs/index_research.yaml")
    parser.add_argument("--parquet-root", default="data/parquet")
    parser.add_argument("--output-dir", default="reports/index_research")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    config = load_index_research_config(args.config)
    catalog = default_index_catalog()
    if args.limit is not None:
        catalog = catalog[:args.limit]
    admission = load_index_frames(args.parquet_root, catalog, config)
    output = run_index_research(admission, config)
    paths = publish_index_research(output, args.output_dir)
    print(f"指数趋势研究完成：纳入 {len(admission.frames)} 个，排除 {len(admission.exclusions)} 个，输出 {len(paths)} 个文件")
```

Verify the existing `reports/` ignore rule covers `reports/index_research/`; do not change `.gitignore` when that rule is already present.

- [ ] **Step 6: Run focused tests and a bounded local smoke run, then commit**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py tests\test_index_research_validation.py -q`

Expected: all tests pass.

Run: `.venv-win\Scripts\python.exe scripts\run_index_research.py --limit 2 --output-dir reports\index_research_smoke`

Expected: exit 0, an admitted/excluded summary, and eight artifact files; generated files remain untracked.

```powershell
git add src/etf_trading/research/index_report.py scripts/run_index_research.py tests/test_index_research_report.py
git commit -m "feat: publish index trend research reports"
```

---

### Task 6: Stored-Result Strategy Lab Page

**Files:**
- Modify: `src/etf_trading/nicegui_app/navigation.py`
- Modify: `src/etf_trading/nicegui_app/pages/research.py`
- Create: `tests/test_index_research_page.py`
- Modify: `tests/test_nicegui_navigation.py`

**Interfaces:**
- Consumes: the eight files under `reports/index_research/` from Task 5.
- Produces: `load_index_research_artifacts(report_dir) -> IndexResearchArtifacts` and `render_index_trend_research(report_dir, parquet_store)`.

- [ ] **Step 1: Write failing navigation, loading, and empty-state tests**

```python
def test_research_navigation_includes_index_trend_backtest():
    research = get_page_by_slug("research")
    assert "指数趋势回测" in research.sections


def test_artifact_loader_rejects_partial_publication(tmp_path):
    pd.DataFrame([{"index_code": "000300"}]).to_csv(tmp_path / "index_backtest_results.csv", index=False)
    artifacts = load_index_research_artifacts(tmp_path)
    assert artifacts.state == "incomplete"
    assert artifacts.missing_files


def test_index_research_source_contains_required_views():
    source = Path("src/etf_trading/nicegui_app/pages/research.py").read_text(encoding="utf-8")
    for label in ("总体结论", "净值对比", "回撤曲线", "年度收益", "参数稳定性", "交易记录", "排除原因"):
        assert label in source
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_page.py tests\test_nicegui_navigation.py -q`

Expected: failures for the missing section and artifact loader.

- [ ] **Step 3: Add a read-only artifact loader and route**

Add `指数趋势回测` to the research page sections and route it before the legacy index-filter fallback. The loader must distinguish `missing`, `incomplete`, `invalid`, and `ready`; it must never calculate a strategy or overwrite an artifact during page rendering.

```python
INDEX_RESEARCH_REPORT_DIR = Path("reports/index_research")


@dataclass(frozen=True)
class IndexResearchArtifacts:
    state: str
    results: pd.DataFrame
    trades: pd.DataFrame
    summary: pd.DataFrame
    yearly: pd.DataFrame
    sensitivity: pd.DataFrame
    exclusions: pd.DataFrame
    nav: pd.DataFrame
    report_markdown: str
    missing_files: tuple[str, ...] = ()
```

- [ ] **Step 4: Render the result hierarchy**

Render in this order:

1. verdict card and six gate rows;
2. strategy comparison table for `oos_complete`;
3. index selector using code and catalog name;
4. selected-index strategy and buy-hold NAV plus drawdown series;
5. selected-index yearly rows and trades;
6. sensitivity and doubled-cost tables;
7. exclusions, coverage, and limitations.

Use stored result/trade/yearly/sensitivity rows and `index_strategy_nav.parquet` for the two curves. Do not rerun the strategy in the page. Keep tables paginated and show explicit missing/incomplete/error states.

- [ ] **Step 5: Run focused UI tests and browser QA**

Run: `.venv-win\Scripts\python.exe -m pytest tests\test_index_research_page.py tests\test_nicegui_navigation.py tests\test_nicegui_app_import.py tests\test_nicegui_theme.py -q`

Expected: all tests pass.

Run the app with `.venv-win\Scripts\python.exe scripts\run_nicegui.py`, open the `策略实验室 → 指数趋势回测` page, and verify at 1440px and 390px that tables do not overflow the viewport, selectors update the detail, both charts render, and the browser console has no errors. Capture screenshots for both widths.

- [ ] **Step 6: Commit the page**

```powershell
git add src/etf_trading/nicegui_app/navigation.py src/etf_trading/nicegui_app/pages/research.py tests/test_index_research_page.py tests/test_nicegui_navigation.py
git commit -m "feat: show index trend research in strategy lab"
```

---

### Task 7: Full-Universe Run, Cross-Artifact Validation, and Project Memory

**Files:**
- Modify: `tests/test_index_research_report.py`
- Modify: `docs/task-memory.md`
- Generate only: `reports/index_research/*`

**Interfaces:**
- Consumes: all code and tests from Tasks 1–6 plus the local index Parquet set.
- Produces: a verified full research artifact set and durable implementation notes.

- [ ] **Step 1: Add a cross-artifact consistency test**

```python
def test_published_summary_matches_result_recalculation(tmp_path):
    output = deterministic_multi_index_output()
    publish_index_research(output, tmp_path)
    results = pd.read_csv(tmp_path / "index_backtest_results.csv")
    summary = pd.read_csv(tmp_path / "index_strategy_summary.csv")
    expected = recalculate_oos_drawdown_win_rate(results)
    actual = float(summary.loc[summary["metric"] == "drawdown_win_rate", "value"].iloc[0])
    assert actual == pytest.approx(expected)
```

- [ ] **Step 2: Run the entire automated suite**

Run: `.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-backtest-full`

Expected: all tests pass; the opt-in live Tushare smoke test remains skipped unless explicitly enabled.

- [ ] **Step 3: Run the complete local index study**

Run: `.venv-win\Scripts\python.exe scripts\run_index_research.py --output-dir reports\index_research`

Expected: exit 0; every catalog index has either result rows or a specific exclusion; all published artifacts are readable and contain no temporary files.

- [ ] **Step 4: Validate artifact integrity and the six gates**

Run this read-only verification:

```powershell
@'
from pathlib import Path
import pandas as pd
root = Path("reports/index_research")
required = {
    "index_backtest_results.csv", "index_backtest_trades.csv",
        "index_strategy_summary.csv", "index_strategy_yearly.csv",
        "index_strategy_sensitivity.csv", "index_strategy_exclusions.csv",
        "index_strategy_nav.parquet",
        "index_trend_strategy_report.md",
}
assert required.issubset({p.name for p in root.iterdir()})
assert not list(root.glob("*.tmp"))
summary = pd.read_csv(root / "index_strategy_summary.csv")
gates = summary[summary["row_type"] == "effectiveness_gate"]
assert len(gates) == 6
assert gates["passed"].notna().all()
print(gates[["metric", "value", "threshold", "passed"]].to_string(index=False))
'@ | .venv-win\Scripts\python.exe -
```

Expected: six explicit gate rows print, with no assertion failures. Do not claim the strategy is effective unless every gate's stored value passes.

- [ ] **Step 5: Perform final browser QA with the real artifacts**

Start NiceGUI, inspect the real overall verdict, one passing index if present, one failing index, and the exclusion table at desktop and mobile widths. Confirm page numbers match the CSV rows and the Markdown verdict. Record actual evidence; do not substitute fixture screenshots.

- [ ] **Step 6: Update task memory and commit only source documentation**

Add a dated entry to `docs/task-memory.md` containing the implementation summary, exact full-suite command/result, full-run admitted/excluded counts, stored verdict, browser QA result, and cautions about official base dates, survivorship bias, correlated indices, and index-to-ETF execution differences.

```powershell
git add tests/test_index_research_report.py docs/task-memory.md
git commit -m "test: verify complete index trend research"
git status --short
```

Expected: generated `reports/index_research/` remains ignored, and no unrelated pre-existing workspace changes are staged.

---

## Final Acceptance Checklist

- The default MA60+3ATR rules and all comparison rules match the approved design exactly.
- Main results exclude unofficial/missing base-date histories and histories shorter than 1,000 valid rows.
- No signal executes before the next valid open; gaps use the actual open and costs are directional.
- Full-history, complete OOS, late-entry OOS, yearly, configured stage years, nine sensitivity neighbors, and doubled-cost results are identifiable in artifacts.
- All six effectiveness gates are stored and rendered whether they pass or fail.
- Every catalog index has a result or exclusion reason.
- CSV, Markdown, and NiceGUI values share one durable output source.
- Existing ETF behavior is unchanged and the full test suite passes.
- Browser QA uses real full-run artifacts at desktop and mobile widths.
- The final user-facing conclusion distinguishes historical evidence from future performance and lists selection/correlation/execution limitations.
