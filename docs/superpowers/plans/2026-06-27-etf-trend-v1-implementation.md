# ETF Trend V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a configurable and backtestable A-share ETF trend V1 strategy based on MA60 trend, 60/120-day skip-5 momentum, ATR risk filters, and research candidate comparison.

**Architecture:** Keep the existing MA51/MA120 strategy path intact and add V1 behavior through additive fields, a new `TrendV1Strategy`, and new research candidates. Technical features remain centralized in `src/etf_trading/strategy/features.py`; research signal generation consumes parameterized `StrategyCandidate` fields without changing the T+1 execution model.

**Tech Stack:** Python, pandas, dataclasses, PyYAML, pytest, local Parquet research data, existing `StrategySignal` and `BacktestEngine`.

---

## File Structure

- Modify `src/etf_trading/strategy/features.py`: add MA20/MA60/MA120, MA60 slope, skip-5 momentum, ATR20, and ATR distance from MA20.
- Modify `tests/test_features.py`: cover the new feature columns and missing OHLC behavior.
- Modify `src/etf_trading/strategy/trend.py`: add `TrendV1Strategy` while preserving `TrendStrategy`.
- Modify `tests/test_strategy.py`: cover V1 entry, blocked entries, exits, and market-risk reduction.
- Modify `src/etf_trading/research/models.py`: add optional V1 candidate fields with backwards-compatible defaults.
- Modify `src/etf_trading/research/config.py`: parse tuple/list fields from YAML.
- Modify `src/etf_trading/research/signals.py`: apply V1 candidate filters and trailing ATR exit in the research state machine.
- Modify `tests/test_research_cli_config.py`: cover YAML parsing for V1 fields.
- Modify `tests/test_research_signals.py`: cover V1 candidate signal generation.
- Modify `src/etf_trading/risk/position_sizing.py`: expose theme group, aggregate, risk budget, and drawdown overlay caps.
- Modify `tests/test_risk.py`: cover the new risk helper methods.
- Modify `configs/strategy.yaml`: add `trend_v1` parameters.
- Modify `configs/risk.yaml`: add V1 risk fields without removing existing fields.
- Modify `configs/research.yaml`: add V1 research candidates while keeping existing candidates.

---

### Task 1: Add ETF Trend V1 Technical Features

**Files:**
- Modify: `tests/test_features.py`
- Modify: `src/etf_trading/strategy/features.py`

- [ ] **Step 1: Write failing feature tests**

Append these tests to `tests/test_features.py`:

```python
def test_adds_trend_v1_moving_averages_slope_skip_momentum_and_atr():
    result = add_technical_features(_price_frame(180))

    last = result.iloc[-1]
    assert last["ma20"] == np.mean(np.arange(161, 181))
    assert last["ma60"] == np.mean(np.arange(121, 181))
    assert last["ma120"] == np.mean(np.arange(61, 181))
    assert last["ma60_slope_20"] > 0
    assert last["momentum_60_skip5"] == result["close"].iloc[-6] / result["close"].iloc[-66] - 1.0
    assert last["momentum_120_skip5"] == result["close"].iloc[-6] / result["close"].iloc[-126] - 1.0
    assert last["atr20"] > 0
    assert last["distance_ma20_atr"] > 0


def test_atr_is_missing_when_high_low_or_close_are_missing():
    prices = _price_frame(80).drop(columns=["high"])

    result = add_technical_features(prices)

    assert "atr20" in result.columns
    assert result["atr20"].isna().all()
    assert result["distance_ma20_atr"].isna().all()
```

- [ ] **Step 2: Run feature tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_features.py -v
```

Expected: FAIL because `ma20`, `ma60`, `ma60_slope_20`, `momentum_60_skip5`, `atr20`, or `distance_ma20_atr` do not exist yet.

- [ ] **Step 3: Implement V1 features**

Update `src/etf_trading/strategy/features.py` so the constants and function include:

```python
MA_WINDOWS = (20, 51, 60, 120, 250, 850)
MOMENTUM_WINDOWS = (20, 60, 120)


