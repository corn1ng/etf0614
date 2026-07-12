# Index Health Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cached `市场地图 -> 指数体检` workflow that shows each index's current trend gate, trend atomic diagnostics, valuation atomic diagnostics, and data completeness from local snapshot caches only.

**Architecture:** Keep two cache layers. Raw valuation and macro history are normalized into local Parquet first; then a page-ready index health snapshot cache stores one summary row per index plus long-form detail rows for trend and valuation diagnostics. The research layer computes the snapshot, the state layer handles `ready/stale/building/failed`, and the NiceGUI page only reads cached frames and renders them.

**Tech Stack:** Python 3.11, pandas, pyarrow/Parquet, AkShare, NiceGUI, pytest.

## Global Constraints

- `市场地图` sections must become `市场总览`, `指数体检`, `指数买卖参考`, `指数K线`.
- `指数买卖参考` remains only the `TrendRegimeClassifier` gate and must not absorb the new diagnostics table.
- `指数体检` must read only local Parquet snapshot caches; page render must not call external providers directly.
- Keep two cache layers: raw `data/parquet/index_valuations/{index_code}.parquet` and `data/parquet/macro/*.parquet`, then page-ready `data/parquet/cache/index_health_snapshot.parquet` plus `data/parquet/cache/index_health_snapshot.meta.json`.
- The snapshot read path must support `ready`, `stale`, `building`, and `failed` without blocking first paint when an old cache already exists.
- The main table shows summary columns only; the selected index renders two separate detail tables below it: one for trend metrics and one for valuation metrics.
- `valuation_overview_label` is a summary tag from `pe_ttm`, `pb`, and `erp` only: `low_percentile`, `mid_percentile`, `high_percentile`, `missing`, `insufficient_history`.
- Do not output any composite scores, total scores, weighted scores, target weights, or buy/sell advice.
- Non-normal states must carry explicit reason strings instead of silent blanks.
- Keep current `ETF数据 -> 原子指标` cache/page behavior and current `指数买卖参考` semantics intact.
- Do not create git commits unless the user explicitly asks for commits in that execution session.

---

## File Structure

- `src/etf_trading/data/index_valuations.py`
  Normalized valuation schema, history finalizers, and utility constants shared by providers, services, and research.
- `src/etf_trading/data/provider.py`
  Optional valuation and macro fetch hooks added to the existing provider boundary without changing current ETF/index callers.
- `src/etf_trading/data/providers/akshare_provider.py`
  AkShare valuation fetch implementation for index PE/PB/history, with safe empty returns when a field or series is unavailable.
- `src/etf_trading/data/index_valuation_service.py`
  Sync service that writes normalized valuation and macro histories into `ParquetStore`.
- `src/etf_trading/data/storage.py`
  Parquet read/write methods for raw valuation histories and macro series.
- `src/etf_trading/research/index_health_snapshot.py`
  Pure snapshot builder that reads index prices, valuation histories, and macro caches, then emits summary and detail frames.
- `src/etf_trading/nicegui_app/state.py`
  Disk/memory cache orchestration for the page-ready index health snapshot, including background rebuilds.
- `src/etf_trading/nicegui_app/view_models.py`
  UI-neutral summary, filter, row, and detail helpers for `指数体检`.
- `src/etf_trading/nicegui_app/components/tables.py`
  Display labels and enum translations for new index health columns and statuses.
- `src/etf_trading/nicegui_app/navigation.py`
  Adds `指数体检` to the market page section list.
- `src/etf_trading/nicegui_app/pages/market.py`
  Renders the new cached `指数体检` section without computing diagnostics inside the page.
- `tests/test_index_valuations.py`
  Raw schema, normalization, and Parquet persistence tests.
- `tests/test_akshare_provider_fallback.py`
  AkShare valuation fetch tests using fake AkShare objects.
- `tests/test_index_valuation_service.py`
  Valuation sync service tests.
- `tests/test_index_health_snapshot.py`
  Snapshot summary/detail rules, valuation overview label rules, and missing-data diagnostics tests.
- `tests/test_nicegui_state_cache.py`
  Index health snapshot cache state tests mirroring the ETF atomic cache pattern.
- `tests/test_nicegui_navigation.py`
  Market/ETF boundary regression tests.
- `tests/test_nicegui_view_models.py`
  `指数体检` summary/filter/detail row tests.
- `tests/test_nicegui_app_import.py`
  Page render smoke tests proving `指数体检` uses cached snapshots instead of sync builders.
- `docs/task-memory.md`
  Persist reusable notes after the feature is implemented and verified.

---

### Task 1: Raw Valuation Schema and Parquet Foundation

**Files:**
- Create: `src/etf_trading/data/index_valuations.py`
- Modify: `src/etf_trading/data/storage.py`
- Test: `tests/test_index_valuations.py`

**Interfaces:**
- Produces: `INDEX_VALUATION_COLUMNS: list[str]`
- Produces: `MACRO_SERIES_COLUMNS: list[str]`
- Produces: `CORE_VALUATION_METRICS: tuple[str, ...]`
- Produces: `finalize_index_valuation_frame(frame: pd.DataFrame, index_code: str, data_source: str, source_quality: str) -> pd.DataFrame`
- Produces: `normalize_macro_series(frame: pd.DataFrame, series_name: str, data_source: str) -> pd.DataFrame`
- Produces: `ParquetStore.write_index_valuations(index_code: str, frame: pd.DataFrame) -> Path`
- Produces: `ParquetStore.read_index_valuations(index_code: str) -> pd.DataFrame`
- Produces: `ParquetStore.write_macro_series(series_name: str, frame: pd.DataFrame) -> Path`
- Produces: `ParquetStore.read_macro_series(series_name: str) -> pd.DataFrame`

- [ ] **Step 1: Write the failing schema and storage tests**

Create `tests/test_index_valuations.py` with:

```python
import pandas as pd

from etf_trading.data.index_valuations import (
    CORE_VALUATION_METRICS,
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
    assert CORE_VALUATION_METRICS == ("pe_ttm", "pb", "erp")
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

- [ ] **Step 3: Add the normalized valuation schema**

Create `src/etf_trading/data/index_valuations.py` with:

```python
"""Normalized schemas and helpers for index valuation histories."""

from __future__ import annotations

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

MACRO_SERIES_COLUMNS = [
    "series_name",
    "trade_date",
    "value",
    "data_source",
    "source_updated_at",
]

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

