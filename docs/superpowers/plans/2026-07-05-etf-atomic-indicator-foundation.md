# ETF Atomic Indicator Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ETF platform foundation for a daily relative-strength workflow by exposing full exchange-traded ETF coverage, atomic indicators, and data-completeness diagnostics without weighted scores or trading advice.

**Architecture:** Keep provider normalization, feature calculation, atomic-indicator calculation, NiceGUI view models, and NiceGUI page rendering as separate layers. `research.atomic_indicators` produces UI-neutral DataFrames from master/history inputs; `nicegui_app.view_models` reshapes them for metrics, filters, and dense tables; `pages.etf_data` renders the new `原子指标` section without running maintenance jobs automatically.

**Tech Stack:** Python 3.11, pandas, AkShare adapter, existing `SQLiteStore`/`ParquetStore`, NiceGUI, pytest.

## Global Constraints

- Do not implement the relative-strength strategy itself.
- Do not calculate a final weighted score.
- Do not expose `BUY`, `SELL`, `REDUCE`, `买入`, `卖出`, or target-position fields in the atomic-indicator table.
- The tradable ETF master pool must come from AkShare `fund_etf_spot_em`; `fund_name_em` can only be auxiliary and must not be merged into the tradable pool.
- The NiceGUI primary entry is `ETF数据 -> 原子指标`; Streamlit remains a fallback and is not the target UI for this work.
- The atomic-indicator page is diagnostic only; long-running repair/catch-up actions remain under `数据维护 -> 补齐任务`.
- Work in the current dirty workspace because the latest NiceGUI style changes are uncommitted there; do not revert unrelated user changes.

---

## File Structure

Create:

- `src/etf_trading/research/atomic_indicators.py`  
  UI-neutral daily/weekly feature health, history coverage, ranks, and atomic indicator snapshot builder.
- `tests/test_atomic_indicators.py`  
  Unit tests for history status, feature status, rankings, missing reasons, and no-score/no-advice schema.

Modify:

- `src/etf_trading/data/provider.py`  
  Add provider capability for exchange-traded ETF spot data while preserving the existing interface.
- `src/etf_trading/data/providers/akshare_provider.py`  
  Make the tradable ETF list spot-only and mark normalized rows as `exchange_traded`.
- `src/etf_trading/strategy/features.py`  
  Add missing daily feature columns and a weekly trend feature helper.
- `src/etf_trading/data/initialization.py`  
  Add a batch job creator for all exchange-traded ETFs from the master table.
- `src/etf_trading/nicegui_app/navigation.py`  
  Add the `原子指标` section under `ETF数据`.
- `src/etf_trading/nicegui_app/view_models.py`  
  Add atomic indicator summary, rows, and filters without NiceGUI imports.
- `src/etf_trading/nicegui_app/pages/etf_data.py`  
  Render the new atomic-indicator diagnostics section using existing workbench styling.
- `src/etf_trading/nicegui_app/pages/maintenance.py`  
  Add an explicit all-ETF history task entry in `补齐任务`.
- `tests/test_akshare_provider_fallback.py`  
  Update provider boundary tests so `fund_name_em` no longer enters the tradable list.
- `tests/test_features.py`  
  Add tests for new daily and weekly feature columns.
- `tests/test_storage_and_services.py`  
  Add tests for creating all-master ETF history jobs.
- `tests/test_nicegui_navigation.py`  
  Assert `ETF数据` includes `原子指标` and `市场地图` does not.
- `tests/test_nicegui_view_models.py`  
  Add atomic summary/filter/schema tests.
- `docs/task-memory.md`  
  Append implementation and verification notes at the end.

---

### Task 1: Provider Boundary for Exchange-Traded ETF Master

**Files:**
- Modify: `src/etf_trading/data/provider.py`
- Modify: `src/etf_trading/data/providers/akshare_provider.py`
- Test: `tests/test_akshare_provider_fallback.py`

**Interfaces:**
- Produces: `DataProvider.fetch_exchange_traded_etf_spot() -> pd.DataFrame`.
- Produces: `AkShareProvider.fetch_exchange_traded_etf_spot() -> pd.DataFrame`.
- Updates: `AkShareProvider.fetch_etf_list()` returns only exchange-traded spot rows.
- Normalized tradable rows include `tradability_status="exchange_traded"` and `data_source="fund_etf_spot_em"`.

