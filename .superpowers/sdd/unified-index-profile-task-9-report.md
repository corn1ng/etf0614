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
