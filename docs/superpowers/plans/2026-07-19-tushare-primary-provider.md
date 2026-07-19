# Tushare Primary Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Tushare the system-wide primary ETF/index data source while visibly and durably falling back to AkShare whenever Tushare fails or lacks a required capability.

**Architecture:** Add an isolated `TushareProvider`, a `PrimaryFallbackProvider` that records structured notices, and one provider factory used by every application and script entry point. Keep market-data frames on the existing `DataProvider` contract; carry fallback metadata separately through drainable notices, then render or persist those notices at UI, task-runner, and CLI boundaries.

**Tech Stack:** Python 3.11, pandas, tushare SDK, PyYAML, SQLite, Parquet, NiceGUI, Streamlit, pytest.

## Global Constraints

- Read the Token only from `TUSHARE_TOKEN`; never write it to source, YAML, tests, logs, task results, or Git history.
- Use `TUSHARE_API_URL` when set; otherwise use `https://ts.gyzcloud.top/api` from `configs/data_sources.yaml`.
- Default local throttling must stay below the account's 150 requests/minute limit; use 120 requests/minute.
- Tushare is always attempted first for supported calls; any fallback must produce a visible `ProviderNotice`.
- A successful fallback is reported as `warning`, not pure `success` and not `failed`.
- Never return unadjusted `fund_daily` prices for an `adjust="qfq"` request.
- Keep actual source labels on every market-data row; never store provider notices as Parquet columns.
- Default pytest runs must not call either live provider.
- Preserve all unrelated dirty-worktree changes and stage only files named by the active task.

---

## File Map

- Create `src/etf_trading/data/provider_runtime.py`: settings, error taxonomy, notices, redaction, throttling, aggregation helpers.
- Create `src/etf_trading/data/providers/tushare_provider.py`: Tushare SDK adapter and normalization.
- Create `src/etf_trading/data/providers/fallback_provider.py`: Tushare-first dispatch and combined failures.
- Create `src/etf_trading/data/providers/factory.py`: the only application-level provider constructor.
- Modify `src/etf_trading/data/providers/akshare_provider.py`: guarantee granular AkShare source labels.
- Modify `src/etf_trading/data/index_catalog.py`, `src/etf_trading/data/storage.py`, and `configs/index_universe.yaml`: optional durable Tushare index symbols.
- Modify `src/etf_trading/nicegui_app/maintenance_tasks.py` and `src/etf_trading/nicegui_app/pages/maintenance.py`: durable and immediate completed-with-warning behavior.
- Modify `src/etf_trading/ui/app.py`: Streamlit provider factory and visible notices.
- Modify `scripts/update_data.py` and `scripts/fetch_all_etf_history.py`: factory usage and stderr/JSON warning summaries.
- Modify `pyproject.toml`, `configs/data_sources.yaml`, `README.md`, and `docs/task-memory.md`: dependency, configuration, operator instructions, and project memory.
- Create focused tests under `tests/` for each boundary plus an opt-in real-proxy smoke test.

---

### Task 1: Provider Runtime Contract and Configuration

**Files:**
- Create: `src/etf_trading/data/provider_runtime.py`
- Modify: `pyproject.toml:11-22`
- Modify: `configs/data_sources.yaml:1-5`
- Test: `tests/test_provider_runtime.py`

**Interfaces:**
- Consumes: `yaml.safe_load`, environment mappings, monotonic clock and sleep callables.
- Produces: `ProviderSettings`, `ProviderError`, `ProviderConfigurationError`, `ProviderCapabilityError`, `ProviderCallError`, `ProviderNotice`, `ProviderOperationResult[T]`, `RequestRateLimiter`, `redact_provider_text()`, `summarize_provider_notices()`.

- [ ] **Step 1: Write failing settings, redaction, aggregation, and throttling tests**

Create `tests/test_provider_runtime.py`:

```python
from pathlib import Path

from etf_trading.data.provider_runtime import (
    ProviderNotice,
    RequestRateLimiter,
    load_provider_settings,
    redact_provider_text,
    summarize_provider_notices,
)


def test_settings_read_secret_only_from_environment(tmp_path: Path):
    config = tmp_path / "sources.yaml"
    config.write_text(
        "primary_provider: tushare\n"
        "fallback_provider: akshare\n"
        "tushare:\n"
        "  api_url: https://proxy.example/api\n"
        "  requests_per_minute: 120\n"
        "  attempts: 3\n",
        encoding="utf-8",
    )
    settings = load_provider_settings(config, {"TUSHARE_TOKEN": "secret-value"})
    assert settings.primary_provider == "tushare"
    assert settings.fallback_provider == "akshare"
    assert settings.api_url == "https://proxy.example/api"
    assert settings.token == "secret-value"
    assert "secret-value" not in repr(settings)


def test_environment_overrides_proxy_url(tmp_path: Path):
    config = tmp_path / "sources.yaml"
    config.write_text("tushare:\n  api_url: https://default.example/api\n", encoding="utf-8")
    settings = load_provider_settings(
        config,
        {"TUSHARE_TOKEN": "token", "TUSHARE_API_URL": "https://override.example/api"},
    )
    assert settings.api_url == "https://override.example/api"


def test_redaction_removes_token_and_tokenized_url():
    text = "failed token=secret-value at https://proxy.example/mcp/token=secret-value"
    assert redact_provider_text(text, secrets=("secret-value",)) == (
        "failed token=[REDACTED] at https://proxy.example/mcp/token=[REDACTED]"
    )


def test_notice_summary_aggregates_without_spamming_codes():
    notices = [
        ProviderNotice("fetch_etf_daily", "510300", "network", "timeout", "akshare"),
        ProviderNotice("fetch_etf_daily", "510500", "network", "timeout", "akshare"),
    ]
    assert summarize_provider_notices(notices, example_limit=1) == (
        "Tushare 异常后已使用 AkShare：2 次；示例：510300；原因：network"
    )


def test_rate_limiter_waits_for_configured_interval():
    times = iter([0.0, 0.1])
    sleeps: list[float] = []
    limiter = RequestRateLimiter(120, clock=lambda: next(times), sleep=sleeps.append)
    limiter.wait()
    limiter.wait()
    assert sleeps == [0.4]
```

