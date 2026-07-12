# ETF Research Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-pass research framework that can compare A-share ETF trend candidates with repeatable backtests, risk metrics, segment tables, and CSV outputs.

**Architecture:** Add a separate `etf_trading.research` package so research code does not distort the existing daily advisory strategy. Candidate rules generate close-of-day signals, the existing `BacktestEngine` executes them at next-day open, and research metrics summarize the result for ranking and later data-source upgrades.

**Tech Stack:** Python 3.11, pandas, existing strategy features, existing backtest engine, pytest.

---

### Task 1: Research Models And Metrics

**Files:**
- Create: `src/etf_trading/research/__init__.py`
- Create: `src/etf_trading/research/models.py`
- Create: `src/etf_trading/research/metrics.py`
- Test: `tests/test_research_metrics.py`

- [ ] **Step 1: Write failing tests**

Add tests that construct a simple `BacktestResult` with one completed trade and assert that `summarize_backtest()` reports total return, annualized return, volatility, Sharpe ratio, max drawdown, Calmar ratio, trade count, win rate, and average holding days.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest tests/test_research_metrics.py -q`
Expected: fail because `etf_trading.research.metrics` does not exist.

- [ ] **Step 3: Implement minimal code**

Create dataclasses for research candidates/results and implement metric calculations from NAV and trade lists.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_research_metrics.py -q`
Expected: pass.

### Task 2: Candidate Signal Generation

**Files:**
- Create: `src/etf_trading/research/signals.py`
- Test: `tests/test_research_signals.py`

- [ ] **Step 1: Write failing tests**

Add tests for a right-side candidate that buys only after price is above entry and trend moving averages, blocks overextended entries, and exits after the exit moving average breaks.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest tests/test_research_signals.py -q`
Expected: fail because `generate_candidate_signals()` does not exist.

- [ ] **Step 3: Implement minimal code**

Generate `StrategySignal` objects from featured price rows, using close-of-day conditions and preserving no-lookahead execution through the existing backtest engine.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_research_signals.py -q`
Expected: pass.

### Task 3: Experiment Runner And Ranking

**Files:**
- Create: `src/etf_trading/research/experiment.py`
- Test: `tests/test_research_experiment.py`

- [ ] **Step 1: Write failing tests**

Add tests that run two candidates over multiple synthetic ETFs, return one row per ETF/candidate, include metric columns, and produce an aggregate candidate ranking.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest tests/test_research_experiment.py -q`
Expected: fail because `StrategyExperimentRunner` and `rank_candidates()` do not exist.

- [ ] **Step 3: Implement minimal code**

Use `generate_candidate_signals()`, `BacktestEngine.run_single_etf()`, and `summarize_backtest()` to create reproducible result tables.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_research_experiment.py -q`
Expected: pass.

### Task 4: Local Research CLI

**Files:**
- Create: `configs/research.yaml`
- Create: `scripts/run_research.py`
- Test: `tests/test_research_cli_config.py`

- [ ] **Step 1: Write failing tests**

Add a test that loads candidate definitions from YAML and checks that names and numeric parameters become `StrategyCandidate` objects.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest tests/test_research_cli_config.py -q`
Expected: fail because config loading helper does not exist.

- [ ] **Step 3: Implement minimal code**

Add a CLI that reads local Parquet ETF prices, runs configured candidates, and writes `reports/research/research_results.csv` plus `reports/research/candidate_ranking.csv`.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_research_cli_config.py -q`
Expected: pass.

### Task 5: Full Verification

**Files:**
- Existing test suite.

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Inspect git diff**

Run: `git diff --stat`
Expected: only research framework files, tests, config, and this plan changed.
