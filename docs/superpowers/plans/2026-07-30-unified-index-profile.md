# Unified Index Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only unified index profile that combines Tushare official valuation history with price-based trend, momentum, risk, activity, event, and quality atoms in one readable NiceGUI dialog.

**Architecture:** Official valuation history and index price history remain separate Parquet inputs. A maintenance-owned snapshot builder aligns both sources to the latest price observation date and atomically publishes one summary/details snapshot; the market page only reads and formats that snapshot. Unsupported valuation coverage degrades only the valuation group, never the price-derived groups.

**Tech Stack:** Python 3.11, pandas, Tushare Pro, Parquet, SQLite, NiceGUI, pytest, browser-based responsive QA.

## Global Constraints

- Initial official valuation mappings are exactly `000001 -> 000001.SH`, `000016 -> 000016.SH`, `000300 -> 000300.SH`, `000905 -> 000905.SH`, `399001 -> 399001.SZ`, and `399006 -> 399006.SZ`.
- Tushare token is runtime-only and must never enter configuration files, caches, logs, task results, test output, or UI text.
- `index_dailybasic` has no AkShare fallback and unsupported indexes get no synthetic valuation cache.
- PE-TTM and PB use deterministic mid-rank percentiles over 3/5/10 calendar-year windows with exact minimum valid sample counts of 500/900/1800.
- Non-positive, non-finite, and non-numeric PE/PE-TTM/PB observations do not participate in percentile calculations.
- The snapshot uses the latest price trade date and the latest valuation record not later than that date; valuation lag greater than 5 price trading days is stale.
- No composite score, ranking, target price, position advice, buy/sell signal, component-derived valuation, or market-breadth calculation.
- Opening, refreshing, filtering, or switching tabs in the market page must not fetch external data, calculate atoms, or write caches.
- The dialog width is `min(1180px, 92vw)` and all new styles remain under `index-profile-*`.
- The five dialog tabs are exactly `画像总览`, `估值详情`, `趋势与风险`, `全部指标`, and `数据质量`.
- Keep unrelated user changes untouched. Each task stages only the files listed in that task.

---

## File Structure

- Modify `src/etf_trading/data/provider.py`: add the optional official-index-valuation provider capability.
- Modify `src/etf_trading/data/providers/tushare_provider.py`: call and normalize `index_dailybasic`.
- Modify `src/etf_trading/data/providers/fallback_provider.py`: delegate official valuations to Tushare without AkShare fallback.
- Modify `src/etf_trading/data/index_valuations.py`: define official mappings and extend the canonical valuation schema.
- Create `src/etf_trading/data/index_valuation_service.py`: own full/incremental valuation synchronization and merge rules.
- Create `src/etf_trading/research/index_valuation_atoms.py`: calculate aligned valuation facts, percentiles, bands, and valuation events.
- Modify `src/etf_trading/research/index_health_snapshot.py`: add price atoms and merge valuation atoms into one snapshot.
- Modify `src/etf_trading/nicegui_app/state.py`: include valuation files in signatures and publish schema version 3 safely.
- Modify `src/etf_trading/nicegui_app/maintenance_tasks.py`: persist official valuation synchronization and unified snapshot rebuilds.
- Modify `src/etf_trading/nicegui_app/pages/maintenance.py`: expose the explicit synchronization action.
- Modify `src/etf_trading/nicegui_app/view_models.py`: produce the five-tab, read-only profile model.
- Modify `src/etf_trading/nicegui_app/pages/market.py`: render the approved B layout without calculation or networking.
- Modify `src/etf_trading/nicegui_app/theme.py`: add scoped desktop/mobile profile styles and remove ladder dependence.
- Modify `docs/task-memory.md`: record verified behavior, commands, and reusable cautions.

---

### Task 1: Official Valuation Provider Contract

**Files:**
- Modify: `src/etf_trading/data/provider.py`
- Modify: `src/etf_trading/data/index_valuations.py`
- Modify: `src/etf_trading/data/providers/tushare_provider.py`
- Modify: `src/etf_trading/data/providers/fallback_provider.py`
- Test: `tests/test_index_valuations.py`
- Test: `tests/test_tushare_provider.py`
- Test: `tests/test_primary_fallback_provider.py`

**Interfaces:**
- Produces: `OFFICIAL_INDEX_VALUATION_TS_CODES: dict[str, str]`
- Produces: `DataProvider.fetch_index_official_valuations(index_code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame`
- Produces canonical columns including `total_mv`, `float_mv`, `total_share`, `float_share`, `free_share`, `turnover_rate`, and `turnover_rate_f`.

- [ ] **Step 1: Write failing provider and schema tests**

```python
def test_index_dailybasic_normalizes_all_official_fields():
    pro = _FakePro({"index_dailybasic": pd.DataFrame({
        "ts_code": ["000300.SH"],
        "trade_date": ["20260729"],
        "total_mv": [51_000_000.0],
        "float_mv": [42_000_000.0],
        "total_share": [3_000_000.0],
        "float_share": [2_500_000.0],
        "free_share": [1_800_000.0],
        "turnover_rate": [0.27],
        "turnover_rate_f": [0.45],
        "pe": [11.90],
        "pe_ttm": [11.60],
        "pb": [1.24],
    })})
    provider = TushareProvider(ProviderSettings(token="test", attempts=1), pro_client=pro)

    result = provider.fetch_index_official_valuations("000300", "2026-07-01", "2026-07-29")

    assert pro.calls[0][0] == "index_dailybasic"
    assert pro.calls[0][2]["ts_code"] == "000300.SH"
    assert result.loc[0, ["index_code", "pe_static", "pe_ttm", "pb", "turnover_rate", "data_source"]].to_dict() == {
        "index_code": "000300",
        "pe_static": 11.90,
        "pe_ttm": 11.60,
        "pb": 1.24,
        "turnover_rate": 0.27,
        "data_source": "tushare_index_dailybasic",
    }


def test_official_valuation_rejects_unmapped_index_without_fallback():
    primary = _Provider(ProviderCapabilityError("unsupported"))
    fallback = _Provider(AssertionError("fallback must not be called"))
    provider = PrimaryFallbackProvider(primary, fallback)

    with pytest.raises(ProviderCapabilityError, match="unsupported"):
        provider.fetch_index_official_valuations("801010", "2026-01-01", "2026-07-29")

    assert provider.drain_notices() == ()
```

Extend the existing `_Provider` test double with:

```python
def fetch_index_official_valuations(self, index_code, start_date, end_date):
    return self._call()
```

- [ ] **Step 2: Run the provider tests to verify RED**