- [ ] **Step 2: Run the tests and verify the module is missing**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_provider_runtime.py -q
```

Expected: collection fails with `ModuleNotFoundError: etf_trading.data.provider_runtime`.

- [ ] **Step 3: Implement the runtime contracts**

Create `src/etf_trading/data/provider_runtime.py` with these concrete definitions:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from time import monotonic, sleep
from typing import Callable, Generic, Mapping, Sequence, TypeVar
import os
import re

import yaml


DEFAULT_DATA_SOURCE_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "data_sources.yaml"
T = TypeVar("T")


@dataclass(frozen=True)
class ProviderSettings:
    primary_provider: str = "tushare"
    fallback_provider: str = "akshare"
    api_url: str = "https://ts.gyzcloud.top/api"
    requests_per_minute: int = 120
    attempts: int = 3
    token: str = field(default="", repr=False)


class ProviderError(RuntimeError):
    category = "provider"


class ProviderConfigurationError(ProviderError):
    category = "configuration"


class ProviderCapabilityError(ProviderError):
    category = "unsupported"


class ProviderCallError(ProviderError):
    def __init__(self, message: str, *, category: str = "provider") -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class ProviderNotice:
    operation: str
    asset_code: str
    category: str
    reason: str
    fallback_provider: str
    known_gap: bool = False


@dataclass(frozen=True)
class ProviderOperationResult(Generic[T]):
    value: T
    notices: tuple[ProviderNotice, ...] = ()


def load_provider_settings(
    path: str | Path = DEFAULT_DATA_SOURCE_CONFIG,
    environ: Mapping[str, str] | None = None,
) -> ProviderSettings:
    values = os.environ if environ is None else environ
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    tushare = raw.get("tushare", {}) or {}
    return ProviderSettings(
        primary_provider=str(raw.get("primary_provider") or "tushare"),
        fallback_provider=str(raw.get("fallback_provider") or "akshare"),
        api_url=str(values.get("TUSHARE_API_URL") or tushare.get("api_url") or "https://ts.gyzcloud.top/api"),
        requests_per_minute=int(tushare.get("requests_per_minute", 120)),
        attempts=int(tushare.get("attempts", 3)),
        token=str(values.get("TUSHARE_TOKEN") or "").strip(),
    )


def redact_provider_text(text: object, *, secrets: Sequence[str] = ()) -> str:
    result = str(text)
    for secret in sorted({value for value in secrets if value}, key=len, reverse=True):
        result = result.replace(secret, "[REDACTED]")
    result = re.sub(r"(?i)(token\s*[=:]\s*)[^\s&]+", r"\1[REDACTED]", result)
    result = re.sub(r"(?i)(authorization\s*[=:]\s*)[^\s,]+", r"\1[REDACTED]", result)
    return result


def summarize_provider_notices(notices: Sequence[ProviderNotice], *, example_limit: int = 5) -> str:
    if not notices:
        return ""
    examples = list(dict.fromkeys(item.asset_code for item in notices if item.asset_code))[:example_limit]
    categories = list(dict.fromkeys(item.category for item in notices))
    example_text = "、".join(examples) or "全局配置"
    return (
        f"Tushare 异常后已使用 AkShare：{len(notices)} 次；"
        f"示例：{example_text}；原因：{'、'.join(categories)}"
    )


class RequestRateLimiter:
    def __init__(
        self,
        requests_per_minute: int,
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], None] = sleep,
    ) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        self.interval = 60.0 / requests_per_minute
        self.clock = clock
        self.sleep = sleep
        self._lock = Lock()
        self._last_call: float | None = None

    def wait(self) -> None:
        with self._lock:
            now = self.clock()
            if self._last_call is not None:
                delay = self.interval - (now - self._last_call)
                if delay > 0:
                    self.sleep(delay)
                    now += delay
            self._last_call = now
```

Update `configs/data_sources.yaml` to start with:

```yaml
primary_provider: tushare
fallback_provider: akshare
tushare:
  api_url: https://ts.gyzcloud.top/api
  requests_per_minute: 120
  attempts: 3
storage:
```

Add `"tushare>=1.4.24",` immediately after the AkShare dependency in `pyproject.toml`.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_provider_runtime.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit the runtime contract**

```powershell
git add pyproject.toml configs/data_sources.yaml src/etf_trading/data/provider_runtime.py tests/test_provider_runtime.py
git commit -m "feat: add provider runtime contract"
```

---

### Task 2: Tushare ETF Data Adapter

**Files:**
- Create: `src/etf_trading/data/providers/tushare_provider.py`
- Modify: `src/etf_trading/data/providers/__init__.py`
- Test: `tests/test_tushare_provider.py`

**Interfaces:**
- Consumes: `DataProvider`, `ProviderSettings`, `RequestRateLimiter`, `classify_etf`, injected SDK-like client exposing `query(api_name, fields=..., **params)`.
- Produces: `TushareProvider(settings: ProviderSettings, *, pro_client=None, limiter=None, sleeper=time.sleep)` implementing ETF list, spot capability, daily prices, and NAV.

- [ ] **Step 1: Write failing ETF normalization and adjustment tests**

Create `tests/test_tushare_provider.py` with a `_FakePro` that records calls and returns configured frames, then add:

```python
import pandas as pd
import pytest

from etf_trading.data.provider_runtime import ProviderCallError, ProviderCapabilityError, ProviderSettings
from etf_trading.data.providers.tushare_provider import TushareProvider


class _FakePro:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def query(self, api_name, fields="", **params):
        self.calls.append((api_name, fields, params))
        response = self.responses[api_name]
        if isinstance(response, Exception):
            raise response
        return response.copy()


class _SequencePro:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def query(self, api_name, fields="", **params):
        self.call_count += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response.copy()


def _provider(responses):
    return TushareProvider(
        ProviderSettings(token="test-token", attempts=1),
        pro_client=_FakePro(responses),
    )


def test_etf_list_keeps_listed_etfs_and_excludes_lof():
    provider = _provider({
        "fund_basic": pd.DataFrame({
            "ts_code": ["510300.SH", "501050.SH"],
            "name": ["沪深300ETF", "50AH优选LOF"],
            "management": ["华泰柏瑞", "华夏"],
            "fund_type": ["股票型", "股票型"],
            "type": ["ETF", "LOF"],
            "list_date": ["20120528", "20161128"],
            "status": ["L", "L"],
        })
    })
    result = provider.fetch_etf_list()
    assert result["etf_code"].tolist() == ["510300"]
    assert result.iloc[0]["exchange"] == "SSE"
    assert result.iloc[0]["data_source"] == "tushare_fund_basic"


def test_qfq_uses_latest_adjustment_factor_without_adjusting_volume():
    provider = _provider({
        "fund_daily": pd.DataFrame({
            "ts_code": ["510300.SH", "510300.SH"],
            "trade_date": ["20260702", "20260701"],
            "open": [2.0, 1.0], "high": [2.2, 1.1], "low": [1.8, 0.9], "close": [2.0, 1.0],
            "vol": [20.0, 10.0], "amount": [4.0, 1.0], "pct_chg": [100.0, 0.0],
        }),
        "fund_adj": pd.DataFrame({
            "ts_code": ["510300.SH", "510300.SH"],
            "trade_date": ["20260702", "20260701"],
            "adj_factor": [2.0, 1.0],
        }),
    })
    result = provider.fetch_etf_daily("510300", "2026-07-01", "2026-07-02", adjust="qfq")
    assert result["close"].tolist() == [0.5, 2.0]
    assert result["volume"].tolist() == [10.0, 20.0]
    assert result["amount"].tolist() == [1000.0, 4000.0]
    assert result["adjust"].tolist() == ["qfq", "qfq"]


def test_qfq_rejects_incomplete_adjustment_factors():
    provider = _provider({
        "fund_daily": pd.DataFrame({
            "ts_code": ["510300.SH"], "trade_date": ["20260701"],
            "open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0],
            "vol": [10.0], "amount": [1.0],
        }),
        "fund_adj": pd.DataFrame(columns=["ts_code", "trade_date", "adj_factor"]),
    })
    with pytest.raises(ProviderCallError, match="adjustment factors"):
        provider.fetch_etf_daily("510300", "2026-07-01", "2026-07-01", adjust="qfq")


def test_empty_master_is_invalid_not_a_successful_empty_universe():
    provider = _provider({"fund_basic": pd.DataFrame()})
    with pytest.raises(ProviderCallError, match="no listed ETFs"):
        provider.fetch_etf_list()


def test_realtime_spot_is_an_explicit_capability_gap():
    provider = _provider({})
    with pytest.raises(ProviderCapabilityError, match="realtime ETF spot"):
        provider.fetch_exchange_traded_etf_spot()


def test_nav_normalizes_available_fields_and_keeps_missing_iopv_empty():
    provider = _provider({
        "fund_nav": pd.DataFrame({
            "ts_code": ["510300.SH"], "nav_date": ["20260701"],
            "unit_nav": [4.2], "accum_nav": [4.2],
        })
    })
    result = provider.fetch_etf_nav("510300", "2026-07-01", "2026-07-02")
    assert result.loc[0, "etf_code"] == "510300"
    assert result.loc[0, "unit_nav"] == 4.2
    assert pd.isna(result.loc[0, "iopv"])


def test_temporary_error_is_retried_then_succeeds():
    client = _SequencePro([TimeoutError("temporary timeout"), pd.DataFrame({
        "ts_code": ["510300.SH"], "name": ["沪深300ETF"], "management": ["华泰柏瑞"],
        "fund_type": ["股票型"], "type": ["ETF"], "list_date": ["20120528"], "status": ["L"],
    })])
    provider = TushareProvider(
        ProviderSettings(token="test", attempts=2), pro_client=client, sleeper=lambda _: None
    )
    assert provider.fetch_etf_list()["etf_code"].tolist() == ["510300"]
    assert client.call_count == 2


def test_permission_error_is_not_retried():
    client = _SequencePro([RuntimeError("没有权限调用 fund_adj")])
    provider = TushareProvider(
        ProviderSettings(token="test", attempts=3), pro_client=client, sleeper=lambda _: None
    )
    with pytest.raises(ProviderCallError) as captured:
        provider._query("fund_adj", fields="ts_code", ts_code="510300.SH")
    assert captured.value.category == "permission"
    assert client.call_count == 1
```


- [ ] **Step 2: Run the tests and verify the adapter is missing**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_tushare_provider.py -q
```

Expected: collection fails because `tushare_provider.py` does not exist.

- [ ] **Step 3: Implement SDK bootstrap, retry classification, and ETF methods**

Create `src/etf_trading/data/providers/tushare_provider.py`. Use lazy SDK bootstrap so importing the app never performs network access:

```python
class TushareProvider(DataProvider):
    def __init__(self, settings, *, pro_client=None, limiter=None, sleeper=time.sleep):
        self.settings = settings
        self._pro_client = pro_client
        self.limiter = limiter or RequestRateLimiter(settings.requests_per_minute)
        self.sleeper = sleeper
        self._index_basic_cache = None

    @property
    def pro(self):
        if self._pro_client is not None:
            return self._pro_client
        if not self.settings.token:
            raise ProviderConfigurationError("TUSHARE_TOKEN is not configured")
        import tushare as ts
        ts.set_token(self.settings.token)
        client = ts.pro_api(self.settings.token)
        client._DataApi__http_url = self.settings.api_url
        self._pro_client = client
        return client

    def _query(self, api_name, *, fields, **params):
        last_error = None
        for attempt in range(1, self.settings.attempts + 1):
            self.limiter.wait()
            try:
                result = self.pro.query(api_name, fields=fields, **params)
                if not isinstance(result, pd.DataFrame):
                    raise ProviderCallError(f"{api_name} returned a non-table response", category="schema")
                return result
            except ProviderError:
                raise
            except Exception as exc:
                category = _classify_tushare_error(exc)
                if category in {"authentication", "permission", "parameter"}:
                    raise ProviderCallError(str(exc), category=category) from exc
                last_error = exc
                if attempt < self.settings.attempts:
                    self.sleeper(min(2 ** (attempt - 1), 4))
        raise ProviderCallError(str(last_error), category=_classify_tushare_error(last_error)) from last_error