CORE_VALUATION_METRICS = ("pe_ttm", "pb", "erp")


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

    pe = result["pe_ttm"].where(result["pe_ttm"] > 0)
    missing_earnings = result["earnings_yield"].isna()
    result.loc[missing_earnings, "earnings_yield"] = 1.0 / pe.loc[missing_earnings]

    missing_erp = result["erp"].isna()
    result.loc[missing_erp, "erp"] = result.loc[missing_erp, "earnings_yield"] - result.loc[missing_erp, "bond_yield_10y"]

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

    result["series_name"] = str(series_name)
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result["data_source"] = data_source
    result["source_updated_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    result = result.drop_duplicates(subset=["series_name", "trade_date"], keep="last")
    return result[MACRO_SERIES_COLUMNS].sort_values("trade_date").reset_index(drop=True)
```

- [ ] **Step 4: Add raw valuation and macro Parquet helpers**

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

- [ ] **Step 5: Run test to verify it passes**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuations.py -q
```

Expected: PASS with 4 tests.

- [ ] **Step 6: Stage files and record the suggested commit command**

Run only if the user explicitly asks for a commit in the execution session:

```powershell
git add src/etf_trading/data/index_valuations.py src/etf_trading/data/storage.py tests/test_index_valuations.py
git commit -m "feat: add index valuation parquet foundation"
```

---

### Task 2: Valuation Provider Boundary and Sync Service

**Files:**
- Modify: `src/etf_trading/data/provider.py`
- Modify: `src/etf_trading/data/providers/akshare_provider.py`
- Create: `src/etf_trading/data/index_valuation_service.py`
- Test: `tests/test_akshare_provider_fallback.py`
- Test: `tests/test_index_valuation_service.py`

**Interfaces:**
- Produces: `DataProvider.fetch_index_valuation(index_code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame`
- Produces: `DataProvider.fetch_macro_series(series_name: str, start_date: date | str, end_date: date | str) -> pd.DataFrame`
- Produces: `IndexValuationSyncResult(index_code: str, status: str, rows: int, first_date: str = "", latest_date: str = "", error_message: str | None = None)`
- Produces: `MacroSeriesSyncResult(series_name: str, status: str, rows: int, first_date: str = "", latest_date: str = "", error_message: str | None = None)`
- Produces: `IndexValuationSyncService.ensure_index_valuation(index_code: str, start_date: date | str, end_date: date | str) -> IndexValuationSyncResult`
- Produces: `IndexValuationSyncService.ensure_macro_series(series_name: str, start_date: date | str, end_date: date | str) -> MacroSeriesSyncResult`

- [ ] **Step 1: Write the failing provider and service tests**

Create `tests/test_index_valuation_service.py` with:

```python
from datetime import date

import pandas as pd

from etf_trading.data.index_valuation_service import IndexValuationSyncService
from etf_trading.data.storage import ParquetStore


class _Provider:
    def fetch_index_valuation(self, index_code, start_date, end_date):
        return pd.DataFrame(
            {
                "index_code": [index_code],
                "trade_date": [pd.Timestamp("2026-07-03")],
                "pe_ttm": [12.5],
                "pb": [1.4],
                "dividend_yield": [0.025],
                "earnings_yield": [0.08],
                "bond_yield_10y": [0.018],
                "erp": [0.062],
                "data_source": ["unit"],
                "source_quality": ["primary"],
                "source_updated_at": ["2026-07-06 09:00:00"],
            }
        )

    def fetch_macro_series(self, series_name, start_date, end_date):
        return pd.DataFrame(
            {
                "series_name": [series_name],
                "trade_date": [pd.Timestamp("2026-07-03")],
                "value": [0.018],
                "data_source": ["unit"],
                "source_updated_at": ["2026-07-06 09:00:00"],
            }
        )


class _FailingProvider:
    def fetch_index_valuation(self, index_code, start_date, end_date):
        raise RuntimeError("boom")

    def fetch_macro_series(self, series_name, start_date, end_date):
        raise RuntimeError("boom")


def test_service_writes_index_valuation_and_macro_series(tmp_path):
    store = ParquetStore(tmp_path)
    service = IndexValuationSyncService(_Provider(), store)

    valuation_result = service.ensure_index_valuation("000300", date(2026, 7, 1), date(2026, 7, 3))
    macro_result = service.ensure_macro_series("10y_bond_yield", date(2026, 7, 1), date(2026, 7, 3))

    assert valuation_result.status == "SUCCESS"
    assert valuation_result.rows == 1
    assert store.read_index_valuations("000300")["pe_ttm"].tolist() == [12.5]
    assert macro_result.status == "SUCCESS"
    assert store.read_macro_series("10y_bond_yield")["value"].tolist() == [0.018]


def test_service_surfaces_provider_failures_without_writing(tmp_path):
    store = ParquetStore(tmp_path)
    service = IndexValuationSyncService(_FailingProvider(), store)

    valuation_result = service.ensure_index_valuation("000300", "2026-07-01", "2026-07-03")
    macro_result = service.ensure_macro_series("10y_bond_yield", "2026-07-01", "2026-07-03")

    assert valuation_result.status == "FAILED"
    assert "boom" in str(valuation_result.error_message)
    assert store.read_index_valuations("000300").empty
    assert macro_result.status == "FAILED"
    assert store.read_macro_series("10y_bond_yield").empty
```

Create `tests/test_akshare_provider_fallback.py` with:

```python
import pandas as pd

from etf_trading.data.providers.akshare_provider import AkShareProvider


class _FakeAk:
    def stock_index_pe_lg(self, symbol):
        assert symbol == "沪深300"
        return pd.DataFrame(
            {
                "日期": ["2026-07-01", "2026-07-02"],
                "等权滚动市盈率": [11.0, 12.0],
            }
        )

    def stock_index_pb_lg(self, symbol):
        assert symbol == "沪深300"
        return pd.DataFrame(
            {
                "日期": ["2026-07-01", "2026-07-02"],
                "等权市净率": [1.20, 1.25],
            }
        )

    def stock_zh_index_value_csindex(self, symbol):
        assert symbol == "000300"
        return pd.DataFrame(
            {
                "交易日期": ["2026-07-03"],
                "滚动市盈率": [12.5],
                "市净率": [1.30],
                "股息率": [2.5],
            }
        )


def test_fetch_index_valuation_combines_legulegu_history_and_recent_csindex_check():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeAk()

    result = provider.fetch_index_valuation("000300", "2026-07-01", "2026-07-03")

    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-01", "2026-07-02", "2026-07-03"]
    latest = result.iloc[-1]
    assert latest["pe_ttm"] == 12.5
    assert latest["pb"] == 1.30
    assert round(float(latest["dividend_yield"]), 4) == 0.0250
    assert latest["data_source"] == "akshare_legulegu"


def test_fetch_macro_series_defaults_to_empty_frame():
    provider = AkShareProvider.__new__(AkShareProvider)
    provider.ak = _FakeAk()

    result = provider.fetch_macro_series("10y_bond_yield", "2026-07-01", "2026-07-03")

    assert result.empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuation_service.py tests/test_akshare_provider_fallback.py -q
```

Expected: FAIL with missing `IndexValuationSyncService`, missing valuation provider methods, or both.

- [ ] **Step 3: Extend the provider boundary with optional valuation hooks**

Modify `src/etf_trading/data/provider.py` by appending these non-abstract methods to `class DataProvider`:

```python
    def fetch_index_valuation(self, index_code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        """Return normalized valuation history for one index when the source supports it."""

        return pd.DataFrame()

    def fetch_macro_series(self, series_name: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        """Return a normalized macro time series such as 10-year bond yield when available."""

        return pd.DataFrame()
```

- [ ] **Step 4: Add the sync service**

Create `src/etf_trading/data/index_valuation_service.py` with:

```python
"""Services for syncing index valuation histories into local Parquet cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from etf_trading.data.storage import ParquetStore


@dataclass(frozen=True)
class IndexValuationSyncResult:
    index_code: str
    status: str
    rows: int
    first_date: str = ""
    latest_date: str = ""
    error_message: str | None = None


@dataclass(frozen=True)
class MacroSeriesSyncResult:
    series_name: str
    status: str
    rows: int
    first_date: str = ""
    latest_date: str = ""
    error_message: str | None = None


class IndexValuationSyncService:
    def __init__(self, provider, parquet_store: ParquetStore) -> None:
        self.provider = provider
        self.parquet_store = parquet_store

    def ensure_index_valuation(self, index_code: str, start_date: date | str, end_date: date | str) -> IndexValuationSyncResult:
        try:
            frame = self.provider.fetch_index_valuation(index_code, start_date, end_date)
        except Exception as exc:  # noqa: BLE001
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

    def ensure_macro_series(self, series_name: str, start_date: date | str, end_date: date | str) -> MacroSeriesSyncResult:
        try:
            frame = self.provider.fetch_macro_series(series_name, start_date, end_date)
        except Exception as exc:  # noqa: BLE001
            return MacroSeriesSyncResult(series_name=series_name, status="FAILED", rows=0, error_message=str(exc))
        if frame.empty:
            return MacroSeriesSyncResult(series_name=series_name, status="EMPTY", rows=0)
        frame = frame.sort_values("trade_date").reset_index(drop=True)
        self.parquet_store.write_macro_series(series_name, frame)
        return MacroSeriesSyncResult(
            series_name=series_name,
            status="SUCCESS",
            rows=int(len(frame)),
            first_date=pd.Timestamp(frame["trade_date"].min()).strftime("%Y-%m-%d"),
            latest_date=pd.Timestamp(frame["trade_date"].max()).strftime("%Y-%m-%d"),
        )
```

- [ ] **Step 5: Add AkShare valuation history support**

Modify imports in `src/etf_trading/data/providers/akshare_provider.py`:

```python
from etf_trading.data.index_valuations import finalize_index_valuation_frame
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

Add helpers near `_choose_latest_index_frame`:

```python
def _normalize_legulegu_pe(raw: pd.DataFrame, index_code: str) -> pd.DataFrame:
    frame = raw.rename(columns={"日期": "trade_date", "等权滚动市盈率": "pe_ttm"}).copy()
    return finalize_index_valuation_frame(frame[["trade_date", "pe_ttm"]], index_code, "akshare_legulegu", "fallback")


def _normalize_legulegu_pb(raw: pd.DataFrame, index_code: str) -> pd.DataFrame:
    frame = raw.rename(columns={"日期": "trade_date", "等权市净率": "pb"}).copy()
    return finalize_index_valuation_frame(frame[["trade_date", "pb"]], index_code, "akshare_legulegu", "fallback")


def _normalize_csindex_recent_valuation(raw: pd.DataFrame, index_code: str) -> pd.DataFrame:
    frame = raw.rename(
        columns={
            "交易日期": "trade_date",
            "滚动市盈率": "pe_ttm",
            "静态市盈率": "pe_static",
            "市净率": "pb",
            "股息率": "dividend_yield",
        }
    ).copy()
    if "dividend_yield" in frame.columns:
        frame["dividend_yield"] = pd.to_numeric(frame["dividend_yield"], errors="coerce") / 100.0
    keep = [column for column in ["trade_date", "pe_ttm", "pe_static", "pb", "dividend_yield"] if column in frame.columns]
    return finalize_index_valuation_frame(frame[keep], index_code, "akshare_csindex", "recent_check")


def _merge_valuation_frames(index_code: str, frames: list[pd.DataFrame]) -> pd.DataFrame:
    available = [frame for frame in frames if not frame.empty]
    if not available:
        return pd.DataFrame()
    merged = available[0].copy()
    for frame in available[1:]:
        value_columns = [
            column
            for column in frame.columns
            if column not in {"index_code", "trade_date", "data_source", "source_quality", "source_updated_at"}
        ]
        merged = merged.merge(frame[["trade_date", *value_columns]], on="trade_date", how="outer", suffixes=("", "_new"))
        for column in value_columns:
            new_column = f"{column}_new"
            if new_column in merged.columns:
                merged[column] = merged[column].combine_first(merged[new_column])
                merged = merged.drop(columns=[new_column])
    return finalize_index_valuation_frame(merged, index_code, "akshare_legulegu", "fallback")
```

Add methods to `class AkShareProvider`:

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
                frames.append(_normalize_legulegu_pe(pe_raw, code))
            except Exception:
                pass
            try:
                pb_raw = _call_with_retries(self.ak.stock_index_pb_lg, f"AkShare 乐咕指数PB {code}", attempts=2, symbol=symbol)
                frames.append(_normalize_legulegu_pb(pb_raw, code))
            except Exception:
                pass

        try:
            recent_raw = _call_with_retries(self.ak.stock_zh_index_value_csindex, f"AkShare 中证指数估值 {code}", attempts=2, symbol=code)
            frames.append(_normalize_csindex_recent_valuation(recent_raw, code))
        except Exception:
            pass

        merged = _merge_valuation_frames(code, frames)
        if merged.empty:
            return merged
        return merged[(merged["trade_date"] >= start) & (merged["trade_date"] <= end)].reset_index(drop=True)

    def fetch_macro_series(self, series_name: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        return pd.DataFrame()
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuation_service.py tests/test_akshare_provider_fallback.py -q
```

Expected: PASS.

- [ ] **Step 7: Stage files and record the suggested commit command**

Run only if the user explicitly asks for a commit in the execution session:

```powershell
git add src/etf_trading/data/provider.py src/etf_trading/data/providers/akshare_provider.py src/etf_trading/data/index_valuation_service.py tests/test_akshare_provider_fallback.py tests/test_index_valuation_service.py
git commit -m "feat: add index valuation provider and sync service"
```

---

### Task 3: Build the Index Health Snapshot Research Layer

**Files:**
- Create: `src/etf_trading/research/index_health_snapshot.py`
- Test: `tests/test_index_health_snapshot.py`

**Interfaces:**
- Consumes: `ParquetStore.read_index_prices(index_code: str) -> pd.DataFrame`
- Consumes: `ParquetStore.read_index_valuations(index_code: str) -> pd.DataFrame`
- Consumes: `ParquetStore.read_macro_series(series_name: str) -> pd.DataFrame`
- Produces: `INDEX_HEALTH_SNAPSHOT_COLUMNS: list[str]`
- Produces: `INDEX_HEALTH_DETAIL_COLUMNS: list[str]`
- Produces: `build_index_health_snapshot(parquet_store, definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES, *, as_of_date: pd.Timestamp | str | None = None, min_valuation_history_rows: int = 756) -> tuple[pd.DataFrame, pd.DataFrame]`
- Produces: `build_index_trend_detail_rows(index_code: str, prices: pd.DataFrame) -> pd.DataFrame`
- Produces: `build_index_valuation_detail_rows(index_code: str, valuations: pd.DataFrame, *, as_of_date: pd.Timestamp | str | None = None, min_history_rows: int = 756) -> pd.DataFrame`

- [ ] **Step 1: Write the failing snapshot tests**

Create `tests/test_index_health_snapshot.py` with:

```python
from datetime import date

import pandas as pd

from etf_trading.data.indexes import IndexDefinition
from etf_trading.data.index_valuations import finalize_index_valuation_frame, normalize_macro_series
from etf_trading.research.index_health_snapshot import (
    build_index_health_snapshot,
    build_index_trend_detail_rows,
    build_index_valuation_detail_rows,
)


class _Store:
    def __init__(self, prices=None, valuations=None, macro=None):
        self._prices = prices or {}
        self._valuations = valuations or {}
        self._macro = macro or {}

    def read_index_prices(self, index_code):
        return self._prices.get(index_code, pd.DataFrame())

    def read_index_valuations(self, index_code):
        return self._valuations.get(index_code, pd.DataFrame())

    def read_macro_series(self, series_name):
        return self._macro.get(series_name, pd.DataFrame())


def _price_frame(rows=900):
    dates = pd.date_range("2022-01-03", periods=rows, freq="B")
    close = pd.Series([3000.0 + index * 2.0 for index in range(rows)], dtype=float)
    return pd.DataFrame(
        {
            "index_code": ["000300"] * rows,
            "trade_date": dates,
            "open": close - 5.0,
            "high": close + 10.0,
            "low": close - 10.0,
            "close": close,
            "volume": 1_000_000,
            "amount": 10_000_000,
            "data_source": "unit",
        }
    )


def _valuation_frame(rows=820):
    dates = pd.date_range("2023-01-02", periods=rows, freq="B")
    raw = pd.DataFrame(
        {
            "trade_date": dates,
            "pe_ttm": [12.0 + index / 200 for index in range(rows)],
            "pb": [1.20 + index / 2000 for index in range(rows)],
            "dividend_yield": [0.025 for _ in range(rows)],
            "bond_yield_10y": [0.018 for _ in range(rows)],
        }
    )
    return finalize_index_valuation_frame(raw, "000300", "unit", "primary")


def test_trend_detail_rows_expose_current_value_status_and_reason():
    rows = build_index_trend_detail_rows("000300", _price_frame())

    names = set(rows["metric_name"].tolist())
    assert {"large_trend", "medium_trend", "small_trend", "ma250_slope_60", "momentum_60", "drawdown_120"} <= names
    state_row = rows[rows["metric_name"] == "large_trend"].iloc[0]
    assert state_row["detail_kind"] == "trend"
    assert state_row["status"] in {"normal", "watch"}
    assert state_row["reason"]


def test_valuation_detail_rows_compute_percentiles_and_keep_missing_reasons():
    frame = _valuation_frame().drop(columns=["ps"])

    rows = build_index_valuation_detail_rows("000300", frame, as_of_date="2026-02-20")
    by_metric = {row.metric_name: row for row in rows.itertuples(index=False)}

    assert by_metric["pe_ttm"].status == "computed"
    assert by_metric["pe_ttm"].historical_percentile > 90
    assert by_metric["ps"].status == "missing_field"
    assert pd.isna(by_metric["ps"].historical_percentile)


def test_build_index_health_snapshot_returns_summary_plus_long_form_details():
    definitions = (IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),)
    store = _Store(
        prices={"000300": _price_frame()},
        valuations={"000300": _valuation_frame()},
        macro={"10y_bond_yield": normalize_macro_series(pd.DataFrame({"trade_date": ["2026-07-03"], "value": [0.018]}), "10y_bond_yield", "unit")},
    )

    summary, details = build_index_health_snapshot(store, definitions, as_of_date=date(2026, 7, 3))

    row = summary.iloc[0]
    assert row["index_code"] == "000300"
    assert row["detail_payload_key"] == "000300"
    assert row["trend_health_status"] in {"normal", "watch"}
    assert row["valuation_health_status"] == "complete"
    assert row["valuation_overview_label"] in {"low_percentile", "mid_percentile", "high_percentile"}
    assert set(details["detail_kind"]) == {"trend", "valuation"}


def test_build_index_health_snapshot_marks_missing_valuation_without_crashing():
    definitions = (IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),)
    store = _Store(prices={"000300": _price_frame()}, valuations={})

    summary, details = build_index_health_snapshot(store, definitions, as_of_date="2026-07-03")

    row = summary.iloc[0]
    assert row["valuation_health_status"] == "missing_valuation"
    assert row["valuation_overview_label"] == "missing"
    assert not details[details["detail_kind"] == "trend"].empty
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_health_snapshot.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `etf_trading.research.index_health_snapshot`.

- [ ] **Step 3: Implement the snapshot builder**

Create `src/etf_trading/research/index_health_snapshot.py` with:

```python
"""Build page-ready index health summary and detail diagnostics."""

from __future__ import annotations

import math

import pandas as pd

from etf_trading.data.indexes import DEFAULT_INDEXES, IndexDefinition
from etf_trading.data.index_valuations import CORE_VALUATION_METRICS
from etf_trading.research.regime import TrendRegimeClassifier, add_trend_regime_features


INDEX_HEALTH_SNAPSHOT_COLUMNS = [
    "index_code",
    "index_name",
    "market",
    "category",
    "latest_date",
    "history_rows",
    "large_trend",
    "medium_trend",
    "small_trend",
    "allows_new_position",
    "trend_health_status",
    "trend_health_reason",
    "valuation_overview_label",
    "valuation_health_status",
    "valuation_health_reason",
    "valuation_latest_date",
    "valuation_coverage_years",
    "valuation_primary_source",
    "detail_payload_key",
]

INDEX_HEALTH_DETAIL_COLUMNS = [
    "index_code",
    "detail_kind",
    "metric_name",
    "metric_label",
    "current_value",
    "status",
    "reason",
    "display_direction",
    "historical_percentile",
    "window_years",
    "first_date",
    "latest_date",
    "sample_count",
    "data_source",
]


def build_index_health_snapshot(
    parquet_store,
    definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES,
    *,
    as_of_date: pd.Timestamp | str | None = None,
    min_valuation_history_rows: int = 756,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    details: list[pd.DataFrame] = []
    for definition in definitions:
        prices = parquet_store.read_index_prices(definition.index_code)
        valuations = parquet_store.read_index_valuations(definition.index_code)

        trend_rows = build_index_trend_detail_rows(definition.index_code, prices)
        valuation_rows = build_index_valuation_detail_rows(
            definition.index_code,
            valuations,
            as_of_date=as_of_date,
            min_history_rows=min_valuation_history_rows,
        )
        details.append(trend_rows)
        details.append(valuation_rows)

        trend_summary = _trend_summary(definition, prices, trend_rows)
        valuation_summary = _valuation_summary(valuations, valuation_rows)
        rows.append(
            {
                "index_code": definition.index_code,
                "index_name": definition.name,
                "market": definition.market,
                "category": definition.category,
                **trend_summary,
                **valuation_summary,
                "detail_payload_key": definition.index_code,
            }
        )

    summary = pd.DataFrame(rows, columns=INDEX_HEALTH_SNAPSHOT_COLUMNS)
    detail_frame = pd.concat(details, ignore_index=True) if details else pd.DataFrame(columns=INDEX_HEALTH_DETAIL_COLUMNS)
    return summary, detail_frame


def build_index_trend_detail_rows(index_code: str, prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(
            [
                {
                    "index_code": index_code,
                    "detail_kind": "trend",
                    "metric_name": "trend_inputs",
                    "metric_label": "trend_inputs",
                    "current_value": pd.NA,
                    "status": "missing_history",
                    "reason": "missing index price history",
                    "display_direction": "n/a",
                    "historical_percentile": pd.NA,
                    "window_years": pd.NA,
                    "first_date": "",
                    "latest_date": "",
                    "sample_count": 0,
                    "data_source": "",
                }
            ],
            columns=INDEX_HEALTH_DETAIL_COLUMNS,
        )

    featured = add_trend_regime_features(prices)
    if featured.empty:
        return pd.DataFrame(columns=INDEX_HEALTH_DETAIL_COLUMNS)

    last = featured.iloc[-1]
    regime = TrendRegimeClassifier().classify(last)
    latest_date = pd.Timestamp(last["trade_date"]).strftime("%Y-%m-%d")
    metrics = [
        ("large_trend", "large_trend", regime.large_trend, "higher_is_better", "normal" if regime.large_trend in {"UP", "RECOVERY"} else "watch", ",".join(regime.trigger_rules or ["large_trend_not_ready"])),
        ("medium_trend", "medium_trend", regime.medium_trend, "higher_is_better", "normal" if regime.medium_trend in {"UP", "TURNING_UP"} else "watch", ",".join(regime.trigger_rules or ["medium_trend_not_ready"])),
        ("small_trend", "small_trend", regime.small_trend, "higher_is_better", "normal" if regime.small_trend in {"RIGHT_SIDE_START", "PULLBACK"} else "watch", ",".join(regime.risk_tags or ["small_trend_not_ready"])),
        ("allows_new_position", "allows_new_position", bool(regime.allows_new_position), "higher_is_better", "normal" if regime.allows_new_position else "watch", "trend_gate_open" if regime.allows_new_position else "trend_gate_closed"),
        ("ma250_slope_60", "ma250_slope_60", last.get("ma250_slope_60"), "higher_is_better", "normal", "derived from add_trend_regime_features"),
        ("momentum_60", "momentum_60", last.get("momentum_60"), "higher_is_better", "normal", "60-day momentum"),
        ("momentum_120", "momentum_120", last.get("momentum_120"), "higher_is_better", "normal", "120-day momentum"),
        ("drawdown_120", "drawdown_120", last.get("drawdown_120"), "higher_is_better", "normal", "120-day drawdown"),
        ("distance_ma20_pct", "distance_ma20_pct", last.get("distance_ma20_pct"), "higher_is_better", "normal", "distance to MA20"),
    ]

    rows = []
    for metric_name, metric_label, current_value, display_direction, status, reason in metrics:
        rows.append(
            {
                "index_code": index_code,
                "detail_kind": "trend",
                "metric_name": metric_name,
                "metric_label": metric_label,
                "current_value": current_value,
                "status": status,
                "reason": reason,
                "display_direction": display_direction,
                "historical_percentile": pd.NA,
                "window_years": pd.NA,
                "first_date": "",
                "latest_date": latest_date,
                "sample_count": int(len(featured)),
                "data_source": str(last.get("data_source", "")),
            }
        )
    return pd.DataFrame(rows, columns=INDEX_HEALTH_DETAIL_COLUMNS)


def build_index_valuation_detail_rows(
    index_code: str,
    valuations: pd.DataFrame,
    *,
    as_of_date: pd.Timestamp | str | None = None,
    min_history_rows: int = 756,
) -> pd.DataFrame:
    as_of = pd.Timestamp(as_of_date) if as_of_date is not None else None
    metrics = [
        ("pe_ttm", "pe_ttm", "higher_is_more_expensive"),
        ("pb", "pb", "higher_is_more_expensive"),
        ("dividend_yield", "dividend_yield", "lower_is_more_expensive"),
        ("earnings_yield", "earnings_yield", "lower_is_more_expensive"),
        ("bond_yield_10y", "bond_yield_10y", "macro_context"),
        ("erp", "erp", "lower_is_tighter_risk_premium"),
        ("ps", "ps", "higher_is_more_expensive"),
        ("roe", "roe", "higher_is_better"),
        ("forward_pe", "forward_pe", "higher_is_more_expensive"),
    ]
    rows = []
    frame = valuations.copy()
    if not frame.empty and "trade_date" in frame.columns:
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        if as_of is not None:
            frame = frame[frame["trade_date"] <= as_of].reset_index(drop=True)

    for metric_name, metric_label, display_direction in metrics:
        if frame.empty or "trade_date" not in frame.columns:
            rows.append(_valuation_row(index_code, metric_name, metric_label, display_direction, status="missing_valuation", reason="missing valuation history"))
            continue
        if metric_name not in frame.columns:
            rows.append(_valuation_row(index_code, metric_name, metric_label, display_direction, status="missing_field", reason=f"missing column: {metric_name}", latest_date=_latest_date(frame), sample_count=len(frame), data_source=_latest_source(frame)))
            continue
        series = pd.to_numeric(frame[metric_name], errors="coerce").dropna()
        if series.empty:
            rows.append(_valuation_row(index_code, metric_name, metric_label, display_direction, status="missing_field", reason=f"all values missing: {metric_name}", latest_date=_latest_date(frame), sample_count=len(frame), data_source=_latest_source(frame)))
            continue
        if len(series) < min_history_rows:
            rows.append(_valuation_row(index_code, metric_name, metric_label, display_direction, status="insufficient_history", reason=f"history shorter than {min_history_rows} rows", current_value=series.iloc[-1], latest_date=_latest_date(frame), first_date=_first_date(frame), sample_count=len(series), data_source=_latest_source(frame)))
            continue
        percentile = _percentile_rank_current(series)
        rows.append(_valuation_row(index_code, metric_name, metric_label, display_direction, status="computed", reason="ok", current_value=series.iloc[-1], historical_percentile=percentile, window_years=round(len(series) / 252.0, 1), first_date=_first_date(frame), latest_date=_latest_date(frame), sample_count=len(series), data_source=_latest_source(frame)))
    return pd.DataFrame(rows, columns=INDEX_HEALTH_DETAIL_COLUMNS)


def _trend_summary(definition: IndexDefinition, prices: pd.DataFrame, trend_rows: pd.DataFrame) -> dict[str, object]:
    if prices.empty:
        return {
            "latest_date": "",
            "history_rows": 0,
            "large_trend": "UNKNOWN",
            "medium_trend": "UNKNOWN",
            "small_trend": "UNKNOWN",
            "allows_new_position": False,
            "trend_health_status": "missing_history",
            "trend_health_reason": "missing index price history",
        }
    featured = add_trend_regime_features(prices)
    if featured.empty:
        return {
            "latest_date": "",
            "history_rows": 0,
            "large_trend": "UNKNOWN",
            "medium_trend": "UNKNOWN",
            "small_trend": "UNKNOWN",
            "allows_new_position": False,
            "trend_health_status": "missing_features",
            "trend_health_reason": "trend features unavailable",
        }
    last = featured.iloc[-1]
    regime = TrendRegimeClassifier().classify(last)
    status = "normal" if regime.allows_new_position else "watch"
    reason = f"large={regime.large_trend}, medium={regime.medium_trend}, small={regime.small_trend}"
    if len(featured) < 850:
        status = "missing_history"
        reason = "price history shorter than 850 rows for long trend context"
    return {
        "latest_date": pd.Timestamp(last["trade_date"]).strftime("%Y-%m-%d"),
        "history_rows": int(len(featured)),
        "large_trend": regime.large_trend,
        "medium_trend": regime.medium_trend,
        "small_trend": regime.small_trend,
        "allows_new_position": bool(regime.allows_new_position),
        "trend_health_status": status,
        "trend_health_reason": reason,
    }


def _valuation_summary(valuations: pd.DataFrame, valuation_rows: pd.DataFrame) -> dict[str, object]:
    if valuations.empty or "trade_date" not in valuations.columns:
        return {
            "valuation_overview_label": "missing",
            "valuation_health_status": "missing_valuation",
            "valuation_health_reason": "missing valuation history",
            "valuation_latest_date": "",
            "valuation_coverage_years": "",
            "valuation_primary_source": "",
        }

    statuses = valuation_rows[valuation_rows["metric_name"].isin(CORE_VALUATION_METRICS)]
    computed = statuses[statuses["status"] == "computed"]
    insufficient = statuses[statuses["status"] == "insufficient_history"]
    if len(computed) == 0 and len(insufficient) == len(statuses):
        overview = "insufficient_history"
        health_status = "insufficient_history"
        health_reason = "core valuation metrics do not have enough history"
    elif len(computed) == 0:
        overview = "missing"
        health_status = "missing_valuation"
        health_reason = "core valuation metrics are missing"
    else:
        overview = _overview_from_percentiles(computed["historical_percentile"].tolist())
        health_status = "complete" if len(computed) == len(statuses) else "partial"
        health_reason = "all core valuation metrics available" if health_status == "complete" else "some core valuation metrics are missing or short"

    trade_dates = pd.to_datetime(valuations["trade_date"])
    years = round(len(trade_dates) / 252.0, 1)
    return {
        "valuation_overview_label": overview,
        "valuation_health_status": health_status,
        "valuation_health_reason": health_reason,
        "valuation_latest_date": pd.Timestamp(trade_dates.max()).strftime("%Y-%m-%d"),
        "valuation_coverage_years": f"{years:.1f}",
        "valuation_primary_source": _latest_source(valuations),
    }


def _overview_from_percentiles(values: list[object]) -> str:
    numeric = [float(value) for value in values if not pd.isna(value)]
    if not numeric:
        return "missing"
    low = sum(value <= 33.0 for value in numeric)
    high = sum(value >= 67.0 for value in numeric)
    if low >= max(high, 2 if len(numeric) >= 2 else 1):
        return "low_percentile"
    if high >= max(low, 2 if len(numeric) >= 2 else 1):
        return "high_percentile"
    return "mid_percentile"


def _valuation_row(
    index_code: str,
    metric_name: str,
    metric_label: str,
    display_direction: str,
    *,
    status: str,
    reason: str,
    current_value: object = pd.NA,
    historical_percentile: object = pd.NA,
    window_years: object = pd.NA,
    first_date: str = "",
    latest_date: str = "",
    sample_count: int = 0,
    data_source: str = "",
) -> dict[str, object]:
    return {
        "index_code": index_code,
        "detail_kind": "valuation",
        "metric_name": metric_name,
        "metric_label": metric_label,
        "current_value": current_value,
        "status": status,
        "reason": reason,
        "display_direction": display_direction,
        "historical_percentile": historical_percentile,
        "window_years": window_years,
        "first_date": first_date,
        "latest_date": latest_date,
        "sample_count": sample_count,
        "data_source": data_source,
    }


def _percentile_rank_current(values: pd.Series) -> float:
    series = pd.to_numeric(values, errors="coerce").dropna()
    if series.empty:
        return math.nan
    current = series.iloc[-1]
    less = (series < current).sum()
    equal = (series == current).sum()
    return float(100.0 * (less + 0.5 * equal) / len(series))


def _latest_source(frame: pd.DataFrame) -> str:
    if "data_source" not in frame.columns or frame.empty:
        return ""
    return str(frame["data_source"].dropna().iloc[-1]) if not frame["data_source"].dropna().empty else ""


def _first_date(frame: pd.DataFrame) -> str:
    return pd.Timestamp(frame["trade_date"].min()).strftime("%Y-%m-%d")


def _latest_date(frame: pd.DataFrame) -> str:
    return pd.Timestamp(frame["trade_date"].max()).strftime("%Y-%m-%d")
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_health_snapshot.py -q
```

Expected: PASS.

- [ ] **Step 5: Stage files and record the suggested commit command**

Run only if the user explicitly asks for a commit in the execution session:

```powershell
git add src/etf_trading/research/index_health_snapshot.py tests/test_index_health_snapshot.py
git commit -m "feat: build index health snapshot research layer"
```

---

### Task 4: Add Page-Ready Index Health Snapshot Cache State

**Files:**
- Modify: `src/etf_trading/nicegui_app/state.py`
- Test: `tests/test_nicegui_state_cache.py`

**Interfaces:**
- Produces: `IndexHealthSnapshotCacheResult(summary: pd.DataFrame, details: pd.DataFrame, status: str, generated_at: datetime | None = None, message: str = "")`
- Produces: `load_index_health_snapshot_cached(parquet_store: ParquetStore, definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES, *, force_refresh: bool = False) -> IndexHealthSnapshotCacheResult`
- Produces: `invalidate_index_health_snapshot_cache(parquet_store: ParquetStore | None = None) -> None`
- Produces: `_index_health_snapshot_cache_paths(parquet_store: ParquetStore) -> tuple[Path, Path, Path]`
- Produces: `_build_index_health_snapshot_worker(parquet_root: Path, source_signature: str, definitions: tuple[IndexDefinition, ...]) -> None`

- [ ] **Step 1: Add failing cache state tests**

Append to `tests/test_nicegui_state_cache.py`:

```python
def _write_index_health_cache(root: Path, signature: str) -> None:
    cache_dir = root / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "index_code": ["000300"],
            "index_name": ["沪深300"],
            "category": ["A股宽基"],
            "trend_health_status": ["normal"],
            "valuation_health_status": ["complete"],
            "valuation_overview_label": ["mid_percentile"],
        }
    ).to_parquet(cache_dir / "index_health_snapshot.parquet", index=False)
    pd.DataFrame(
        {
            "index_code": ["000300", "000300"],
            "detail_kind": ["trend", "valuation"],
            "metric_name": ["large_trend", "pe_ttm"],
            "status": ["normal", "computed"],
            "reason": ["ok", "ok"],
        }
    ).to_parquet(cache_dir / "index_health_snapshot_details.parquet", index=False)
    (cache_dir / "index_health_snapshot.meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_signature": signature,
                "generated_at": "2026-07-06T10:00:00",
                "summary_rows": 1,
                "detail_rows": 2,
            }
        ),
        encoding="utf-8",
    )