Run:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_index_valuations.py tests\test_tushare_provider.py tests\test_primary_fallback_provider.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-provider-red
```

Expected: FAIL because the capability, official mapping, and canonical fields do not exist.

- [ ] **Step 3: Implement the provider contract and normalization**

Add to `index_valuations.py`:

```python
OFFICIAL_INDEX_VALUATION_TS_CODES = {
    "000001": "000001.SH",
    "000016": "000016.SH",
    "000300": "000300.SH",
    "000905": "000905.SH",
    "399001": "399001.SZ",
    "399006": "399006.SZ",
}

INDEX_VALUATION_COLUMNS = [
    "index_code", "trade_date",
    "pe_ttm", "pe_static", "pb", "ps", "dividend_yield",
    "earnings_yield", "bond_yield_10y", "erp", "roe", "payout_ratio", "forward_pe",
    "total_mv", "float_mv", "total_share", "float_share", "free_share",
    "turnover_rate", "turnover_rate_f",
    "data_source", "source_quality", "source_updated_at",
]

NUMERIC_VALUATION_COLUMNS = [
    "pe_ttm", "pe_static", "pb", "ps", "dividend_yield", "earnings_yield",
    "bond_yield_10y", "erp", "roe", "payout_ratio", "forward_pe",
    "total_mv", "float_mv", "total_share", "float_share", "free_share",
    "turnover_rate", "turnover_rate_f",
]
```

Import `ProviderCapabilityError` from `etf_trading.data.provider_runtime`, then add a non-abstract default method to `DataProvider`:

```python
def fetch_index_official_valuations(
    self,
    index_code: str,
    start_date: date | str,
    end_date: date | str,
) -> pd.DataFrame:
    raise ProviderCapabilityError(f"official index valuation is unsupported: {index_code}")
```

Implement in `TushareProvider`:

```python
def fetch_index_official_valuations(self, index_code, start_date, end_date):
    code = str(index_code).zfill(6)
    ts_code = OFFICIAL_INDEX_VALUATION_TS_CODES.get(code)
    if ts_code is None:
        raise ProviderCapabilityError(f"official index valuation is unsupported: {code}")
    raw = self._query(
        "index_dailybasic",
        fields=(
            "ts_code,trade_date,total_mv,float_mv,total_share,float_share,free_share,"
            "turnover_rate,turnover_rate_f,pe,pe_ttm,pb"
        ),
        ts_code=ts_code,
        start_date=_fmt_date(start_date),
        end_date=_fmt_date(end_date),
    )
    return finalize_index_valuation_frame(
        raw.rename(columns={"pe": "pe_static"}),
        code,
        "tushare_index_dailybasic",
        "official",
    )
```

`PrimaryFallbackProvider.fetch_index_official_valuations` must call `self.primary` directly; it must not call `_dispatch`.

- [ ] **Step 4: Run the provider tests to verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Commit the provider capability**

```powershell
git add src/etf_trading/data/provider.py src/etf_trading/data/index_valuations.py src/etf_trading/data/providers/tushare_provider.py src/etf_trading/data/providers/fallback_provider.py tests/test_index_valuations.py tests/test_tushare_provider.py tests/test_primary_fallback_provider.py
git commit -m "feat: fetch official index valuation history"
```

---

### Task 2: Idempotent Official Valuation Synchronization

**Files:**
- Create: `src/etf_trading/data/index_valuation_service.py`
- Test: `tests/test_index_valuation_service.py`

**Interfaces:**
- Consumes: `DataProvider.fetch_index_official_valuations(...)`
- Consumes: `ParquetStore.read_index_valuations(index_code)` and `write_index_valuations(index_code, frame)`
- Produces: `OfficialIndexValuationProgress(done: int, total: int, index_code: str, status: str)`
- Produces: `OfficialIndexValuationSyncService.sync_all(through: date | str, on_progress: Callable[[OfficialIndexValuationProgress], None] | None = None) -> pd.DataFrame`

- [ ] **Step 1: Write failing full, incremental, and failure-preservation tests**

```python
def _valuation_rows(dates):
    return finalize_index_valuation_frame(
        pd.DataFrame({
            "trade_date": dates,
            "pe_ttm": [11.6] * len(dates),
            "pe_static": [11.9] * len(dates),
            "pb": [1.24] * len(dates),
        }),
        "000300",
        "tushare_index_dailybasic",
        "official",
    )


class FakeOfficialProvider:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def fetch_index_official_valuations(self, code, start, end):
        self.calls.append((str(code), pd.Timestamp(start).strftime("%Y-%m-%d"), pd.Timestamp(end).strftime("%Y-%m-%d")))
        return self.frames.get(str(code), pd.DataFrame()).copy()


class FailingOfficialProvider:
    def __init__(self, message):
        self.message = message

    def fetch_index_official_valuations(self, code, start, end):
        raise ProviderCallError(self.message, category="permission")


def test_sync_all_initializes_then_increments_without_duplicates(tmp_path):
    provider = FakeOfficialProvider({
        "000300": _valuation_rows(["2026-07-28", "2026-07-29"]),
    })
    store = ParquetStore(tmp_path / "parquet")
    service = OfficialIndexValuationSyncService(provider, store, index_codes=("000300",))

    first = service.sync_all("2026-07-29")
    second = service.sync_all("2026-07-29")

    assert first.loc[0, "status"] == "INITIALIZED"
    assert second.loc[0, "status"] == "CURRENT"
    assert store.read_index_valuations("000300")["trade_date"].nunique() == 2
    assert provider.calls == [("000300", "2004-01-01", "2026-07-29")]


def test_sync_failure_preserves_previous_successful_cache(tmp_path):
    store = ParquetStore(tmp_path / "parquet")
    existing = _valuation_rows(["2026-07-28"])
    store.write_index_valuations("000300", existing)
    service = OfficialIndexValuationSyncService(
        FailingOfficialProvider("permission denied token=secret"),
        store,
        index_codes=("000300",),
        secrets=("secret",),
    )

    result = service.sync_all("2026-07-29")

    assert result.loc[0, "status"] == "FAILED"
    assert "secret" not in result.loc[0, "message"]
    pd.testing.assert_frame_equal(store.read_index_valuations("000300"), existing)
```

- [ ] **Step 2: Run the service tests to verify RED**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_index_valuation_service.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-sync-red
```

Expected: FAIL with `ModuleNotFoundError` for `index_valuation_service`.

- [ ] **Step 3: Implement synchronization and merge rules**

