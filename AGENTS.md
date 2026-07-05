# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.11 ETF trading research and Streamlit workbench. Core package code lives in `src/etf_trading/`, organized by domain: `data/` for AkShare providers and storage, `strategy/` and `risk/` for signal and sizing logic, `backtest/` for simulation, `research/` for candidate experiments, `report/` for summaries, and `ui/` for the Streamlit app. CLI entry points are in `scripts/`. Configuration files are in `configs/`. Tests mirror the package behavior in `tests/test_*.py`. Generated local state belongs in ignored paths: `data/`, `database/*.sqlite`, `logs/`, and `reports/`.

## Build, Test, and Development Commands

Create or update the local environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Run the app locally:

```bash
.venv/bin/streamlit run app.py
```

Run the full test suite:

```bash
.venv/bin/python -m pytest
```

Run common workflows:

```bash
.venv/bin/python scripts/update_data.py
.venv/bin/python scripts/run_backtest.py
.venv/bin/python scripts/run_research.py --limit 20
```

`run_research.py` reads `configs/research.yaml` and writes CSV outputs under `reports/research/`.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints for public functions, and concise docstrings for modules or non-obvious domain logic. Keep package modules lowercase with underscores, for example `position_sizing.py`; use `PascalCase` for dataclasses such as `StrategyCandidate`; use `snake_case` for functions, variables, and test names. Prefer `pathlib.Path` for filesystem paths and pandas DataFrames for tabular market data. Keep configuration-driven behavior in YAML files under `configs/` rather than hard-coding strategy parameters.

## Testing Guidelines

Pytest is configured in `pyproject.toml` with `testpaths = ["tests"]` and `pythonpath = ["src"]`. Add tests as `tests/test_<feature>.py` and name cases `test_<behavior>`. Prefer deterministic fixtures and small in-memory DataFrames; avoid live AkShare/network calls in unit tests. Run `python -m pytest` before submitting, and add targeted tests for strategy, risk, storage, or research changes that alter calculations.

## Task Memory

Before starting substantive work, read `docs/task-memory.md` when it exists and apply the project-specific reminders there. After every task that changes files or project behavior, append a short dated entry to `docs/task-memory.md` before the final response.

Each entry should include a brief summary, verification command or an explicit reason verification was not run, and 1-3 reusable "watch out next time" notes. Keep the notes actionable and deduplicated: capture lessons that can prevent future mistakes, not a raw activity log.

## Commit & Pull Request Guidelines

History uses Conventional Commit style, especially `feat: ...`; follow that pattern with imperative subjects such as `fix: handle missing ETF category`. Keep commits focused and avoid including generated `data/`, `database/`, `logs/`, or `reports/` artifacts. Pull requests should describe the user-facing or research impact, list verification commands run, note config changes, and include screenshots only for Streamlit UI changes.

## Security & Configuration Tips

Do not commit secrets or local credentials; `.streamlit/secrets.toml` is ignored. Treat generated market data and SQLite files as reproducible local cache. When changing data-source behavior, document any new external dependency or rate-limit assumption in the relevant config or README.