```

Implement `fetch_etf_list()`, `fetch_exchange_traded_etf_spot()`, `fetch_etf_daily()`, and `fetch_etf_nav()` using the field lists and formulas asserted above. The required QFQ calculation is:

```python
merged = daily.merge(factors[["trade_date", "adj_factor"]], on="trade_date", how="left", validate="one_to_one")
if merged["adj_factor"].isna().any() or merged.empty:
    raise ProviderCallError("fund_adj returned incomplete adjustment factors", category="schema")
latest_factor = float(merged.sort_values("trade_date").iloc[-1]["adj_factor"])
for column in ("open", "high", "low", "close"):
    merged[column] = pd.to_numeric(merged[column], errors="coerce") * merged["adj_factor"] / latest_factor
merged["adjust"] = "qfq"
```

Use `_etf_ts_code()` to map prefixes `51/52/53/56/58` to `.SH` and `15/16` to `.SZ`; raise `ProviderCallError(category="parameter")` for unknown prefixes. Set `data_source` to the exact interface name and convert `amount * 1000` while leaving Tushare's lot-based `vol` unchanged.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_tushare_provider.py -q
```

Expected: all ETF adapter tests pass.

- [ ] **Step 5: Commit the ETF adapter**

```powershell
git add src/etf_trading/data/providers/tushare_provider.py src/etf_trading/data/providers/__init__.py tests/test_tushare_provider.py
git commit -m "feat: add tushare ETF provider"
```

---

### Task 3: Durable Tushare Index Symbols and Trading Calendar

**Files:**
- Modify: `src/etf_trading/data/index_catalog.py:78-310`
- Modify: `src/etf_trading/data/storage.py:100-285`
- Modify: `src/etf_trading/data/providers/tushare_provider.py`
- Modify: `configs/index_universe.yaml:1`
- Modify: `tests/test_index_catalog.py`
- Modify: `tests/test_storage_and_services.py`
- Modify: `tests/test_tushare_provider.py`

**Interfaces:**
- Consumes: `IndexCatalogEntry.tushare_symbol`, Tushare `index_basic`, `index_daily`, and `trade_cal`.
- Produces: optional durable `tushare_symbol: str | None`; `TushareProvider.fetch_index_daily()` and `fetch_trade_calendar()`.

- [ ] **Step 1: Write failing catalog persistence tests**

Add to `tests/test_index_catalog.py` a direct-entry YAML case asserting `entry.tushare_symbol == "000300.SH"`. Add to `tests/test_storage_and_services.py`:

```python
def test_index_catalog_persists_optional_tushare_symbol(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    entry = _index_entry("000300")
    entry = replace(entry, tushare_symbol="000300.SH")
    store.upsert_index_catalog([entry])
    restored = catalog_entries_from_frame(store.list_index_catalog(include_reserve=True))[0]
    assert restored.tushare_symbol == "000300.SH"
```

Import `replace` and `catalog_entries_from_frame` in that test file.

- [ ] **Step 2: Write failing index and calendar provider tests**

Add to `tests/test_tushare_provider.py`:

```python
def test_index_daily_uses_explicit_catalog_symbol_and_normalizes_amount():
    fake = _FakePro({
        "index_daily": pd.DataFrame({
            "ts_code": ["000300.SH"], "trade_date": ["20260701"],
            "open": [3900.0], "high": [3920.0], "low": [3880.0], "close": [3910.0],
            "vol": [12.0], "amount": [34.0],
        })
    })
    provider = TushareProvider(ProviderSettings(token="test", attempts=1), pro_client=fake)
    entry = _catalog_entry(code="000300", source_kind="csi", tushare_symbol="000300.SH")
    result = provider.fetch_index_daily(entry, "2026-07-01", "2026-07-02")
    assert fake.calls[0][2]["ts_code"] == "000300.SH"
    assert result.loc[0, "amount"] == 34000.0
    assert result.loc[0, "data_source"] == "tushare_index_daily"


def test_shenwan_index_is_known_capability_gap():
    provider = _provider({})
    entry = _catalog_entry(code="801010", source_kind="shenwan", tushare_symbol=None)
    with pytest.raises(ProviderCapabilityError, match="Shenwan"):
        provider.fetch_index_daily(entry, "2026-07-01", "2026-07-02")


def test_trade_calendar_uses_exchange_calendar():
    provider = _provider({
        "trade_cal": pd.DataFrame({
            "exchange": ["SSE", "SSE"], "cal_date": ["20260701", "20260702"], "is_open": [1, 0]
        })
    })
    result = provider.fetch_trade_calendar("SSE", "2026-07-01", "2026-07-02")
    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-07-01", "2026-07-02"]
    assert result["is_open"].tolist() == [1, 0]
```

- [ ] **Step 3: Run focused tests and verify failures**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_catalog.py tests\test_storage_and_services.py tests\test_tushare_provider.py -q
```

Expected: failures mention missing `tushare_symbol` and unimplemented index/calendar methods.

- [ ] **Step 4: Add catalog field and idempotent SQLite migration**

Add `tushare_symbol: str | None = None` after `provider_symbol` in `IndexCatalogEntry`. Parse it with `str(value).strip() or None`, include it in `catalog_entries_from_frame()`, and include a `tushare_symbol TEXT` column in fresh schema creation.

In `SQLiteStore.initialize_schema()`, add an idempotent migration beside the existing catalog evidence migrations:

```python
existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(index_catalog)")}
if "tushare_symbol" not in existing_columns:
    conn.execute("ALTER TABLE index_catalog ADD COLUMN tushare_symbol TEXT")
```

Add `tushare_symbol` to `upsert_index_catalog()` columns and row values. Add explicit symbols at the top of `configs/index_universe.yaml` through a `tushare_symbols` mapping:

```yaml
tushare_symbols:
  "000001": "000001.SH"
  "000016": "000016.SH"
  "000300": "000300.SH"
  "000688": "000688.SH"
  "000852": "000852.SH"
  "000905": "000905.SH"
  "399001": "399001.SZ"
  "399006": "399006.SZ"