```python
@dataclass(frozen=True)
class OfficialIndexValuationProgress:
    done: int
    total: int
    index_code: str
    status: str


class OfficialIndexValuationSyncService:
    def __init__(self, provider, parquet_store, *, index_codes=None, secrets=()):
        self.provider = provider
        self.parquet_store = parquet_store
        self.index_codes = tuple(index_codes or OFFICIAL_INDEX_VALUATION_TS_CODES)
        self.secrets = tuple(value for value in secrets if value)

    def sync_all(self, through, on_progress=None):
        through_date = pd.Timestamp(through).normalize()
        results = []
        for done, code in enumerate(self.index_codes, start=1):
            existing = self.parquet_store.read_index_valuations(code)
            latest = pd.to_datetime(existing.get("trade_date"), errors="coerce").max() if not existing.empty else pd.NaT
            if pd.notna(latest) and latest.normalize() >= through_date:
                status, fetched, message = "CURRENT", pd.DataFrame(), "本地估值已是最新"
            else:
                start = pd.Timestamp("2004-01-01") if pd.isna(latest) else latest.normalize() + pd.Timedelta(days=1)
                try:
                    fetched = self.provider.fetch_index_official_valuations(code, start, through_date)
                    if fetched.empty:
                        status, message = "EMPTY", "接口未返回新增估值"
                    else:
                        merged = pd.concat([existing, fetched], ignore_index=True)
                        merged = merged.drop_duplicates(["index_code", "trade_date"], keep="last").sort_values("trade_date")
                        self.parquet_store.write_index_valuations(code, merged.reset_index(drop=True))
                        status = "INITIALIZED" if existing.empty else "UPDATED"
                        message = f"写入 {len(fetched)} 行估值"
                except Exception as exc:
                    fetched = pd.DataFrame()
                    status = "FAILED"
                    message = redact_provider_text(exc, secrets=self.secrets)
            results.append({"index_code": code, "status": status, "fetched_rows": len(fetched), "message": message})
            if on_progress:
                on_progress(OfficialIndexValuationProgress(done, len(self.index_codes), code, status))
        return pd.DataFrame(results)
```

Do not write an empty response. Validate fetched frames contain `trade_date` and at least one of `pe_static`, `pe_ttm`, or `pb` before merging.

- [ ] **Step 4: Run the service tests to verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Commit the synchronization service**

```powershell
git add src/etf_trading/data/index_valuation_service.py tests/test_index_valuation_service.py
git commit -m "feat: sync official index valuation cache"
```

---

### Task 3: Durable Valuation Maintenance Task

**Files:**
- Modify: `src/etf_trading/nicegui_app/maintenance_tasks.py`
- Modify: `src/etf_trading/nicegui_app/pages/maintenance.py`
- Modify: `src/etf_trading/nicegui_app/components/tables.py`
- Test: `tests/test_nicegui_maintenance_task_runner.py`
- Test: `tests/test_nicegui_maintenance_tasks.py`
- Test: `tests/test_nicegui_table_display.py`

**Interfaces:**
- Produces: `OFFICIAL_INDEX_VALUATION_SYNC_TASK_TYPE = "official_index_valuation_sync"`
- Produces: `OfficialIndexValuationMaintenanceRunner.start(through: str) -> MaintenanceTaskRun`
- Consumes: `OfficialIndexValuationSyncService.sync_all(...)`

- [ ] **Step 1: Write failing runner and page-action tests**

```python
class _FakeOfficialValuationSyncService:
    def sync_all(self, through, on_progress=None):
        if on_progress is not None:
            on_progress(OfficialIndexValuationProgress(1, 1, "000300", "UPDATED"))
        return pd.DataFrame([
            {"index_code": "000300", "status": "UPDATED", "fetched_rows": 1, "message": "写入 1 行估值"},
        ])


def test_official_valuation_runner_persists_progress_and_result(monkeypatch, tmp_path):
    sqlite_store = SQLiteStore(tmp_path / "etf.sqlite")
    sqlite_store.initialize_schema()
    runner = maintenance_tasks.OfficialIndexValuationMaintenanceRunner(
        sqlite_store,
        ParquetStore(tmp_path / "parquet"),
        service_factory=_FakeOfficialValuationSyncService,
    )
    async def run_inline(callback):
        return callback()
    monkeypatch.setattr(maintenance_tasks.run, "io_bound", run_inline)
    task = sqlite_store.create_maintenance_task_run("official_index_valuation_sync", progress_total=6)

    asyncio.run(runner._run(task.task_id, "2026-07-29"))

    persisted = sqlite_store.get_maintenance_task_run(task.task_id)
    assert persisted.state == "success"
    assert json.loads(persisted.result_json)[0]["status"] == "UPDATED"


def test_catalog_panel_exposes_explicit_official_valuation_sync():
    source = inspect.getsource(maintenance._render_catalog_index_tasks)
    assert '"同步官方指数估值"' in source
    assert "_start_official_index_valuation_sync_task" in source
```

- [ ] **Step 2: Run maintenance tests to verify RED**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_maintenance_task_runner.py tests\test_nicegui_maintenance_tasks.py tests\test_nicegui_table_display.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-maintenance-red
```

Expected: FAIL because the runner, task type, trigger, and localized statuses are absent.

- [ ] **Step 3: Implement the durable runner and explicit UI action**

The runner mirrors existing interruption and active-key behavior:

```python
OFFICIAL_INDEX_VALUATION_SYNC_TASK_TYPE = "official_index_valuation_sync"


class OfficialIndexValuationMaintenanceRunner:
    def start(self, through: str) -> MaintenanceTaskRun:
        self.reconcile_interrupted()
        running = self.store.get_running_maintenance_task_run(OFFICIAL_INDEX_VALUATION_SYNC_TASK_TYPE)
        if running is not None:
            return running
        task = self.store.create_maintenance_task_run(
            OFFICIAL_INDEX_VALUATION_SYNC_TASK_TYPE,
            progress_total=len(OFFICIAL_INDEX_VALUATION_TS_CODES),
        )
        _ACTIVE_OFFICIAL_VALUATION_TASK_KEYS.add(self._task_key(task.task_id))
        background_tasks.create(self._run(task.task_id, through), name=f"official-index-valuation-{task.task_id}")
        return task
