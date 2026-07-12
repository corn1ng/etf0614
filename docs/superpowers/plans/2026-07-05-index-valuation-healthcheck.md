# Index Valuation Healthcheck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a source-switchable index valuation cache and a NiceGUI `市场地图 -> 指数估值体检` page that shows atomic valuation indicators, historical percentiles, data coverage, and missing-data reasons without composite scores or trading advice.

**Architecture:** Keep valuation source normalization, Parquet persistence, valuation healthcheck calculations, UI-neutral view models, and NiceGUI rendering as separate layers. External data sources write normalized valuation history to local Parquet; the healthcheck reads only local cache and returns atomic metric rows with explicit status and reason fields.

**Tech Stack:** Python 3.11, pandas, pyarrow/Parquet, AkShare, NiceGUI, pytest.

## Global Constraints

- Do not calculate index level historical percentiles.
- Do not calculate any weighted valuation score, composite heat score, buy/sell score, or thermometer total.
- Only show atomic valuation indicators: raw value, historical percentile, coverage years, data source, and missing reason.
- Each atomic indicator is calculated independently and marked independently.
- If a field is missing, too short, stale, or invalid, leave that metric percentile blank and show the reason.
- Do not expose `BUY`, `SELL`, `REDUCE`, `买入`, `卖出`, `减仓`, `目标仓位`, `valuation_hot_pct`, `综合分`, `估值总分`, or `买卖分` in production valuation outputs.
- Keep iFind, AKShare, Tushare, CSV, and Parquet import behind provider interfaces so source switching does not change healthcheck calculation or UI.
- All percentile calculations must use only observations with `trade_date <= as_of_date`.
- The primary UI entry is NiceGUI `市场地图 -> 指数估值体检`.

---

## File Structure

- `src/etf_trading/data/index_valuations.py`  
  Normalized valuation schema, provider protocol, source-specific normalizers, and CSV/callable provider adapters.
- `src/etf_trading/data/storage.py`  
  Parquet read/write methods for index valuations and macro series.
- `src/etf_trading/data/providers/akshare_provider.py`  
  AKShare valuation fetch method that combines Legulegu long-history PE/PB and CSIndex recent valuation checks.
- `src/etf_trading/data/index_valuation_service.py`  
  Sync service that fetches normalized valuation frames from a provider and writes them into `ParquetStore`.
- `src/etf_trading/research/index_valuation_health.py`  
  UI-neutral coverage and atomic metric healthcheck calculations.
- `src/etf_trading/nicegui_app/view_models.py`  
  NiceGUI-free view-model helpers for valuation coverage metrics, table rows, filters, and selected-index metric rows.
- `src/etf_trading/nicegui_app/navigation.py`  
  Adds the `指数估值体检` section under `市场地图`.
- `src/etf_trading/nicegui_app/pages/market.py`  
  Renders the new valuation healthcheck section.
- `tests/test_index_valuations.py`  
  Normalization, provider adapters, and Parquet cache tests.
- `tests/test_index_valuation_health.py`  
  Percentile, coverage, missing-data, and forbidden-output tests.
- `tests/test_akshare_provider_fallback.py`  
  AKShare valuation adapter tests using fake AKShare objects.
- `tests/test_index_valuation_service.py`  
  Sync service and CSV import tests.
- `tests/test_nicegui_navigation.py`  
  Navigation boundary tests.
- `tests/test_nicegui_view_models.py`  
  Valuation healthcheck UI-neutral view-model tests.

---

### Task 1: Valuation Schema, Normalization, and Parquet Cache

**Files:**
- Create: `src/etf_trading/data/index_valuations.py`
- Modify: `src/etf_trading/data/storage.py`
- Test: `tests/test_index_valuations.py`

**Interfaces:**
- Produces: `INDEX_VALUATION_COLUMNS: list[str]`.
- Produces: `MACRO_SERIES_COLUMNS: list[str]`.
- Produces: `IndexValuationProvider` protocol with `source_name`, `fetch_index_valuation(...)`, and `fetch_macro_series(...)`.
- Produces: `finalize_index_valuation_frame(frame: pd.DataFrame, index_code: str, data_source: str, source_quality: str) -> pd.DataFrame`.
- Produces: `normalize_macro_series(frame: pd.DataFrame, series_name: str, data_source: str) -> pd.DataFrame`.
- Produces: `ParquetStore.write_index_valuations(index_code: str, frame: pd.DataFrame) -> Path`.
- Produces: `ParquetStore.read_index_valuations(index_code: str) -> pd.DataFrame`.
- Produces: `ParquetStore.write_macro_series(series_name: str, frame: pd.DataFrame) -> Path`.
- Produces: `ParquetStore.read_macro_series(series_name: str) -> pd.DataFrame`.

- [ ] **Step 1: Write failing valuation normalization and storage tests**

Create `tests/test_index_valuations.py` with:

```python
import pandas as pd

from etf_trading.data.index_valuations import (
    INDEX_VALUATION_COLUMNS,
    MACRO_SERIES_COLUMNS,
    finalize_index_valuation_frame,
    normalize_macro_series,
)
from etf_trading.data.storage import ParquetStore


def test_finalize_index_valuation_frame_derives_yields_and_orders_columns():
    raw = pd.DataFrame(
        {
            "trade_date": ["2026-07-03", "2026-07-02"],
            "pe_ttm": [12.5, 10.0],
            "pb": [1.4, 1.3],
            "dividend_yield": [0.025, 0.024],
            "bond_yield_10y": [0.018, 0.019],
        }
    )

    result = finalize_index_valuation_frame(raw, "000300", "unit", "primary")

    assert result.columns.tolist() == INDEX_VALUATION_COLUMNS
    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-02", "2026-07-03"]
    latest = result.iloc[-1]
    assert latest["index_code"] == "000300"
    assert round(float(latest["earnings_yield"]), 4) == 0.08
    assert round(float(latest["erp"]), 4) == 0.062
    assert latest["data_source"] == "unit"
    assert latest["source_quality"] == "primary"


def test_finalize_index_valuation_frame_keeps_invalid_pe_from_yield_derivation():
    raw = pd.DataFrame(
        {
            "trade_date": ["2026-07-03"],
            "pe_ttm": [0],
            "bond_yield_10y": [0.018],
        }
    )

    result = finalize_index_valuation_frame(raw, "000300", "unit", "primary")

    assert pd.isna(result.iloc[0]["earnings_yield"])
    assert pd.isna(result.iloc[0]["erp"])


def test_normalize_macro_series_uses_standard_schema():
    raw = pd.DataFrame({"trade_date": ["2026-07-03"], "value": [0.018]})

    result = normalize_macro_series(raw, "10y_bond_yield", "unit")

    assert result.columns.tolist() == MACRO_SERIES_COLUMNS
    assert result.iloc[0]["series_name"] == "10y_bond_yield"
    assert result.iloc[0]["data_source"] == "unit"


def test_parquet_store_reads_and_writes_index_valuations_and_macro(tmp_path):
    store = ParquetStore(tmp_path)
    valuations = finalize_index_valuation_frame(
        pd.DataFrame({"trade_date": ["2026-07-03"], "pe_ttm": [12.5], "pb": [1.4]}),
        "000300",
        "unit",
        "primary",
    )
    macro = normalize_macro_series(
        pd.DataFrame({"trade_date": ["2026-07-03"], "value": [0.018]}),
        "10y_bond_yield",
        "unit",
    )

    valuation_path = store.write_index_valuations("000300", valuations)
    macro_path = store.write_macro_series("10y_bond_yield", macro)

    assert valuation_path.name == "000300.parquet"
    assert macro_path.name == "10y_bond_yield.parquet"
    assert store.read_index_valuations("000300")["index_code"].tolist() == ["000300"]
    assert store.read_macro_series("10y_bond_yield")["series_name"].tolist() == ["10y_bond_yield"]
    assert store.read_index_valuations("missing").empty
    assert store.read_macro_series("missing").empty
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuations.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `etf_trading.data.index_valuations` or missing `ParquetStore` methods.

- [ ] **Step 3: Add valuation schema and normalization code**

Create `src/etf_trading/data/index_valuations.py` with:

```python
"""Index valuation schemas, normalization helpers, and provider contracts."""