```

Apply the mapping in `load_index_catalog()` immediately after parsing entries:

```python
raw_symbols = raw.get("tushare_symbols", {}) or {}
if not isinstance(raw_symbols, dict):
    raise ValueError("tushare_symbols must be a mapping")
entries = tuple(
    replace(entry, tushare_symbol=str(raw_symbols.get(entry.index_code) or "").strip() or None)
    for entry in entries
)
```

Do not guess symbols for the remaining catalog entries.

- [ ] **Step 5: Implement exact symbol resolution, index daily, and calendar methods**

In `TushareProvider.fetch_index_daily()`:

```python
entry = _resolve_index_catalog_entry(code)
if entry.source_kind == "shenwan":
    raise ProviderCapabilityError(f"Shenwan index_daily is not supported by Tushare: {entry.index_code}")
if entry.source_kind == "hk":
    raise ProviderCapabilityError(f"Hong Kong index route is not supported by this Tushare adapter: {entry.index_code}")
ts_code = entry.tushare_symbol or self._resolve_index_symbol(entry)
raw = self._query(
    "index_daily",
    fields="ts_code,trade_date,open,high,low,close,vol,amount",
    ts_code=ts_code,
    start_date=_fmt_date(start_date),
    end_date=_fmt_date(end_date),
)
return _normalize_index_daily(raw, entry.index_code)
```

`_resolve_index_symbol()` may cache one `index_basic` table, but it must accept only one exact `symbol == entry.index_code` match; zero or multiple matches raise `ProviderCapabilityError`. Implement `fetch_trade_calendar()` with `trade_cal`, normalize `cal_date` to `trade_date`, and preserve closed days.

- [ ] **Step 6: Run focused tests and catalog regressions**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_catalog.py tests\test_storage_and_services.py tests\test_tushare_provider.py tests\test_index_support.py -q
```

Expected: all selected tests pass, including old databases without `tushare_symbol`.

- [ ] **Step 7: Commit index and calendar support**

```powershell
git add configs/index_universe.yaml src/etf_trading/data/index_catalog.py src/etf_trading/data/storage.py src/etf_trading/data/providers/tushare_provider.py tests/test_index_catalog.py tests/test_storage_and_services.py tests/test_tushare_provider.py
git commit -m "feat: add tushare index and calendar routes"
```

---

### Task 4: Tushare-First Fallback Provider and Factory

**Files:**
- Create: `src/etf_trading/data/providers/fallback_provider.py`
- Create: `src/etf_trading/data/providers/factory.py`
- Modify: `src/etf_trading/data/providers/akshare_provider.py`
- Test: `tests/test_primary_fallback_provider.py`
- Test: `tests/test_provider_factory.py`
- Modify: `tests/test_akshare_provider_fallback.py`

**Interfaces:**
- Consumes: two `DataProvider` instances and `ProviderSettings`.
- Produces: `CombinedProviderError`, `PrimaryFallbackProvider(primary, fallback, *, secrets=())`, read-only `primary`/`fallback`, `drain_notices() -> tuple[ProviderNotice, ...]`, and `create_data_provider(...) -> PrimaryFallbackProvider`.

- [ ] **Step 1: Write failing dispatch and redaction tests**

Create small `_Provider` fakes implementing all `DataProvider` methods, then test:

```python
def test_primary_success_does_not_call_fallback():
    primary = _Provider(etf_daily=_daily("tushare_fund_daily"))
    fallback = _Provider(etf_daily=AssertionError("fallback should not run"))
    provider = PrimaryFallbackProvider(primary, fallback)
    result = provider.fetch_etf_daily("510300", "2026-07-01", "2026-07-02")
    assert result["data_source"].tolist() == ["tushare_fund_daily"]
    assert provider.drain_notices() == ()


def test_primary_failure_returns_fallback_and_records_notice():
    primary = _Provider(etf_daily=ProviderCallError("timeout", category="network"))
    fallback = _Provider(etf_daily=_daily("akshare_eastmoney"))
    provider = PrimaryFallbackProvider(primary, fallback)
    result = provider.fetch_etf_daily("510300", "2026-07-01", "2026-07-02")
    notices = provider.drain_notices()
    assert result["data_source"].tolist() == ["akshare_eastmoney"]
    assert [(item.asset_code, item.category) for item in notices] == [("510300", "network")]


def test_capability_gap_is_distinguished_from_failure():
    primary = _Provider(index_daily=ProviderCapabilityError("Shenwan unsupported"))
    fallback = _Provider(index_daily=_index_daily("akshare_shenwan"))
    provider = PrimaryFallbackProvider(primary, fallback)
    provider.fetch_index_daily(_catalog_entry("801010"), "2026-07-01", "2026-07-02")
    assert provider.drain_notices()[0].known_gap is True


def test_double_failure_redacts_token():
    primary = _Provider(etf_daily=RuntimeError("token=secret-token denied"))
    fallback = _Provider(etf_daily=RuntimeError("eastmoney down"))
    provider = PrimaryFallbackProvider(primary, fallback, secrets=("secret-token",))
    with pytest.raises(CombinedProviderError) as captured:
        provider.fetch_etf_daily("510300", "2026-07-01", "2026-07-02")
    assert "secret-token" not in str(captured.value)
    assert "[REDACTED]" in str(captured.value)
```

Create `tests/test_provider_factory.py` asserting the factory builds Tushare primary/AkShare fallback and does not instantiate or call the SDK during construction.
Also construct the factory with an environment mapping that omits `TUSHARE_TOKEN`, perform one fake-backed call, and assert the result comes from AkShare with one `configuration` notice; missing credentials must not become a silent AkShare-only mode.

- [ ] **Step 2: Run focused tests and verify missing modules**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_primary_fallback_provider.py tests\test_provider_factory.py -q
```

Expected: collection fails for the missing fallback/factory modules.

- [ ] **Step 3: Implement the composite provider**

Define the combined error and initialize the provider with public read-only references plus a locked notice buffer:

```python
class CombinedProviderError(ProviderError):
    category = "combined"