```

Persist per-index progress, JSON results, and redacted failure messages. Add the runner to restored/latest task selection. Render one outlined `同步官方指数估值` button beside `重建指数原子指标`. Localize `INITIALIZED`, `UPDATED`, `CURRENT`, `EMPTY`, and `FAILED` in task-result tables.

- [ ] **Step 4: Run maintenance tests to verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Commit the maintenance workflow**

```powershell
git add src/etf_trading/nicegui_app/maintenance_tasks.py src/etf_trading/nicegui_app/pages/maintenance.py src/etf_trading/nicegui_app/components/tables.py tests/test_nicegui_maintenance_task_runner.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_table_display.py
git commit -m "feat: add official valuation maintenance task"
```

---

### Task 4: Pure Valuation Atom Calculator

**Files:**
- Create: `src/etf_trading/research/index_valuation_atoms.py`
- Test: `tests/test_index_valuation_atoms.py`

**Interfaces:**
- Produces: `VALUATION_PERCENTILE_WINDOWS = (("3y", 3, 500), ("5y", 5, 900), ("10y", 10, 1800))`
- Produces: `valuation_band(percentile: float) -> str`
- Produces: `build_index_valuation_atoms(index_code: str, valuations: pd.DataFrame, price_as_of_date: pd.Timestamp, price_trade_dates: pd.Series, *, supported: bool) -> list[dict[str, object]]`
- Every row includes `window_start_date` and `window_end_date`.

- [ ] **Step 1: Write failing percentile, alignment, stale, unsupported, and invalid-value tests**

```python
def _daily_valuations(start, periods):
    dates = pd.bdate_range(start, periods=periods)
    return pd.DataFrame({
        "index_code": "000300",
        "trade_date": dates,
        "pe_static": np.linspace(9.0, 15.0, periods),
        "pe_ttm": np.linspace(8.0, 14.0, periods),
        "pb": np.linspace(1.0, 1.8, periods),
        "turnover_rate": np.linspace(0.2, 0.8, periods),
        "data_source": "tushare_index_dailybasic",
    })


def _by_key(rows):
    return {str(row["metric_key"]): row for row in rows}


def test_midrank_percentile_uses_valid_values_and_exact_window():
    history = _daily_valuations("2021-01-01", periods=1300)
    history.loc[history.index[-3:], "pe_ttm"] = [10.0, 10.0, float("inf")]
    atoms = _by_key(build_index_valuation_atoms(
        "000300", history, pd.Timestamp("2026-01-01"), history["trade_date"], supported=True
    ))
    pe = atoms["pe_ttm_percentile_5y"]
    valid = history.loc[
        history["trade_date"].between("2021-01-01", "2026-01-01")
        & history["pe_ttm"].gt(0)
        & np.isfinite(history["pe_ttm"]),
        "pe_ttm",
    ]
    expected = ((valid < 10.0).sum() + 0.5 * (valid == 10.0).sum()) / len(valid)
    assert pe["value"] == pytest.approx(expected)
    assert pe["sample_count"] == len(valid)
    assert pe["window_start_date"] == "2021-01-01"


def test_valuation_more_than_five_price_days_old_is_stale():
    one_row = _daily_valuations("2026-07-20", 1)
    atoms = _by_key(build_index_valuation_atoms(
        "000300",
        one_row,
        pd.Timestamp("2026-07-29"),
        pd.Series(pd.bdate_range("2026-07-20", "2026-07-29")),
        supported=True,
    ))
    assert atoms["valuation_lag_trading_days"]["value"] == 7
    assert atoms["valuation_freshness_status"]["value"] == "stale"


def test_unsupported_index_returns_explicit_atoms_without_tracks():
    atoms = _by_key(build_index_valuation_atoms(
        "801010", pd.DataFrame(), pd.Timestamp("2026-07-29"), pd.Series(dtype="datetime64[ns]"), supported=False
    ))
    assert atoms["valuation_support_status"]["value"] == "unsupported"
    assert "pe_ttm_percentile_5y" not in atoms
```

- [ ] **Step 2: Run valuation-atom tests to verify RED**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_index_valuation_atoms.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-valuation-atoms-red
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement deterministic valuation atoms**

Use this exact percentile and band logic:

```python
def _midrank_percentile(values: pd.Series, current: float) -> float:
    return float(((values < current).sum() + 0.5 * (values == current).sum()) / len(values))


def valuation_band(percentile: float) -> str:
    if percentile < 0.20:
        return "历史低位"
    if percentile < 0.40:
        return "偏低"
    if percentile <= 0.60:
        return "中部"
    if percentile <= 0.80:
        return "偏高"
    return "历史高位"
```

For each window and each of `pe_ttm` and `pb`, emit percentile, median, median deviation, band, sample count, and exact window dates. Emit current direct values and Tushare size/turnover values. Calculate 20/60-day turnover means and deviations only from valid positive turnover observations. Emit `pe_ttm_5y_band_changed` and `pb_5y_band_changed` only when the previous valid observation and current observation occupy different fixed bands.

- [ ] **Step 4: Run valuation-atom tests to verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Commit valuation atoms**

```powershell
git add src/etf_trading/research/index_valuation_atoms.py tests/test_index_valuation_atoms.py
git commit -m "feat: calculate index valuation percentiles"
```

---

### Task 5: Expanded Price, Momentum, and Risk Atoms

**Files:**
- Modify: `src/etf_trading/research/index_health_snapshot.py`
- Test: `tests/test_index_health_snapshot.py`

**Interfaces:**
- Extends `_METRIC_SPECS` without removing existing metric keys.
- Produces `ma_{20|60|120}_change_20`, `rsi_14`, `up_day_ratio_20`, `max_drawdown_{60|120|250}`, `annualized_volatility_{20|60}`, `downside_volatility_60`, `atr_14_pct`, `amount_avg_60`, and `amount_vs_avg_{20|60}`.

- [ ] **Step 1: Write failing formula and partial-data tests**

```python
def test_snapshot_calculates_expanded_momentum_risk_and_activity_atoms(tmp_path):
    prices = _price_history(300)
    store = _store_with_index_prices(tmp_path, "000300", prices)

    _, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    returns = prices["close"].pct_change()
    assert _detail_value(details, "000300", "ma_60_change_20") == pytest.approx(
        prices["close"].rolling(60).mean().iloc[-1] / prices["close"].rolling(60).mean().iloc[-21] - 1
    )
    assert _detail_value(details, "000300", "annualized_volatility_20") == pytest.approx(returns.iloc[-20:].std() * np.sqrt(252))
    assert _detail_value(details, "000300", "downside_volatility_60") == pytest.approx(
        np.sqrt(np.square(np.minimum(returns.iloc[-60:], 0)).mean()) * np.sqrt(252)
    )
    assert _detail_value(details, "000300", "atr_14_pct") == pytest.approx(
        _detail_value(details, "000300", "atr_14") / prices["close"].iloc[-1]
    )
    assert _detail_status(details, "000300", "amount_avg_60") == "computed"


def test_missing_amount_only_marks_activity_atoms_missing(tmp_path):
    prices = _price_history(300, amount=None)
    store = _store_with_index_prices(tmp_path, "000300", prices)
    _, details = build_index_atomic_snapshot(store, (_definition("000300"),))
    assert _detail_status(details, "000300", "amount_avg_60") == "missing_input"
    assert _detail_status(details, "000300", "rsi_14") == "computed"
```

- [ ] **Step 2: Run snapshot tests to verify RED**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_index_health_snapshot.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-price-atoms-red
```

Expected: FAIL because the new metric keys do not exist.

- [ ] **Step 3: Add pure helpers and emit the new atoms**

Import `numpy as np`, then implement:

