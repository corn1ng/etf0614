# Task 5 report: versioned index trend evidence publishing

## Delivered

- Added `index_report.py` with a ten-artifact evidence package, staging-directory
  validation, atomic directory/pointer replacement, strict latest-only loading,
  safe unique run IDs, JSON finite-value protection, and a zero-admission guard.
- Added the fixed-order Chinese conclusion-first report.  It states the index-only
  limitation, distinguishes prospective evidence, preserves failures as failures,
  and exposes every gate's actual evidence, pre-committed threshold, and reason.
- Added `run_and_publish_index_research(...)` as the common runner used by the
  direct CLI.  It hashes the locked config, reads local Parquet through Task 1
  admission, records real metadata, and marks `--limit` runs as limited.
- Added discriminating publication, corruption, schema, report, runner, zero
  admission, and CLI help tests.

## RED evidence

Initial feature RED:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task5-red
```

Result: expected collection failure:
`ModuleNotFoundError: No module named 'etf_trading.research.index_report'`.

Strict CSV schema RED:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task5-schema-red
```

Result: 15 passed and one expected failure because the loader did not reject a
latest-target results CSV missing required columns.

Gate-reporting RED:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task5-report-gates-red
```

Result: 16 passed and one expected failure because the Chinese report had not
shown the pre-committed threshold next to each gate's actual value.

Zero-admission RED:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task5-zero-admission-red
```

Result: 16 passed and one expected failure because an empty admission could have
published a misleading zero-index package.

## GREEN and verification

Final report suite:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task5-green9
```

Result: `17 passed in 1.46s`.

Required focused suite:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_report.py tests\test_index_research_validation.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task5-focused-final
```

Result: `39 passed in 12.54s`.

Required full suite:

```powershell
.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task5-full-final
```

Result: `539 passed, 1 skipped in 40.81s`.

## Real two-index smoke

The worktree has no local `data/parquet/indexes`; the main workspace data root was
checked read-only and does contain local index Parquet files.  The smoke used that
absolute root without changing it and wrote only to a separate temporary report
root:

```powershell
.venv-win\Scripts\python.exe scripts\run_index_research.py --limit 2 --parquet-root H:\pythonproject\etf0614\etf0614\data\parquet --report-root C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task5-smoke-final
```

Result: exit code 0; run ID `20260730T163010179800Z-01017ace8a`; cutoff
`2026-07-28`; `official_count=2`; `limited_run=true`; all ten required artifacts
and `latest.json` were present.  The package correctly reported `failed`, not a
success claim: gates 1, 2, and 5 passed; gates 3, 4, and 6 failed.  The report
contains the actual values, fixed thresholds, and reasons for each gate, and
records that there is no prospective sample after the lock date.

## Self-check and limits

- A write, validation, rename, or pointer-update exception leaves the pre-existing
  `latest.json` untouched; failed staging cleanup never masks the original error.
- Loader reads exactly the pointer's formal run, rejects staging and corrupted
  artifacts/metadata, and validates required CSV columns plus Parquet readability.
- CSV identity fields are loaded as strings so index identifiers retain leading
  zeros. JSON rejects NaN/Infinity; dates and timezone-bearing run time are stored
  in reversible ISO form.
- The two-index smoke is explicitly limited and is not a full-universe conclusion.
  The first phase remains an index theoretical backtest, not ETF implementation
  evidence.
