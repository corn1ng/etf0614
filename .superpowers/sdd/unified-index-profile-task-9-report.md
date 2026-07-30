# Task 9: Read-Only Cross-Index Valuation Comparison Report

## RED

Added regression coverage for the market-section order, the official-valuation row projection, and the page's provider/synchronization import boundary. The focused command failed as expected: the “指数估值” section and the official valuation comparison row model did not exist (2 failures, 96 passes).

## GREEN

Added the “指数估值” section after “指数体检”. It reads only the published unified index snapshot through the read-only snapshot loader, projects the six configured official mappings in stable configured order, and renders a compact table of PE/PB, independent five-year percentiles, freshness, and source. Empty, missing, and failed states direct users to “数据维护 -> 补齐任务”; non-ready snapshots remain explicitly labelled. Unsupported rows are excluded, and not-synced/stale labels remain transparent without fetching, calculation, writes, scores, rankings, or trading conclusions.

## Tests

- RED: H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_navigation.py tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-comparison-red — expected 2 failures.
- GREEN: same selection with --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-comparison-green — 98 passed.
- Full: H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-comparison-full — 517 passed, 1 skipped, 2 existing pandas warnings.

## Files

- src/etf_trading/nicegui_app/navigation.py
- src/etf_trading/nicegui_app/view_models.py
- src/etf_trading/nicegui_app/pages/market.py
- tests/test_nicegui_navigation.py
- tests/test_nicegui_view_models.py
- tests/test_nicegui_app_import.py

docs/task-memory.md was intentionally left unstaged as required.

## Commit

feat: add index valuation comparison page

## Self-check

- The page consumes a published unified snapshot only; it imports no provider or synchronization service.
- UI presentation contains only official valuation facts, percentiles, freshness/status, and source.
- Page interaction does not perform network access, metric calculation, or data writes.
- Browser QA was not performed; Task 10 owns it.

## Review Follow-up

### RED

Added a route-policy regression plus a rendered-shell lifecycle regression for “指数估值”; both failed because the route selected full snapshot initialization. Added a comparison-row regression for a not-synced official mapping and stale freshness; it failed because the not-synced mapping was filtered. Focused RED: 3 failures, 93 passes.

### GREEN

The valuation section now shares the atomic-index snapshot policy with index health, so shell rendering uses the lightweight maintenance snapshot rather than load_snapshot_cached. Comparison projection excludes only explicit unsupported rows, retains official not-synced/stale rows, and renders their profile-specific Chinese status labels.

### Verification

- Focused GREEN: tests/test_nicegui_app_import.py + tests/test_nicegui_view_models.py — 96 passed.
- Related: tests/test_nicegui_navigation.py + tests/test_nicegui_app_import.py + tests/test_nicegui_view_models.py + tests/test_nicegui_state_cache.py — 129 passed.
- Full: 519 passed, 1 skipped, 2 existing pandas warnings.

### Follow-up Commit

fix: keep index valuation comparison readonly

## Second Review Follow-up

### RED

Added a recorded-store shell lifecycle regression. It failed because atomic_index reused the maintenance snapshot loader, which invoked initialize_schema. Added a state projection regression and changed the unsynced comparison fixture to the canonical shape: valuation_support_status is not_synced and valuation_freshness_status is empty. The projection initially showed “数据不足”. Focused RED finished with 3 failures, 123 passes; a follow-up renderer boundary test failed because the valuation section still created a store.

### GREEN

Atomic-index shell rendering now uses a dedicated published-snapshot projection that accepts only the parquet store and never accesses SQLite. The valuation renderer now also reads its published snapshot without creating a store. Its state label uses freshness when present, otherwise the support state, so canonical not-synced rows display “官方估值尚未同步”. Index health retains the atomic-index route policy and its page-level read contract.

### Verification

- Focused GREEN: tests/test_nicegui_app_import.py + tests/test_nicegui_view_models.py + tests/test_nicegui_state_cache.py — 127 passed.
- Related: the focused files plus navigation and index health snapshot coverage — 165 passed, 2 existing pandas warnings.
- Full: 521 passed, 1 skipped, 2 existing pandas warnings.

### Follow-up Commit

fix: make index valuation shell snapshot readonly