def add_technical_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Return prices with moving averages, momentum, ATR, and risk features."""

    if prices.empty:
        return prices.copy()

    required = {"trade_date", "close"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"prices missing required columns: {sorted(missing)}")

    result = prices.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result = result.sort_values("trade_date").reset_index(drop=True)

    close = result["close"].astype(float)
    for window in MA_WINDOWS:
        result[f"ma{window}"] = close.rolling(window=window, min_periods=window).mean()

    for window in MOMENTUM_WINDOWS:
        result[f"momentum_{window}"] = close / close.shift(window) - 1.0

    result["momentum_60_skip5"] = close.shift(5) / close.shift(65) - 1.0
    result["momentum_120_skip5"] = close.shift(5) / close.shift(125) - 1.0
    result["ma60_slope_20"] = result["ma60"] / result["ma60"].shift(20) - 1.0

    if "amount" in result.columns:
        result["avg_amount_20"] = result["amount"].astype(float).rolling(20, min_periods=1).mean()
    else:
        result["avg_amount_20"] = pd.NA

    result["return_1d"] = close.pct_change()
    result["volatility_20"] = result["return_1d"].rolling(20, min_periods=5).std()
    result["drawdown_120"] = close / close.rolling(120, min_periods=20).max() - 1.0

    if {"high", "low", "close"}.issubset(result.columns):
        high = result["high"].astype(float)
        low = result["low"].astype(float)
        previous_close = close.shift(1)
        true_range = pd.concat(
            [
                high - low,
                (high - previous_close).abs(),
                (low - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        result["atr20"] = true_range.rolling(20, min_periods=20).mean()
        result["distance_ma20_atr"] = (close - result["ma20"]) / result["atr20"]
    else:
        result["atr20"] = pd.NA
        result["distance_ma20_atr"] = pd.NA

    return result
```

- [ ] **Step 4: Run feature tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_features.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit feature changes**

Run:

```bash
git add src/etf_trading/strategy/features.py tests/test_features.py
git commit -m "feat: add ETF trend v1 technical features"
```

Expected: commit succeeds and only these two files are staged.

---

### Task 2: Add `TrendV1Strategy`

**Files:**
- Modify: `tests/test_strategy.py`
- Modify: `src/etf_trading/strategy/trend.py`

- [ ] **Step 1: Write failing strategy tests**

Add this import to `tests/test_strategy.py`:

```python
from etf_trading.strategy.trend import TrendStrategy, TrendV1Strategy
```

Add this helper and tests:

```python
def _trend_v1_row(**overrides):
    base = {
        "etf_code": "510300",
        "trade_date": pd.Timestamp("2026-06-25"),
        "close": 10.0,
        "ma20": 9.7,
        "ma60": 9.2,
        "ma120": 8.8,
        "ma60_slope_20": 0.03,
        "momentum_60_skip5": 0.08,
        "momentum_120_skip5": 0.12,
        "momentum_20": 0.03,
        "relative_strength_rank": 0.20,
        "category": "A股宽基",
        "avg_amount_20": 150_000_000,
        "premium_rate": 0.001,
        "atr20": 0.18,
        "distance_ma20_atr": 1.67,
        "data_quality_score": 0.98,
        "underlying_market_open": True,
        "last_action_date": pd.Timestamp("2026-05-30"),
    }
    base.update(overrides)
    return pd.Series(base)


def test_trend_v1_buys_when_all_core_filters_pass():
    strategy = TrendV1Strategy(min_trade_interval_days=10)

    signal = strategy.evaluate(_trend_v1_row(), market_risk_on=True)

    assert signal.action == "BUY"
    assert signal.target_weight > 0
    assert "price_above_MA60" in signal.trigger_rules
    assert "MA20_above_MA60" in signal.trigger_rules
    assert "not_overextended_2ATR" in signal.trigger_rules


def test_trend_v1_blocks_when_ma20_is_not_above_ma60():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(ma20=9.0), market_risk_on=True)

    assert signal.action == "HOLD"
    assert "趋势未满足" in signal.reason


def test_trend_v1_blocks_overheated_new_entries():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(distance_ma20_atr=2.4), market_risk_on=True)

    assert signal.action == "HOLD"
    assert "过热" in signal.reason
    assert "overextended_2ATR" in signal.risk_tags


def test_trend_v1_sells_when_close_breaks_ma60():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(close=9.0, ma60=9.2), market_risk_on=True, current_weight=0.10)

    assert signal.action == "SELL"
    assert signal.target_weight == 0.0
    assert "close_below_MA60" in signal.trigger_rules


def test_trend_v1_reduces_existing_position_when_market_risk_is_off():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(), market_risk_on=False, current_weight=0.12)

    assert signal.action == "REDUCE"
    assert signal.target_weight == 0.06
```

- [ ] **Step 2: Run strategy tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_strategy.py -v
```

Expected: FAIL because `TrendV1Strategy` is not defined.

- [ ] **Step 3: Implement `TrendV1Strategy`**

Add this class to `src/etf_trading/strategy/trend.py` below `TrendStrategy`:

```python
class TrendV1Strategy:
    """MA60/ATR ETF trend strategy for research and semi-automated review."""

    def __init__(
        self,
        min_trade_interval_days: int = 10,
        min_avg_amount_20: float = 100_000_000,
        max_abs_premium_rate: float = 0.005,
        max_atr_distance_from_ma20: float = 2.0,
        sizer: PositionSizer | None = None,
    ) -> None:
        self.min_trade_interval_days = min_trade_interval_days
        self.min_avg_amount_20 = min_avg_amount_20
        self.max_abs_premium_rate = max_abs_premium_rate
        self.max_atr_distance_from_ma20 = max_atr_distance_from_ma20
        self.sizer = sizer or PositionSizer()

    def evaluate(
        self,
        row: pd.Series,
        market_risk_on: bool,
        current_weight: float = 0.0,
    ) -> StrategySignal:
        etf_code = str(row.get("etf_code", ""))
        trade_date = pd.Timestamp(row.get("trade_date"))
        category = str(row.get("category", "A股主题"))

        quality = _safe_float(row.get("data_quality_score"), default=1.0)
        if quality < 0.9:
            return TrendStrategy._signal(etf_code, trade_date, "FORBID", 0.0, "数据质量不足", ["data_quality"], ["数据质量"])

        if is_hk_cross_market(category) and row.get("underlying_market_open") is False:
            return TrendStrategy._signal(etf_code, trade_date, "FORBID", 0.0, "底层市场休市，折溢价风险升高", ["hk_market_closed"], ["底层市场休市"])

        avg_amount = _safe_float(row.get("avg_amount_20"))
        if avg_amount < self.min_avg_amount_20:
            return TrendStrategy._signal(etf_code, trade_date, "FORBID", 0.0, "近20日成交额不足", ["liquidity"], ["流动性"])

        premium = _safe_float(row.get("premium_rate"))
        if abs(premium) > self.max_abs_premium_rate:
            return TrendStrategy._signal(etf_code, trade_date, "FORBID", 0.0, "折溢价异常，禁止新增买入", ["premium"], ["折溢价"])

        close = _safe_float(row.get("close"))
        ma20 = _safe_float(row.get("ma20"))
        ma60 = _safe_float(row.get("ma60"))
        ma60_slope = _safe_float(row.get("ma60_slope_20"))
        momentum_60_skip5 = _safe_float(row.get("momentum_60_skip5"))
        momentum_120_skip5 = _safe_float(row.get("momentum_120_skip5"))
        momentum_20 = _safe_float(row.get("momentum_20"))
        rs_rank = _safe_float(row.get("relative_strength_rank"), default=1.0)
        distance_ma20_atr = _safe_float(row.get("distance_ma20_atr"), default=math.inf)

        if current_weight > 0 and close < ma60:
            return TrendStrategy._signal(etf_code, trade_date, "SELL", 0.0, "跌破MA60，趋势失效", ["close_below_MA60"], ["趋势失效"])

        if not market_risk_on:
            if current_weight > 0:
                return TrendStrategy._signal(etf_code, trade_date, "REDUCE", current_weight * 0.5, "大盘风险过滤关闭，降低权益仓位", ["market_risk_off"], ["大盘风险"])
            return TrendStrategy._signal(etf_code, trade_date, "HOLD", 0.0, "大盘风险过滤关闭，暂不新增", ["market_risk_off"], ["大盘风险"])

        if distance_ma20_atr > self.max_atr_distance_from_ma20:
            return TrendStrategy._signal(etf_code, trade_date, "HOLD", current_weight, "价格相对MA20过热，暂停新增", ["no_new_buy"], ["overextended_2ATR"])

        buy_conditions = [
            close > ma60,
            ma20 > ma60,
            ma60_slope > 0,
            momentum_60_skip5 > 0,
            momentum_120_skip5 > 0,
            rs_rank <= 0.30,
        ]
        if all(buy_conditions):
            if not _trade_interval_ok(row.get("last_action_date"), trade_date, self.min_trade_interval_days):
                return TrendStrategy._signal(etf_code, trade_date, "HOLD", current_weight, "低频交易约束：距离上次主动交易不足", ["低频交易约束"], [])

            target = self.sizer.recommend_buy_percentage(
                category=category,
                current_weight=current_weight,
                target_weight=self.sizer.single_etf_cap(category),
            ).target_weight
            return TrendStrategy._signal(
                etf_code,
                trade_date,
                "BUY",
                target,
                "ETF趋势V1信号触发",
                [
                    "price_above_MA60",
                    "MA20_above_MA60",
                    "MA60_slope_positive",
                    "momentum_60_skip5_positive",
                    "momentum_120_skip5_positive",
                    "relative_strength_top_30pct",
                    "not_overextended_2ATR",
                ],
                [],
            )

        if close < ma20 and momentum_20 < 0 and current_weight > 0:
            return TrendStrategy._signal(etf_code, trade_date, "REDUCE", current_weight * 0.5, "跌破MA20且短期动量转弱", ["close_below_MA20", "momentum_20_negative"], [])

        return TrendStrategy._signal(etf_code, trade_date, "HOLD", current_weight, "趋势未满足新交易条件", ["no_action"], [])
```

- [ ] **Step 4: Run strategy tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_strategy.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit strategy changes**

Run:

```bash
git add src/etf_trading/strategy/trend.py tests/test_strategy.py
git commit -m "feat: add ETF trend v1 strategy"
```

Expected: commit succeeds.

---

### Task 3: Extend Research Candidates for Trend V1

**Files:**
- Modify: `src/etf_trading/research/models.py`
- Modify: `src/etf_trading/research/config.py`
- Modify: `src/etf_trading/research/signals.py`
- Modify: `tests/test_research_cli_config.py`
- Modify: `tests/test_research_signals.py`

- [ ] **Step 1: Write failing YAML parsing test**

Append this test to `tests/test_research_cli_config.py`:

```python
def test_load_research_candidates_parses_trend_v1_fields(tmp_path: Path):
    config_path = tmp_path / "research.yaml"
    config_path.write_text(
        """