class PrimaryFallbackProvider(DataProvider):
    def __init__(self, primary: DataProvider, fallback: DataProvider, *, secrets=()) -> None:
        self.primary = primary
        self.fallback = fallback
        self.secrets = tuple(value for value in secrets if value)
        self._notices: list[ProviderNotice] = []
        self._notice_lock = Lock()

    def drain_notices(self) -> tuple[ProviderNotice, ...]:
        with self._notice_lock:
            result = tuple(self._notices)
            self._notices.clear()
            return result
```

Use one private dispatch function in `fallback_provider.py`; append the notice while holding `_notice_lock`:

```python
def _dispatch(self, operation, asset_code, primary_call, fallback_call):
    try:
        return primary_call()
    except Exception as primary_error:
        category = getattr(primary_error, "category", "provider")
        reason = redact_provider_text(primary_error, secrets=self.secrets)
        with self._notice_lock:
            self._notices.append(ProviderNotice(
                operation=operation,
                asset_code=asset_code,
                category=category,
                reason=reason,
                fallback_provider="akshare",
                known_gap=isinstance(primary_error, ProviderCapabilityError),
            ))
        try:
            return fallback_call()
        except Exception as fallback_error:
            fallback_reason = redact_provider_text(fallback_error, secrets=self.secrets)
            raise CombinedProviderError(
                f"Tushare {operation} failed: {reason}; AkShare failed: {fallback_reason}"
            ) from fallback_error
```

Implement all six `DataProvider` methods as thin calls into `_dispatch()`. Protect `_notices` with a lock because NiceGUI background work uses threads. `drain_notices()` must atomically return a tuple and clear the buffer.

- [ ] **Step 4: Implement the factory and AkShare provenance fixes**

In `factory.py`:

```python
def create_data_provider(
    settings: ProviderSettings | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    primary: DataProvider | None = None,
    fallback: DataProvider | None = None,
) -> PrimaryFallbackProvider:
    resolved = settings or load_provider_settings(environ=environ)
    if resolved.primary_provider != "tushare" or resolved.fallback_provider != "akshare":
        raise ProviderConfigurationError("supported provider order is tushare -> akshare")
    primary_provider = primary or TushareProvider(resolved)
    fallback_provider = fallback or AkShareProvider()
    return PrimaryFallbackProvider(primary_provider, fallback_provider, secrets=(resolved.token,))
```

Ensure AkShare EastMoney ETF daily rows use `akshare_eastmoney`, Sina rows use `akshare_sina`, and the spot list uses `akshare_fund_etf_spot_em`. Update old tests to assert these exact labels.

- [ ] **Step 5: Run provider tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_provider_runtime.py tests\test_tushare_provider.py tests\test_primary_fallback_provider.py tests\test_provider_factory.py tests\test_akshare_provider_fallback.py -q
```

Expected: all provider tests pass.

- [ ] **Step 6: Commit the fallback boundary**

```powershell
git add src/etf_trading/data/providers/fallback_provider.py src/etf_trading/data/providers/factory.py src/etf_trading/data/providers/akshare_provider.py tests/test_primary_fallback_provider.py tests/test_provider_factory.py tests/test_akshare_provider_fallback.py
git commit -m "feat: add explicit provider fallback"
```

---

### Task 5: Service Capture Helpers and CLI Entry Points

**Files:**
- Modify: `src/etf_trading/data/provider_runtime.py`
- Modify: `scripts/update_data.py`
- Modify: `scripts/fetch_all_etf_history.py`
- Create: `tests/test_provider_cli_integration.py`

**Interfaces:**
- Consumes: `PrimaryFallbackProvider.drain_notices()`.
- Produces: `capture_provider_operation(provider, action) -> ProviderOperationResult[T]`; CLI stderr warnings and batch JSON `fallback_count`/`fallback_notices`.

- [ ] **Step 1: Write failing capture and CLI tests**

Add a unit test proving `capture_provider_operation()` returns the action value and drained notices. In `tests/test_provider_cli_integration.py`, monkeypatch each script's `create_data_provider()` with a fake provider and assert:

```python
def test_update_data_prints_fallback_warning_to_stderr(monkeypatch, capsys):
    provider = _FakeProvider(notices=[ProviderNotice(
        "fetch_etf_daily", "510300", "network", "timeout", "akshare"
    )])
    monkeypatch.setattr(update_data, "create_data_provider", lambda: provider)
    monkeypatch.setattr(update_data, "SQLiteStore", _StoreWithOneWatchlistRow)
    monkeypatch.setattr(update_data, "InitializationService", _SuccessfulService)
    update_data.main()
    assert "Tushare 异常后已使用 AkShare" in capsys.readouterr().err
```

Add a batch-script test that reads the generated summary JSON and asserts `fallback_count == 1` and the notice reason contains no secret.

- [ ] **Step 2: Run tests and verify direct AkShare construction fails expectations**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_provider_runtime.py tests\test_provider_cli_integration.py -q
```

Expected: failures for missing capture helper and missing factory/warning output.

- [ ] **Step 3: Add the capture helper**

Append to `provider_runtime.py`:

```python
def capture_provider_operation(provider: object, action: Callable[[], T]) -> ProviderOperationResult[T]:
    value = action()
    drain = getattr(provider, "drain_notices", None)
    notices = tuple(drain()) if callable(drain) else ()
    return ProviderOperationResult(value=value, notices=notices)
