# Task 8: Unified Index Profile Dialog Report

## RED

Added structure and CSS regression tests for the exact five profile tabs, read-only boundary, profile width, scoped grids, and mobile layout. The focused UI command failed as expected: the profile tabs and `.index-profile-*` CSS were absent (2 failures, 56 passes).

## GREEN

Implemented `_open_index_profile_dialog(result, index_code)` as a read-only projection of `result.summary` and `result.details` through `index_profile_view`. Row click now opens the five-tab dialog: 画像总览, 估值详情, 趋势与风险, 全部指标, 数据质量. Added `index-profile-*` styling with `width: min(1180px, 92vw)`, responsive single-column grids, and horizontally scrollable narrow-screen tabs. Unsupported, missing, stale, and insufficient states stay textual; no score, recommendation, market breadth, request, calculation, or write was added.

## Tests

- RED: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_app_import.py tests\test_nicegui_theme.py tests\test_nicegui_navigation.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-ui-red` — expected 2 failures.
- GREEN: same command with `--basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-ui-green` — 58 passed.
- Full: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-ui-full` — 513 passed, 1 skipped, 2 existing pandas warnings.

## Files

- `src/etf_trading/nicegui_app/pages/market.py`
- `src/etf_trading/nicegui_app/theme.py`
- `tests/test_nicegui_app_import.py`
- `tests/test_nicegui_theme.py`

`docs/task-memory.md` was intentionally left unstaged as required.

## Commit

`feat: redesign unified index profile dialog`

## Self-check

- Five labels are exact and ordered as approved.
- Close button and NiceGUI tab accessibility are preserved.
- No external work is registered by opening or switching tabs.
- Browser visual QA was not performed; Task 10 owns it.
