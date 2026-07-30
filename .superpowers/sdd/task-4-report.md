# Task 4 report: locked index trend V1 validation

## Delivered

- Added the deterministic research matrix in `index_validation.py`: full-history,
  calendar-year, named-stage, complete five-calendar-year rolling, buffer ablation,
  doubled-cost stress, and strictly post-lock prospective outputs.
- Added immutable output contracts for the matrix and six-gate assessment.
- Added validation tests for matrix coverage, calendar windows, prospective boundary,
  official-only aggregation, each safe failure mode, stress recomputation,
  deterministic ordering/progress/cancellation, and reporting aggregates.

## RED evidence

Command:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_validation.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task4-red
```

Result: collection failed as expected with
`ModuleNotFoundError: No module named 'etf_trading.research.index_validation'`.

## GREEN evidence

Focused command:

```powershell
.venv-win\Scripts\python.exe -m pytest tests\test_index_research_validation.py tests\test_index_research_data.py tests\test_index_trend_v1.py tests\test_index_research_backtest.py tests\test_index_research_metrics.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task4-focused
```

Result: `63 passed in 8.85s`.

Full command:

```powershell
.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-trend-v1-task4-full
```

Result: `512 passed, 1 skipped in 37.26s`.

## Design choices and self-check

- Results are sorted by index, period, strategy, and label so input dictionary order
  cannot affect output order.  Cancellation is checked before each index and raises
  `IndexResearchCancelled`, never returning a partial output.
- Each evaluation starts empty.  V1 receives only one preceding row for an initial
  crossover comparison; its NAV is filtered strictly to the evaluation range.  Buy
  and hold receives no preceding row, so it buys only at the evaluation start.
- The gates fail closed for empty official pairs, non-finite metrics, zero buy-hold
  drawdown, missing buffer evidence, and invalid stress evidence.  Main gates and
  rolling pass rate use official rows only; reference rows remain in their own
  outputs and group statistics.
- The post-lock sample is `trade_date > locked_at`; when absent the output records
  `no_prospective_sample` rather than treating an empty sample as evidence.

## Known limits

This task supplies in-memory research outputs only.  Versioned artifact publishing,
  report rendering, background execution, and the complete real-index run are
  intentionally reserved for later tasks.

## Commit

Pending commit: `feat: validate locked index trend v1`.