- [ ] **Step 1: Write the failing provider tests**

Update `tests/test_akshare_provider_fallback.py`:

```python
def test_fetch_etf_list_uses_spot_only_for_tradable_master():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeEtfListAk()

    result = provider.fetch_etf_list()

    assert result["etf_code"].tolist() == ["510300"]
    assert result.iloc[0]["tradability_status"] == "exchange_traded"
    assert result.iloc[0]["data_source"] == "fund_etf_spot_em"
    assert "515080" not in set(result["etf_code"])


def test_fetch_exchange_traded_etf_spot_normalizes_realtime_fields():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeEtfListAk()

    result = provider.fetch_exchange_traded_etf_spot()

    row = result.iloc[0]
    assert row["etf_code"] == "510300"
    assert row["exchange"] == "SSE"
    assert row["is_active"] == 1
    assert row["tradability_status"] == "exchange_traded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_akshare_provider_fallback.py -q
```

Expected: FAIL because `fetch_etf_list()` still includes `fund_name_em` fallback and `fetch_exchange_traded_etf_spot()` is missing.

- [ ] **Step 3: Implement the provider boundary**

In `src/etf_trading/data/provider.py`, add a default method:

```python
    def fetch_exchange_traded_etf_spot(self) -> pd.DataFrame:
        """Return the current exchange-traded ETF spot universe."""

        return self.fetch_etf_list()
```

In `src/etf_trading/data/providers/akshare_provider.py`, make `fetch_etf_list()` delegate to `fetch_exchange_traded_etf_spot()` and add:

```python
    def fetch_exchange_traded_etf_spot(self) -> pd.DataFrame:
        raw = _call_with_retries(self.ak.fund_etf_spot_em, "AkShare ETF实时列表")
        frame = _normalize_etf_spot(raw)
        frame["etf_code"] = frame["etf_code"].astype(str).str.zfill(6)
        frame["exchange"] = frame["etf_code"].map(_infer_exchange)
        frame["category"] = frame.apply(lambda r: classify_etf(r["etf_code"], r.get("name", ""), r.get("tracking_index", "")), axis=1)
        frame["is_active"] = 1
        frame["tradability_status"] = "exchange_traded"
        frame["data_source"] = "fund_etf_spot_em"
        return frame.sort_values("etf_code").drop_duplicates(subset=["etf_code"], keep="first").reset_index(drop=True)
```

Extend `_normalize_etf_spot()` to map optional spot fields if present:

```python
rename_map = {
    "代码": "etf_code",
    "名称": "name",
    "最新价": "latest_price",
    "IOPV实时估值": "iopv",
    "基金折价率": "premium_rate",
    "成交额": "amount",
    "成交量": "volume",
    "最新份额": "latest_share",
    "流通市值": "float_market_value",
    "总市值": "total_market_value",
    "涨跌幅": "pct_change",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_akshare_provider_fallback.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/data/provider.py src/etf_trading/data/providers/akshare_provider.py tests/test_akshare_provider_fallback.py
git commit -m "feat: restrict ETF master to exchange-traded spot"
```

---

### Task 2: Daily and Weekly Atomic Feature Columns

**Files:**
- Modify: `src/etf_trading/strategy/features.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Updates: `add_technical_features(prices: pd.DataFrame) -> pd.DataFrame`.
- Produces: `add_weekly_trend_features(prices: pd.DataFrame) -> pd.DataFrame`.
- New daily fields: `return_20`, `return_60`, `return_120`, `avg_amount_5`, `amount_ratio_5_20`, `distance_ma20_pct`, `rolling_high_close_60`, `is_60d_close_breakout`.
- New weekly fields: `weekly_close`, `weekly_ma10`, `weekly_ma30`, `weekly_ma10_slope`, `weekly_ma30_slope`, `weekly_close_above_ma10`, `weekly_close_above_ma30`.

- [ ] **Step 1: Write failing feature tests**

Add to `tests/test_features.py`:

```python
def test_adds_atomic_daily_feature_columns():
    result = add_technical_features(_price_frame(120))

    last = result.iloc[-1]
    assert np.isclose(last["return_20"], last["momentum_20"])
    assert np.isclose(last["return_60"], last["momentum_60"])
    assert np.isclose(last["avg_amount_5"], 1_000_000)
    assert np.isclose(last["amount_ratio_5_20"], 1.0)
    assert np.isclose(last["distance_ma20_pct"], last["close"] / last["ma20"] - 1.0)
    assert last["rolling_high_close_60"] == result["close"].tail(60).max()
    assert bool(last["is_60d_close_breakout"]) is True