def test_load_index_health_snapshot_cached_uses_fresh_disk_cache_without_building(tmp_path, monkeypatch):
    root = tmp_path / "parquet"
    _write_index_health_cache(root, "current-signature")
    scheduled = []
    monkeypatch.setattr(state, "_index_health_snapshot_source_signature", lambda parquet_store, definitions: "current-signature", raising=False)
    monkeypatch.setattr(state, "_start_index_health_snapshot_build", lambda *args, **kwargs: scheduled.append("build"), raising=False)
    state.invalidate_index_health_snapshot_cache()

    result = state.load_index_health_snapshot_cached(FakeParquetStore(str(root)))

    assert result.status == "ready"
    assert result.summary["index_code"].tolist() == ["000300"]
    assert set(result.details["detail_kind"]) == {"trend", "valuation"}
    assert scheduled == []


def test_load_index_health_snapshot_cached_serves_stale_cache_while_scheduling_refresh(tmp_path, monkeypatch):
    root = tmp_path / "parquet"
    _write_index_health_cache(root, "old-signature")
    scheduled = []
    monkeypatch.setattr(state, "_index_health_snapshot_source_signature", lambda parquet_store, definitions: "current-signature", raising=False)
    monkeypatch.setattr(state, "_start_index_health_snapshot_build", lambda *args, **kwargs: scheduled.append("build"), raising=False)
    state.invalidate_index_health_snapshot_cache()

    result = state.load_index_health_snapshot_cached(FakeParquetStore(str(root)))

    assert result.status == "stale"
    assert result.summary["index_code"].tolist() == ["000300"]
    assert scheduled == ["build"]


