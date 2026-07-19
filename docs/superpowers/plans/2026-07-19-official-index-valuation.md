# 官方指数估值页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 同步并展示 Tushare 覆盖的六个宽基指数官方 PE、TTM PE 与 PB。

**Architecture:** 以 Tushare index_dailybasic 为唯一来源，结果复用现有指数估值 Parquet 标准结构。维护任务负责联网同步，市场页只读取本地缓存，保证页面渲染不发网络请求。

**Tech Stack:** Python 3.11、pandas、Tushare Pro、Parquet、SQLite、NiceGUI、pytest。

## Global Constraints

- 支持代码固定为 000001、000016、000300、000905、399001、399006。
- 仅展示官方静态 PE、TTM PE、PB、日期和来源；不产生 ERP、百分位、评分或交易结论。
- 不使用 AkShare 回退，不为未支持指数创建估值缓存。
- Tushare token 只从运行时环境读取，绝不写入配置、日志、任务结果或界面。
- 页面读取缓存，不得因打开、筛选或刷新发起网络调用。

---

### Task 1: 官方估值提供方与规范化契约

**Files:**
- Modify: src/etf_trading/data/provider.py
- Modify: src/etf_trading/data/providers/tushare_provider.py
- Modify: src/etf_trading/data/providers/fallback_provider.py
- Test: tests/test_tushare_provider.py
- Test: tests/test_primary_fallback_provider.py