def test_add_weekly_trend_features_backfills_latest_week_state():
    result = add_weekly_trend_features(_price_frame(220))

    last = result.iloc[-1]
    assert "weekly_ma10" in result.columns
    assert not pd.isna(last["weekly_close"])
    assert not pd.isna(last["weekly_ma10"])
    assert not pd.isna(last["weekly_ma30"])
    assert isinstance(bool(last["weekly_close_above_ma10"]), bool)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_features.py -q
```

Expected: FAIL because the new daily fields and `add_weekly_trend_features` are missing.

- [ ] **Step 3: Implement daily and weekly features**

In `add_technical_features()`, after momentum and amount calculations, add:

```python
for window in MOMENTUM_WINDOWS:
    result[f"return_{window}"] = result[f"momentum_{window}"]

if "amount" in result.columns:
    amount = result["amount"].astype(float)
    result["avg_amount_5"] = amount.rolling(5, min_periods=1).mean()
    result["avg_amount_20"] = amount.rolling(20, min_periods=1).mean()
    result["amount_ratio_5_20"] = result["avg_amount_5"] / result["avg_amount_20"]
else:
    result["avg_amount_5"] = pd.NA
    result["avg_amount_20"] = pd.NA
    result["amount_ratio_5_20"] = pd.NA

result["distance_ma20_pct"] = close / result["ma20"] - 1.0
result["rolling_high_close_60"] = close.rolling(60, min_periods=60).max()
result["is_60d_close_breakout"] = close >= result["rolling_high_close_60"]
```

Add `add_weekly_trend_features()` to the same module:

```python
def add_weekly_trend_features(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return prices.copy()

    required = {"trade_date", "close"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"prices missing required columns: {sorted(missing)}")

    result = prices.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result = result.sort_values("trade_date").reset_index(drop=True)
    weekly = (
        result.set_index("trade_date")["close"]
        .astype(float)
        .resample("W-FRI")
        .last()
        .dropna()
        .to_frame("weekly_close")
    )
    weekly["weekly_ma10"] = weekly["weekly_close"].rolling(10, min_periods=10).mean()
    weekly["weekly_ma30"] = weekly["weekly_close"].rolling(30, min_periods=30).mean()
    weekly["weekly_ma10_slope"] = weekly["weekly_ma10"] / weekly["weekly_ma10"].shift(4) - 1.0
    weekly["weekly_ma30_slope"] = weekly["weekly_ma30"] / weekly["weekly_ma30"].shift(4) - 1.0
    weekly["weekly_close_above_ma10"] = weekly["weekly_close"] > weekly["weekly_ma10"]
    weekly["weekly_close_above_ma30"] = weekly["weekly_close"] > weekly["weekly_ma30"]
    weekly = weekly.reindex(result["trade_date"], method="ffill")
    weekly = weekly.reset_index(drop=True)
    return pd.concat([result.reset_index(drop=True), weekly], axis=1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_features.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/strategy/features.py tests/test_features.py
git commit -m "feat: add ETF atomic feature columns"
```

---

### Task 3: Atomic Indicator Snapshot Builder

**Files:**
- Create: `src/etf_trading/research/atomic_indicators.py`
- Test: `tests/test_atomic_indicators.py`

**Interfaces:**
- Produces: `ATOMIC_INDICATOR_COLUMNS: list[str]`.
- Produces: `build_etf_atomic_indicator_snapshot(master: pd.DataFrame, parquet_store, *, today: pd.Timestamp | None = None, min_history_rows: int = 252) -> pd.DataFrame`.
- Consumes: `parquet_store.read_prices(etf_code)`.
- The output must not include final score or advice fields.

- [ ] **Step 1: Write failing atomic-indicator tests**

Create `tests/test_atomic_indicators.py`:

```python
import numpy as np
import pandas as pd

from etf_trading.research.atomic_indicators import build_etf_atomic_indicator_snapshot


class FakeParquetStore:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def read_prices(self, code: str) -> pd.DataFrame:
        value = self.frames.get(str(code))
        if isinstance(value, Exception):
            raise value
        return pd.DataFrame() if value is None else value.copy()


def _master() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "etf_code": ["510300", "512880", "513180", "515000"],
            "name": ["沪深300ETF", "证券ETF", "恒生科技ETF", "科技ETF联接"],
            "category": ["A股宽基", "A股行业", "港股科技", "A股科技"],
            "exchange": ["SSE", "SSE", "SSE", "SSE"],
            "amount": [1000.0, 900.0, 800.0, None],
            "tradability_status": ["exchange_traded", "exchange_traded", "exchange_traded", "auxiliary_only"],
        }
    )