candidates:
  - name: etf_trend_v1_standard
    entry_ma: ma60
    trend_ma: ma60
    exit_ma: ma60
    momentum_windows: []
    skip_momentum_windows: [60, 120]
    required_ma_relations:
      - [ma20, ma60]
    slope_field: ma60_slope_20
    rs_rank_max: 0.30
    max_atr_distance_from_ma: 2.0
    trailing_atr_multiple: 3.0
    min_trade_interval_days: 10
    target_weight: 1.0
""",
        encoding="utf-8",
    )

    candidates = load_research_candidates(config_path)

    candidate = candidates[0]
    assert candidate.name == "etf_trend_v1_standard"
    assert candidate.skip_momentum_windows == (60, 120)
    assert candidate.required_ma_relations == (("ma20", "ma60"),)
    assert candidate.slope_field == "ma60_slope_20"
    assert candidate.max_atr_distance_from_ma == 2.0
    assert candidate.trailing_atr_multiple == 3.0
```

- [ ] **Step 2: Write failing research signal tests**

Add these fields to `_featured_prices()` in `tests/test_research_signals.py`:

```python
"ma60": [9.6, 10.0, 10.1],
"ma60_slope_20": [0.01, 0.03, 0.03],
"momentum_60_skip5": [0.01, 0.08, 0.07],
"momentum_120_skip5": [0.02, 0.10, 0.09],
"atr20": [0.20, 0.20, 0.20],
"distance_ma20_atr": [-0.5, 1.5, 1.0],
```

Append these tests:

```python
def test_generate_candidate_signals_supports_trend_v1_filters():
    candidate = StrategyCandidate(
        name="etf_trend_v1_standard",
        entry_ma="ma60",
        trend_ma="ma60",
        exit_ma="ma60",
        momentum_windows=(),
        skip_momentum_windows=(60, 120),
        required_ma_relations=(("ma20", "ma60"),),
        slope_field="ma60_slope_20",
        rs_rank_max=0.30,
        max_atr_distance_from_ma=2.0,
        min_trade_interval_days=1,
    )

    signals = generate_candidate_signals("510300", _featured_prices(), candidate)

    assert len(signals) == 1
    assert signals[0].action == "BUY"
    assert "ma20_above_ma60" in signals[0].trigger_rules
    assert "ma60_slope_20_positive" in signals[0].trigger_rules
    assert "momentum_60_skip5_positive" in signals[0].trigger_rules
    assert "not_overextended_2ATR" in signals[0].trigger_rules


def test_generate_candidate_signals_blocks_trend_v1_atr_overheat():
    candidate = StrategyCandidate(
        name="etf_trend_v1_standard",
        entry_ma="ma60",
        trend_ma="ma60",
        exit_ma="ma60",
        momentum_windows=(),
        skip_momentum_windows=(60, 120),
        required_ma_relations=(("ma20", "ma60"),),
        slope_field="ma60_slope_20",
        rs_rank_max=0.30,
        max_atr_distance_from_ma=2.0,
        min_trade_interval_days=1,
    )

    signals = generate_candidate_signals(
        "510300",
        _featured_prices(distance_ma20_atr=[-0.5, 2.4, 2.2]),
        candidate,
    )

    assert signals == []


def test_generate_candidate_signals_sells_on_trailing_atr_stop():
    candidate = StrategyCandidate(
        name="etf_trend_v1_standard",
        entry_ma="ma60",
        trend_ma="ma60",
        exit_ma="ma60",
        momentum_windows=(),
        skip_momentum_windows=(60, 120),
        required_ma_relations=(("ma20", "ma60"),),
        slope_field="ma60_slope_20",
        rs_rank_max=0.30,
        max_atr_distance_from_ma=2.0,
        trailing_atr_multiple=3.0,
        min_trade_interval_days=1,
    )

    signals = generate_candidate_signals(
        "510300",
        _featured_prices(
            close=[9.8, 10.6, 9.9],
            ma60=[9.6, 10.0, 9.6],
            atr20=[0.20, 0.20, 0.20],
        ),
        candidate,
    )

    assert [signal.action for signal in signals] == ["BUY", "SELL"]
    assert "trailing_ATR_stop" in signals[1].trigger_rules
```

- [ ] **Step 3: Run research tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_research_cli_config.py tests/test_research_signals.py -v
```

Expected: FAIL because `StrategyCandidate` and signal logic do not support V1 fields yet.

- [ ] **Step 4: Extend `StrategyCandidate`**

Update `src/etf_trading/research/models.py`:

```python
@dataclass(frozen=True)
class StrategyCandidate:
    """A parameterized trend rule used for research, not live advice."""

    name: str
    entry_ma: str = "ma51"
    trend_ma: str = "ma120"
    exit_ma: str = "ma120"
    momentum_windows: tuple[int, ...] = (20, 60)
    skip_momentum_windows: tuple[int, ...] = ()
    required_ma_relations: tuple[tuple[str, str], ...] = ()
    slope_field: str | None = None
    rs_rank_max: float | None = 0.30
    max_distance_from_entry_ma: float | None = 0.12
    max_recent_return_20: float | None = 0.25
    max_atr_distance_from_ma: float | None = None
    atr_distance_field: str = "distance_ma20_atr"
    trailing_atr_multiple: float | None = None
    trailing_atr_field: str = "atr20"
    min_trade_interval_days: int = 10
    target_weight: float = 1.0
    require_trend_regime: bool = False
```

- [ ] **Step 5: Parse V1 fields from YAML**

Update `_candidate_from_mapping()` in `src/etf_trading/research/config.py`:

```python
def _candidate_from_mapping(item: Any) -> StrategyCandidate:
    if not isinstance(item, dict):
        raise ValueError("each research candidate must be a mapping")
    values = dict(item)
    if "name" not in values:
        raise ValueError("each research candidate must include a name")
    if "momentum_windows" in values:
        values["momentum_windows"] = tuple(int(window) for window in values["momentum_windows"])
    if "skip_momentum_windows" in values:
        values["skip_momentum_windows"] = tuple(int(window) for window in values["skip_momentum_windows"])
    if "required_ma_relations" in values:
        values["required_ma_relations"] = tuple(
            (str(left), str(right)) for left, right in values["required_ma_relations"]
        )
    return StrategyCandidate(**values)
```

- [ ] **Step 6: Implement V1 research filters and trailing ATR exit**

Update `src/etf_trading/research/signals.py`:

```python
def generate_candidate_signals(
    etf_code: str,
    featured_prices: pd.DataFrame,
    candidate: StrategyCandidate,
    category: str = "A股行业",
) -> list[StrategySignal]:
    """Generate close-of-day research signals for one ETF and candidate."""

    if featured_prices.empty:
        return []

    frame = featured_prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date").reset_index(drop=True)

    signals: list[StrategySignal] = []
    in_position = False
    last_action_date: pd.Timestamp | None = None
    highest_close_since_entry = math.nan
    regime_classifier = TrendRegimeClassifier()

    for _, row in frame.iterrows():
        trade_date = pd.Timestamp(row["trade_date"]).normalize()
        close = _safe_float(row.get("close"), default=math.nan)

        if in_position and not _is_missing(close):
            highest_close_since_entry = close if _is_missing(highest_close_since_entry) else max(highest_close_since_entry, close)

        trailing_exit, trailing_rules = _trailing_atr_exit(row, candidate, close, highest_close_since_entry)
        if in_position and (trailing_exit or _exit_condition(row, candidate, close)):
            trigger_rules = trailing_rules or [f"price_below_{candidate.exit_ma}"]
            signals.append(
                StrategySignal(
                    etf_code=etf_code,
                    trade_date=trade_date,
                    action="SELL",
                    target_weight=0.0,
                    reason=f"{candidate.name}: exit rule triggered",
                    trigger_rules=trigger_rules,
                )
            )
            in_position = False
            highest_close_since_entry = math.nan
            last_action_date = trade_date
            continue

        if in_position:
            continue

        entry_ok, trigger_rules = _entry_condition(row, candidate, close)
        if not entry_ok:
            continue
        risk_tags = [category]
        if candidate.require_trend_regime:
            regime = regime_classifier.classify(row)
            if not regime.allows_new_position:
                continue
            trigger_rules = trigger_rules + regime.trigger_rules
            risk_tags.extend(regime.risk_tags)
        if not _trade_interval_ok(last_action_date, trade_date, candidate.min_trade_interval_days):
            continue

        signals.append(
            StrategySignal(
                etf_code=etf_code,
                trade_date=trade_date,
                action="BUY",
                target_weight=candidate.target_weight,
                reason=f"{candidate.name}: right-side entry",
                trigger_rules=trigger_rules,
                risk_tags=risk_tags,
            )
        )
        in_position = True
        highest_close_since_entry = close
        last_action_date = trade_date

    return signals
```

Then extend `_entry_condition()`:

```python
    for left_field, right_field in candidate.required_ma_relations:
        left_value = _safe_float(row.get(left_field), default=math.nan)
        right_value = _safe_float(row.get(right_field), default=math.nan)
        if _is_missing(left_value) or _is_missing(right_value) or left_value <= right_value:
            return False, trigger_rules
        trigger_rules.append(f"{left_field}_above_{right_field}")

    if candidate.slope_field is not None:
        slope = _safe_float(row.get(candidate.slope_field), default=math.nan)
        if _is_missing(slope) or slope <= 0:
            return False, trigger_rules
        trigger_rules.append(f"{candidate.slope_field}_positive")

    for window in candidate.skip_momentum_windows:
        field = f"momentum_{window}_skip5"
        value = _safe_float(row.get(field), default=math.nan)
        if _is_missing(value) or value <= 0:
            return False, trigger_rules
        trigger_rules.append(f"{field}_positive")

    if candidate.max_atr_distance_from_ma is not None:
        atr_distance = _safe_float(row.get(candidate.atr_distance_field), default=math.nan)
        if _is_missing(atr_distance) or atr_distance > candidate.max_atr_distance_from_ma:
            return False, trigger_rules
        trigger_rules.append(f"not_overextended_{candidate.max_atr_distance_from_ma:g}ATR")
```

Add helper:

```python
def _trailing_atr_exit(
    row: pd.Series,
    candidate: StrategyCandidate,
    close: float,
    highest_close_since_entry: float,
) -> tuple[bool, list[str]]:
    if candidate.trailing_atr_multiple is None:
        return False, []
    atr = _safe_float(row.get(candidate.trailing_atr_field), default=math.nan)
    if _is_missing(close) or _is_missing(atr) or _is_missing(highest_close_since_entry):
        return False, []
    stop = highest_close_since_entry - candidate.trailing_atr_multiple * atr
    if close <= stop:
        return True, ["trailing_ATR_stop"]
    return False, []
```

- [ ] **Step 7: Run research tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_research_cli_config.py tests/test_research_signals.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit research changes**

Run:

```bash
git add src/etf_trading/research/models.py src/etf_trading/research/config.py src/etf_trading/research/signals.py tests/test_research_cli_config.py tests/test_research_signals.py
git commit -m "feat: add ETF trend v1 research candidates"
```

Expected: commit succeeds.

---

### Task 4: Add Risk Configuration Helpers and YAML Parameters

**Files:**
- Modify: `tests/test_risk.py`
- Modify: `src/etf_trading/risk/position_sizing.py`
- Modify: `configs/strategy.yaml`
- Modify: `configs/risk.yaml`
- Modify: `configs/research.yaml`

- [ ] **Step 1: Write failing risk tests**

Append these tests to `tests/test_risk.py`:

```python
def test_theme_group_and_aggregate_caps_are_available():
    sizer = PositionSizer()

    assert sizer.theme_group_cap("科技高相关") == 0.25
    assert sizer.aggregate_cap("industry_theme_total") == 0.50
    assert sizer.risk_budget("A股宽基") == 0.0075
    assert sizer.risk_budget("A股主题") == 0.0040


def test_drawdown_overlay_returns_equity_cap_multiplier():
    sizer = PositionSizer()

    assert sizer.drawdown_equity_multiplier(0.05) == 1.0
    assert sizer.drawdown_equity_multiplier(0.08) == 0.75
    assert sizer.drawdown_equity_multiplier(0.12) == 0.30
    assert sizer.drawdown_equity_multiplier(0.15) == 0.0
```

- [ ] **Step 2: Run risk tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_risk.py -v
```

Expected: FAIL because new helper methods do not exist.

- [ ] **Step 3: Implement risk helpers**

Add these constants and methods to `src/etf_trading/risk/position_sizing.py` inside `PositionSizer`:

```python
    THEME_GROUP_CAPS = {
        "科技高相关": 0.25,
        "港股跨境": 0.20,
    }

    AGGREGATE_CAPS = {
        "industry_theme_total": 0.50,
    }

    RISK_BUDGETS = {
        "A股宽基": 0.0075,
        "A股行业": 0.0050,
        "A股主题": 0.0040,
        "港股宽基": 0.0050,
        "港股科技": 0.0040,
        "港股医药": 0.0040,
    }

    DRAWDOWN_EQUITY_MULTIPLIERS = (
        (0.15, 0.0),
        (0.12, 0.30),
        (0.08, 0.75),
    )

    def theme_group_cap(self, group_name: str) -> float:
        return self.THEME_GROUP_CAPS.get(group_name, 0.25)

    def aggregate_cap(self, cap_name: str) -> float:
        return self.AGGREGATE_CAPS.get(cap_name, 1.0)

    def risk_budget(self, category: str) -> float:
        return self.RISK_BUDGETS.get(category, 0.0040)

    def drawdown_equity_multiplier(self, drawdown: float) -> float:
        absolute_drawdown = abs(drawdown)
        for threshold, multiplier in self.DRAWDOWN_EQUITY_MULTIPLIERS:
            if absolute_drawdown >= threshold:
                return multiplier
        return 1.0
```

- [ ] **Step 4: Run risk tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_risk.py -v
```

Expected: PASS.

- [ ] **Step 5: Add V1 strategy config**

Modify `configs/strategy.yaml` by keeping the existing `trend` block and adding:

```yaml
trend_v1:
  moving_averages: [20, 60, 120, 250, 850]
  momentum_windows: [60, 120]
  momentum_skip_days: 5
  relative_strength_buy_rank: 0.30
  min_trade_interval_days: 10
  min_listing_days: 252
  min_avg_amount_20: 100000000
  compatibility_min_avg_amount_20: 30000000
  max_abs_premium_rate: 0.005
  max_cross_market_premium_rate: 0.015
  atr_window: 20
  max_atr_distance_from_ma20: 2.0
  trailing_atr_multiple: 3.0
  initial_stop_atr_multiple: 2.5
  initial_stop_min_pct: 0.05
  initial_stop_max_pct: 0.12
  max_recent_return_5: 0.12
  max_recent_return_20: 0.25
```

- [ ] **Step 6: Add V1 risk config**

Modify `configs/risk.yaml` by preserving existing keys and adding:

```yaml
trend_v1:
  theme_group_caps:
    科技高相关: 0.25
    港股跨境: 0.20
  aggregate_caps:
    industry_theme_total: 0.50
  risk_budgets:
    A股宽基: 0.0075
    A股行业: 0.0050
    A股主题: 0.0040
    港股宽基: 0.0050
    港股科技: 0.0040
    港股医药: 0.0040
  drawdown_overlay:
    warning_8pct_multiplier: 0.75
    reduce_12pct_equity_cap: 0.30
    review_15pct_equity_cap: 0.0
```

- [ ] **Step 7: Add V1 research candidates**

Append to `configs/research.yaml`:

```yaml
  - name: etf_trend_v1_standard
    entry_ma: ma60
    trend_ma: ma60
    exit_ma: ma60
    momentum_windows: []
    skip_momentum_windows: [60, 120]
    required_ma_relations:
      - [ma20, ma60]
    slope_field: ma60_slope_20
    rs_rank_max: 0.30
    max_distance_from_entry_ma: null
    max_recent_return_20: 0.25
    max_atr_distance_from_ma: 2.0
    trailing_atr_multiple: 3.0
    min_trade_interval_days: 10
    target_weight: 1.0
    require_trend_regime: false
  - name: etf_trend_v1_width_filtered
    entry_ma: ma60
    trend_ma: ma60
    exit_ma: ma60
    momentum_windows: []
    skip_momentum_windows: [60, 120]
    required_ma_relations:
      - [ma20, ma60]
    slope_field: ma60_slope_20
    rs_rank_max: 0.30
    max_distance_from_entry_ma: null
    max_recent_return_20: 0.25
    max_atr_distance_from_ma: 2.0
    trailing_atr_multiple: 3.0
    min_trade_interval_days: 10
    target_weight: 1.0
    require_trend_regime: true
  - name: etf_trend_v1_tight_heat_filter
    entry_ma: ma60
    trend_ma: ma60
    exit_ma: ma60
    momentum_windows: []
    skip_momentum_windows: [60, 120]
    required_ma_relations:
      - [ma20, ma60]
    slope_field: ma60_slope_20
    rs_rank_max: 0.30
    max_distance_from_entry_ma: null
    max_recent_return_20: 0.18
    max_atr_distance_from_ma: 1.5
    trailing_atr_multiple: 3.0
    min_trade_interval_days: 10
    target_weight: 1.0
    require_trend_regime: false
```

- [ ] **Step 8: Run config and risk tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_risk.py tests/test_research_cli_config.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit config and risk changes**

Run:

```bash
git add configs/strategy.yaml configs/risk.yaml configs/research.yaml src/etf_trading/risk/position_sizing.py tests/test_risk.py
git commit -m "feat: configure ETF trend v1 risk and research"
```

Expected: commit succeeds.

---

### Task 5: Full Verification and Research Smoke Run

**Files:**
- No planned code changes.
- Possible generated outputs under `reports/research/` from the smoke run.

- [ ] **Step 1: Run the full unit test suite**

Run:

```bash
.venv/bin/python -m pytest
```

Expected: PASS. If failures appear in tests unrelated to ETF Trend V1, inspect whether they predate this work before editing.

- [ ] **Step 2: Run the research smoke test**

Run:

```bash
.venv/bin/python scripts/run_research.py --limit 20
```

Expected: command completes and writes or updates:

```text
reports/research/research_results.csv
reports/research/candidate_ranking.csv
```

If local Parquet data is missing, record the exact exception and do not fabricate results.

- [ ] **Step 3: Inspect candidate ranking**

Run:

```bash
tail -n 20 reports/research/candidate_ranking.csv
```

Expected: V1 candidates such as `etf_trend_v1_standard` appear in the ranking if the smoke run completed.

- [ ] **Step 4: Check git status**

Run:

```bash
git status --short
```

Expected: only intended source/config/test files and generated research report files are changed. Do not stage generated reports unless the project already tracks them and the user wants them committed.

- [ ] **Step 5: Final implementation commit if needed**

If Task 5 required small fixes, commit them:

```bash
git add <specific fixed files>
git commit -m "test: verify ETF trend v1 implementation"
```

Expected: commit succeeds. If no fixes were needed, do not create an empty commit.

---

## Self-Review Notes

- Spec coverage: Tasks 1-4 cover features, strategy, research candidates, config, risk caps, and tests. Task 5 covers full verification and research smoke execution.
- Explicit non-goals from the spec remain out of scope: full point-in-time ETF universe, delisted ETF data, full market breadth from individual stocks, multi-ETF portfolio execution, and automated trading.
- Backwards compatibility is preserved by keeping `TrendStrategy`, retaining old research candidates, and adding new `StrategyCandidate` fields with default values.
- T+1 execution remains in `BacktestEngine`; this plan only changes signal generation and candidate parameters.