**Interfaces:**
- Produces: OFFICIAL_INDEX_VALUATION_CODES: frozenset[str].
- Produces: fetch_index_official_valuations(index_code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame.

- [ ] **Step 1: Write the failing tests**

    def test_index_dailybasic_normalizes_official_valuation_history():
        provider = _provider({"index_dailybasic": pd.DataFrame({
            "ts_code": ["000300.SH"], "trade_date": ["20260717"],
            "pe": [14.21], "pe_ttm": [13.98], "pb": [1.42],
        })})
        result = provider.fetch_index_official_valuations("000300", "2026-01-01", "2026-07-17")
        assert result.loc[0, ["index_code", "pe_static", "pe_ttm", "pb", "data_source"]].to_dict() == {
            "index_code": "000300", "pe_static": 14.21, "pe_ttm": 13.98, "pb": 1.42,
            "data_source": "tushare_index_dailybasic",
        }

    def test_official_valuation_rejects_uncovered_index_without_fallback():
        with pytest.raises(ProviderCapabilityError, match="official index valuation is unsupported"):
            _provider({}).fetch_index_official_valuations("801010", "2026-01-01", "2026-07-17")

- [ ] **Step 2: Run the tests to verify RED**

Run: ./.venv-win/Scripts/python.exe -m pytest tests/test_tushare_provider.py tests/test_primary_fallback_provider.py -q --basetemp C:/Users/cjj/AppData/Local/Temp/official-valuation-provider-red

Expected: FAIL because the public provider method does not exist.

- [ ] **Step 3: Write the minimal implementation**

    OFFICIAL_INDEX_VALUATION_CODES = frozenset({"000001", "000016", "000300", "000905", "399001", "399006"})

    def fetch_index_official_valuations(self, index_code, start_date, end_date):
        code = str(index_code)
        if code not in OFFICIAL_INDEX_VALUATION_CODES:
            raise ProviderCapabilityError(f"official index valuation is unsupported: {code}")
        raw = self._query("index_dailybasic", fields="ts_code,trade_date,pe,pe_ttm,pb",
            ts_code=_official_index_ts_code(code), start_date=_fmt_date(start_date), end_date=_fmt_date(end_date))
        return finalize_index_valuation_frame(
            raw.rename(columns={"pe": "pe_static"}), code, "tushare_index_dailybasic", "official")

Add a default capability-error method to DataProvider. Make PrimaryFallbackProvider delegate this method directly to primary, never through AkShare fallback.

- [ ] **Step 4: Run the tests to verify GREEN**

Run: ./.venv-win/Scripts/python.exe -m pytest tests/test_tushare_provider.py tests/test_primary_fallback_provider.py -q --basetemp C:/Users/cjj/AppData/Local/Temp/official-valuation-provider-green

Expected: PASS.

- [ ] **Step 5: Commit**

    git add src/etf_trading/data/provider.py src/etf_trading/data/providers/tushare_provider.py src/etf_trading/data/providers/fallback_provider.py tests/test_tushare_provider.py tests/test_primary_fallback_provider.py
    git commit -m "feat: fetch official index valuations from tushare"

### Task 2: 缓存同步服务与持久化维护任务

**Files:**
- Modify: src/etf_trading/data/initialization.py
- Modify: src/etf_trading/nicegui_app/maintenance_tasks.py
- Test: tests/test_storage_and_services.py
- Test: tests/test_nicegui_maintenance_tasks.py

**Interfaces:**
- Produces: InitializationService.sync_official_index_valuations(through: date | str) -> pd.DataFrame.
- Produces: OfficialIndexValuationMaintenanceRunner.start(through: str) -> MaintenanceTaskRun.

- [ ] **Step 1: Write the failing tests**

    def test_sync_official_index_valuations_writes_only_supported_histories(tmp_path):
        service = InitializationService(SQLiteStore(tmp_path / "db.sqlite"), provider=_valuation_provider(), parquet_store=ParquetStore(tmp_path / "parquet"))
        result = service.sync_official_index_valuations("2026-07-17")
        assert result["index_code"].tolist() == ["000001", "000016", "000300", "000905", "399001", "399006"]
        assert service.parquet_store.read_index_valuations("000300").iloc[-1]["pe_ttm"] == 13.98
        assert service.parquet_store.read_index_valuations("801010").empty

- [ ] **Step 2: Run the tests to verify RED**

Run: ./.venv-win/Scripts/python.exe -m pytest tests/test_storage_and_services.py tests/test_nicegui_maintenance_tasks.py -q --basetemp C:/Users/cjj/AppData/Local/Temp/official-valuation-sync-red

Expected: FAIL because the sync service and runner are absent.

- [ ] **Step 3: Write incremental synchronization and task persistence**

    def sync_official_index_valuations(self, through):
        rows = []
        for index_code in OFFICIAL_INDEX_VALUATION_CODES:
            existing = self.parquet_store.read_index_valuations(index_code)
            start = "2004-01-01" if existing.empty else (pd.Timestamp(existing["trade_date"].max()) + pd.Timedelta(days=1)).date().isoformat()
            try:
                fetched = self.provider.fetch_index_official_valuations(index_code, start, through)
                if not fetched.empty:
                    self.parquet_store.write_index_valuations(index_code, _merge_valuation_history(existing, fetched, index_code))
                rows.append({"index_code": index_code, "status": "SYNCED" if not fetched.empty else "EMPTY"})
            except Exception as exc:
                rows.append({"index_code": index_code, "status": "FAILED", "reason": str(exc)})
        return pd.DataFrame(rows)

Add distinct task type official_index_valuation_sync, per-store running-task de-duplication, and a runner that serializes the result table without secrets. Failed rows preserve their prior cache and do not stop other rows.

- [ ] **Step 4: Run the tests to verify GREEN**

Run: ./.venv-win/Scripts/python.exe -m pytest tests/test_storage_and_services.py tests/test_nicegui_maintenance_tasks.py -q --basetemp C:/Users/cjj/AppData/Local/Temp/official-valuation-sync-green

Expected: PASS.

- [ ] **Step 5: Commit**

    git add src/etf_trading/data/initialization.py src/etf_trading/nicegui_app/maintenance_tasks.py tests/test_storage_and_services.py tests/test_nicegui_maintenance_tasks.py
    git commit -m "feat: sync official index valuation cache"

### Task 3: 独立估值页面与轻量缓存读取

**Files:**
- Modify: src/etf_trading/nicegui_app/navigation.py
- Modify: src/etf_trading/nicegui_app/layout.py
- Modify: src/etf_trading/nicegui_app/pages/market.py
- Modify: src/etf_trading/nicegui_app/components/tables.py
- Test: tests/test_ui_navigation.py
- Test: tests/test_nicegui_app_import.py
- Test: tests/test_nicegui_table_display.py

**Interfaces:**
- Produces: official_index_valuation_rows(parquet_store) -> list[dict[str, object]].
- Produces: market section 指数估值 using only maintenance/lightweight snapshot mode.

- [ ] **Step 1: Write the failing tests**

    def test_market_navigation_exposes_separate_official_index_valuation_section():
        market = get_page_by_slug("market")
        assert "指数估值" in market.sections
        assert snapshot_mode_for_route("market", "指数估值") == MAINTENANCE_TASK_SNAPSHOT_MODE

    def test_official_index_valuation_rows_read_cached_direct_values_only(tmp_path):
        store = ParquetStore(tmp_path)
        store.write_index_valuations("000300", _valuation_frame("000300", 14.21, 13.98, 1.42))
        rows = official_index_valuation_rows(store)
        assert rows[0]["指数代码"] == "000300"
        assert set(rows[0]) == {"指数代码", "指数名称", "估值日期", "静态PE", "TTM PE", "PB", "数据来源"}

- [ ] **Step 2: Run the tests to verify RED**

Run: ./.venv-win/Scripts/python.exe -m pytest tests/test_ui_navigation.py tests/test_nicegui_app_import.py tests/test_nicegui_table_display.py -q --basetemp C:/Users/cjj/AppData/Local/Temp/official-valuation-page-red

Expected: FAIL because navigation, route policy, and cached-row helper are absent.

- [ ] **Step 3: Implement the no-network page**

    def official_index_valuation_rows(parquet_store):
        rows = []
        for code, name in OFFICIAL_INDEX_VALUATION_INDEXES:
            history = parquet_store.read_index_valuations(code)
            if history.empty:
                continue
            latest = history.sort_values("trade_date").iloc[-1]
            rows.append({"指数代码": code, "指数名称": name, "估值日期": _date_text(latest["trade_date"]),
                         "静态PE": _number_text(latest["pe_static"]), "TTM PE": _number_text(latest["pe_ttm"]),
                         "PB": _number_text(latest["pb"]), "数据来源": _data_source_text(latest["data_source"])})
        return rows

Add 指数估值 after 指数体检; render an empty-state link to 数据维护 -> 补齐任务 if cache is empty. Never construct a provider or call a network-aware service from market page code.

- [ ] **Step 4: Run the tests to verify GREEN**

Run: ./.venv-win/Scripts/python.exe -m pytest tests/test_ui_navigation.py tests/test_nicegui_app_import.py tests/test_nicegui_table_display.py -q --basetemp C:/Users/cjj/AppData/Local/Temp/official-valuation-page-green

Expected: PASS.

- [ ] **Step 5: Commit**

    git add src/etf_trading/nicegui_app/navigation.py src/etf_trading/nicegui_app/layout.py src/etf_trading/nicegui_app/pages/market.py src/etf_trading/nicegui_app/components/tables.py tests/test_ui_navigation.py tests/test_nicegui_app_import.py tests/test_nicegui_table_display.py
    git commit -m "feat: show official index valuations"

### Task 4: 维护页触发器、文档与回归验证

**Files:**
- Modify: src/etf_trading/nicegui_app/pages/maintenance.py
- Modify: src/etf_trading/nicegui_app/components/tables.py
- Modify: docs/task-memory.md
- Test: tests/test_nicegui_maintenance_tasks.py
- Test: tests/test_nicegui_table_display.py

**Interfaces:**
- Consumes: OfficialIndexValuationMaintenanceRunner.start(through: str).
- Produces: an explicit 同步官方指数估值 maintenance action and Chinese task-result labels.

- [ ] **Step 1: Write the failing tests**

    def test_catalog_task_panel_offers_official_valuation_sync(monkeypatch):
        labels = _rendered_button_labels(monkeypatch)
        maintenance._render_catalog_index_tasks(_store(), _parquet(), _holder(), _status(), _catalog_runner(), _atomic_runner(), _official_valuation_runner())
        assert "同步官方指数估值" in labels

- [ ] **Step 2: Run the tests to verify RED**

Run: ./.venv-win/Scripts/python.exe -m pytest tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_table_display.py -q --basetemp C:/Users/cjj/AppData/Local/Temp/official-valuation-maintenance-red

Expected: FAIL because the trigger and labels are absent.

- [ ] **Step 3: Wire the explicit maintenance action and document it**

Add the runner to _render_tasks, render outlined button 同步官方指数估值, and reuse the persisted task center. Map SYNCED, EMPTY, and FAILED to Chinese display labels. Append a task-memory entry with verification evidence and the no-fallback/no-page-network caveats.

- [ ] **Step 4: Run focused and full verification**

Run: ./.venv-win/Scripts/python.exe -m pytest tests/test_tushare_provider.py tests/test_primary_fallback_provider.py tests/test_storage_and_services.py tests/test_nicegui_maintenance_tasks.py tests/test_ui_navigation.py tests/test_nicegui_app_import.py tests/test_nicegui_table_display.py -q --basetemp C:/Users/cjj/AppData/Local/Temp/official-valuation-focused

Expected: PASS.

Run: ./.venv-win/Scripts/python.exe -m pytest -q --basetemp C:/Users/cjj/AppData/Local/Temp/official-valuation-full

Expected: PASS.

- [ ] **Step 5: Commit**

    git add src/etf_trading/nicegui_app/pages/maintenance.py src/etf_trading/nicegui_app/components/tables.py docs/task-memory.md tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_table_display.py
    git commit -m "feat: add official valuation maintenance action"
