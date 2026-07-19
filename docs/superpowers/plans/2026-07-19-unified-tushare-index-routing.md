# Unified Tushare Index Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every index history request through Tushare first, with the existing AkShare provider as the fallback.

**Architecture:** `TushareProvider` will always submit the configured catalog symbol to `index_daily`; it will not reject a request solely because its catalog source kind is `hk` or `shenwan`. The provider composition remains unchanged, so exceptions and empty-data handling continue through `PrimaryFallbackProvider` to AkShare.

**Tech Stack:** Python 3.11, pandas, pytest, Tushare SDK, AkShare.

## Global Constraints

- Do not store credentials in source, configuration, tests, logs, or Git.
- Preserve `PrimaryFallbackProvider` notices and actual `data_source` values.
- Use TDD: each behavior test must fail before production code changes.

---

### Task 1: Route catalog symbols through Tushare

**Files:**

- Modify: `tests/test_tushare_provider.py`
- Modify: `src/etf_trading/data/providers/tushare_provider.py`
- Modify: `configs/index_universe.yaml`

**Interfaces:**

- Consumes: `IndexCatalogEntry.provider_symbol`.
- Produces: `TushareProvider.fetch_index_daily(entry, start_date, end_date)` that submits the configured symbol for every catalog source kind.

- [ ] **Step 1: Write the failing test**

```python
def test_index_daily_uses_csi_symbol_for_hk_catalog_entry():
    pro = _FakePro({"index_daily": pd.DataFrame()})
    provider = TushareProvider(ProviderSettings(token="test", attempts=1), pro_client=pro)
    entry = IndexCatalogEntry("H30533", "China Internet 50", "HK", "theme", "theme", "broad", "core", None, "official", "hk", "H30533.CSI")

    provider.fetch_index_daily(entry, "2026-07-01", "2026-07-01")

    assert pro.calls[-1][2]["ts_code"] == "H30533.CSI"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest tests/test_tushare_provider.py::test_index_daily_uses_csi_symbol_for_hk_catalog_entry -q`

Expected: FAIL with `ProviderCapabilityError` before the fake Tushare client is called.

- [ ] **Step 3: Write the minimal implementation**

Remove the `source_kind` capability rejection from `fetch_index_daily()` so the existing `provider_symbol` lookup flows to `_query("index_daily", ...)`. Set `H30533`'s catalog provider symbol to `H30533.CSI` while retaining its display code and aliases.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest tests/test_tushare_provider.py tests/test_primary_fallback_provider.py tests/test_provider_factory.py -q`

Expected: PASS.

### Task 2: Record the operational behavior

**Files:**

- Modify: `docs/task-memory.md`

**Interfaces:**

- Consumes: verified routing and fallback test results.
- Produces: a durable note that all data requests are Tushare-first with AkShare as fallback.

- [ ] **Step 1: Add the task-memory entry**

Record that category-based Tushare skips were removed, catalog symbols now reach Tushare first, and empty or unsupported responses fall back to AkShare without persisting tokens.

- [ ] **Step 2: Run the full test suite**

Run: `PYTHONPATH=src .venv-win\Scripts\python.exe -m pytest -q`

Expected: PASS with the opt-in live smoke test skipped when no environment Token is configured.