```python
def _annualized_volatility(close, window):
    values, status, reason = _tail(close, window + 1, "close")
    if values is None:
        return pd.NA, status, reason
    return float(values.pct_change().iloc[1:].std() * (252 ** 0.5)), "computed", "按日收益率样本标准差年化"


def _maximum_drawdown(close, window):
    values, status, reason = _tail(close, window, "close")
    if values is None:
        return pd.NA, status, reason
    drawdowns = values / values.cummax() - 1
    return float(drawdowns.min()), "computed", "按窗口内此前累计最高收盘计算"


def _rsi_14(close):
    values, status, reason = _tail(close, 15, "close")
    if values is None:
        return pd.NA, status, reason
    changes = values.diff().iloc[1:]
    gains = changes.clip(lower=0).mean()
    losses = -changes.clip(upper=0).mean()
    if losses == 0:
        return 100.0, "computed", "最近14日没有下跌变动"
    return float(100 - 100 / (1 + gains / losses)), "computed", "按14日平均涨跌幅计算"


def _ma_change(close, ma_window, lookback=20):
    values, status, reason = _tail(close, ma_window + lookback, "close")
    if values is None:
        return pd.NA, status, reason
    moving_average = values.rolling(ma_window).mean().dropna()
    reference = float(moving_average.iloc[-lookback - 1])
    if reference == 0:
        return pd.NA, "calculation_failed", f"{ma_window}日均线参考值为零"
    return float(moving_average.iloc[-1]) / reference - 1, "computed", "按20个交易日均线变化计算"


def _up_day_ratio_20(close):
    values, status, reason = _tail(close, 21, "close")
    if values is None:
        return pd.NA, status, reason
    returns = values.pct_change().iloc[1:]
    return float((returns > 0).mean()), "computed", "按最近20个日收益方向计算"


def _downside_volatility_60(close):
    values, status, reason = _tail(close, 61, "close")
    if values is None:
        return pd.NA, status, reason
    returns = values.pct_change().iloc[1:].to_numpy(dtype=float)
    downside = np.minimum(returns, 0.0)
    return float(np.sqrt(np.square(downside).mean()) * np.sqrt(252)), "computed", "按60日下行收益均方根年化"
```

For `atr_14_pct`, divide the computed ATR14 by the latest positive close. For `amount_avg_60`, reuse `_mean(amount, 60)`. For `amount_vs_avg_20` and `amount_vs_avg_60`, divide current amount by the respective positive average and subtract one. Use independent status propagation for every atom. Keep existing `drawdown_{window}` as current drawdown; add distinct `max_drawdown_{window}` keys.

- [ ] **Step 4: Run snapshot tests to verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Commit expanded price atoms**

```powershell
git add src/etf_trading/research/index_health_snapshot.py tests/test_index_health_snapshot.py
git commit -m "feat: expand index trend and risk atoms"
```

---

### Task 6: Unified Snapshot Merge and Input Signatures

**Files:**
- Modify: `src/etf_trading/research/index_health_snapshot.py`
- Modify: `src/etf_trading/nicegui_app/state.py`
- Modify: `src/etf_trading/nicegui_app/maintenance_tasks.py`
- Test: `tests/test_index_health_snapshot.py`
- Test: `tests/test_nicegui_state_cache.py`
- Test: `tests/test_nicegui_maintenance_tasks.py`

**Interfaces:**
- Consumes: `build_index_valuation_atoms(...)`
- Extends `INDEX_ATOMIC_DETAIL_COLUMNS` with `window_start_date` and `window_end_date`.
- Extends summary with `valuation_support_status`, `valuation_as_of_date`, `valuation_freshness_status`, `valuation_source`, `pe_static`, `pe_ttm`, `pe_ttm_5y_percentile`, `pb`, and `pb_5y_percentile`.
- Bumps `INDEX_ATOMIC_SNAPSHOT_CACHE_SCHEMA_VERSION` from `2` to `3`.

- [ ] **Step 1: Replace the old “never reads valuations” test and add signature regressions**

```python
def _five_year_valuation_history():
    dates = pd.bdate_range("2021-07-29", "2026-07-29")
    return finalize_index_valuation_frame(
        pd.DataFrame({
            "trade_date": dates,
            "pe_ttm": np.linspace(9.0, 14.0, len(dates)),
            "pe_static": np.linspace(9.5, 14.5, len(dates)),
            "pb": np.linspace(1.0, 1.8, len(dates)),
            "turnover_rate": np.linspace(0.2, 0.8, len(dates)),
        }),
        "000300",
        "tushare_index_dailybasic",
        "official",
    )


def test_snapshot_merges_supported_valuation_without_blocking_price_atoms(tmp_path):
    store = _store_with_index_prices(tmp_path, "000300", _price_history(300))
    store.write_index_valuations("000300", _five_year_valuation_history())

    summary, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    row = summary.iloc[0]
    assert row["valuation_support_status"] == "supported"
    assert row["valuation_as_of_date"] <= row["latest_date"]
    assert row["pe_ttm_5y_percentile"] == pytest.approx(
        _detail_value(details, "000300", "pe_ttm_percentile_5y")
    )
    assert _detail_status(details, "000300", "ma_20") == "computed"


def test_unsupported_valuation_does_not_downgrade_price_snapshot(tmp_path):
    store = _store_with_index_prices(tmp_path, "801010", _price_history(300))
    summary, details = build_index_atomic_snapshot(store, (_definition("801010"),))
    assert summary.iloc[0]["snapshot_status"] == "computed"
    assert _detail_value(details, "801010", "valuation_support_status") == "unsupported"


def test_valuation_cache_change_marks_published_snapshot_stale(tmp_path):
    parquet_store = _parquet_store(tmp_path)
    definitions = (_definition("000300"),)
    coverage = _coverage("000300")
    parquet_store.write_index_valuations("000300", _five_year_valuation_history().iloc[:-1])
    source_signature = state._index_atomic_snapshot_source_signature(parquet_store, definitions, coverage)
    state.write_index_atomic_snapshot(
        _summary("000300"),
        _details("000300"),
        source_signature,
        datetime(2026, 7, 29, 9, 0),
        parquet_store,
        definitions=definitions,
        coverage=coverage,
        expected_input_signature=source_signature,
    )
    parquet_store.write_index_valuations("000300", _five_year_valuation_history())

    loaded = state.load_index_atomic_snapshot_readonly(parquet_store, definitions, coverage=coverage)
    assert loaded.status == "stale"
```

