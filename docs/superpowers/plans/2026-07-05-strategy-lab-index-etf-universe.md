# Strategy Lab Index ETF Universe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable strategy lab loop: index-selected ETF sample pools, parameterized ETF strategies, index-scoped backtests, strategy comparison, ETF replay, and removal of unvalidated index buy/sell advice from core pages.

**Architecture:** Add a focused research module for ETF-to-index mapping and sample pool selection, then wire it into the existing Streamlit research UI and background research runner. Reuse existing `StrategyCandidate`, `generate_candidate_signals`, `run_research`, and `BacktestEngine`; do not add a second strategy engine in this phase.

**Tech Stack:** Python 3.11+, pandas, PyYAML, Streamlit, pytest, existing SQLite/Parquet stores.

## Global Constraints

- Trading strategies operate on ETF data; index rules are filters, sample selectors, or research factors.
- Index buy/sell advice must not appear in market map or daily action as a core recommendation.
- First version uses parameterized strategy forms, not in-page Python custom strategy code.
- Every ETF sample must show tracked index name, mapping source, and confidence.
- Each index defaults to at most 10 ETFs by liquidity and sufficient local history.
- Experimental strategies must not feed daily action.
- Existing user changes must not be reverted.
- Current environment does not expose `git`; skip commit steps and report that limitation.

---

### Task 1: Navigation and Core Page Repositioning

**Files:**
- Modify: `src/etf_trading/ui/navigation.py`
- Modify: `src/etf_trading/ui/pages/market.py`
- Modify: `src/etf_trading/ui/pages/decision.py`
- Modify: `src/etf_trading/ui/app.py`
- Test: `tests/test_ui_navigation.py`

**Interfaces:**
- Consumes: existing `PageSpec`, `market.render`, `decision.render`, `app.main`.
- Produces: navigation labels where `research` is shown as `策略实验室`, market sections are `ETF行情` and `指数K线`, research sections include `策略库`, `新建策略`, `运行回测`, `策略比较`, `ETF复盘`, `指数过滤实验`, `指数ETF池`.

- [ ] **Step 1: Write failing navigation tests**

```python
def test_primary_navigation_promotes_strategy_lab():
    assert page_labels() == ["今日行动", "市场地图", "ETF池", "策略实验室", "数据维护"]


def test_market_map_only_contains_observation_views():
    sections_by_label = {page.label: section_options(page) for page in PAGE_SPECS}

    assert sections_by_label["市场地图"] == ["ETF行情", "指数K线"]
    assert "指数买卖参考" not in sections_by_label["市场地图"]


def test_strategy_lab_exposes_research_workflow():
    sections_by_label = {page.label: section_options(page) for page in PAGE_SPECS}

    assert sections_by_label["策略实验室"] == [
        "策略库",
        "新建策略",
        "运行回测",
        "策略比较",
        "ETF复盘",
        "指数过滤实验",
        "指数ETF池",
    ]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_ui_navigation.py -v`

Expected: FAIL because current labels still include `研究复盘` and market still includes `指数买卖参考`.

- [ ] **Step 3: Update navigation and market page routing**

Implementation requirements:

```python
PageSpec(
    slug="market",
    label="市场地图",
    caption="观察 ETF 行情和指数趋势，不输出未验证交易建议。",
    sections=("ETF行情", "指数K线"),
)
PageSpec(
    slug="research",
    label="策略实验室",
    caption="创建策略、运行回测、比较表现并复盘 ETF 的 B/S 点。",
    sections=("策略库", "新建策略", "运行回测", "策略比较", "ETF复盘", "指数过滤实验", "指数ETF池"),
)
```

`market.render` should route `ETF行情` to `render_etf_chart` and all other market views to `render_index_watch`. Remove the direct `render_index_filter_explorer` branch from market.

- [ ] **Step 4: Remove unverified index summary from daily action**

Implementation requirements:

`decision.render` should no longer show `当前通过趋势过滤的指数` as a core action summary. Keep status cards, next steps, daily advice, and calculation pool behavior unchanged.

- [ ] **Step 5: Run navigation tests**

Run: `pytest tests/test_ui_navigation.py -v`

Expected: PASS.

---

### Task 2: Index ETF Universe Module

**Files:**
- Create: `src/etf_trading/research/index_etf_universe.py`
- Test: `tests/test_index_etf_universe.py`

**Interfaces:**
- Consumes: `DEFAULT_INDEXES`, ETF master DataFrame, `ParquetStore.read_prices`.
- Produces:
  - `IndexEtfSampleConfig(max_per_index: int = 10, min_history_rows: int = 252)`
  - `build_index_etf_universe(master: pd.DataFrame, parquet_store: ParquetStore, definitions: Sequence[IndexDefinition] = DEFAULT_INDEXES, config: IndexEtfSampleConfig | None = None) -> pd.DataFrame`
  - `selected_etf_codes(universe: pd.DataFrame, index_codes: Sequence[str]) -> list[str]`

- [ ] **Step 1: Write failing universe tests**

