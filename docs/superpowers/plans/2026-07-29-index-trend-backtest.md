# Index Trend Backtest Implementation Plan

This earlier English plan has been superseded after the strategy was simplified and locked on 2026-07-30.

The canonical, executable implementation plan is now the Chinese document:

[`2026-07-29-index-trend-backtest-zh.md`](2026-07-29-index-trend-backtest-zh.md)

It replaces the former MA/momentum/channel parameter research with:

- fixed `index_trend_v1` rules;
- MA60 ±2% hysteresis bands;
- a 3×ATR20 emergency close-based exit;
- all eligible official history and rolling five-year windows;
- 0%/2%/3% buffer ablation only, with no parameter selection;
- prospective out-of-sample tracking beginning after the 2026-07-30 lock date;
- page-triggered background reruns after index data updates;
- index-theory testing in phase one, with ETF execution validation deferred to a separately approved phase two.
