# Data Trust Layer Design

## Scope

This first refactor makes local market-data readiness a shared, testable rule for ETF and index diagnostics. It fixes contradictory freshness/status counts and prevents stale or insufficient-history ETFs from appearing in opportunity rankings. It does not expand the security catalogue, add HKEX-listed ETF coverage, change strategy formulas, or fetch external data.

## Goals

- Give every ETF and index history one primary, mutually exclusive readiness status: `ready`, `stale`, `short_history`, `missing_history`, or `read_failed`.
- Preserve overlapping reasons separately. For example, a new ETF whose latest bar is old is primarily `stale` and also records `short_history` as a reason.
- Use the same assessment in atomic indicators, ETF overview, maintenance gaps, coverage totals, and index summaries.
- Separate source freshness from feature availability and snapshot generation time.
- Exclude any ETF that is not fresh, has insufficient history, or lacks required features from opportunity rankings and opportunity counts.
- Ensure every health headline counts unique assets; detailed reason chips may overlap but never become the total.

## Non-goals

- No new external market-data dependency or automatic batch refresh in this phase.
- No scoring, buy/sell recommendation, or strategy parameter change.
- No attempt to infer missing ETF tracking-index mappings or replace the current curated index list.
- No schema migration. Existing SQLite and Parquet files remain readable.

## Data Model

Create `etf_trading.data.quality` as the single owner of local history assessment.

`HistoryReadiness` is a string enum with `ready`, `stale`, `short_history`, `missing_history`, and `read_failed`. `HistoryAssessment` contains the primary status, latest local trading date, expected local trading date, history row count, trading-day lag, and a tuple of reason codes.

`assess_price_history(prices, expected_trade_date, min_history_rows)` evaluates a successfully read price frame. Callers convert read exceptions to `read_failed` and empty frames to `missing_history`. The primary-status precedence is `read_failed`, `missing_history`, `stale`, `short_history`, then `ready`. The reasons tuple retains every applicable condition.

`expected_latest_trade_date(as_of, holidays=())` keeps the current weekday behaviour but accepts explicit exchange-holiday dates. `trading_day_lag` uses the same calendar input, so page data can declare the calendar assumption rather than silently using a business-day approximation.

## Data Flow

```text
Parquet price frame / read error
        -> assess_price_history
        -> HistoryAssessment
        -> ETF overview + maintenance gaps + atomic snapshot
        -> view-model summaries and filters
        -> NiceGUI health/status presentation
```

The atomic snapshot keeps existing `history_status` and `feature_status` fields for compatibility, and adds readiness evidence: `expected_trade_date`, `trading_day_lag`, `history_reason_codes`, and `is_rank_eligible`.

Technical indicators remain visible in the diagnostic view whenever they can be calculated. Their return ranks, breakout count, weekly-strength count, and opportunity-table membership are computed only for `is_rank_eligible == True`. This avoids treating a technically calculable but stale price series as a current opportunity.

## UI Semantics

- The shell labels `generated_at` as `页面计算` or `快照生成`, never as `数据更新`.
- ETF health uses the primary readiness status for the mutually exclusive asset breakdown and uses one unique `需关注 ETF` total.
- Feature gaps are shown as a secondary diagnostic factor rather than added to the primary total.
- The opportunity view defaults to rank-eligible ETFs. The health view contains all ETFs and exposes primary status, extra reasons, expected date, latest date, and lag.
- Filtered atomic tables must retain the complete filtered set for pagination; they may not silently cap it at 300 rows.

## Error Handling

One unreadable Parquet file produces `read_failed` for that asset and cannot prevent snapshot generation. Invalid or absent trade-date values are treated as unreadable history. Empty histories are `missing_history`. The view displays the assessment reason and directs repair actions to the maintenance workflow.

## Testing and Acceptance

- Weekend and explicit-holiday calendars produce the expected latest tradable date and lag.
- A stale-and-short asset has primary status `stale` and contains both reason codes.
- Primary readiness counts sum to the ETF pool total; the unique issue total is never greater than that total.
- A stale, short, missing, or feature-incomplete ETF has no opportunity rank and is absent from the opportunity table.
- A ready, feature-complete ETF retains its existing indicator and rank behaviour.
- ETF overview and maintenance gaps report the same status for the same local frame.
- Page snapshot time is not labelled as source-data update time.
- Full pytest and desktop/mobile NiceGUI smoke checks remain green.

## Follow-up Phases

After this foundation is stable, the next independent changes are: exchange-calendar integration, full index/ETF catalogue ingestion, tracking-index mapping lineage, and classification corrections. Those changes remain separate because they alter source coverage rather than readiness semantics.