```python
def test_build_index_etf_universe_maps_by_tracking_index_first(tmp_path):
    parquet_store = ParquetStore(tmp_path)
    parquet_store.write_prices("510300", _price_frame(300))
    master = pd.DataFrame(
        {
            "etf_code": ["510300"],
            "name": ["沪深300ETF华泰柏瑞"],
            "tracking_index": ["000300"],
            "amount": [100_000_000],
            "volume": [1_000_000],
            "is_active": [1],
        }
    )

    universe = build_index_etf_universe(master, parquet_store, definitions=(IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),))

    assert universe.iloc[0]["etf_code"] == "510300"
    assert universe.iloc[0]["index_code"] == "000300"
    assert universe.iloc[0]["index_name"] == "沪深300"
    assert universe.iloc[0]["mapping_source"] == "data_source"
    assert universe.iloc[0]["confidence"] == "high"
    assert bool(universe.iloc[0]["is_top_sample"]) is True
```

```python
def test_build_index_etf_universe_infers_by_name_and_limits_to_top_10(tmp_path):
    parquet_store = ParquetStore(tmp_path)
    codes = [f"5103{i:02d}" for i in range(12)]
    for code in codes:
        parquet_store.write_prices(code, _price_frame(300))
    master = pd.DataFrame(
        {
            "etf_code": codes,
            "name": [f"沪深300ETF测试{i}" for i in range(12)],
            "tracking_index": [None] * 12,
            "amount": [i for i in range(12)],
            "volume": [1_000] * 12,
            "is_active": [1] * 12,
        }
    )

    universe = build_index_etf_universe(master, parquet_store, definitions=(IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),))
    selected = universe[universe["is_top_sample"]]

    assert len(selected) == 10
    assert selected["amount"].tolist() == sorted(selected["amount"].tolist(), reverse=True)
    assert selected.iloc[0]["mapping_source"] == "name_inferred"
    assert selected.iloc[0]["confidence"] == "medium"
```

```python
def test_selected_etf_codes_returns_deduplicated_top_samples(tmp_path):
    universe = pd.DataFrame(
        {
            "index_code": ["000300", "000300", "000905"],
            "etf_code": ["510300", "510300", "510500"],
            "is_top_sample": [True, True, False],
        }
    )

    assert selected_etf_codes(universe, ["000300", "000905"]) == ["510300"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_index_etf_universe.py -v`

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement universe builder**

Implementation requirements:

```python
@dataclass(frozen=True)
class IndexEtfSampleConfig:
    max_per_index: int = 10
    min_history_rows: int = 252


def build_index_etf_universe(master, parquet_store, definitions=DEFAULT_INDEXES, config=None):
    config = config or IndexEtfSampleConfig()
    normalized = _normalize_master(master)
    rows = []
    for definition in definitions:
        candidates = _candidates_for_index(normalized, definition)
        candidates = _attach_history_rows(candidates, parquet_store)
        candidates = candidates[candidates["history_rows"] >= config.min_history_rows]
        candidates = candidates.sort_values(["amount", "history_rows", "etf_code"], ascending=[False, False, True])
        for rank, row in enumerate(candidates.to_dict("records"), start=1):
            row.update(
                {
                    "index_code": definition.index_code,
                    "index_name": definition.name,
                    "market": definition.market,
                    "index_category": definition.category,
                    "sample_rank": rank,
                    "is_top_sample": rank <= config.max_per_index,
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)
```

Matching rules:

- If `tracking_index` equals `definition.index_code` or `definition.name`, source is `data_source`, confidence `high`.
- Otherwise infer by ETF name containing the index name or aliases from a local alias table, source `name_inferred`, confidence `medium`.
- Skip inactive ETFs where `is_active` is present and false.
- Normalize ETF codes to six digits.

- [ ] **Step 4: Run universe tests**

Run: `pytest tests/test_index_etf_universe.py -v`

Expected: PASS.

---

### Task 3: Strategy Config Save and Status Support

**Files:**
- Modify: `src/etf_trading/research/models.py`
- Modify: `src/etf_trading/research/config.py`
- Test: `tests/test_research_cli_config.py`

**Interfaces:**
- Consumes: existing `StrategyCandidate`.
- Produces:
  - `status: str = "experimental"` field on `StrategyCandidate`
  - `append_research_candidate(path: str | Path, candidate: StrategyCandidate) -> None`
  - `adopted_candidates(candidates: Sequence[StrategyCandidate]) -> list[StrategyCandidate]`

- [ ] **Step 1: Write failing tests**

```python
def test_load_research_candidates_defaults_status_to_experimental(tmp_path):
    config_path = tmp_path / "research.yaml"
    config_path.write_text("candidates:\n  - name: custom\n", encoding="utf-8")

    candidate = load_research_candidates(config_path)[0]

    assert candidate.status == "experimental"
```

```python
def test_append_research_candidate_writes_parameterized_strategy(tmp_path):
    config_path = tmp_path / "research.yaml"
    config_path.write_text("candidates: []\n", encoding="utf-8")
    append_research_candidate(config_path, StrategyCandidate(name="custom", entry_ma="ma60", status="experimental"))

    loaded = load_research_candidates(config_path)

    assert loaded[0].name == "custom"
    assert loaded[0].entry_ma == "ma60"
    assert loaded[0].status == "experimental"
```