def test_load_index_health_snapshot_cached_returns_building_without_cache(tmp_path, monkeypatch):
    root = tmp_path / "parquet"
    scheduled = []
    monkeypatch.setattr(state, "_index_health_snapshot_source_signature", lambda parquet_store, definitions: "current-signature", raising=False)
    monkeypatch.setattr(state, "_start_index_health_snapshot_build", lambda *args, **kwargs: scheduled.append("build"), raising=False)
    state.invalidate_index_health_snapshot_cache()

    result = state.load_index_health_snapshot_cached(FakeParquetStore(str(root)))

    assert result.status == "building"
    assert result.summary.empty
    assert result.details.empty
    assert scheduled == ["build"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_state_cache.py -q
```

Expected: FAIL with missing `load_index_health_snapshot_cached`, missing dataclass, or missing cache helpers.

- [ ] **Step 3: Add the memory/disk cache state machine**

Modify `src/etf_trading/nicegui_app/state.py`:

```python
INDEX_HEALTH_SNAPSHOT_CACHE_SCHEMA_VERSION = 1
_INDEX_HEALTH_SNAPSHOT_CACHE: dict[str, tuple[str, pd.DataFrame, pd.DataFrame, datetime | None]] = {}
_INDEX_HEALTH_SNAPSHOT_ERRORS: dict[str, str] = {}
_INDEX_HEALTH_SNAPSHOT_CACHE_LOCK = RLock()
INDEX_HEALTH_SNAPSHOT_BUILD_MARKER_MAX_AGE_SECONDS = 600.0


@dataclass(frozen=True)
class IndexHealthSnapshotCacheResult:
    summary: pd.DataFrame
    details: pd.DataFrame
    status: str
    generated_at: datetime | None = None
    message: str = ""
```

Append cache helpers near the atomic snapshot helpers:

```python
def load_index_health_snapshot_cached(
    parquet_store: ParquetStore,
    definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES,
    *,
    force_refresh: bool = False,
) -> IndexHealthSnapshotCacheResult:
    source_signature = _index_health_snapshot_source_signature(parquet_store, definitions)
    cache_key = _index_health_snapshot_cache_key(parquet_store)

    if not force_refresh:
        with _INDEX_HEALTH_SNAPSHOT_CACHE_LOCK:
            cached = _INDEX_HEALTH_SNAPSHOT_CACHE.get(cache_key)
            if cached is not None:
                cached_signature, summary, details, generated_at = cached
                if cached_signature == source_signature:
                    return IndexHealthSnapshotCacheResult(summary=summary.copy(), details=details.copy(), status="ready", generated_at=generated_at)

    disk_cache = _read_index_health_snapshot_disk_cache(parquet_store)
    if disk_cache is not None:
        disk_signature, summary, details, generated_at = disk_cache
        if disk_signature == source_signature and not force_refresh:
            with _INDEX_HEALTH_SNAPSHOT_CACHE_LOCK:
                _INDEX_HEALTH_SNAPSHOT_CACHE[cache_key] = (disk_signature, summary.copy(), details.copy(), generated_at)
            return IndexHealthSnapshotCacheResult(summary=summary.copy(), details=details.copy(), status="ready", generated_at=generated_at)

        _start_index_health_snapshot_build(parquet_store, source_signature, definitions)
        return IndexHealthSnapshotCacheResult(
            summary=summary.copy(),
            details=details.copy(),
            status="stale",
            generated_at=generated_at,
            message="指数体检快照正在后台刷新",
        )

    _start_index_health_snapshot_build(parquet_store, source_signature, definitions)
    with _INDEX_HEALTH_SNAPSHOT_CACHE_LOCK:
        error_message = _INDEX_HEALTH_SNAPSHOT_ERRORS.get(cache_key, "")
    if error_message:
        return IndexHealthSnapshotCacheResult(summary=pd.DataFrame(), details=pd.DataFrame(), status="failed", message=error_message)
    return IndexHealthSnapshotCacheResult(summary=pd.DataFrame(), details=pd.DataFrame(), status="building", message="指数体检快照正在后台生成")


def invalidate_index_health_snapshot_cache(parquet_store: ParquetStore | None = None) -> None:
    with _INDEX_HEALTH_SNAPSHOT_CACHE_LOCK:
        if parquet_store is None:
            _INDEX_HEALTH_SNAPSHOT_CACHE.clear()
            _INDEX_HEALTH_SNAPSHOT_ERRORS.clear()
            return
        cache_key = _index_health_snapshot_cache_key(parquet_store)
        _INDEX_HEALTH_SNAPSHOT_CACHE.pop(cache_key, None)
        _INDEX_HEALTH_SNAPSHOT_ERRORS.pop(cache_key, None)


def _index_health_snapshot_cache_key(parquet_store: ParquetStore) -> str:
    return str(Path(getattr(parquet_store, "root", "data/parquet")).resolve())


def _index_health_snapshot_cache_paths(parquet_store: ParquetStore) -> tuple[Path, Path, Path]:
    cache_dir = Path(getattr(parquet_store, "root", "data/parquet")).resolve() / "cache"
    return (
        cache_dir / "index_health_snapshot.parquet",
        cache_dir / "index_health_snapshot_details.parquet",
        cache_dir / "index_health_snapshot.meta.json",
    )


def _index_health_snapshot_build_marker_path(parquet_store: ParquetStore) -> Path:
    summary_file, _detail_file, _meta_file = _index_health_snapshot_cache_paths(parquet_store)
    return summary_file.with_name("index_health_snapshot.building")


def _index_health_snapshot_source_signature(
    parquet_store: ParquetStore,
    definitions: tuple[IndexDefinition, ...],
) -> str:
    digest = hashlib.sha256()
    root = Path(getattr(parquet_store, "root", "data/parquet")).resolve()
    for folder_name in ("indexes", "index_valuations", "macro"):
        folder = root / folder_name
        if folder.exists():
            for path in sorted(folder.glob("*.parquet")):
                stat = path.stat()
                digest.update(f"{path.name}|{stat.st_size}|{stat.st_mtime_ns}".encode())
    digest.update(",".join(definition.index_code for definition in definitions).encode())
    return digest.hexdigest()
```

Append disk read/write and worker helpers:

```python
def _read_index_health_snapshot_disk_cache(
    parquet_store: ParquetStore,
) -> tuple[str, pd.DataFrame, pd.DataFrame, datetime | None] | None:
    summary_file, detail_file, meta_file = _index_health_snapshot_cache_paths(parquet_store)
    if not summary_file.exists() or not detail_file.exists() or not meta_file.exists():
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if int(meta.get("schema_version", 0)) != INDEX_HEALTH_SNAPSHOT_CACHE_SCHEMA_VERSION:
            return None
        summary = pd.read_parquet(summary_file)
        details = pd.read_parquet(detail_file)
    except Exception:
        return None
    generated_at = _parse_cache_datetime(meta.get("generated_at"))
    return str(meta.get("source_signature", "")), summary, details, generated_at


def _write_index_health_snapshot_disk_cache(
    summary: pd.DataFrame,
    details: pd.DataFrame,
    source_signature: str,
    generated_at: datetime,
    parquet_store: ParquetStore,
) -> None:
    summary_file, detail_file, meta_file = _index_health_snapshot_cache_paths(parquet_store)
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_summary = summary_file.with_name(f"{summary_file.stem}.tmp{summary_file.suffix}")
    tmp_details = detail_file.with_name(f"{detail_file.stem}.tmp{detail_file.suffix}")
    tmp_meta = meta_file.with_name(f"{meta_file.stem}.tmp{meta_file.suffix}")
    summary.to_parquet(tmp_summary, index=False)
    details.to_parquet(tmp_details, index=False)
    tmp_summary.replace(summary_file)
    tmp_details.replace(detail_file)
    tmp_meta.write_text(
        json.dumps(
            {
                "schema_version": INDEX_HEALTH_SNAPSHOT_CACHE_SCHEMA_VERSION,
                "source_signature": source_signature,
                "generated_at": generated_at.isoformat(timespec="seconds"),
                "summary_rows": int(len(summary)),
                "detail_rows": int(len(details)),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp_meta.replace(meta_file)


def _start_index_health_snapshot_build(
    parquet_store: ParquetStore,
    source_signature: str,
    definitions: tuple[IndexDefinition, ...],
) -> bool:
    cache_key = _index_health_snapshot_cache_key(parquet_store)
    marker_file = _index_health_snapshot_build_marker_path(parquet_store)
    marker_file.parent.mkdir(parents=True, exist_ok=True)
    with _INDEX_HEALTH_SNAPSHOT_CACHE_LOCK:
        if marker_file.exists() and not _is_stale_build_marker(marker_file):
            return False
        _INDEX_HEALTH_SNAPSHOT_ERRORS.pop(cache_key, None)
        marker_file.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")

    parquet_root = Path(getattr(parquet_store, "root", "data/parquet")).resolve()
    project_root = Path(__file__).resolve().parents[3]
    src_root = project_root / "src"
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(src_root) if not existing_pythonpath else f"{src_root}{os.pathsep}{existing_pythonpath}"
    code = (
        "from etf_trading.nicegui_app.state import _build_index_health_snapshot_subprocess; "
        f"_build_index_health_snapshot_subprocess({str(parquet_root)!r}, {source_signature!r}, {tuple(item.index_code for item in definitions)!r}, {str(marker_file)!r})"
    )
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen([sys.executable, "-c", code], cwd=project_root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
    return True


def _build_index_health_snapshot_subprocess(parquet_root: str, source_signature: str, index_codes: tuple[str, ...], marker_file: str) -> None:
    marker_path = Path(marker_file)
    try:
        worker_store = ParquetStore(parquet_root)
        definitions = tuple(item for item in DEFAULT_INDEXES if item.index_code in set(index_codes))
        summary, details = build_index_health_snapshot(worker_store, definitions)
        _write_index_health_snapshot_disk_cache(summary, details, source_signature, datetime.now(), worker_store)
    finally:
        _safe_unlink(marker_path)
```

Add import near the top of the file:

```python
from etf_trading.research.index_health_snapshot import build_index_health_snapshot
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_state_cache.py -q
```

Expected: PASS, including the new ready/stale/building index health cache tests.

- [ ] **Step 5: Stage files and record the suggested commit command**

Run only if the user explicitly asks for a commit in the execution session:

```powershell
git add src/etf_trading/nicegui_app/state.py tests/test_nicegui_state_cache.py
git commit -m "feat: cache index health snapshot for NiceGUI"
```

---

### Task 5: UI-Neutral View Models and Table Labels

**Files:**
- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Modify: `src/etf_trading/nicegui_app/components/tables.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Produces: `IndexHealthFilters(query: str = "", category: str = "全部分类", trend_status: str = "全部趋势体检", valuation_status: str = "全部估值体检")`
- Produces: `index_health_summary(frame: pd.DataFrame) -> list[MetricTile]`
- Produces: `index_health_rows(frame: pd.DataFrame, filters: IndexHealthFilters | None = None, limit: int = 200) -> list[dict[str, object]]`
- Produces: `index_health_detail_rows(details: pd.DataFrame, index_code: str, detail_kind: str) -> list[dict[str, object]]`
- Produces: `index_health_filter_options(frame: pd.DataFrame, column: str, default_label: str) -> list[str]`

- [ ] **Step 1: Write the failing view-model tests**

Append to `tests/test_nicegui_view_models.py`:

```python
from etf_trading.nicegui_app.view_models import (
    IndexHealthFilters,
    index_health_detail_rows,
    index_health_rows,
    index_health_summary,
)


def _index_health_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": ["000300", "000905"],
            "index_name": ["沪深300", "中证500"],
            "category": ["A股宽基", "A股宽基"],
            "large_trend": ["UP", "RANGE"],
            "medium_trend": ["UP", "DOWN"],
            "small_trend": ["PULLBACK", "BROKEN"],
            "allows_new_position": [True, False],
            "trend_health_status": ["normal", "watch"],
            "valuation_overview_label": ["mid_percentile", "missing"],
            "valuation_health_status": ["complete", "missing_valuation"],
            "latest_date": ["2026-07-03", "2026-07-03"],
            "history_rows": [900, 900],
        }
    )


def _index_health_details_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": ["000300", "000300", "000300"],
            "detail_kind": ["trend", "trend", "valuation"],
            "metric_name": ["large_trend", "momentum_60", "pe_ttm"],
            "metric_label": ["large_trend", "momentum_60", "pe_ttm"],
            "current_value": ["UP", 0.12, 12.5],
            "status": ["normal", "normal", "computed"],
            "reason": ["ok", "60-day momentum", "ok"],
            "display_direction": ["higher_is_better", "higher_is_better", "higher_is_more_expensive"],
            "historical_percentile": [pd.NA, pd.NA, 65.0],
            "window_years": [pd.NA, pd.NA, 3.2],
            "first_date": ["", "", "2023-01-02"],
            "latest_date": ["2026-07-03", "2026-07-03", "2026-07-03"],
            "sample_count": [900, 900, 820],
            "data_source": ["unit", "unit", "unit"],
        }
    )


def test_index_health_summary_counts_complete_and_missing_states():
    metrics = index_health_summary(_index_health_summary_frame())

    assert [metric.label for metric in metrics][:5] == ["指数总数", "趋势可判定", "允许新开仓", "估值完整", "估值缺失"]
    assert [metric.value for metric in metrics][:5] == ["2", "2", "1", "1", "1"]


def test_index_health_rows_filter_without_exposing_composite_scores():
    rows = index_health_rows(_index_health_summary_frame(), IndexHealthFilters(query="300", valuation_status="全部估值体检"))

    assert len(rows) == 1
    assert rows[0]["index_code"] == "000300"
    forbidden = {"综合分", "估值总分", "买卖分", "target_weight"}
    assert forbidden.isdisjoint(rows[0].keys())


def test_index_health_detail_rows_split_trend_and_valuation_tables():
    trend_rows = index_health_detail_rows(_index_health_details_frame(), "000300", "trend")
    valuation_rows = index_health_detail_rows(_index_health_details_frame(), "000300", "valuation")

    assert [row["metric_name"] for row in trend_rows] == ["large_trend", "momentum_60"]
    assert [row["metric_name"] for row in valuation_rows] == ["pe_ttm"]
    assert valuation_rows[0]["historical_percentile"] == 65.0
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py -q
```

Expected: FAIL with missing `IndexHealthFilters`, missing helper functions, or missing labels.

- [ ] **Step 3: Add index health view models**

Modify `src/etf_trading/nicegui_app/view_models.py`:

```python
@dataclass(frozen=True)
class IndexHealthFilters:
    query: str = ""
    category: str = "全部分类"
    trend_status: str = "全部趋势体检"
    valuation_status: str = "全部估值体检"
```

Append helpers:

```python
def index_health_summary(frame: pd.DataFrame) -> list[MetricTile]:
    if frame.empty:
        return [
            MetricTile("指数总数", "0", "warning", "体检池"),
            MetricTile("趋势可判定", "0", "warning", "趋势快照"),
            MetricTile("允许新开仓", "0", "neutral", "门禁"),
            MetricTile("估值完整", "0", "warning", "估值快照"),
            MetricTile("估值缺失", "0", "warning", "缺口"),
            MetricTile("最新快照", "", "neutral", "缓存"),
        ]

    trend_status = frame.get("trend_health_status", pd.Series(dtype=str)).fillna("").astype(str)
    valuation_status = frame.get("valuation_health_status", pd.Series(dtype=str)).fillna("").astype(str)
    latest = frame["latest_date"].dropna().astype(str).max() if "latest_date" in frame and not frame["latest_date"].dropna().empty else ""
    return [
        MetricTile("指数总数", str(len(frame)), "neutral", "体检池"),
        MetricTile("趋势可判定", str(int((trend_status != "missing_history").sum())), "info", "趋势快照"),
        MetricTile("允许新开仓", str(int(frame.get("allows_new_position", pd.Series(dtype=bool)).fillna(False).astype(bool).sum())), "success", "门禁"),
        MetricTile("估值完整", str(int((valuation_status == "complete").sum())), "success", "估值快照"),
        MetricTile("估值缺失", str(int((valuation_status == "missing_valuation").sum())), "warning", "缺口"),
        MetricTile("最新快照", latest, "info", "缓存"),
    ]


def index_health_rows(
    frame: pd.DataFrame,
    filters: IndexHealthFilters | None = None,
    limit: int = 200,
) -> list[dict[str, object]]:
    if frame.empty:
        return []
    filters = filters or IndexHealthFilters()
    data = frame.copy()
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
    if filters.category not in {"", "全部", "全部分类"} and "category" in data:
        data = data[data["category"].fillna("").astype(str) == filters.category]
    if filters.trend_status not in {"", "全部", "全部趋势体检"} and "trend_health_status" in data:
        data = data[data["trend_health_status"].fillna("").astype(str) == filters.trend_status]
    if filters.valuation_status not in {"", "全部", "全部估值体检"} and "valuation_health_status" in data:
        data = data[data["valuation_health_status"].fillna("").astype(str) == filters.valuation_status]
    data = data.sort_values(["allows_new_position", "index_code"], ascending=[False, True])
    return data.head(limit).fillna("").to_dict("records")


def index_health_detail_rows(details: pd.DataFrame, index_code: str, detail_kind: str) -> list[dict[str, object]]:
    if details.empty:
        return []
    data = details.copy()
    data = data[(data["index_code"].astype(str) == str(index_code)) & (data["detail_kind"].astype(str) == str(detail_kind))]
    return data.fillna("").to_dict("records")


def index_health_filter_options(frame: pd.DataFrame, column: str, default_label: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return [default_label]
    values = sorted({str(value) for value in frame[column].dropna().astype(str).tolist() if str(value).strip()})
    return [default_label, *values]
```

- [ ] **Step 4: Add display labels for the new fields and enums**

Modify `src/etf_trading/nicegui_app/components/tables.py` by extending `COLUMN_LABELS`:

```python
    "trend_health_status": "趋势体检",
    "trend_health_reason": "趋势说明",
    "valuation_overview_label": "估值总览",
    "valuation_health_status": "估值体检",
    "valuation_health_reason": "估值说明",
    "valuation_latest_date": "估值最新日期",
    "valuation_coverage_years": "估值覆盖年数",
    "valuation_primary_source": "估值来源",
    "detail_kind": "明细类型",
    "metric_name": "指标代码",
    "metric_label": "指标",
    "current_value": "当前值",
    "display_direction": "方向",
    "historical_percentile": "历史分位",
    "window_years": "覆盖年数",
    "first_date": "起始日期",
    "sample_count": "样本数",
    "data_source": "数据源",
    "reason": "说明",
```

Extend `VALUE_LABELS`:

```python
    "normal": "正常",
    "watch": "观察",
    "missing_valuation": "估值缺失",
    "partial": "部分完整",
    "complete": "完整",
    "mid_percentile": "中分位",
    "low_percentile": "低分位",
    "high_percentile": "高分位",
    "missing_field": "字段缺失",
    "computed": "已计算",
    "trend": "趋势",
    "valuation": "估值",
```

Extend `COMPACT_COLUMN_WIDTHS`:

```python
    "trend_health_status": 96,
    "valuation_overview_label": 96,
    "valuation_health_status": 96,
    "valuation_coverage_years": 96,
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Stage files and record the suggested commit command**

Run only if the user explicitly asks for a commit in the execution session:

```powershell
git add src/etf_trading/nicegui_app/view_models.py src/etf_trading/nicegui_app/components/tables.py tests/test_nicegui_view_models.py
git commit -m "feat: add index health view models and labels"
```

---

### Task 6: Add Navigation and Render the `指数体检` Page from Cache

**Files:**
- Modify: `src/etf_trading/nicegui_app/navigation.py`
- Modify: `src/etf_trading/nicegui_app/pages/market.py`
- Test: `tests/test_nicegui_navigation.py`
- Test: `tests/test_nicegui_app_import.py`

**Interfaces:**
- Consumes: `load_index_health_snapshot_cached(parquet_store, definitions=DEFAULT_INDEXES, force_refresh=False) -> IndexHealthSnapshotCacheResult`
- Consumes: `invalidate_index_health_snapshot_cache(parquet_store=None) -> None`
- Consumes: `index_health_summary(frame) -> list[MetricTile]`
- Consumes: `index_health_rows(frame, filters) -> list[dict[str, object]]`
- Consumes: `index_health_detail_rows(details, index_code, detail_kind) -> list[dict[str, object]]`
- Updates: `pages.market.render()` routes `section == "指数体检"` to `_render_index_health(snapshot, parquet_store)`

- [ ] **Step 1: Update the failing navigation and page render tests**

Modify `tests/test_nicegui_navigation.py`:

```python
def test_nicegui_sections_keep_market_and_etf_boundaries():
    sections_by_slug = {page.slug: list(page.sections) for page in NICEGUI_PAGES}

    assert sections_by_slug["market"] == ["市场总览", "指数体检", "指数买卖参考", "指数K线"]
    assert sections_by_slug["etf-data"] == ["ETF总览", "原子指标", "ETF行情", "搜索加入", "每日计算池", "指数样本池"]
    assert sections_by_slug["maintenance"] == ["数据总览", "缺口明细", "补齐任务", "日志与设置"]
    assert "ETF行情" not in sections_by_slug["market"]
    assert "原子指标" not in sections_by_slug["market"]
```

Append to `tests/test_nicegui_app_import.py`:

```python
def test_index_health_page_uses_cached_snapshot(monkeypatch):
    from etf_trading.nicegui_app.pages import market
    from etf_trading.nicegui_app.state import IndexHealthSnapshotCacheResult
    from etf_trading.nicegui_app.view_models import PlatformSnapshot

    calls = []
    rendered_rows = []

    class FakeElement:
        def __init__(self, value=None, options=None):
            self.value = value
            self.options = options or []

        def classes(self, value):
            return self

        def props(self, value):
            return self

        def on_value_change(self, handler):
            return self

        def on(self, *args, **kwargs):
            return self

        def clear(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def input(self, *args, **kwargs):
            return FakeElement(value="")

        def select(self, options, value=None, label=None):
            return FakeElement(value=value, options=options)

        def button(self, *args, **kwargs):
            return FakeElement()

        def checkbox(self, *args, **kwargs):
            return FakeElement(value=False)

        def label(self, *args, **kwargs):
            return FakeElement()

        def table(self, columns, rows, row_key=None, pagination=None):
            rendered_rows.extend(rows)
            return FakeElement()

        def notify(self, *args, **kwargs):
            return None

    summary = pd.DataFrame(
        {
            "index_code": ["000300"],
            "index_name": ["沪深300"],
            "category": ["A股宽基"],
            "large_trend": ["UP"],
            "medium_trend": ["UP"],
            "small_trend": ["PULLBACK"],
            "allows_new_position": [True],
            "trend_health_status": ["normal"],
            "valuation_overview_label": ["mid_percentile"],
            "valuation_health_status": ["complete"],
            "latest_date": ["2026-07-03"],
            "history_rows": [900],
        }
    )
    details = pd.DataFrame(
        {
            "index_code": ["000300", "000300"],
            "detail_kind": ["trend", "valuation"],
            "metric_name": ["large_trend", "pe_ttm"],
            "metric_label": ["large_trend", "pe_ttm"],
            "current_value": ["UP", 12.5],
            "status": ["normal", "computed"],
            "reason": ["ok", "ok"],
            "display_direction": ["higher_is_better", "higher_is_more_expensive"],
            "historical_percentile": [pd.NA, 65.0],
            "window_years": [pd.NA, 3.2],
            "first_date": ["", "2023-01-02"],
            "latest_date": ["2026-07-03", "2026-07-03"],
            "sample_count": [900, 820],
            "data_source": ["unit", "unit"],
        }
    )

    def fake_cached(parquet_store, definitions=None, *, force_refresh=False):
        calls.append(force_refresh)
        return IndexHealthSnapshotCacheResult(summary=summary, details=details, status="ready", generated_at=datetime(2026, 7, 6, 10, 0, 0))

    monkeypatch.setattr(market, "ui", FakeUi())
    monkeypatch.setattr(market, "load_index_health_snapshot_cached", fake_cached, raising=False)
    monkeypatch.setattr(
        market,
        "build_index_health_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sync snapshot builder should not run in page render")),
        raising=False,
    )
    snapshot = PlatformSnapshot(
        master=pd.DataFrame(),
        watchlist=pd.DataFrame(),
        index_summary=summary,
        universe=pd.DataFrame(),
        gaps=pd.DataFrame(),
        coverage=pd.DataFrame(),
        generated_at=datetime(2026, 7, 6, 10, 0, 0),
    )

    market._render_index_health(snapshot, object())

    assert calls == [False]
    assert rendered_rows[0]["index_code"] == "000300"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_app_import.py -q
```

Expected: FAIL because `指数体检` is not in navigation and `_render_index_health` does not exist yet.

- [ ] **Step 3: Add the new section to market navigation**

Modify `src/etf_trading/nicegui_app/navigation.py`:

```python
    NicePageSpec(
        slug="market",
        label="市场地图",
        caption="观察指数和市场参与状态，不承载 ETF 行情下钻。",
        sections=("市场总览", "指数体检", "指数买卖参考", "指数K线"),
    ),
```

- [ ] **Step 4: Render the cached `指数体检` page**

Modify imports in `src/etf_trading/nicegui_app/pages/market.py`:

```python
from etf_trading.nicegui_app.state import (
    index_chart_payload,
    invalidate_index_health_snapshot_cache,
    load_index_health_snapshot_cached,
)
from etf_trading.nicegui_app.view_models import (
    IndexHealthFilters,
    PlatformSnapshot,
    code_from_option,
    current_ui_audit_findings,
    index_choice_options,
    index_health_detail_rows,
    index_health_filter_options,
    index_health_rows,
    index_health_summary,
    market_overview,
)
```

Update `render()`:

```python
def render(snapshot: PlatformSnapshot, section: str, parquet_store=None) -> None:
    if section == "市场总览":
        _render_overview(snapshot)
    elif section == "指数体检":
        _render_index_health(snapshot, parquet_store)
    elif section == "指数买卖参考":
        _render_index_reference(snapshot)
    else:
        _render_index_chart(snapshot, parquet_store)
```

Add the cached page renderer:

```python
def _render_index_health(snapshot: PlatformSnapshot, parquet_store) -> None:
    if parquet_store is None:
        empty_state("暂无指数体检", "当前页面没有可用历史数据存储。")
        return

    try:
        cache_result = load_index_health_snapshot_cached(parquet_store)
        holder = {"summary": cache_result.summary, "details": cache_result.details, "result": cache_result}
    except Exception as exc:  # noqa: BLE001
        empty_state("指数体检快照生成失败", str(exc))
        return

    status_area = ui.row().classes("w-full")
    metric_area = ui.row().classes("w-full gap-2")
    table_area = ui.column().classes("w-full")
    detail_area = ui.column().classes("w-full gap-2")
    categories = index_health_filter_options(holder["summary"], "category", "全部分类")
    trend_statuses = index_health_filter_options(holder["summary"], "trend_health_status", "全部趋势体检")
    valuation_statuses = index_health_filter_options(holder["summary"], "valuation_health_status", "全部估值体检")
    index_options = index_choice_options(holder["summary"])

    with ui.row().classes("workbench-toolbar w-full"):
        query = ui.input("代码 / 名称 / 分类").props("dense outlined clearable debounce=250").classes("w-72")
        category = ui.select(categories, value=categories[0], label="分类").props("dense outlined").classes("w-40")
        trend_status = ui.select(trend_statuses, value=trend_statuses[0], label="趋势体检").props("dense outlined").classes("w-40")
        valuation_status = ui.select(valuation_statuses, value=valuation_statuses[0], label="估值体检").props("dense outlined").classes("w-40")
        selected = ui.select(index_options, value=index_options[0] if index_options else None, label="查看指数").props("dense outlined").classes("w-72")
        ui.button("刷新快照", icon="refresh", on_click=lambda: reload_snapshot()).props("dense outline")

    def render_status() -> None:
        status_area.clear()
        result = holder["result"]
        if result.status == "ready":
            return
        with status_area:
            if result.status == "stale":
                ui.label("指数体检快照正在后台刷新，当前先展示上一版缓存。").classes("text-xs text-amber-700")
            elif result.status == "building":
                ui.label("指数体检快照正在后台生成，稍后再点刷新快照即可查看。").classes("text-xs text-blue-700")
            elif result.status == "failed":
                ui.label(f"指数体检快照后台生成失败：{result.message}").classes("text-xs text-red-700")

    def render_metrics() -> None:
        metric_area.clear()
        with metric_area:
            for metric in index_health_summary(holder["summary"]):
                _metric(metric.label, metric.value, metric.detail)

    def current_filters() -> IndexHealthFilters:
        return IndexHealthFilters(
            query=str(query.value or ""),
            category=str(category.value or "全部分类"),
            trend_status=str(trend_status.value or "全部趋势体检"),
            valuation_status=str(valuation_status.value or "全部估值体检"),
        )

    def render_table() -> None:
        rows = index_health_rows(holder["summary"], current_filters())
        table_area.clear()
        with table_area:
            if rows:
                ui.table(columns=table_columns(rows, compact=True), rows=table_rows(rows), pagination=15).classes("workbench-data-table w-full")
            else:
                empty_state("没有匹配指数体检", "换一个筛选条件，或先补齐指数历史与估值缓存。")

    def render_details() -> None:
        detail_area.clear()
        index_code = code_from_option(str(selected.value or ""))
        with detail_area:
            if not index_code:
                empty_state("暂无指数体检详情", "请选择一个指数。")
                return
            trend_rows = index_health_detail_rows(holder["details"], index_code, "trend")
            valuation_rows = index_health_detail_rows(holder["details"], index_code, "valuation")
            ui.label(f"趋势原子指标：{index_code}").classes("text-sm font-semibold text-slate-700")
            if trend_rows:
                ui.table(columns=table_columns(trend_rows, compact=True), rows=table_rows(trend_rows), pagination=12).classes("workbench-data-table w-full")
            else:
                empty_state("暂无趋势原子指标", "当前缓存中没有这个指数的趋势明细。")
            ui.label(f"估值原子指标：{index_code}").classes("text-sm font-semibold text-slate-700")
            if valuation_rows:
                ui.table(columns=table_columns(valuation_rows, compact=True), rows=table_rows(valuation_rows), pagination=12).classes("workbench-data-table w-full")
            else:
                empty_state("暂无估值原子指标", "当前缓存中没有这个指数的估值明细。")

    def reload_snapshot() -> None:
        try:
            should_force_refresh = holder["result"].status == "ready"
            invalidate_index_health_snapshot_cache(parquet_store)
            cache_result = load_index_health_snapshot_cached(parquet_store, force_refresh=should_force_refresh)
            holder["summary"] = cache_result.summary
            holder["details"] = cache_result.details
            holder["result"] = cache_result
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"刷新指数体检失败：{exc}", type="negative")
            return
        render_status()
        render_metrics()
        render_table()
        render_details()
        if cache_result.status in {"building", "stale"}:
            ui.notify("指数体检快照已转入后台刷新，页面会继续保持可用", type="info")
        elif cache_result.status == "failed":
            ui.notify("指数体检快照生成失败，请查看页面提示", type="negative")
        else:
            ui.notify("指数体检快照已刷新", type="positive")

    query.on_value_change(lambda event: render_table())
    category.on_value_change(lambda event: render_table())
    trend_status.on_value_change(lambda event: render_table())
    valuation_status.on_value_change(lambda event: render_table())
    selected.on_value_change(lambda event: render_details())
    render_status()
    render_metrics()
    render_table()
    render_details()
    _render_audit("market")
```

- [ ] **Step 5: Run the focused page tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_app_import.py -q
```

Expected: PASS.

- [ ] **Step 6: Stage files and record the suggested commit command**

Run only if the user explicitly asks for a commit in the execution session:

```powershell
git add src/etf_trading/nicegui_app/navigation.py src/etf_trading/nicegui_app/pages/market.py tests/test_nicegui_navigation.py tests/test_nicegui_app_import.py
git commit -m "feat: add cached index health page"
```

---

### Task 7: Verification, Regression, and Task Memory

**Files:**
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: all prior tasks
- Produces: verification evidence and a durable memory note for future work

- [ ] **Step 1: Run the focused feature test suite**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_index_valuations.py tests/test_akshare_provider_fallback.py tests/test_index_valuation_service.py tests/test_index_health_snapshot.py tests/test_nicegui_state_cache.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_nicegui_app_import.py -q --basetemp pytest-tmp-index-health-focused
```

Expected: PASS.

- [ ] **Step 2: Run a forbidden-output scan**

Run:

```powershell
rg -n "综合分|估值总分|买卖分|weighted_score|target_weight|BUY|SELL|REDUCE|买入|卖出|减仓" src\etf_trading\data\index_valuations.py src\etf_trading\data\index_valuation_service.py src\etf_trading\research\index_health_snapshot.py src\etf_trading\nicegui_app\view_models.py src\etf_trading\nicegui_app\pages\market.py tests\test_index_health_snapshot.py tests\test_nicegui_view_models.py
```

Expected: production files contain no forbidden composite/advice outputs. Test files may mention them only in absence assertions if needed.

- [ ] **Step 3: Run nearby regression tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests/test_storage_and_services.py tests/test_nicegui_charts.py tests/test_nicegui_state_cache.py -q --basetemp pytest-tmp-index-health-regression
```

Expected: PASS.

- [ ] **Step 4: Append task memory**

Append to `docs/task-memory.md`:

```markdown
## 2026-07-06 - Implement index health snapshot

- Summary: Added raw index valuation cache, page-ready `指数体检` snapshot cache, and NiceGUI market diagnostics with separate trend and valuation detail tables.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_index_valuations.py tests/test_akshare_provider_fallback.py tests/test_index_valuation_service.py tests/test_index_health_snapshot.py tests/test_nicegui_state_cache.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_nicegui_app_import.py -q --basetemp pytest-tmp-index-health-focused` passed; `.venv-win\Scripts\python.exe -m pytest tests/test_storage_and_services.py tests/test_nicegui_charts.py tests/test_nicegui_state_cache.py -q --basetemp pytest-tmp-index-health-regression` passed.
- Watch out next time:
  - Keep `指数买卖参考` as the gate view only; do not merge the diagnostic tables back into it.
  - Keep page render cache-only; all heavy snapshot work belongs in `research/*` and `nicegui_app/state.py`.
  - Show missing/insufficient valuation rows explicitly instead of backfilling fake values.
```

- [ ] **Step 5: Stage files and record the suggested commit command**

Run only if the user explicitly asks for a commit in the execution session:

```powershell
git add docs/task-memory.md
git commit -m "docs: record index health snapshot work"
```

---

## Self-Review

**Spec coverage:**
The plan covers the approved navigation split (`市场总览`, `指数体检`, `指数买卖参考`, `指数K线`), the raw valuation cache layer, the page-ready snapshot cache layer, separate trend and valuation detail tables, valuation overview tags, local-cache-only page rendering, and the `ready/stale/building/failed` behavior.

**Placeholder scan:**
This plan contains concrete file paths, commands, test cases, and code blocks for each task. It does not rely on deferred implementation notes or cross-task shorthand.

**Type consistency:**
`build_index_health_snapshot()` returns `(summary, details)` and that same pair flows through `IndexHealthSnapshotCacheResult`, `index_health_rows()`, and `index_health_detail_rows()`. Raw valuation history lives in `ParquetStore.read_index_valuations()` and is consumed by the research layer only, not by the page.