- [ ] **Step 2: Run unified snapshot tests to verify RED**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_index_health_snapshot.py tests\test_nicegui_state_cache.py tests\test_nicegui_maintenance_tasks.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-unified-snapshot-red
```

Expected: FAIL because valuations are not read, signed, summarized, or persisted.

- [ ] **Step 3: Merge valuation atoms and sign both input families**

In `build_index_atomic_snapshot`, read price history first. For supported codes, read valuation history independently; a valuation read error emits `read_failed` valuation atoms but keeps price atoms available. For unsupported codes, do not call `read_index_valuations`.

Extend `_detail`:

```python
def _detail(
    index_code, group_key, metric_key, metric_label, value, status, reason,
    as_of_date="", sample_count=0, data_source="",
    window_start_date="", window_end_date="",
):
    return {
        "index_code": index_code,
        "group_key": group_key,
        "metric_key": metric_key,
        "metric_label": metric_label,
        "value": value,
        "status": status,
        "reason": reason,
        "as_of_date": as_of_date,
        "sample_count": sample_count,
        "data_source": data_source,
        "window_start_date": window_start_date,
        "window_end_date": window_end_date,
    }
```

In `_index_atomic_snapshot_source_signature`, hash `index_valuations/{code}.parquet` existence, size, and mtime for every supported selected definition in addition to index price files. Update cache-safe detail casting for the two window date columns. The maintenance runner captures and rechecks this combined signature before publication.

- [ ] **Step 4: Run unified snapshot tests to verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Commit the unified publication boundary**

```powershell
git add src/etf_trading/research/index_health_snapshot.py src/etf_trading/nicegui_app/state.py src/etf_trading/nicegui_app/maintenance_tasks.py tests/test_index_health_snapshot.py tests/test_nicegui_state_cache.py tests/test_nicegui_maintenance_tasks.py
git commit -m "feat: publish unified index profile snapshots"
```

---

### Task 7: Five-Tab Read-Only Profile View Model

**Files:**
- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Test: `tests/test_nicegui_view_models.py`

**Interfaces:**
- Produces: `IndexProfileView`
- Produces: `index_profile_view(summary: dict[str, object], details: pd.DataFrame, index_code: str) -> IndexProfileView | None`
- Produces grouped detail collections for valuation, trend/risk, all atoms, events, and quality.

- [ ] **Step 1: Write failing normal and degraded-state view-model tests**

```python
def _profile_detail(metric_key, value, *, group_key="valuation", status="computed", reason="已计算"):
    return {
        "index_code": "000300",
        "group_key": group_key,
        "metric_key": metric_key,
        "metric_label": metric_key,
        "value": value,
        "status": status,
        "reason": reason,
        "as_of_date": "2026-07-29",
        "sample_count": 1000,
        "data_source": "tushare_index_dailybasic" if group_key == "valuation" else "unit",
        "window_start_date": "2021-07-29" if "5y" in metric_key else "",
        "window_end_date": "2026-07-29" if "5y" in metric_key else "",
    }


def _profile_summary():
    return {
        "index_code": "000300", "index_name": "沪深300", "latest_date": "2026-07-29",
        "valuation_as_of_date": "2026-07-29", "valuation_support_status": "supported",
        "valuation_freshness_status": "fresh", "pe_ttm": 11.6, "pe_ttm_5y_percentile": 0.18,
        "pb": 1.24, "pb_5y_percentile": 0.22, "close_above_ma_20": False,
        "close_vs_ma_20": -0.037, "drawdown_250": -0.079,
    }


def _profile_details():
    return pd.DataFrame([
        _profile_detail("pe_ttm", 11.6),
        _profile_detail("pe_ttm_percentile_5y", 0.18),
        _profile_detail("pe_ttm_band_5y", "历史低位"),
        _profile_detail("pb", 1.24),
        _profile_detail("pb_percentile_5y", 0.22),
        _profile_detail("pb_band_5y", "偏低"),
        _profile_detail("close", 4569.52, group_key="price_ma"),
        _profile_detail("ma_20", 4743.52, group_key="price_ma"),
        _profile_detail("close_above_ma_20", False, group_key="price_ma"),
        _profile_detail("drawdown_250", -0.079, group_key="return_drawdown"),
        _profile_detail("rsi_14", 41.2, group_key="momentum_return"),
        _profile_detail("annualized_volatility_20", 0.146, group_key="drawdown_risk"),
        _profile_detail("amount_avg_20", 100_000_000, group_key="trading_activity"),
    ])


def test_index_profile_view_builds_approved_summary_and_five_domains():
    view = index_profile_view(_profile_summary(), _profile_details(), "000300")
    assert view.identity == "000300 · 沪深300"
    assert [card.label for card in view.summary_cards] == ["PE-TTM", "PB", "趋势位置", "250日当前回撤"]
    assert view.valuation.pe_ttm.percentile_5y == "18.0%"
    assert view.valuation.pe_ttm.band_5y == "历史低位"
    assert [section.title for section in view.trend_risk_sections] == [
        "趋势结构", "动量与收益", "回撤与风险", "成交活跃度",
    ]


def test_index_profile_view_hides_valuation_tracks_when_unsupported():
    summary = _profile_summary() | {
        "index_code": "801010", "index_name": "农林牧渔", "valuation_support_status": "unsupported",
        "valuation_as_of_date": "",
    }
    details = _profile_details().copy()
    details["index_code"] = "801010"
    details = pd.concat([details, pd.DataFrame([{
        **_profile_detail("valuation_support_status", "unsupported", status="unsupported",
                          reason="Tushare 官方估值暂不支持该指数"),
        "index_code": "801010",
    }])], ignore_index=True)
    view = index_profile_view(summary, details, "801010")
    assert view.valuation.visible is False
    assert view.valuation.reason == "Tushare 官方估值暂不支持该指数"
    assert view.trend.visible is True


def test_index_profile_view_exposes_stale_dates_without_relabeling_old_value():
    summary = _profile_summary() | {
        "valuation_as_of_date": "2026-07-20", "valuation_freshness_status": "stale",
    }
    view = index_profile_view(summary, _profile_details(), "000300")
    assert view.valuation.status == "估值数据已过期"
    assert view.price_as_of_date == "2026-07-29"
    assert view.valuation_as_of_date == "2026-07-20"
```

- [ ] **Step 2: Run view-model tests to verify RED**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_view_models.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-view-model-red
```

Expected: FAIL because `IndexProfileView` and `index_profile_view` do not exist.

- [ ] **Step 3: Implement the read-only display model**

Define immutable dataclasses for:

```python
@dataclass(frozen=True)
class IndexProfileSummaryCard:
    label: str
    value: str
    detail: str
    available: bool


@dataclass(frozen=True)
class IndexProfileValuationMetric:
    label: str
    current_value: str
    percentile_3y: str
    percentile_5y: str
    percentile_10y: str
    band_5y: str
    median_5y: str
    median_deviation_5y: str
    sample_count_5y: int


@dataclass(frozen=True)
class IndexProfileValuationSection:
    visible: bool
    status: str
    reason: str
    pe_ttm: IndexProfileValuationMetric | None
    pb: IndexProfileValuationMetric | None
    metrics: tuple[IndexAtomicOverviewMetric, ...]


@dataclass(frozen=True)
class IndexProfileTrendSection:
    visible: bool
    close: IndexAtomicOverviewMetric
    rows: tuple[IndexAtomicOverviewMetric, ...]
    reason: str


@dataclass(frozen=True)
class IndexProfileMetricSection:
    title: str
    items: tuple[IndexAtomicDetailItem, ...]


@dataclass(frozen=True)
class IndexProfileView:
    identity: str
    price_as_of_date: str
    valuation_as_of_date: str
    summary_cards: tuple[IndexProfileSummaryCard, ...]
    valuation: IndexProfileValuationSection
    trend: IndexProfileTrendSection
    trend_risk_sections: tuple[IndexProfileMetricSection, ...]
    events: tuple[IndexAtomicOverviewEvent, ...]
    all_groups: tuple[IndexAtomicOverviewEvidenceGroup, ...]
    quality: tuple[IndexAtomicOverviewMetric, ...]
```

Build every field exclusively from stored summary/detail rows. Delete transient ladder-position calculation from the profile path. Add source label `tushare_index_dailybasic -> Tushare（官方指数每日指标）` and status labels for `supported`, `unsupported`, `not_synced`, `fresh`, and `stale`.

- [ ] **Step 4: Run view-model tests to verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Commit the profile view model**

```powershell
git add src/etf_trading/nicegui_app/view_models.py tests/test_nicegui_view_models.py
git commit -m "feat: build unified index profile view model"
```

---

### Task 8: Approved NiceGUI Dialog and Responsive Styling

**Files:**
- Modify: `src/etf_trading/nicegui_app/pages/market.py`
- Modify: `src/etf_trading/nicegui_app/theme.py`
- Test: `tests/test_nicegui_app_import.py`
- Test: `tests/test_nicegui_theme.py`
- Test: `tests/test_nicegui_navigation.py`

**Interfaces:**
- Consumes: `index_profile_view(...)`
- Produces: `_open_index_profile_dialog(result, index_code)`
- Preserves: row-click behavior and read-only `load_index_atomic_snapshot_readonly(...)`.

- [ ] **Step 1: Write failing structure, import-boundary, and CSS tests**

```python
def test_market_dialog_uses_five_profile_tabs_and_no_builder_import():
    source = inspect.getsource(market)
    for label in ("画像总览", "估值详情", "趋势与风险", "全部指标", "数据质量"):
        assert f'ui.tab("{label}")' in source
    assert "build_index_atomic_snapshot" not in source
    assert "fetch_index_official_valuations" not in source
    assert "OfficialIndexValuationSyncService" not in source


def test_theme_scopes_profile_width_grid_and_mobile_rules():
    css = WORKBENCH_CSS
    assert ".index-profile-dialog" in css
    assert "width: min(1180px, 92vw)" in css
    assert ".index-profile-summary-grid" in css
    assert ".index-profile-trend-row" in css
    assert "@media (max-width: 720px)" in css
    mobile = css.split("@media (max-width: 720px)", 1)[1]
    assert ".index-profile-dialog" in mobile
    assert "grid-template-columns: minmax(0, 1fr)" in mobile
```

- [ ] **Step 2: Run UI structure tests to verify RED**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_app_import.py tests\test_nicegui_theme.py tests\test_nicegui_navigation.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-ui-red
```

Expected: FAIL because the old three-tab `index-atomic-*` dialog and ladder remain.

- [ ] **Step 3: Render the approved B layout**

Use this exact tab skeleton:

```python
with ui.card().classes("index-profile-dialog"):
    _render_index_profile_header(profile, dialog.close)
    with ui.tabs().classes("index-profile-tabs w-full") as tabs:
        overview_tab = ui.tab("画像总览")
        valuation_tab = ui.tab("估值详情")
        trend_risk_tab = ui.tab("趋势与风险")
        all_tab = ui.tab("全部指标")
        quality_tab = ui.tab("数据质量")
    with ui.tab_panels(tabs, value=overview_tab).classes("index-profile-panels w-full"):
        with ui.tab_panel(overview_tab):
            _render_index_profile_overview(profile)
        with ui.tab_panel(valuation_tab):
            _render_index_profile_valuation(profile.valuation)
        with ui.tab_panel(trend_risk_tab):
            _render_index_profile_trend_risk(profile)
        with ui.tab_panel(all_tab):
            _render_index_profile_all_groups(profile.all_groups)
        with ui.tab_panel(quality_tab):
            _render_index_profile_quality(profile)
```

The overview uses four summary cards, a valuation percentile panel, a collision-free trend relation table, then three compact panels for momentum/risk, recent events, and availability. Unsupported, missing, stale, and insufficient states render text instead of empty tracks.

Add scoped CSS:

```css
.index-profile-dialog { width: min(1180px, 92vw); max-height: 92vh; border-radius: 18px; }
.index-profile-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.index-profile-primary-grid { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1.35fr); gap: 14px; }
.index-profile-secondary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.index-profile-detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 720px) {
  .index-profile-dialog { width: min(100%, 96vw); max-height: 96vh; }
  .index-profile-summary-grid,
  .index-profile-primary-grid,
  .index-profile-secondary-grid,
  .index-profile-detail-grid { grid-template-columns: minmax(0, 1fr); }
  .index-profile-tabs { overflow-x: auto; flex-wrap: nowrap; }
}
```

- [ ] **Step 4: Run UI structure tests to verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Commit the dialog redesign**

```powershell
git add src/etf_trading/nicegui_app/pages/market.py src/etf_trading/nicegui_app/theme.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py tests/test_nicegui_navigation.py
git commit -m "feat: redesign unified index profile dialog"
```

---

### Task 9: Read-Only Cross-Index Valuation Comparison

**Files:**
- Modify: `src/etf_trading/nicegui_app/navigation.py`
- Modify: `src/etf_trading/nicegui_app/view_models.py`
- Modify: `src/etf_trading/nicegui_app/pages/market.py`
- Test: `tests/test_nicegui_navigation.py`
- Test: `tests/test_nicegui_view_models.py`
- Test: `tests/test_nicegui_app_import.py`

**Interfaces:**
- Produces: `official_index_valuation_comparison_rows(summary: pd.DataFrame) -> list[dict[str, object]]`
- Produces: market section `指数估值`, ordered after `指数体检`.
- Consumes only the published unified summary returned by `load_index_atomic_snapshot_readonly`.

- [ ] **Step 1: Write failing navigation, comparison-row, and no-network tests**

```python
def _comparison_summary():
    codes = ["399006", "801010", "000300", "000001", "399001", "000905", "000016"]
    return pd.DataFrame([
        {
            "index_code": code,
            "index_name": f"指数{code}",
            "valuation_support_status": "unsupported" if code == "801010" else "supported",
            "valuation_as_of_date": "2026-07-29",
            "pe_static": 11.9,
            "pe_ttm": 11.6,
            "pe_ttm_5y_percentile": 0.18,
            "pb": 1.24,
            "pb_5y_percentile": 0.22,
            "valuation_freshness_status": "fresh",
            "valuation_source": "tushare_index_dailybasic",
        }
        for code in codes
    ])