```python
def test_adopted_candidates_filters_only_adopted():
    candidates = [StrategyCandidate(name="a", status="adopted"), StrategyCandidate(name="b", status="experimental")]

    assert [candidate.name for candidate in adopted_candidates(candidates)] == ["a"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_research_cli_config.py -v`

Expected: FAIL because `status`, `append_research_candidate`, and `adopted_candidates` do not exist.

- [ ] **Step 3: Implement config support**

Implementation requirements:

- Add `status: str = "experimental"` to `StrategyCandidate`.
- When loading YAML, ignore unknown status absence by defaulting to experimental.
- `append_research_candidate` reads the YAML, appends a serializable mapping for the candidate, and writes UTF-8 YAML.
- Reject duplicate strategy names with `ValueError`.
- `adopted_candidates` returns only status `adopted`.

- [ ] **Step 4: Run config tests**

Run: `pytest tests/test_research_cli_config.py -v`

Expected: PASS.

---

### Task 4: Strategy Lab UI Wiring

**Files:**
- Modify: `src/etf_trading/ui/app.py`
- Test: `tests/test_ui_navigation.py`
- Test: `tests/test_research_display_labels.py`

**Interfaces:**
- Consumes:
  - `build_index_etf_universe`
  - `selected_etf_codes`
  - `append_research_candidate`
  - existing `ResearchJobManager.start`
- Produces:
  - `_render_strategy_library`
  - `_render_strategy_form`
  - `_render_index_etf_pool`
  - updated `_render_research_run_controls` that selects indexes and runs only selected index ETF samples.

- [ ] **Step 1: Write failing UI helper tests**

```python
def test_index_etf_universe_display_uses_chinese_headers():
    frame = pd.DataFrame(
        {
            "index_code": ["000300"],
            "index_name": ["沪深300"],
            "etf_code": ["510300"],
            "etf_name": ["沪深300ETF华泰柏瑞"],
            "mapping_source": ["name_inferred"],
            "confidence": ["medium"],
            "amount": [100_000_000],
            "history_rows": [300],
            "is_top_sample": [True],
        }
    )

    display = app._index_etf_universe_display_frame(frame)

    assert "追踪指数" in display.columns
    assert "映射来源" in display.columns
    assert "置信度" in display.columns
    assert display.iloc[0]["映射来源"] == "名称推断"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_research_display_labels.py::test_index_etf_universe_display_uses_chinese_headers -v`

Expected: FAIL because helper does not exist.

- [ ] **Step 3: Implement UI helpers and research routing**

Implementation requirements:

- `_tab_research` title becomes `策略实验室`.
- `策略库` shows loaded strategies with status and parameters.
- `新建策略` shows a parameterized form and calls `append_research_candidate` on submit.
- `运行回测` uses index ETF pool selection:
  - build universe from `store.list_etf_master()` and `parquet_store`
  - let user choose one or more indexes
  - derive `research_codes = selected_etf_codes(universe, selected_index_codes)`
  - show task size before confirm
  - call `job_manager.start(..., etf_codes=research_codes, scope_text="指数ETF池")`
- `策略比较`, `ETF复盘`, and existing result displays remain based on CSV outputs.
- `指数过滤实验` renders `_render_index_filter_explorer`.
- `指数ETF池` renders `_render_index_etf_pool`.

- [ ] **Step 4: Run UI tests**

Run: `pytest tests/test_ui_navigation.py tests/test_research_display_labels.py -v`

Expected: PASS.

---

### Task 5: Full Verification

**Files:**
- All modified files.

**Interfaces:**
- Consumes: completed Tasks 1-4.
- Produces: verified working suite.

- [ ] **Step 1: Run focused research tests**

Run: `pytest tests/test_index_etf_universe.py tests/test_research_cli_config.py tests/test_research_experiment.py tests/test_research_signals.py -v`

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 3: Manual UI smoke check if Streamlit can run**

Run: `streamlit run src/etf_trading/ui/app.py`

Expected: app opens with `策略实验室`, market has no `指数买卖参考`, and `指数ETF池` displays rows when local data exists.

If Streamlit cannot run inside the environment, report this explicitly and provide the test evidence instead.

## Self-Review

Spec coverage:

- Market map removal of unverified index advice: Task 1.
- Strategy lab pages: Task 1 and Task 4.
- ETF strategy object and parameterized form: Task 3 and Task 4.
- Index ETF pool and Top 10 selection: Task 2 and Task 4.
- Tracking index, source, confidence display: Task 2 and Task 4.
- Index-scoped backtest task size: Task 4.
- Adopted-only daily action groundwork: Task 3; daily action integration remains conservative because existing daily action still uses legacy strategy signals until adopted strategy execution is implemented.

No placeholder terms are intentionally present. First phase deliberately excludes official external data ingestion and page-level Python custom strategies.
