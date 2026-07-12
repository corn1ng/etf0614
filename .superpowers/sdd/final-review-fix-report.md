# Final Review Fix Report

## Scope

Implemented the complete final-review fix wave in the isolated worktree:

- Added immutable, transient normalized positions for stored finite close, MA20, MA60, MA120, and MA250 facts.
- Rendered a position-based MA ladder with named `收盘` and `MAxx` markers, numeric stored values, and retained `收盘在 MAxx 上方/下方` wording.
- Suppressed the complete ladder when a required trend fact is unavailable or non-finite.
- Rendered `result.generated_at` in `状态概览` without loading, recalculating, or writing data.
- Made the range rail endpoints and distances explicit as `20日低点 / 距低点` and `20日高点 / 距高点`.

## Files changed

- `src/etf_trading/nicegui_app/view_models.py`
- `src/etf_trading/nicegui_app/pages/market.py`
- `src/etf_trading/nicegui_app/theme.py`
- `tests/test_nicegui_view_models.py`
- `tests/test_nicegui_app_import.py`
- `tests/test_nicegui_theme.py`
- `docs/task-memory.md`

## TDD evidence

All commands were run from `H:\pythonproject\etf0614\etf0614\.worktrees\index-atomic-detail-readability-sdd-20260713` with:

```powershell
$env:PYTHONPATH = "H:\pythonproject\etf0614\etf0614\.worktrees\index-atomic-detail-readability-sdd-20260713\src"
```

### RED: final-review regression wave

```powershell
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py tests\test_nicegui_theme.py -q -k 'normalizes_finite_stored_trend_heights or hides_trend_for_computed_nonfinite_close_or_ma or overview_renders_snapshot_generation_time or trend_ladder_rendering_uses_named_normalized_markers or range_rail_labels_both_endpoints or positioned_index_atomic_ma_ladder_markers' --basetemp 'C:\Users\cjj\AppData\Local\Temp\index-atomic-detail-final-review-red'
```

Result: expected exit 1; 7 failures. They were all missing requested behavior: the marker view-model field, normalized rendering helper, snapshot-generation text helper, range-rail label helper, and positioned marker CSS.

### GREEN: final-review regression wave

```powershell
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py tests\test_nicegui_theme.py -q -k 'normalizes_finite_stored_trend_heights or hides_trend_for_computed_nonfinite_close_or_ma or overview_renders_snapshot_generation_time or trend_ladder_rendering_uses_named_normalized_markers or range_rail_labels_both_endpoints or positioned_index_atomic_ma_ladder_markers' --basetemp 'C:\Users\cjj\AppData\Local\Temp\index-atomic-detail-final-review-green'
```

Result: exit 0; `7 passed, 83 deselected`.

### RED/GREEN: MA marker stacking follow-up

```powershell
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_theme.py -q -k 'positioned_index_atomic_ma_ladder_markers' --basetemp 'C:\Users\cjj\AppData\Local\Temp\index-atomic-detail-final-review-css-red'
```

Result: expected exit 1; 1 failure for the absent foreground label stacking rule.

```powershell
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_theme.py -q -k 'positioned_index_atomic_ma_ladder_markers' --basetemp 'C:\Users\cjj\AppData\Local\Temp\index-atomic-detail-final-review-css-green'
```

Result: exit 0; `1 passed, 9 deselected`.

## Final verification

```powershell
git diff --check
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py tests\test_nicegui_theme.py tests\test_nicegui_navigation.py tests\test_index_health_snapshot.py -q --basetemp 'C:\Users\cjj\AppData\Local\Temp\index-atomic-detail-final-review-focused-final'
```

Result: exit 0; `102 passed in 1.72s`. `git diff --check` produced no errors.

```powershell
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest -q --basetemp 'C:\Users\cjj\AppData\Local\Temp\index-atomic-detail-final-review-full-final'
```

Result: exit 0; `428 passed in 28.85s`.

## Self-review

- The normalization is a frozen view-model projection over only the stored close/MA rows; it accepts only finite values and emits no persisted or domain indicator.
- `trend.visible` requires all close, MA, and directional source facts plus a complete marker set; otherwise the renderer returns the existing text-only unavailable state.
- The page still calls only `load_index_atomic_snapshot_readonly`; no snapshot builder, external fetch, or storage write was added.
- The changes add no score, rank, forecast, target, or trading conclusion. Direction remains explicit text; normal computed statuses remain hidden in detailed facts; CSS remains scoped to `index-atomic-*`.

## Remaining browser-QA risk

This worktree has no generated atomic snapshot. Therefore, no browser QA was run or claimed for the ready, stale, failed, or insufficient-data overview dialog at 1440px/390px. That real-data QA remains required when a generated snapshot is available.

## Commit

Commit subject: `fix: complete index atomic detail overview`. This report is included in that same commit; its final object ID is recorded in the task handoff because a commit cannot accurately contain its own post-commit ID.