def test_market_navigation_places_index_valuation_after_healthcheck():
    market_page = next(page for page in NAVIGATION if page.slug == "market")
    assert market_page.sections == ("市场总览", "指数体检", "指数估值", "指数买卖参考", "指数K线")


def test_official_index_valuation_comparison_uses_supported_published_rows_only():
    rows = official_index_valuation_comparison_rows(_comparison_summary())
    assert [row["指数代码"] for row in rows] == [
        "000001", "000016", "000300", "000905", "399001", "399006",
    ]
    assert rows[2]["PE-TTM"] == "11.60"
    assert rows[2]["PE-TTM 5年分位"] == "18.0%"
    assert "801010" not in {row["指数代码"] for row in rows}


def test_index_valuation_page_does_not_import_provider_or_sync_service():
    source = inspect.getsource(market)
    assert "TushareProvider" not in source
    assert "OfficialIndexValuationSyncService" not in source
    assert "fetch_index_official_valuations" not in source
```

- [ ] **Step 2: Run comparison-page tests to verify RED**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_navigation.py tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-comparison-red
```

Expected: FAIL because navigation and the comparison row model do not exist.

- [ ] **Step 3: Implement the read-only comparison section**

```python
def official_index_valuation_comparison_rows(summary: pd.DataFrame) -> list[dict[str, object]]:
    if summary.empty or "index_code" not in summary:
        return []
    mapped_order = tuple(OFFICIAL_INDEX_VALUATION_TS_CODES)
    by_code = {
        str(row["index_code"]): row
        for row in summary.to_dict("records")
        if str(row.get("index_code", "")) in OFFICIAL_INDEX_VALUATION_TS_CODES
    }
    return [
        {
            "指数代码": code,
            "指数名称": _text(by_code[code].get("index_name")),
            "估值日期": _date_text(by_code[code].get("valuation_as_of_date")),
            "静态 PE": _format_number(by_code[code].get("pe_static")),
            "PE-TTM": _format_number(by_code[code].get("pe_ttm")),
            "PE-TTM 5年分位": _format_percentile(by_code[code].get("pe_ttm_5y_percentile")),
            "PB": _format_number(by_code[code].get("pb")),
            "PB 5年分位": _format_percentile(by_code[code].get("pb_5y_percentile")),
            "新鲜度": _index_atomic_status_label(by_code[code].get("valuation_freshness_status")),
            "数据来源": _index_atomic_data_source_label(by_code[code].get("valuation_source")),
        }
        for code in mapped_order
        if code in by_code
    ]
```

Render the rows as a compact table. If the unified snapshot is missing, failed, or contains no supported valuation rows, show an empty state linking to `数据维护 -> 补齐任务`. Page refresh only rereads the published snapshot.

- [ ] **Step 4: Run comparison-page tests to verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Commit the comparison page**

```powershell
git add src/etf_trading/nicegui_app/navigation.py src/etf_trading/nicegui_app/view_models.py src/etf_trading/nicegui_app/pages/market.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_nicegui_app_import.py
git commit -m "feat: add index valuation comparison page"
```

---

### Task 10: Integrated Verification, Browser QA, and Task Memory

**Files:**
- Modify: `docs/task-memory.md`
- Test: all focused tests and full suite

**Interfaces:**
- Verifies the complete provider-to-cache-to-snapshot-to-view flow.
- Produces durable verification evidence and cautions in task memory.

- [ ] **Step 1: Run the complete focused suite**

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_index_valuations.py tests\test_tushare_provider.py tests\test_primary_fallback_provider.py tests\test_index_valuation_service.py tests\test_index_valuation_atoms.py tests\test_index_health_snapshot.py tests\test_nicegui_state_cache.py tests\test_nicegui_maintenance_task_runner.py tests\test_nicegui_maintenance_tasks.py tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py tests\test_nicegui_theme.py tests\test_nicegui_navigation.py tests\test_nicegui_table_display.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-focused
```

Expected: PASS with no failed tests.

- [ ] **Step 2: Run the complete offline suite**

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-full
```

Expected: PASS; the opt-in live Tushare smoke test may skip when `TUSHARE_TOKEN` is unset.

- [ ] **Step 3: Seed deterministic local profile data and start NiceGUI**

Use a temporary Parquet/SQLite root and the existing test fixture patterns to publish:

- one supported, complete `000300` profile;
- one unsupported valuation profile with complete price atoms;
- one stale valuation profile;
- one insufficient 10-year percentile profile.

Start:

```powershell
.\.venv-win\Scripts\python.exe scripts\run_nicegui.py
```

Expected: the app serves locally without fetching valuation data during page navigation.

- [ ] **Step 4: Verify desktop and mobile behavior in the browser**

At 1440px and 390px viewport widths:

1. Open `市场地图 -> 指数体检`.
2. Open each seeded index row.
3. Switch all five tabs and expand every full-indicator group.
4. Assert no root horizontal overflow.
5. Assert no trend label overlap or clipped value.
6. Assert unsupported/missing/old/sample-insufficient valuation states show text and no fabricated track.
7. Assert no console errors or warnings.
8. Save screenshots for the overview, valuation details, trend/risk, and mobile layout under a temporary evidence directory outside Git.

Expected: all assertions pass.

- [ ] **Step 5: Append verified task memory**

Add an entry to `docs/task-memory.md` containing the exact commands run, observed pass/skip counts, browser evidence path, and these fixed summary/caution lines:

```markdown
## 2026-07-30 - Add unified index valuation and trend profile

- Summary: Added Tushare official index valuation history, transparent 3/5/10-year PE-TTM and PB percentiles, expanded price/risk atoms, one signed unified snapshot, and the five-tab index profile dialog.
- Caution: Keep valuation and price histories as separate inputs, include both in the snapshot signature, never derive unsupported index valuations from constituents, and keep market-page interactions read-only.
```

Insert the verification bullet between Summary and Caution using the literal commands from Steps 1–2, pytest's observed counts, and the actual temporary browser evidence directory; do not estimate counts.

- [ ] **Step 6: Commit verification documentation**

```powershell
git add docs/task-memory.md
git commit -m "docs: record unified index profile verification"
```