def _prices(code: str, rows: int, end: str, close_start: float = 10.0) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp(end), periods=rows)
    close = np.linspace(close_start, close_start + rows - 1, rows)
    return pd.DataFrame(
        {
            "etf_code": code,
            "trade_date": dates,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(rows, 1000),
            "amount": np.linspace(1_000_000, 2_000_000, rows),
        }
    )


def test_atomic_snapshot_reports_history_feature_status_and_ranks():
    snapshot = build_etf_atomic_indicator_snapshot(
        _master(),
        FakeParquetStore(
            {
                "510300": _prices("510300", 300, "2026-07-03", 10.0),
                "512880": _prices("512880", 300, "2026-07-03", 20.0),
                "513180": _prices("513180", 20, "2026-07-03", 30.0),
            }
        ),
        today=pd.Timestamp("2026-07-05"),
    )

    assert snapshot["etf_code"].tolist() == ["510300", "512880", "513180"]
    ready = snapshot[snapshot["etf_code"] == "510300"].iloc[0]
    assert ready["history_status"] == "complete"
    assert ready["feature_status"] == "complete"
    assert ready["return_20_rank_all"] in {1, 2}
    short = snapshot[snapshot["etf_code"] == "513180"].iloc[0]
    assert short["history_status"] == "short_history"
    assert "ma60" in short["missing_feature_names"]


def test_atomic_snapshot_keeps_unreadable_and_missing_rows_diagnostic():
    snapshot = build_etf_atomic_indicator_snapshot(
        _master().iloc[:3],
        FakeParquetStore({"510300": RuntimeError("broken parquet")}),
        today=pd.Timestamp("2026-07-05"),
    )

    assert snapshot.loc[snapshot["etf_code"] == "510300", "history_status"].item() == "read_failed"
    assert snapshot.loc[snapshot["etf_code"] == "512880", "history_status"].item() == "missing_history"
    assert "read_failed" in snapshot.loc[snapshot["etf_code"] == "510300", "missing_feature_names"].item()


def test_atomic_snapshot_schema_excludes_scores_and_trade_advice():
    snapshot = build_etf_atomic_indicator_snapshot(
        _master(),
        FakeParquetStore({"510300": _prices("510300", 300, "2026-07-03")}),
        today=pd.Timestamp("2026-07-05"),
    )

    forbidden = {"score", "weighted_score", "action", "buy", "sell", "target_weight", "买入", "卖出", "目标仓位"}
    assert forbidden.isdisjoint({column.lower() for column in snapshot.columns})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_atomic_indicators.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `etf_trading.research.atomic_indicators`.

- [ ] **Step 3: Implement the snapshot builder**

Create `src/etf_trading/research/atomic_indicators.py` with:

```python
"""Atomic ETF indicator snapshot builders."""

from __future__ import annotations

from typing import Any

import pandas as pd

from etf_trading.strategy.features import add_technical_features, add_weekly_trend_features
from etf_trading.ui.data_coverage import expected_latest_trade_date

ATOMIC_INDICATOR_COLUMNS = [
    "trade_date",
    "etf_code",
    "name",
    "category",
    "exchange",
    "tradability_status",
    "history_status",
    "feature_status",
    "latest_trade_date",
    "history_rows",
    "return_20",
    "return_60",
    "return_20_rank_all",
    "return_60_rank_all",
    "return_20_rank_category",
    "return_60_rank_category",
    "close_above_ma20",
    "ma20_above_ma60",
    "close_above_ma60",
    "ma60_slope_20",
    "weekly_close_above_ma10",
    "weekly_close_above_ma30",
    "avg_amount_5",
    "avg_amount_20",
    "amount_ratio_5_20",
    "distance_ma20_pct",
    "distance_ma20_atr",
    "is_60d_close_breakout",
    "missing_feature_names",
]
```

Add helper functions for code/name/category normalization, safe price reading, last-row feature extraction, and rank assignment. Use `expected_latest_trade_date(today)` to mark `stale` when the latest local trading date is older than expected. Drop rows whose `tradability_status` is not blank or `exchange_traded`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_atomic_indicators.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/research/atomic_indicators.py tests/test_atomic_indicators.py
git commit -m "feat: build ETF atomic indicator snapshots"
```

---

### Task 4: NiceGUI Atomic View Models and Navigation

**Files:**
- Modify: `src/etf_trading/nicegui_app/navigation.py`
- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Test: `tests/test_nicegui_navigation.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Produces: `AtomicIndicatorFilters(query: str = "", category: str = "全部分类", history_status: str = "全部历史状态", feature_status: str = "全部特征状态", min_avg_amount_20: float | None = None, only_breakout: bool = False, only_weekly_ma10: bool = False)`.
- Produces: `build_atomic_indicator_snapshot(snapshot: PlatformSnapshot, parquet_store, today: pd.Timestamp | None = None) -> pd.DataFrame`.
- Produces: `atomic_indicator_summary(frame: pd.DataFrame) -> list[MetricTile]`.
- Produces: `atomic_indicator_rows(frame: pd.DataFrame, filters: AtomicIndicatorFilters | None = None, limit: int = 300) -> list[dict[str, object]]`.

- [ ] **Step 1: Write failing navigation and view-model tests**

Update `tests/test_nicegui_navigation.py`:

```python
assert sections_by_slug["etf-data"] == ["ETF总览", "原子指标", "ETF行情", "搜索加入", "每日计算池", "指数样本池"]
assert "原子指标" not in sections_by_slug["market"]
```

Add to `tests/test_nicegui_view_models.py`:

```python
from etf_trading.nicegui_app.view_models import (
    AtomicIndicatorFilters,
    atomic_indicator_rows,
    atomic_indicator_summary,
)


def _atomic_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "etf_code": ["510300", "512880"],
            "name": ["沪深300ETF", "证券ETF"],
            "category": ["A股宽基", "A股行业"],
            "exchange": ["SSE", "SSE"],
            "history_status": ["complete", "missing_history"],
            "feature_status": ["complete", "missing_features"],
            "latest_trade_date": ["2026-07-03", ""],
            "return_20": [0.08, None],
            "return_60": [0.12, None],
            "return_20_rank_all": [1, None],
            "return_60_rank_all": [1, None],
            "return_20_rank_category": [1, None],
            "return_60_rank_category": [1, None],
            "close_above_ma20": [True, None],
            "ma20_above_ma60": [True, None],
            "close_above_ma60": [True, None],
            "weekly_close_above_ma10": [True, None],
            "weekly_close_above_ma30": [False, None],
            "avg_amount_5": [2_000_000.0, None],
            "avg_amount_20": [1_500_000.0, None],
            "amount_ratio_5_20": [1.33, None],
            "distance_ma20_pct": [0.03, None],
            "distance_ma20_atr": [1.2, None],
            "is_60d_close_breakout": [True, None],
            "missing_feature_names": ["", "missing_history"],
        }
    )


def test_atomic_indicator_summary_counts_data_readiness():
    metrics = atomic_indicator_summary(_atomic_frame())

    assert [metric.label for metric in metrics][:4] == ["ETF主池", "历史完整", "特征完整", "相对强度可算"]
    assert [metric.value for metric in metrics][:4] == ["2", "1", "1", "1"]


def test_atomic_indicator_rows_are_filtered_and_do_not_expose_advice():
    rows = atomic_indicator_rows(
        _atomic_frame(),
        AtomicIndicatorFilters(query="300", only_breakout=True, only_weekly_ma10=True),
    )

    assert len(rows) == 1
    assert rows[0]["ETF代码"] == "510300"
    forbidden = {"综合分", "买入", "卖出", "目标仓位"}
    assert forbidden.isdisjoint(rows[0].keys())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py -q
```