```

The helper must drain only after a successful operation. Double-provider failures continue to raise `CombinedProviderError` and are handled by existing error paths.

- [ ] **Step 4: Replace CLI constructors and aggregate warnings**

Replace `AkShareProvider()` imports and construction with `create_data_provider()`. After each master/history operation, call `capture_provider_operation(provider, ...)`, use `.value` for existing logic, and send `summarize_provider_notices(result.notices)` to `sys.stderr` when notices exist.

For `fetch_all_etf_history.py`, initialize the summary with:

```python
"fallback_count": 0,
"fallback_notices": [],
```

For each captured notice, increment the count and append only `operation`, `asset_code`, `category`, `reason`, and `fallback_provider`. Do not serialize object representations or settings.

- [ ] **Step 5: Run focused CLI tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_provider_cli_integration.py tests\test_storage_and_services.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit CLI integration**

```powershell
git add src/etf_trading/data/provider_runtime.py scripts/update_data.py scripts/fetch_all_etf_history.py tests/test_provider_cli_integration.py
git commit -m "feat: surface provider fallback in scripts"
```

---

### Task 6: NiceGUI Immediate and Durable Warning States

**Files:**
- Modify: `src/etf_trading/nicegui_app/maintenance_tasks.py`
- Modify: `src/etf_trading/nicegui_app/pages/maintenance.py`
- Modify: `tests/test_nicegui_maintenance_task_runner.py`
- Modify: `tests/test_nicegui_maintenance_tasks.py`
- Modify: `tests/test_nicegui_app_import.py`

**Interfaces:**
- Consumes: `create_data_provider()`, `capture_provider_operation()`, `ProviderOperationResult`, `summarize_provider_notices()`.
- Produces: persisted maintenance state `warning`, restored warning status, yellow notification for synchronous tasks, aggregated batch notice text.

- [ ] **Step 1: Write failing durable runner tests**

Add a fake service whose provider drains one notice. Exercise `IndexHistoryBatchRunner._run()` and `IndexCatalogMaintenanceRunner._run()`, then assert:

```python
saved = store.get_latest_maintenance_task_run(INDEX_HISTORY_BATCH_TASK_TYPE)
assert saved.state == "warning"
assert "Tushare 异常后已使用 AkShare" in saved.error_message
assert saved.result_json is not None
```

Also retain existing tests proving no notices save `state == "success"` and an exception saves `state == "failed"`.

- [ ] **Step 2: Write failing page-state and synchronous notification tests**

Add tests asserting:

```python
status = _task_status_from_run(_maintenance_run(state="warning", error_message="备用源摘要"))
assert status.state == "warning"
assert status.message == "备用源摘要"
assert status.error == ""
assert _task_state_label("warning") == "完成但有警告"
assert _task_state_tone("warning") == "warning"
```

Extend the existing `_run_task` event recorder test with a `ProviderOperationResult(frame, notices)` action and assert one `notify:warning:` event, no positive notification, and the result remains renderable.

- [ ] **Step 3: Run focused tests and verify warning state is unsupported**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_maintenance_task_runner.py tests\test_nicegui_maintenance_tasks.py tests\test_nicegui_app_import.py -q
```

Expected: warning-state and factory-integration tests fail.

- [ ] **Step 4: Capture and persist notices in durable runners**

Replace both `_default_service()` methods with `provider=create_data_provider()`. In each runner action, retain the service so notices can be drained:

```python
def action() -> ProviderOperationResult[pd.DataFrame]:
    service = self.service_factory()
    return capture_provider_operation(
        service.provider,
        lambda: service.ensure_all_index_history(through, on_progress=on_progress),
    )
```

After `run.io_bound`, set:

```python
notice_message = summarize_provider_notices(captured.notices)
self.store.update_maintenance_task_run(
    task_id,
    state="warning" if captured.notices else "success",
    result_json=captured.value.to_json(orient="records", date_format="iso"),
    error_message=notice_message or None,
)
```

Apply the same pattern to catalog runners without changing the local-only atomic snapshot runner.

- [ ] **Step 5: Render restored and synchronous warning states**

In `pages/maintenance.py`, add `warning` label/tone mappings. `_task_status_from_run()` must treat `warning` as a completed result, set `message` from `run.error_message`, keep `error=""`, and retain parsed `result`.

Add:

```python
def _run_provider_service_action(store, parquet_store, action):
    service = _service_with_provider(store, parquet_store)
    return capture_provider_operation(service.provider, lambda: action(service))
```

Use this helper for master, ETF history, individual index history, and synchronous ETF batch buttons. Update `_run_task()` to unwrap `ProviderOperationResult`; when notices exist set state `warning`, render the result, and call `ui.notify(summary, type="warning")` once.

- [ ] **Step 6: Run NiceGUI tests**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_maintenance_task_runner.py tests\test_nicegui_maintenance_tasks.py tests\test_nicegui_app_import.py tests\test_nicegui_navigation.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit NiceGUI warning behavior**

```powershell
git add src/etf_trading/nicegui_app/maintenance_tasks.py src/etf_trading/nicegui_app/pages/maintenance.py tests/test_nicegui_maintenance_task_runner.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_app_import.py
git commit -m "feat: persist provider fallback warnings"
```

---

### Task 7: Streamlit Provider Factory and Visible Warnings

**Files:**
- Modify: `src/etf_trading/ui/app.py`
- Modify: `tests/test_ui_navigation.py`
- Modify: `tests/test_ui_state.py`

**Interfaces:**
- Consumes: provider factory and drainable notices.
- Produces: Streamlit data-maintenance actions that display one aggregated warning after a successful fallback.

- [ ] **Step 1: Write failing factory and warning helper tests**

Add tests that monkeypatch `create_data_provider()` and the Streamlit warning recorder:

```python
def test_streamlit_provider_factory_is_centralized(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(ui_app, "create_data_provider", lambda: sentinel)
    assert ui_app._provider() is sentinel


def test_streamlit_renders_aggregated_provider_warning(monkeypatch):
    messages = []
    monkeypatch.setattr(ui_app.st, "warning", messages.append)
    provider = _NoticeProvider([
        ProviderNotice("fetch_etf_daily", "510300", "network", "timeout", "akshare")
    ])
    ui_app._render_provider_notices(provider)
    assert messages == ["Tushare 异常后已使用 AkShare：1 次；示例：510300；原因：network"]
```

- [ ] **Step 2: Run focused UI tests and verify failure**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_ui_navigation.py tests\test_ui_state.py -q
```

Expected: tests fail because `_provider()` still constructs AkShare and no notice renderer exists.

- [ ] **Step 3: Replace the factory and add the warning renderer**

Replace the AkShare import with `create_data_provider` and change:

```python
def _provider():
    return create_data_provider()


def _render_provider_notices(provider) -> None:
    drain = getattr(provider, "drain_notices", None)
    notices = tuple(drain()) if callable(drain) else ()
    if notices:
        st.warning(summarize_provider_notices(notices))
