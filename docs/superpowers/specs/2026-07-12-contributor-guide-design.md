# Contributor Guide Design

## Goal

Replace the current `AGENTS.md` with a 200–250 word contributor guide that is fast to scan and specific to this Python ETF workbench. Preserve the repository's Task Memory requirement while moving extended explanations to existing documentation.

## Content

The guide will use the required title, `Repository Guidelines`, and six compact sections:

1. Project structure: identify `src/etf_trading/`, `tests/`, `scripts/`, `configs/`, and ignored runtime output directories.
2. Development commands: show editable installation, NiceGUI and Streamlit startup, full pytest, and one representative research command using cross-platform `python` invocations.
3. Style and naming: specify four-space indentation, type hints, standard Python naming, `pathlib.Path`, and configuration-driven parameters.
4. Testing: document pytest discovery and deterministic, network-free unit tests.
5. Task Memory: require reading and updating `docs/task-memory.md`, with that file carrying the detailed entry format.
6. Commits and pull requests: reflect the repository's Conventional Commit-like history and require impact, verification, configuration notes, and UI screenshots when applicable.

The guide will link to `README.md` for workflow detail and `docs/task-memory.md` for agent memory instructions. It will not duplicate lengthy setup, architecture, or security explanations. A short reminder will still prohibit secrets and generated data from commits.

## Validation

Confirm the document is within the requested word range, contains no placeholders, uses valid Markdown headings and fenced commands, and references only paths and commands present in the repository.