Expected: FAIL because navigation and atomic view-model functions are missing.

- [ ] **Step 3: Implement navigation and view models**

In `src/etf_trading/nicegui_app/navigation.py`, update the `ETF数据` sections:

```python
sections=("ETF总览", "原子指标", "ETF行情", "搜索加入", "每日计算池", "指数样本池"),
```

In `src/etf_trading/nicegui_app/view_models.py`, import the research builder and add the dataclass/functions named in this task. `atomic_indicator_rows()` should map raw columns to Chinese display labels, format percentages with one decimal place, format amounts compactly, show booleans as `是`/`否`/`缺失`, and keep rows with missing data visible.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/nicegui_app/navigation.py src/etf_trading/nicegui_app/view_models.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py
git commit -m "feat: add NiceGUI atomic indicator view models"
```

---

### Task 5: NiceGUI Atomic Indicator Page and Maintenance Entry

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/etf_data.py`
- Modify: `src/etf_trading/nicegui_app/pages/maintenance.py`
- Modify: `src/etf_trading/data/initialization.py`
- Test: `tests/test_storage_and_services.py`

**Interfaces:**
- Produces: `InitializationService.create_history_jobs_for_all_master(start_date: date | str | None = None, end_date: date | str | None = None) -> int`.
- Updates: `pages.etf_data.render()` routes `section == "原子指标"` to an atomic diagnostics renderer.
- Updates: `pages.maintenance` includes a user-triggered all-master ETF history job button.

- [ ] **Step 1: Write failing service test**

Add to `tests/test_storage_and_services.py`:

```python
def test_initialization_service_creates_history_jobs_for_all_master_etfs(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.upsert_etf_master(
        pd.DataFrame(
            [
                {"etf_code": "510300", "name": "沪深300ETF", "exchange": "SSE", "category": "A股宽基", "is_active": 1},
                {"etf_code": "512880", "name": "证券ETF", "exchange": "SSE", "category": "A股行业", "is_active": 1},
            ]
        )
    )

    count = InitializationService(store).create_history_jobs_for_all_master("2021-01-01", "2026-07-03")

    assert count == 2
    with store.connect() as conn:
        jobs = pd.read_sql_query("SELECT job_type, asset_code, start_date, end_date FROM data_fetch_job ORDER BY asset_code", conn)
    assert jobs["asset_code"].tolist() == ["510300", "512880"]
    assert jobs["job_type"].tolist() == ["history", "history"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_storage_and_services.py -q
```

Expected: FAIL because `create_history_jobs_for_all_master` is missing.

- [ ] **Step 3: Implement service and UI wiring**

Add to `InitializationService`:

```python
    def create_history_jobs_for_all_master(self, start_date: date | str | None = None, end_date: date | str | None = None) -> int:
        master = self.store.list_etf_master()
        if master.empty or "etf_code" not in master.columns:
            return 0
        if "is_active" in master.columns:
            master = master[master["is_active"].fillna(1).astype(int) == 1]
        count = 0
        for code in master["etf_code"].astype(str).str.zfill(6).drop_duplicates().sort_values():
            self.store.create_fetch_job("history", code, str(start_date) if start_date else None, str(end_date) if end_date else None)
            count += 1
        return count
```

In `pages.etf_data`, add an `elif section == "原子指标"` branch that builds the atomic snapshot through view models and renders:

- 6-8 `workbench-metric` tiles.
- A `workbench-toolbar` with query/category/status filters and a maintenance-link hint.
- A `workbench-data-table` with `atomic_indicator_rows(...)`.
- An empty state when `parquet_store` is unavailable.