```

Call `_render_provider_notices(provider)` in the successful branch immediately after master initialization, ETF history, individual index history, and all-index history actions. For the all-index batch, drain once after the entire service operation so the user sees one aggregate warning.

- [ ] **Step 4: Run Streamlit and import regressions**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_ui_navigation.py tests\test_ui_state.py tests\test_ui_styles.py tests\test_nicegui_app_import.py -q
```

Expected: all selected tests pass and importing either UI performs no network call.

- [ ] **Step 5: Commit Streamlit integration**

```powershell
git add src/etf_trading/ui/app.py tests/test_ui_navigation.py tests/test_ui_state.py
git commit -m "feat: show provider fallback in streamlit"
```

---

### Task 8: Operator Documentation, Opt-In Proxy Smoke Test, and Full Verification

**Files:**
- Create: `tests/test_tushare_proxy_smoke.py`
- Modify: `README.md`
- Modify: `docs/task-memory.md`

**Interfaces:**
- Consumes: real `TUSHARE_TOKEN` and optional `TUSHARE_API_URL` from the process environment.
- Produces: an explicitly enabled four-endpoint smoke check and operator setup instructions.

- [ ] **Step 1: Add an opt-in live smoke test**

Create `tests/test_tushare_proxy_smoke.py`:

```python
import os

import pytest

from etf_trading.data.providers.factory import create_data_provider


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_TUSHARE_SMOKE") != "1",
    reason="set RUN_TUSHARE_SMOKE=1 to call the configured Tushare proxy",
)


def test_tushare_proxy_core_endpoints():
    provider = create_data_provider()
    master = provider.primary.fetch_etf_list()
    etf = provider.primary.fetch_etf_daily("510300", "2026-07-01", "2026-07-10", adjust="none")
    index = provider.primary.fetch_index_daily("000300", "2026-07-01", "2026-07-10")
    calendar = provider.primary.fetch_trade_calendar("SSE", "2026-07-01", "2026-07-10")
    assert not master.empty
    assert not etf.empty and set(etf["data_source"]) == {"tushare_fund_daily"}
    assert not index.empty and set(index["data_source"]) == {"tushare_index_daily"}
    assert not calendar.empty
```

Use the read-only-by-convention `.primary` reference defined in Task 4; never expose settings or Token through a public property.

- [ ] **Step 2: Document secure local setup and behavior**

Add a README section showing names, not values:

```markdown
## Tushare primary data source

Set `TUSHARE_TOKEN` in the process environment before starting the app. Optionally set
`TUSHARE_API_URL`; otherwise the URL in `configs/data_sources.yaml` is used. Never put the
Token in YAML or source files.

Tushare is attempted first. If it is unavailable or does not support a requested dataset,
the application displays “完成但有警告” and uses AkShare. Each stored market-data row keeps
its actual `data_source`.

The live smoke test is opt-in:

```powershell
$env:RUN_TUSHARE_SMOKE = "1"
.venv-win\Scripts\python.exe -m pytest tests\test_tushare_proxy_smoke.py -q
```
```

- [ ] **Step 3: Install the declared dependency without changing lock state**

Run:

```powershell
.venv-win\Scripts\python.exe -m pip install -e ".[dev]"
```

Expected: editable install succeeds and `python -c "import tushare"` exits successfully.

- [ ] **Step 4: Run focused provider and UI regressions**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_provider_runtime.py tests\test_tushare_provider.py tests\test_primary_fallback_provider.py tests\test_provider_factory.py tests\test_akshare_provider_fallback.py tests\test_index_catalog.py tests\test_storage_and_services.py tests\test_nicegui_maintenance_task_runner.py tests\test_nicegui_maintenance_tasks.py tests\test_ui_navigation.py tests\test_ui_state.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\tushare-primary-focused
```

Expected: all selected tests pass.

- [ ] **Step 5: Run the full offline suite**

Run:

```powershell
.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\tushare-primary-full
```

Expected: all tests pass; `test_tushare_proxy_smoke.py` is skipped unless explicitly enabled.

- [ ] **Step 6: Run the real proxy smoke test securely**

After setting `TUSHARE_TOKEN` outside command history, run:

```powershell
$env:RUN_TUSHARE_SMOKE = "1"
.venv-win\Scripts\python.exe -m pytest tests\test_tushare_proxy_smoke.py -q
```

Expected: the four core calls pass. If `fund_adj` is separately tested and permission is unavailable, verify the composite call completes through AkShare and reports a warning; do not weaken QFQ validation.

- [ ] **Step 7: Scan tracked changes and output for secrets**

Run:

```powershell
git diff --check
git grep -n -E "token=[0-9a-f]{20,}|TUSHARE_TOKEN\s*=\s*['\"][^'\"]+" -- . ':!docs/superpowers/plans/2026-07-19-tushare-primary-provider.md'
git status --short
```

Expected: `git diff --check` is clean; secret scan returns no matches; only intended task files are modified.

- [ ] **Step 8: Update task memory with evidence and commit documentation**

Prepend a `docs/task-memory.md` entry containing the implementation summary, exact focused/full/smoke results, and cautions about QFQ, index symbols, warning states, and Token redaction. Then commit:

```powershell
git add README.md tests/test_tushare_proxy_smoke.py docs/task-memory.md
git commit -m "docs: document tushare provider setup"
```

---

## Final Review Checklist

- [ ] Every direct application/script `AkShareProvider()` construction has been replaced; tests may still instantiate it directly.
- [ ] Tushare primary success does not call AkShare or emit a notice.
- [ ] Unsupported, permission, authentication, rate-limit, network, schema, and empty-response failures are distinguishable.
- [ ] Every fallback is visible in immediate UI/CLI output and durable background-task state where applicable.
- [ ] Batch notices are aggregated rather than emitted once per asset.
- [ ] Double-provider failures retain both sanitized causes.
- [ ] QFQ requires complete `fund_adj` coverage.
- [ ] Index symbols are explicit or exactly resolved; ambiguous symbols fall back.
- [ ] Tushare amount units are converted to yuan and source labels are exact.
- [ ] The Token is absent from tracked files, diffs, logs, test output, and persisted task records.
- [ ] Full offline tests and opt-in live proxy smoke evidence are recorded in task memory.