from __future__ import annotations

from collections.abc import Protocol
from datetime import date
from typing import runtime_checkable

import pandas as pd


INDEX_VALUATION_COLUMNS = [
    "index_code",
    "trade_date",
    "pe_ttm",
    "pe_static",
    "pb",
    "ps",
    "dividend_yield",
    "earnings_yield",
    "bond_yield_10y",
    "erp",
    "roe",
    "payout_ratio",
    "forward_pe",
    "data_source",
    "source_quality",
    "source_updated_at",
]

MACRO_SERIES_COLUMNS = ["series_name", "trade_date", "value", "data_source", "source_updated_at"]

NUMERIC_VALUATION_COLUMNS = [
    "pe_ttm",
    "pe_static",
    "pb",
    "ps",
    "dividend_yield",
    "earnings_yield",
    "bond_yield_10y",
    "erp",
    "roe",
    "payout_ratio",
    "forward_pe",
]


@runtime_checkable
class IndexValuationProvider(Protocol):
    source_name: str

    def fetch_index_valuation(self, index_code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        """Return normalized or normalizable valuation rows for one index."""

    def fetch_macro_series(self, series_name: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        """Return normalized macro rows such as 10-year bond yield or CPI."""


def finalize_index_valuation_frame(
    frame: pd.DataFrame,
    index_code: str,
    data_source: str,
    source_quality: str,
) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return pd.DataFrame(columns=INDEX_VALUATION_COLUMNS)

    if "trade_date" not in result.columns:
        raise ValueError("valuation frame missing trade_date")

    result["index_code"] = str(index_code)
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    for column in NUMERIC_VALUATION_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
        result[column] = pd.to_numeric(result[column], errors="coerce")

    pe = result["pe_ttm"]
    if result["earnings_yield"].isna().all():
        result["earnings_yield"] = (1.0 / pe.where(pe > 0)).astype(float)
    if result["erp"].isna().all():
        result["erp"] = result["earnings_yield"] - result["bond_yield_10y"]

    result["data_source"] = data_source
    result["source_quality"] = source_quality
    result["source_updated_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    result = result.drop_duplicates(subset=["index_code", "trade_date"], keep="last")
    return result[INDEX_VALUATION_COLUMNS].sort_values("trade_date").reset_index(drop=True)


def normalize_macro_series(frame: pd.DataFrame, series_name: str, data_source: str) -> pd.DataFrame:
    result = frame.copy()
    if result.empty:
        return pd.DataFrame(columns=MACRO_SERIES_COLUMNS)
    if "trade_date" not in result.columns or "value" not in result.columns:
        raise ValueError("macro series frame must contain trade_date and value")
    result["series_name"] = series_name
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result["data_source"] = data_source
    result["source_updated_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    result = result.drop_duplicates(subset=["series_name", "trade_date"], keep="last")
    return result[MACRO_SERIES_COLUMNS].sort_values("trade_date").reset_index(drop=True)
```

- [ ] **Step 4: Add ParquetStore methods**

Modify `src/etf_trading/data/storage.py` inside `class ParquetStore`:

```python
    def write_index_valuations(self, index_code: str, frame: pd.DataFrame) -> Path:
        path = self.root / "index_valuations" / f"{index_code}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        return path

    def read_index_valuations(self, index_code: str) -> pd.DataFrame:
        path = self.root / "index_valuations" / f"{index_code}.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def write_macro_series(self, series_name: str, frame: pd.DataFrame) -> Path:
        path = self.root / "macro" / f"{series_name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        return path

    def read_macro_series(self, series_name: str) -> pd.DataFrame:
        path = self.root / "macro" / f"{series_name}.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuations.py -q
```

Expected: PASS with 4 tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/etf_trading/data/index_valuations.py src/etf_trading/data/storage.py tests/test_index_valuations.py
git commit -m "feat: add index valuation cache schema"
```

---

### Task 2: Atomic Valuation Healthcheck Calculation

**Files:**
- Create: `src/etf_trading/research/index_valuation_health.py`
- Test: `tests/test_index_valuation_health.py`

**Interfaces:**
- Consumes: `INDEX_VALUATION_COLUMNS`.
- Consumes: `ParquetStore.read_index_valuations(index_code)`.
- Produces: `VALUATION_METRICS: tuple[ValuationMetric, ...]`.
- Produces: `percentile_rank_current(values: pd.Series) -> float`.
- Produces: `build_index_valuation_metric_rows(index_code: str, valuations: pd.DataFrame, *, as_of_date: pd.Timestamp | str | None = None, min_history_rows: int = 756) -> pd.DataFrame`.
- Produces: `build_index_valuation_coverage(definitions: tuple[IndexDefinition, ...], parquet_store, *, as_of_date: pd.Timestamp | str | None = None, min_history_rows: int = 756) -> pd.DataFrame`.

- [ ] **Step 1: Write failing healthcheck tests**

Create `tests/test_index_valuation_health.py` with:

```python
from dataclasses import dataclass

import pandas as pd

from etf_trading.data.index_valuations import finalize_index_valuation_frame
from etf_trading.research.index_valuation_health import (
    build_index_valuation_coverage,
    build_index_valuation_metric_rows,
    percentile_rank_current,
)


@dataclass(frozen=True)
class _Definition:
    index_code: str
    name: str
    market: str = "A股"
    category: str = "A股宽基"
    provider_symbol: str = ""


class _Store:
    def __init__(self, frames):
        self.frames = frames

    def read_index_valuations(self, index_code):
        return self.frames.get(index_code, pd.DataFrame())


def _valuation_frame(rows=820):
    dates = pd.date_range("2023-01-02", periods=rows, freq="B")
    raw = pd.DataFrame(
        {
            "trade_date": dates,
            "pe_ttm": [10 + index / 100 for index in range(rows)],
            "pb": [1.0 + index / 1000 for index in range(rows)],
            "dividend_yield": [0.03 - index / 100000 for index in range(rows)],
            "bond_yield_10y": [0.02 for _ in range(rows)],
        }
    )
    return finalize_index_valuation_frame(raw, "000300", "unit", "primary")


def test_percentile_rank_current_uses_less_plus_half_equal():
    values = pd.Series([1, 2, 2, 4])

    assert percentile_rank_current(values) == 62.5


def test_metric_rows_are_atomic_and_include_missing_reasons():
    frame = _valuation_frame()
    frame = frame.drop(columns=["ps"])

    rows = build_index_valuation_metric_rows("000300", frame, as_of_date="2026-02-20")
    by_metric = {row.metric_name: row for row in rows.itertuples(index=False)}

    assert by_metric["pe_ttm"].status == "computed"
    assert by_metric["pe_ttm"].historical_percentile > 99
    assert by_metric["ps"].status == "missing_field"
    assert pd.isna(by_metric["ps"].historical_percentile)
    forbidden = {"valuation_hot_pct", "综合分", "估值总分", "买卖分"}
    assert forbidden.isdisjoint(rows.columns)


def test_metric_rows_do_not_compute_short_history_percentiles():
    short = _valuation_frame(rows=20)

    rows = build_index_valuation_metric_rows("000300", short, as_of_date="2023-01-31")
    pe_row = rows[rows["metric_name"] == "pe_ttm"].iloc[0]

    assert pe_row["status"] == "insufficient_history"
    assert pd.isna(pe_row["historical_percentile"])
    assert "历史不足" in pe_row["reason"]


def test_coverage_reports_complete_partial_missing_and_stale():
    complete = _valuation_frame()
    partial = _valuation_frame().drop(columns=["pb", "dividend_yield", "erp", "earnings_yield"])
    stale = _valuation_frame(rows=800)
    stale["trade_date"] = pd.date_range("2020-01-02", periods=800, freq="B")
    store = _Store(
        {
            "000300": complete,
            "000905": partial,
            "399006": stale,
        }
    )
    definitions = (
        _Definition("000300", "沪深300"),
        _Definition("000905", "中证500"),
        _Definition("399006", "创业板指"),
        _Definition("000852", "中证1000"),
    )

    coverage = build_index_valuation_coverage(definitions, store, as_of_date="2026-07-03")
    by_code = {row.index_code: row for row in coverage.itertuples(index=False)}

    assert by_code["000300"].coverage_status == "complete"
    assert by_code["000905"].coverage_status == "partial"
    assert by_code["399006"].coverage_status == "stale"
    assert by_code["000852"].coverage_status == "missing_valuation"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuation_health.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `etf_trading.research.index_valuation_health`.

- [ ] **Step 3: Implement atomic healthcheck module**

Create `src/etf_trading/research/index_valuation_health.py` with:

```python
"""Atomic index valuation healthcheck builders."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from etf_trading.data.indexes import IndexDefinition


@dataclass(frozen=True)
class ValuationMetric:
    name: str
    label: str
    direction: str


VALUATION_METRICS: tuple[ValuationMetric, ...] = (
    ValuationMetric("pe_ttm", "PE_TTM", "越高通常越贵"),
    ValuationMetric("pe_static", "静态PE", "越高通常越贵"),
    ValuationMetric("pb", "PB", "越高通常越贵"),
    ValuationMetric("ps", "PS", "越高通常越贵"),
    ValuationMetric("dividend_yield", "股息率", "越低通常越贵"),
    ValuationMetric("earnings_yield", "盈利收益率", "越低通常越贵"),
    ValuationMetric("erp", "ERP", "越低通常风险补偿越低"),
    ValuationMetric("roe", "ROE", "越高通常质量越好"),
    ValuationMetric("payout_ratio", "分红支付率", "分红结构观察"),
    ValuationMetric("forward_pe", "Forward PE", "越高通常越贵"),
)

FORBIDDEN_OUTPUT_COLUMNS = {"valuation_hot_pct", "weighted_score", "target_weight"}
STALE_DAYS = 31


def percentile_rank_current(values: pd.Series) -> float:
    x = pd.to_numeric(values, errors="coerce").dropna()
    if x.empty:
        return math.nan
    current = x.iloc[-1]
    less = (x < current).sum()
    equal = (x == current).sum()
    return float(100.0 * (less + 0.5 * equal) / len(x))


def build_index_valuation_metric_rows(
    index_code: str,
    valuations: pd.DataFrame,
    *,
    as_of_date: pd.Timestamp | str | None = None,
    min_history_rows: int = 756,
) -> pd.DataFrame:
    columns = [
        "index_code",
        "metric_name",
        "metric_label",
        "current_value",
        "historical_percentile",
        "window_years",
        "history_min",
        "history_median",
        "history_max",
        "first_date",
        "latest_date",
        "sample_count",
        "data_source",
        "status",
        "reason",
        "direction",
    ]
    if valuations.empty or "trade_date" not in valuations.columns:
        return pd.DataFrame([_missing_metric(index_code, metric, "missing_field", "无估值数据") for metric in VALUATION_METRICS], columns=columns)

    frame = valuations.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    if as_of_date is not None:
        frame = frame[frame["trade_date"] <= pd.Timestamp(as_of_date)]
    frame = frame.sort_values("trade_date")
    rows = []
    for metric in VALUATION_METRICS:
        rows.append(_metric_row(index_code, frame, metric, as_of_date, min_history_rows))
    result = pd.DataFrame(rows, columns=columns)
    leaked = FORBIDDEN_OUTPUT_COLUMNS & set(result.columns)
    if leaked:
        raise AssertionError(f"forbidden valuation output columns: {sorted(leaked)}")
    return result


def build_index_valuation_coverage(
    definitions: tuple[IndexDefinition, ...],
    parquet_store,
    *,
    as_of_date: pd.Timestamp | str | None = None,
    min_history_rows: int = 756,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for definition in definitions:
        try:
            valuations = parquet_store.read_index_valuations(definition.index_code)
        except Exception as exc:  # noqa: BLE001 - one damaged cache must not block all indexes
            rows.append(_coverage_row(definition, "read_failed", str(exc)))
            continue
        rows.append(_coverage_from_frame(definition, valuations, as_of_date, min_history_rows))
    return pd.DataFrame(rows)


def _metric_row(index_code: str, frame: pd.DataFrame, metric: ValuationMetric, as_of_date: pd.Timestamp | str | None, min_history_rows: int) -> dict[str, object]:
    if metric.name not in frame.columns:
        return _missing_metric(index_code, metric, "missing_field", f"{metric.name} 字段缺失")
    data = frame[["trade_date", metric.name] + [col for col in ["data_source"] if col in frame.columns]].copy()
    data[metric.name] = pd.to_numeric(data[metric.name], errors="coerce")
    data = data.dropna(subset=[metric.name])
    if data.empty:
        return _missing_metric(index_code, metric, "missing_field", f"{metric.name} 无有效观测")
    latest_date = pd.Timestamp(data["trade_date"].max())
    if as_of_date is not None and (pd.Timestamp(as_of_date) - latest_date).days > STALE_DAYS:
        return _metric_status_row(index_code, metric, data, "stale", "估值日期滞后")
    if len(data) < min_history_rows:
        return _metric_status_row(index_code, metric, data, "insufficient_history", f"历史不足 {min_history_rows} 条")
    current = float(data[metric.name].iloc[-1])
    if not math.isfinite(current):
        return _metric_status_row(index_code, metric, data, "invalid_value", "当前值无效")
    percentile = percentile_rank_current(data[metric.name])
    first_date = pd.Timestamp(data["trade_date"].min())
    source = str(data["data_source"].dropna().iloc[-1]) if "data_source" in data and data["data_source"].notna().any() else ""
    return {
        "index_code": index_code,
        "metric_name": metric.name,
        "metric_label": metric.label,
        "current_value": current,
        "historical_percentile": percentile,
        "window_years": round(len(data) / 252, 1),
        "history_min": float(data[metric.name].min()),
        "history_median": float(data[metric.name].median()),
        "history_max": float(data[metric.name].max()),
        "first_date": first_date.strftime("%Y-%m-%d"),
        "latest_date": latest_date.strftime("%Y-%m-%d"),
        "sample_count": int(len(data)),
        "data_source": source,
        "status": "computed",
        "reason": "",
        "direction": metric.direction,
    }


def _metric_status_row(index_code: str, metric: ValuationMetric, data: pd.DataFrame, status: str, reason: str) -> dict[str, object]:
    latest_date = pd.Timestamp(data["trade_date"].max()) if not data.empty else pd.NaT
    first_date = pd.Timestamp(data["trade_date"].min()) if not data.empty else pd.NaT
    current = float(data[metric.name].iloc[-1]) if not data.empty and metric.name in data.columns else pd.NA
    return {
        "index_code": index_code,
        "metric_name": metric.name,
        "metric_label": metric.label,
        "current_value": current,
        "historical_percentile": pd.NA,
        "window_years": round(len(data) / 252, 1),
        "history_min": float(data[metric.name].min()) if not data.empty and metric.name in data.columns else pd.NA,
        "history_median": float(data[metric.name].median()) if not data.empty and metric.name in data.columns else pd.NA,
        "history_max": float(data[metric.name].max()) if not data.empty and metric.name in data.columns else pd.NA,
        "first_date": first_date.strftime("%Y-%m-%d") if pd.notna(first_date) else "",
        "latest_date": latest_date.strftime("%Y-%m-%d") if pd.notna(latest_date) else "",
        "sample_count": int(len(data)),
        "data_source": "",
        "status": status,
        "reason": reason,
        "direction": metric.direction,
    }


def _missing_metric(index_code: str, metric: ValuationMetric, status: str, reason: str) -> dict[str, object]:
    return {
        "index_code": index_code,
        "metric_name": metric.name,
        "metric_label": metric.label,
        "current_value": pd.NA,
        "historical_percentile": pd.NA,
        "window_years": 0.0,
        "history_min": pd.NA,
        "history_median": pd.NA,
        "history_max": pd.NA,
        "first_date": "",
        "latest_date": "",
        "sample_count": 0,
        "data_source": "",
        "status": status,
        "reason": reason,
        "direction": metric.direction,
    }


def _coverage_from_frame(definition: IndexDefinition, valuations: pd.DataFrame, as_of_date: pd.Timestamp | str | None, min_history_rows: int) -> dict[str, object]:
    if valuations.empty or "trade_date" not in valuations.columns:
        return _coverage_row(definition, "missing_valuation", "无估值缓存")
    metrics = build_index_valuation_metric_rows(definition.index_code, valuations, as_of_date=as_of_date, min_history_rows=min_history_rows)
    computed = metrics[metrics["status"] == "computed"]
    available = metrics[metrics["sample_count"] > 0]["metric_name"].tolist()
    missing = metrics[metrics["status"] != "computed"]["metric_name"].tolist()
    latest = pd.to_datetime(valuations["trade_date"]).max()
    first = pd.to_datetime(valuations["trade_date"]).min()
    if metrics["status"].eq("stale").any():
        status = "stale"
        reason = "估值日期滞后"
    elif computed.empty and available:
        status = "insufficient_history"
        reason = "估值历史不足"
    elif computed.empty:
        status = "missing_valuation"
        reason = "无可计算估值字段"
    elif len(computed) >= 3:
        status = "complete"
        reason = ""
    else:
        status = "partial"
        reason = "估值字段覆盖不完整"
    return {
        "index_code": definition.index_code,
        "index_name": definition.name,
        "category": definition.category,
        "primary_source": _latest_source(valuations),
        "available_fields": ", ".join(available),
        "missing_fields": ", ".join(missing),
        "first_date": first.strftime("%Y-%m-%d"),
        "latest_date": latest.strftime("%Y-%m-%d"),
        "sample_count": int(len(valuations)),
        "has_3y_history": bool(len(valuations) >= 756),
        "has_5y_history": bool(len(valuations) >= 1260),
        "has_10y_history": bool(len(valuations) >= 2520),
        "coverage_status": status,
        "coverage_reason": reason,
    }


def _coverage_row(definition: IndexDefinition, status: str, reason: str) -> dict[str, object]:
    return {
        "index_code": definition.index_code,
        "index_name": definition.name,
        "category": definition.category,
        "primary_source": "",
        "available_fields": "",
        "missing_fields": ", ".join(metric.name for metric in VALUATION_METRICS),
        "first_date": "",
        "latest_date": "",
        "sample_count": 0,
        "has_3y_history": False,
        "has_5y_history": False,
        "has_10y_history": False,
        "coverage_status": status,
        "coverage_reason": reason,
    }


def _latest_source(frame: pd.DataFrame) -> str:
    if "data_source" not in frame.columns or frame["data_source"].dropna().empty:
        return ""
    return str(frame["data_source"].dropna().iloc[-1])
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuation_health.py -q
```

Expected: PASS with 4 tests.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/etf_trading/research/index_valuation_health.py tests/test_index_valuation_health.py
git commit -m "feat: build index valuation healthchecks"
```

---

### Task 3: AKShare Valuation Provider Adapter

**Files:**
- Modify: `src/etf_trading/data/index_valuations.py`
- Modify: `src/etf_trading/data/providers/akshare_provider.py`
- Test: `tests/test_akshare_provider_fallback.py`

**Interfaces:**
- Produces: `normalize_legulegu_pe(raw: pd.DataFrame, index_code: str) -> pd.DataFrame`.
- Produces: `normalize_legulegu_pb(raw: pd.DataFrame, index_code: str) -> pd.DataFrame`.
- Produces: `normalize_csindex_recent_valuation(raw: pd.DataFrame, index_code: str) -> pd.DataFrame`.
- Produces: `AkShareProvider.fetch_index_valuation(index_code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame`.

- [ ] **Step 1: Write failing AKShare valuation tests**

Append to `tests/test_akshare_provider_fallback.py`:

```python
class _FakeIndexValuationAk:
    def stock_index_pe_lg(self, symbol):
        assert symbol == "沪深300"
        return pd.DataFrame(
            {
                "日期": ["2026-07-02", "2026-07-03"],
                "滚动市盈率": [13.4, 13.6],
                "静态市盈率": [13.6, 13.85],
            }
        )

    def stock_index_pb_lg(self, symbol):
        assert symbol == "沪深300"
        return pd.DataFrame(
            {
                "日期": ["2026-07-02", "2026-07-03"],
                "市净率": [1.42, 1.43],
            }
        )

    def stock_zh_index_value_csindex(self, symbol):
        assert symbol == "000300"
        return pd.DataFrame(
            {
                "日期": ["2026-07-03"],
                "市盈率1": [14.86],
                "市盈率2": [17.93],
                "股息率1": [2.64],
                "股息率2": [2.17],
            }
        )


def test_fetch_index_valuation_combines_legulegu_history_and_csindex_recent_check():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeIndexValuationAk()

    result = provider.fetch_index_valuation("000300", "2026-07-01", "2026-07-03")

    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-02", "2026-07-03"]
    latest = result.iloc[-1]
    assert latest["pe_ttm"] == 13.6
    assert latest["pe_static"] == 13.85
    assert latest["pb"] == 1.43
    assert round(float(latest["dividend_yield"]), 4) == 0.0264
    assert latest["data_source"] == "akshare_legulegu"
    forbidden = {"valuation_hot_pct", "综合分", "买卖分"}
    assert forbidden.isdisjoint(result.columns)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_akshare_provider_fallback.py::test_fetch_index_valuation_combines_legulegu_history_and_csindex_recent_check -q
```

Expected: FAIL with `AttributeError` for `fetch_index_valuation`.

- [ ] **Step 3: Add source-specific normalizers**

Append to `src/etf_trading/data/index_valuations.py`:

```python
def normalize_legulegu_pe(raw: pd.DataFrame, index_code: str) -> pd.DataFrame:
    frame = raw.rename(
        columns={
            "日期": "trade_date",
            "滚动市盈率": "pe_ttm",
            "静态市盈率": "pe_static",
        }
    )
    keep = [column for column in ["trade_date", "pe_ttm", "pe_static"] if column in frame.columns]
    return finalize_index_valuation_frame(frame[keep], index_code, "akshare_legulegu", "fallback")


def normalize_legulegu_pb(raw: pd.DataFrame, index_code: str) -> pd.DataFrame:
    frame = raw.rename(columns={"日期": "trade_date", "市净率": "pb"})
    keep = [column for column in ["trade_date", "pb"] if column in frame.columns]
    return finalize_index_valuation_frame(frame[keep], index_code, "akshare_legulegu", "fallback")


def normalize_csindex_recent_valuation(raw: pd.DataFrame, index_code: str) -> pd.DataFrame:
    frame = raw.rename(
        columns={
            "日期": "trade_date",
            "市盈率1": "pe_ttm",
            "市盈率2": "pe_static",
            "股息率1": "dividend_yield",
        }
    ).copy()
    if "dividend_yield" in frame.columns:
        frame["dividend_yield"] = pd.to_numeric(frame["dividend_yield"], errors="coerce") / 100.0
    keep = [column for column in ["trade_date", "pe_ttm", "pe_static", "dividend_yield"] if column in frame.columns]
    return finalize_index_valuation_frame(frame[keep], index_code, "akshare_csindex", "recent_check")
```

- [ ] **Step 4: Add `fetch_index_valuation` to AkShareProvider**

Modify imports in `src/etf_trading/data/providers/akshare_provider.py`:

```python
from etf_trading.data.index_valuations import (
    finalize_index_valuation_frame,
    normalize_csindex_recent_valuation,
    normalize_legulegu_pb,
    normalize_legulegu_pe,
)
```

Add module-level mapping near `_fmt_date`:

```python
LEGULEGU_INDEX_SYMBOLS = {
    "000016": "上证50",
    "000300": "沪深300",
    "000905": "中证500",
    "000906": "中证800",
    "000852": "中证1000",
    "000922": "中证红利",
}
```

Add method to `class AkShareProvider`:

```python
    def fetch_index_valuation(self, index_code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        code = str(index_code)
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        frames: list[pd.DataFrame] = []
        symbol = LEGULEGU_INDEX_SYMBOLS.get(code)
        if symbol:
            try:
                pe_raw = _call_with_retries(self.ak.stock_index_pe_lg, f"AkShare 乐咕指数PE {code}", attempts=2, symbol=symbol)
                frames.append(normalize_legulegu_pe(pe_raw, code))
            except Exception:
                pass
            try:
                pb_raw = _call_with_retries(self.ak.stock_index_pb_lg, f"AkShare 乐咕指数PB {code}", attempts=2, symbol=symbol)
                frames.append(normalize_legulegu_pb(pb_raw, code))
            except Exception:
                pass
        try:
            recent_raw = _call_with_retries(self.ak.stock_zh_index_value_csindex, f"AkShare 中证指数估值 {code}", attempts=2, symbol=code)
            frames.append(normalize_csindex_recent_valuation(recent_raw, code))
        except Exception:
            pass
        combined = _merge_valuation_frames(code, frames)
        if combined.empty:
            return combined
        return combined[(combined["trade_date"] >= start) & (combined["trade_date"] <= end)].reset_index(drop=True)
```

Add helper near `_choose_latest_index_frame`:

```python
def _merge_valuation_frames(index_code: str, frames: list[pd.DataFrame]) -> pd.DataFrame:
    available = [frame for frame in frames if not frame.empty]
    if not available:
        return finalize_index_valuation_frame(pd.DataFrame(columns=["trade_date"]), index_code, "akshare", "fallback")
    merged = available[0].copy()
    for frame in available[1:]:
        value_columns = [column for column in frame.columns if column not in {"index_code", "trade_date", "data_source", "source_quality", "source_updated_at"}]
        merged = merged.merge(frame[["trade_date", *value_columns]], on="trade_date", how="outer", suffixes=("", "_new"))
        for column in value_columns:
            new_column = f"{column}_new"
            if new_column in merged.columns:
                merged[column] = merged[column].combine_first(merged[new_column])
                merged = merged.drop(columns=[new_column])
    return finalize_index_valuation_frame(merged, index_code, "akshare_legulegu", "fallback")
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_akshare_provider_fallback.py -q
```

Expected: PASS for the provider tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/etf_trading/data/index_valuations.py src/etf_trading/data/providers/akshare_provider.py tests/test_akshare_provider_fallback.py
git commit -m "feat: add AKShare index valuation provider"
```

---

### Task 4: Source Switching Service and CSV/Callable Providers

**Files:**
- Modify: `src/etf_trading/data/index_valuations.py`
- Create: `src/etf_trading/data/index_valuation_service.py`
- Test: `tests/test_index_valuation_service.py`

**Interfaces:**
- Produces: `CsvIndexValuationProvider(root: str | Path)`.
- Produces: `CallableIndexValuationProvider(source_name: str, fetch_index: Callable[..., pd.DataFrame], fetch_macro: Callable[..., pd.DataFrame] | None = None)`.
- Produces: `IndexValuationSyncResult(index_code: str, status: str, rows: int, first_date: str, latest_date: str, error_message: str | None = None)`.
- Produces: `IndexValuationSyncService(provider: IndexValuationProvider, parquet_store: ParquetStore)`.
- Produces: `IndexValuationSyncService.ensure_index_valuation(index_code: str, start_date: date | str, end_date: date | str) -> IndexValuationSyncResult`.

- [ ] **Step 1: Write failing service and CSV tests**

Create `tests/test_index_valuation_service.py` with:

```python
import pandas as pd

from etf_trading.data.index_valuation_service import IndexValuationSyncService
from etf_trading.data.index_valuations import CallableIndexValuationProvider, CsvIndexValuationProvider
from etf_trading.data.storage import ParquetStore


def test_callable_provider_syncs_normalized_rows_to_parquet(tmp_path):
    def fetch_index(index_code, start_date, end_date):
        return pd.DataFrame(
            {
                "trade_date": ["2026-07-03"],
                "pe_ttm": [12.5],
                "pb": [1.4],
            }
        )

    store = ParquetStore(tmp_path)
    provider = CallableIndexValuationProvider("unit_callable", fetch_index)
    result = IndexValuationSyncService(provider, store).ensure_index_valuation("000300", "2026-07-01", "2026-07-03")

    cached = store.read_index_valuations("000300")
    assert result.status == "SUCCESS"
    assert result.rows == 1
    assert cached.iloc[0]["data_source"] == "unit_callable"


def test_csv_provider_reads_user_supplied_valuation_file(tmp_path):
    root = tmp_path / "csv"
    root.mkdir()
    pd.DataFrame(
        {
            "trade_date": ["2026-07-03"],
            "pe_ttm": [12.5],
            "pb": [1.4],
        }
    ).to_csv(root / "000300.csv", index=False)

    provider = CsvIndexValuationProvider(root)
    result = provider.fetch_index_valuation("000300", "2026-07-01", "2026-07-03")

    assert result["index_code"].tolist() == ["000300"]
    assert result.iloc[0]["data_source"] == "csv_import"


def test_sync_service_records_empty_status_without_writing_rows(tmp_path):
    provider = CallableIndexValuationProvider("empty", lambda index_code, start_date, end_date: pd.DataFrame())
    store = ParquetStore(tmp_path)

    result = IndexValuationSyncService(provider, store).ensure_index_valuation("000300", "2026-07-01", "2026-07-03")

    assert result.status == "EMPTY"
    assert result.rows == 0
    assert store.read_index_valuations("000300").empty
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuation_service.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `etf_trading.data.index_valuation_service` or missing provider adapters.

- [ ] **Step 3: Add CSV and callable providers**

Append to `src/etf_trading/data/index_valuations.py`:

```python
from collections.abc import Callable
from pathlib import Path


class CallableIndexValuationProvider:
    def __init__(
        self,
        source_name: str,
        fetch_index: Callable[[str, date | str, date | str], pd.DataFrame],
        fetch_macro: Callable[[str, date | str, date | str], pd.DataFrame] | None = None,
    ) -> None:
        self.source_name = source_name
        self._fetch_index = fetch_index
        self._fetch_macro = fetch_macro

    def fetch_index_valuation(self, index_code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        raw = self._fetch_index(index_code, start_date, end_date)
        return finalize_index_valuation_frame(raw, index_code, self.source_name, "primary")

    def fetch_macro_series(self, series_name: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        if self._fetch_macro is None:
            return pd.DataFrame(columns=MACRO_SERIES_COLUMNS)
        raw = self._fetch_macro(series_name, start_date, end_date)
        return normalize_macro_series(raw, series_name, self.source_name)


class CsvIndexValuationProvider:
    source_name = "csv_import"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def fetch_index_valuation(self, index_code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        path = self.root / f"{index_code}.csv"
        if not path.exists():
            return pd.DataFrame(columns=INDEX_VALUATION_COLUMNS)
        raw = pd.read_csv(path)
        frame = finalize_index_valuation_frame(raw, index_code, self.source_name, "manual")
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        return frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)].reset_index(drop=True)

    def fetch_macro_series(self, series_name: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        path = self.root / "macro" / f"{series_name}.csv"
        if not path.exists():
            return pd.DataFrame(columns=MACRO_SERIES_COLUMNS)
        raw = pd.read_csv(path)
        frame = normalize_macro_series(raw, series_name, self.source_name)
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        return frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)].reset_index(drop=True)
```

- [ ] **Step 4: Add sync service**

Create `src/etf_trading/data/index_valuation_service.py` with:

```python
"""Services for syncing index valuation histories into local cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from etf_trading.data.index_valuations import IndexValuationProvider
from etf_trading.data.storage import ParquetStore


@dataclass(frozen=True)
class IndexValuationSyncResult:
    index_code: str
    status: str
    rows: int
    first_date: str = ""
    latest_date: str = ""
    error_message: str | None = None


class IndexValuationSyncService:
    def __init__(self, provider: IndexValuationProvider, parquet_store: ParquetStore) -> None:
        self.provider = provider
        self.parquet_store = parquet_store

    def ensure_index_valuation(self, index_code: str, start_date: date | str, end_date: date | str) -> IndexValuationSyncResult:
        try:
            frame = self.provider.fetch_index_valuation(index_code, start_date, end_date)
        except Exception as exc:  # noqa: BLE001 - one source failure must become a visible sync result
            return IndexValuationSyncResult(index_code=index_code, status="FAILED", rows=0, error_message=str(exc))
        if frame.empty:
            return IndexValuationSyncResult(index_code=index_code, status="EMPTY", rows=0)
        frame = frame.sort_values("trade_date").reset_index(drop=True)
        self.parquet_store.write_index_valuations(index_code, frame)
        return IndexValuationSyncResult(
            index_code=index_code,
            status="SUCCESS",
            rows=int(len(frame)),
            first_date=pd.Timestamp(frame["trade_date"].min()).strftime("%Y-%m-%d"),
            latest_date=pd.Timestamp(frame["trade_date"].max()).strftime("%Y-%m-%d"),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuation_service.py -q
```

Expected: PASS with 3 tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/etf_trading/data/index_valuations.py src/etf_trading/data/index_valuation_service.py tests/test_index_valuation_service.py
git commit -m "feat: add index valuation source sync service"
```

---

### Task 5: NiceGUI Valuation View Models and Navigation

**Files:**
- Modify: `src/etf_trading/nicegui_app/navigation.py`
- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Test: `tests/test_nicegui_navigation.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Consumes: `build_index_valuation_coverage(...)`.
- Consumes: `build_index_valuation_metric_rows(...)`.
- Produces: `IndexValuationFilters(query: str = "", coverage_status: str = "全部覆盖状态")`.
- Produces: `build_index_valuation_coverage_frame(snapshot: PlatformSnapshot, parquet_store) -> pd.DataFrame`.
- Produces: `index_valuation_summary(frame: pd.DataFrame) -> list[MetricTile]`.
- Produces: `index_valuation_coverage_rows(frame: pd.DataFrame, filters: IndexValuationFilters | None = None, limit: int = 200) -> list[dict[str, object]]`.
- Produces: `index_valuation_metric_display_rows(parquet_store, index_code: str) -> list[dict[str, object]]`.

- [ ] **Step 1: Write failing navigation and view-model tests**

Modify `tests/test_nicegui_navigation.py`:

```python
def test_nicegui_sections_keep_market_and_etf_boundaries():
    sections_by_slug = {page.slug: section_options(page) for page in NICEGUI_PAGES}

    assert sections_by_slug["market"] == ["市场总览", "指数估值体检", "指数买卖参考", "指数K线"]
    assert sections_by_slug["etf-data"] == ["ETF总览", "原子指标", "ETF行情", "搜索加入", "每日计算池", "指数样本池"]
    assert sections_by_slug["research"] == ["策略库", "新建策略", "运行回测", "策略比较", "ETF复盘", "指数过滤实验"]
    assert sections_by_slug["maintenance"] == ["数据总览", "缺口明细", "补齐任务", "日志与设置"]
    assert "ETF行情" not in sections_by_slug["market"]
    assert "原子指标" not in sections_by_slug["market"]
    assert "指数估值体检" not in sections_by_slug["etf-data"]
```

Append to `tests/test_nicegui_view_models.py`:

```python
from etf_trading.data.index_valuations import finalize_index_valuation_frame
from etf_trading.nicegui_app.view_models import (
    IndexValuationFilters,
    index_valuation_coverage_rows,
    index_valuation_metric_display_rows,
    index_valuation_summary,
)


class _ValuationStore:
    def __init__(self, frame):
        self.frame = frame

    def read_index_valuations(self, index_code):
        return self.frame if index_code == "000300" else pd.DataFrame()


def _valuation_coverage_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": ["000300", "000905"],
            "index_name": ["沪深300", "中证500"],
            "category": ["A股宽基", "A股宽基"],
            "primary_source": ["akshare_legulegu", ""],
            "available_fields": ["pe_ttm, pb", ""],
            "missing_fields": ["ps", "pe_ttm, pb"],
            "first_date": ["2005-04-08", ""],
            "latest_date": ["2026-07-03", ""],
            "sample_count": [5200, 0],
            "has_3y_history": [True, False],
            "has_5y_history": [True, False],
            "has_10y_history": [True, False],
            "coverage_status": ["partial", "missing_valuation"],
            "coverage_reason": ["估值字段覆盖不完整", "无估值缓存"],
        }
    )


def _valuation_frame() -> pd.DataFrame:
    dates = pd.date_range("2023-01-02", periods=820, freq="B")
    return finalize_index_valuation_frame(
        pd.DataFrame(
            {
                "trade_date": dates,
                "pe_ttm": [10 + index / 100 for index in range(820)],
                "pb": [1.0 + index / 1000 for index in range(820)],
            }
        ),
        "000300",
        "unit",
        "primary",
    )


def test_index_valuation_summary_and_rows_show_missing_data_without_scores():
    frame = _valuation_coverage_frame()

    metrics = index_valuation_summary(frame)
    rows = index_valuation_coverage_rows(frame, IndexValuationFilters(query="300"))

    assert [metric.label for metric in metrics][:4] == ["指数总数", "估值完整", "部分缺失", "估值缺失"]
    assert [metric.value for metric in metrics][:4] == ["2", "0", "1", "1"]
    assert rows[0]["指数代码"] == "000300"
    assert rows[0]["缺失字段"] == "ps"
    forbidden = {"综合分", "估值总分", "买卖分", "valuation_hot_pct"}
    assert forbidden.isdisjoint(rows[0].keys())


def test_index_valuation_metric_display_rows_keep_metric_status_visible():
    rows = index_valuation_metric_display_rows(_ValuationStore(_valuation_frame()), "000300")

    by_metric = {row["指标"]: row for row in rows}
    assert by_metric["PE_TTM"]["状态"] == "computed"
    assert by_metric["PE_TTM"]["历史百分位"].endswith("%")
    assert by_metric["PS"]["状态"] == "missing_field"
    assert by_metric["PS"]["历史百分位"] == ""
    forbidden = {"综合分", "估值总分", "买卖分", "目标仓位"}
    assert forbidden.isdisjoint(by_metric["PE_TTM"].keys())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py -q
```

Expected: FAIL because navigation does not include `指数估值体检` and view-model helpers are missing.

- [ ] **Step 3: Add navigation section**

Modify the market page spec in `src/etf_trading/nicegui_app/navigation.py`:

```python
    NicePageSpec(
        slug="market",
        label="市场地图",
        caption="观察指数和市场参与状态，不承载 ETF 行情下钻。",
        sections=("市场总览", "指数估值体检", "指数买卖参考", "指数K线"),
    ),
```

- [ ] **Step 4: Add view-model helpers**

Modify imports in `src/etf_trading/nicegui_app/view_models.py`:

```python
from etf_trading.research.index_valuation_health import (
    build_index_valuation_coverage,
    build_index_valuation_metric_rows,
)
from etf_trading.data.indexes import DEFAULT_INDEXES
```

Add the dataclass near existing filter dataclasses:

```python
@dataclass(frozen=True)
class IndexValuationFilters:
    query: str = ""
    coverage_status: str = "全部覆盖状态"
```

Add functions:

```python
def build_index_valuation_coverage_frame(snapshot: PlatformSnapshot, parquet_store) -> pd.DataFrame:
    return build_index_valuation_coverage(DEFAULT_INDEXES, parquet_store)


def index_valuation_summary(frame: pd.DataFrame) -> list[MetricTile]:
    if frame.empty:
        return [
            MetricTile("指数总数", "0", "neutral", "估值池"),
            MetricTile("估值完整", "0", "neutral", "完整"),
            MetricTile("部分缺失", "0", "neutral", "字段缺口"),
            MetricTile("估值缺失", "0", "neutral", "无缓存"),
        ]
    status = frame["coverage_status"].fillna("").astype(str) if "coverage_status" in frame else pd.Series("", index=frame.index)
    latest = frame["latest_date"].dropna().astype(str).max() if "latest_date" in frame and not frame["latest_date"].dropna().empty else ""
    return [
        MetricTile("指数总数", str(len(frame)), "neutral", "估值池"),
        MetricTile("估值完整", str(int((status == "complete").sum())), "success", "完整"),
        MetricTile("部分缺失", str(int((status == "partial").sum())), "warning", "字段缺口"),
        MetricTile("估值缺失", str(int((status == "missing_valuation").sum())), "warning", "无缓存"),
        MetricTile("历史不足", str(int((status == "insufficient_history").sum())), "warning", "样本不足"),
        MetricTile("最新估值", latest, "info", "缓存日期"),
    ]


def index_valuation_coverage_rows(
    frame: pd.DataFrame,
    filters: IndexValuationFilters | None = None,
    limit: int = 200,
) -> list[dict[str, object]]:
    filters = filters or IndexValuationFilters()
    data = frame.copy()
    if data.empty:
        return []
    query = filters.query.strip().lower()
    if query:
        searchable = (
            data["index_code"].fillna("").astype(str)
            + " "
            + data["index_name"].fillna("").astype(str)
            + " "
            + data["category"].fillna("").astype(str)
        ).str.lower()
        data = data[searchable.str.contains(query, regex=False)]
    if filters.coverage_status not in {"", "全部覆盖状态"} and "coverage_status" in data:
        data = data[data["coverage_status"].astype(str) == filters.coverage_status]
    rows = []
    for row in data.head(limit).fillna("").to_dict("records"):
        rows.append(
            {
                "指数代码": str(row.get("index_code", "")),
                "指数名称": str(row.get("index_name", "")),
                "分类": str(row.get("category", "")),
                "估值覆盖状态": str(row.get("coverage_status", "")),
                "可用字段": str(row.get("available_fields", "")),
                "缺失字段": str(row.get("missing_fields", "")),
                "估值源": str(row.get("primary_source", "")),
                "估值最早日期": str(row.get("first_date", "")),
                "估值最新日期": str(row.get("latest_date", "")),
                "覆盖年数": _format_years(row.get("sample_count", 0)),
                "缺失说明": str(row.get("coverage_reason", "")),
            }
        )
    return rows


def index_valuation_metric_display_rows(parquet_store, index_code: str) -> list[dict[str, object]]:
    frame = parquet_store.read_index_valuations(index_code)
    metrics = build_index_valuation_metric_rows(index_code, frame)
    rows = []
    for row in metrics.fillna("").to_dict("records"):
        rows.append(
            {
                "指标": str(row.get("metric_label", "")),
                "当前值": _format_number(row.get("current_value", "")),
                "历史百分位": _format_percentile(row.get("historical_percentile", "")),
                "覆盖年数": str(row.get("window_years", "")),
                "历史最小值": _format_number(row.get("history_min", "")),
                "历史中位数": _format_number(row.get("history_median", "")),
                "历史最大值": _format_number(row.get("history_max", "")),
                "数据源": str(row.get("data_source", "")),
                "最新日期": str(row.get("latest_date", "")),
                "状态": str(row.get("status", "")),
                "说明": str(row.get("reason", "")),
            }
        )
    return rows
```

Add formatting helpers near existing private helpers:

```python
def _format_percentile(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(number):
        return ""
    return f"{number:.1f}%"


def _format_number(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(number):
        return ""
    return f"{number:.2f}"


def _format_years(sample_count: object) -> str:
    try:
        rows = float(sample_count)
    except (TypeError, ValueError):
        return ""
    if pd.isna(rows) or rows <= 0:
        return ""
    return f"{rows / 252:.1f}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py -q
```

Expected: PASS for navigation and view-model tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/etf_trading/nicegui_app/navigation.py src/etf_trading/nicegui_app/view_models.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py
git commit -m "feat: add valuation healthcheck view models"
```

---

### Task 6: NiceGUI Market Page Rendering

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/market.py`
- Test: `tests/test_nicegui_app_import.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Consumes: `build_index_valuation_coverage_frame(snapshot, parquet_store) -> pd.DataFrame`.
- Consumes: `index_valuation_summary(frame) -> list[MetricTile]`.
- Consumes: `index_valuation_coverage_rows(frame, filters) -> list[dict[str, object]]`.
- Consumes: `index_valuation_metric_display_rows(parquet_store, index_code) -> list[dict[str, object]]`.
- Updates: `pages.market.render()` routes `section == "指数估值体检"` to a valuation healthcheck renderer.

- [ ] **Step 1: Add import smoke test if missing**

If `tests/test_nicegui_app_import.py` does not already import the NiceGUI app, ensure it contains:

```python
def test_nicegui_app_imports_without_side_effects():
    import etf_trading.nicegui_app.main  # noqa: F401
```

- [ ] **Step 2: Run import test before implementation**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py -q
```

Expected: PASS before rendering changes.

- [ ] **Step 3: Add valuation healthcheck renderer**

Modify imports in `src/etf_trading/nicegui_app/pages/market.py`:

```python
from etf_trading.nicegui_app.view_models import (
    IndexValuationFilters,
    PlatformSnapshot,
    build_index_valuation_coverage_frame,
    code_from_option,
    current_ui_audit_findings,
    index_choice_options,
    index_valuation_coverage_rows,
    index_valuation_metric_display_rows,
    index_valuation_summary,
    market_overview,
)
```

Modify `render()`:

```python
def render(snapshot: PlatformSnapshot, section: str, parquet_store=None) -> None:
    if section == "市场总览":
        _render_overview(snapshot)
    elif section == "指数估值体检":
        _render_index_valuation_healthcheck(snapshot, parquet_store)
    elif section == "指数买卖参考":
        _render_index_reference(snapshot)
    else:
        _render_index_chart(snapshot, parquet_store)
```

Add renderer:

```python
def _render_index_valuation_healthcheck(snapshot: PlatformSnapshot, parquet_store) -> None:
    if parquet_store is None:
        empty_state("暂无指数估值体检", "当前页面没有可用估值缓存。")
        return
    coverage = build_index_valuation_coverage_frame(snapshot, parquet_store)
    if coverage.empty:
        empty_state("暂无指数估值体检", "先同步指数估值历史。")
        return

    with ui.row().classes("w-full gap-2"):
        for metric in index_valuation_summary(coverage):
            _metric(metric.label, metric.value, metric.detail)

    statuses = ["全部覆盖状态", *sorted(coverage["coverage_status"].fillna("").astype(str).unique().tolist())]
    with ui.row().classes("workbench-toolbar w-full items-end gap-2"):
        query = ui.input(label="搜索指数").props("dense outlined clearable").classes("w-64")
        status_select = ui.select(statuses, value="全部覆盖状态", label="覆盖状态").props("dense outlined").classes("w-52")
        selected = ui.select(index_choice_options(snapshot.index_summary), label="单指数详情").props("dense outlined").classes("w-96")

    table_area = ui.column().classes("w-full")
    detail_area = ui.column().classes("w-full")

    def redraw_table() -> None:
        rows = index_valuation_coverage_rows(
            coverage,
            IndexValuationFilters(query=str(query.value or ""), coverage_status=str(status_select.value or "全部覆盖状态")),
        )
        table_area.clear()
        with table_area:
            if rows:
                ui.table(columns=table_columns(rows), rows=rows, row_key="指数代码").classes("workbench-data-table w-full")
            else:
                empty_state("没有匹配估值体检", "换一个筛选条件，或先同步指数估值历史。")

    def redraw_detail() -> None:
        detail_area.clear()
        index_code = code_from_option(str(selected.value or ""))
        with detail_area:
            if not index_code:
                empty_state("暂无单指数详情", "请选择一个指数。")
                return
            rows = index_valuation_metric_display_rows(parquet_store, index_code)
            ui.label(f"估值原子指标：{index_code}").classes("text-sm font-semibold text-slate-700")
            ui.table(columns=table_columns(rows), rows=rows, row_key="指标").classes("workbench-data-table w-full")

    query.on("update:model-value", lambda event: redraw_table())
    status_select.on("update:model-value", lambda event: redraw_table())
    selected.on("update:model-value", lambda event: redraw_detail())
    if index_choice_options(snapshot.index_summary):
        selected.value = index_choice_options(snapshot.index_summary)[0]
    redraw_table()
    redraw_detail()
    _render_audit("market")
```

- [ ] **Step 4: Run focused UI import and view-model tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py tests/test_nicegui_view_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/etf_trading/nicegui_app/pages/market.py tests/test_nicegui_app_import.py
git commit -m "feat: render index valuation healthcheck page"
```

---

### Task 7: Final Verification and Memory

**Files:**
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: project memory entry with summary, verification commands, and reusable notes.

- [ ] **Step 1: Run focused test suite**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuations.py tests/test_index_valuation_health.py tests/test_index_valuation_service.py tests/test_akshare_provider_fallback.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_nicegui_app_import.py -q --basetemp pytest-tmp-index-valuation-focused
```

Expected: PASS.

- [ ] **Step 2: Run forbidden-output scan**

Run:

```powershell
rg -n "valuation_hot_pct|weighted_score|target_weight|综合分|估值总分|买卖分|目标仓位|BUY|SELL|REDUCE|买入|卖出|减仓" src\etf_trading\data\index_valuations.py src\etf_trading\data\index_valuation_service.py src\etf_trading\research\index_valuation_health.py src\etf_trading\nicegui_app\view_models.py src\etf_trading\nicegui_app\pages\market.py tests\test_index_valuations.py tests\test_index_valuation_health.py tests\test_nicegui_view_models.py
```

Expected: production files contain no forbidden output fields. Test files may contain forbidden words only inside assertions that prove they are absent.

- [ ] **Step 3: Run broader regression tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_storage_and_services.py tests/test_data_coverage.py tests/test_nicegui_state_cache.py tests/test_nicegui_charts.py -q --basetemp pytest-tmp-index-valuation-broad
```

Expected: PASS.

- [ ] **Step 4: Append task memory**

Append to `docs/task-memory.md`:

```markdown
## 2026-07-05 - Implement index valuation healthcheck

- Summary: Added source-switchable index valuation cache, atomic valuation healthcheck calculations, and NiceGUI `市场地图 -> 指数估值体检`.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_index_valuations.py tests/test_index_valuation_health.py tests/test_index_valuation_service.py tests/test_akshare_provider_fallback.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_nicegui_app_import.py -q --basetemp pytest-tmp-index-valuation-focused` passed; `.venv-win\Scripts\python.exe -m pytest tests/test_storage_and_services.py tests/test_data_coverage.py tests/test_nicegui_state_cache.py tests/test_nicegui_charts.py -q --basetemp pytest-tmp-index-valuation-broad` passed.
- Watch out next time:
  - Keep index valuation healthcheck atomic; do not add weighted, median, or composite scores.
  - Keep missing, stale, and too-short fields visible with blank percentiles instead of default numeric values.
```

- [ ] **Step 5: Commit memory**

Run:

```powershell
git add docs/task-memory.md
git commit -m "docs: record index valuation healthcheck work"
```

---

## Self-Review

**Spec coverage:**  
The plan covers source switching (Tasks 1, 3, 4), local Parquet cache (Task 1), coverage table (Task 2, Task 5), atomic metric percentiles (Task 2), missing-data status and reasons (Task 2, Task 5), no composite scores (all tasks through constraints and tests), NiceGUI `市场地图 -> 指数估值体检` (Tasks 5 and 6), and verification (Task 7).

**Placeholder scan:**  
The author must run the repository's standard red-flag scan before handoff and fix any match in this plan.

**Type consistency:**  
Provider methods return normalized `pd.DataFrame` objects. Storage methods read/write those frames. `build_index_valuation_metric_rows()` and `build_index_valuation_coverage()` consume storage frames. NiceGUI view models consume healthcheck frames and return `MetricTile` lists plus Chinese display rows. The market page consumes only view-model outputs and does not compute metrics directly.