In `pages.maintenance`, add a button in `_render_batch_tasks()`:

```python
all_master_button = ui.button(
    "为全部ETF主池创建历史初始化任务",
    icon="playlist_add_check",
    on_click=lambda: _run_task(
        all_master_button,
        result_area,
        "生成全量ETF历史任务",
        lambda: _service(store, parquet_store).create_history_jobs_for_all_master(),
        lambda result: f"已创建 {result} 个全量 ETF 历史任务",
    ),
).props("dense outline")
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_storage_and_services.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/etf_trading/data/initialization.py src/etf_trading/nicegui_app/pages/etf_data.py src/etf_trading/nicegui_app/pages/maintenance.py tests/test_storage_and_services.py
git commit -m "feat: render ETF atomic indicator diagnostics"
```

---

### Task 6: Verification, Task Memory, and Final Commit Hygiene

**Files:**
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: documented verification and reusable notes.

- [ ] **Step 1: Run focused regression tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_akshare_provider_fallback.py tests/test_features.py tests/test_atomic_indicators.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_storage_and_services.py -q
```

Expected: PASS.

- [ ] **Step 2: Run broader relevant UI/data tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_data_coverage.py tests/test_nicegui_app_import.py tests/test_nicegui_charts.py tests/test_nicegui_state_cache.py -q
```

Expected: PASS, unless pre-existing dirty NiceGUI chart changes introduce unrelated failures; if so, record the exact failure and avoid reverting unrelated files.

- [ ] **Step 3: Check schema text for forbidden output**

Run:

```powershell
rg -n "综合分|买入|卖出|目标仓位|weighted_score|target_weight|BUY|SELL|REDUCE" src\etf_trading\research\atomic_indicators.py src\etf_trading\nicegui_app\view_models.py src\etf_trading\nicegui_app\pages\etf_data.py tests\test_atomic_indicators.py tests\test_nicegui_view_models.py
```

Expected: matches only in tests that assert forbidden fields are absent; production atomic modules must not expose these fields.

- [ ] **Step 4: Append task memory**

Append:

```md
## 2026-07-05 - Implement ETF atomic indicator foundation

- Summary: Added exchange-traded ETF master boundaries, atomic daily/weekly feature columns, UI-neutral ETF atomic snapshots, NiceGUI `ETF数据 -> 原子指标`, and all-master history job creation.
- Verification: `<commands>` passed, or list exact pre-existing failures.
- Watch out next time:
  - Keep `fund_name_em` out of the tradable ETF master pool; use it only as auxiliary discovery data.
  - Keep atomic indicator tables diagnostic-only; scores and trading actions belong to later strategy layers.
  - Long-running all-ETF history work should remain a maintenance task, not an automatic page-load side effect.
```

- [ ] **Step 5: Commit task memory when scoped**

If `docs/task-memory.md` contains only intentional current-session memory changes or the project has accumulated previous memory edits that the user wants tracked, commit it:

```powershell
git add docs/task-memory.md
git commit -m "docs: record ETF atomic indicator foundation work"
```

If unrelated pre-existing dirty memory edits are present, leave it unstaged and mention that final status clearly.

---

## Self-Review

Spec coverage:

- Exchange-traded ETF source boundary: Task 1.
- Daily and weekly feature columns: Task 2.
- History coverage, feature health, ranks, and missing reasons: Task 3.
- NiceGUI `ETF数据 -> 原子指标` with UI-neutral view models: Task 4 and Task 5.
- Data maintenance remains explicit and user-triggered: Task 5.
- No weighted score or trading advice: Global constraints plus Task 3/4 tests.

Placeholder scan:

- No task uses placeholder phrases, vague handling language, or copy-by-reference steps.

Type consistency:

- `build_etf_atomic_indicator_snapshot()` produces English raw columns.
- `atomic_indicator_summary()` consumes the raw DataFrame and returns `MetricTile`.
- `atomic_indicator_rows()` consumes the raw DataFrame and returns Chinese display rows for NiceGUI tables.
- `pages.etf_data` depends on view-model functions, not on raw NiceGUI-inside calculation logic.
