# Task Memory

## 2026-07-30 - Add durable official valuation maintenance task

- Summary: Added a resumable NiceGUI maintenance task for the six explicit official-index valuation mappings. It persists per-index progress and redacted failures, restores the latest task after page refresh, offers an explicit catalog-panel trigger, and localizes valuation-sync states.
- Verification: `H:\\pythonproject\\etf0614\\etf0614\\.venv-win\\Scripts\\python.exe -m pytest -q --basetemp C:\\Users\\cjj\\AppData\\Local\\Temp\\index-profile-maintenance-full` passed with 463 tests and 1 skipped.
- Watch out next time:
  - The official valuation provider route is intentionally Tushare-primary only; do not add AkShare fallback to `fetch_index_official_valuations`.
  - Any persisted failure must be redacted before it reaches SQLite or the maintenance page; keep the token environment-only.
  - Include durable task types in both initial restored-run selection and timer refresh selection.

## 2026-07-30 - Reject invalid official valuation index codes

- Summary: Hardened official valuation synchronization so a non-empty provider response must contain a non-null `index_code` matching the index currently being synchronized before any cache write occurs.
- Verification: `H:\\pythonproject\\etf0614\\etf0614\\.venv-win\\Scripts\\python.exe -m pytest -q --basetemp C:\\Users\\cjj\\AppData\\Local\\Temp\\index-profile-sync-index-code-full` passed with 459 tests and 1 skipped.
- Watch out next time:
  - A valid date and valuation metric are insufficient: every returned row must belong to the requested index before deduplicating or writing.
  - Test cache-preservation paths with a write-recording store as well as persisted-frame equality, so a rejected response cannot cause even a transient write.

## 2026-07-30 - Synchronize official index valuation cache

- Summary: Added an idempotent official-valuation synchronization service for the six explicit Tushare index mappings. It performs a 2004-01-01 first fill, date-bounded incremental updates, deduplicated merges, progress callbacks, response-schema validation, and redacted failure reporting; empty or failed calls leave a successful cache untouched.
- Verification: `H:\\pythonproject\\etf0614\\etf0614\\.venv-win\\Scripts\\python.exe -m pytest -q --basetemp C:\\Users\\cjj\\AppData\\Local\\Temp\\index-profile-sync-full-final` passed with 456 tests and 1 skipped.
- Watch out next time:
  - Call `fetch_index_official_valuations` directly; valuation sync must never fall back to AkShare.
  - Validate a non-empty response has `trade_date` plus at least one valuation metric before replacing cache contents.
  - Keep provider errors redacted before they enter a result frame, progress record, UI, or log.

## 2026-07-19 - Unified Tushare index routing

- Summary: Removed category-based Tushare skips so every index history request reaches Tushare first; AkShare remains the fallback for empty, unsupported, permission, or network failures.
- Verification: `PYTHONPATH=src .venv-win\\Scripts\\python.exe -m pytest tests\\test_tushare_provider.py tests\\test_primary_fallback_provider.py tests\\test_provider_factory.py -q` passed 12 tests.
- Caution: Do not persist Tushare Tokens. The actual `data_source` remains the authoritative record of whether Tushare or AkShare supplied a row.

## 2026-07-19 - Implement Tushare-primary data access

- Summary: Added a Tushare-first provider factory with explicit AkShare fallback, shared configuration/rate limiting/redaction, ETF/index/calendar adapters, durable NiceGUI completed-with-fallback warnings, CLI warning summaries, and an opt-in live proxy smoke test. Tokens remain environment-only.
- Verification: Installed Tushare 1.4.29 into the workspace virtual environment; full offline suite passed 448 tests with one opt-in live test skipped because `TUSHARE_TOKEN` was unset.
- Watch out next time:
  - Set `TUSHARE_TOKEN` in the process environment before starting an app or running the live smoke test; do not put it in source, YAML, or shell history.
  - Unsupported Shenwan and Hong Kong index routes intentionally report a known capability gap and use AkShare.

## 2026-07-19 - Plan Tushare-primary data access

- Summary: Split the approved Tushare-primary integration into eight TDD deliverables covering runtime contracts, ETF data, index symbols/calendar, fallback/factory behavior, CLI wiring, NiceGUI persistence, Streamlit notices, and opt-in live verification.
- Verification: Plan self-review checks provider interfaces, QFQ semantics, durable warning state, secret handling, exact commands, and offline/live test separation.
- Watch out next time:
  - Complete provider boundaries before replacing application constructors so every entry point receives the same tested behavior.
  - Keep live proxy tests opt-in and pass credentials through the process environment only.

## 2026-07-19 - Add Chinese Tushare implementation plan

- Summary: Added a Chinese plan companion covering the approved Tushare-first integration, explicit AkShare fallback, data contracts, delivery stages, and acceptance criteria.
- Verification: Checked the document for placeholder markers, secret values, and whitespace errors.
- Watch out next time:
  - Keep source-code identifiers and shell commands unchanged when translating operational documentation.

## 2026-07-19 - Design Tushare-primary data access

- Summary: Approved a centralized `TushareProvider` plus `PrimaryFallbackProvider`: Tushare is attempted first, every unsupported or failed call produces a visible and durable warning, and AkShare can complete the operation without hiding the actual source.
- Verification: Documentation-only design; checked the specification for secret handling, adjustment semantics, provider provenance, persistent warning behavior, explicit scope, and placeholders.
- Watch out next time:
  - Never treat unadjusted `fund_daily` prices as `qfq`; a missing or unauthorized `fund_adj` response must trigger an explicit fallback.
  - Keep Tushare index symbols separate from AkShare `provider_symbol`; ambiguous mappings must fall back instead of relying on prefix guesses.
  - A successful fallback is neither pure success nor failure: persist and render a completed-with-warning state, and keep provider notices out of market-data Parquet columns.

## 2026-07-13 - Final-review readability fixes

- TDD evidence: the final-review regression wave first ran with the worktree interpreter and `PYTHONPATH` set to `src`; it failed as expected with 7 missing-marker/helper/CSS failures. After the display-only implementation, the same focused selection passed 7 tests. A follow-up CSS stacking regression first failed for the missing foreground marker label rule and then passed after the rule was added.
- Verification: focused NiceGUI/index-snapshot regression suite passed 102 tests. The full suite passed 428 tests before the CSS-only stacking follow-up; the final focused and full-suite reruns are recorded in `.superpowers/sdd/final-review-fix-report.md`.
- Browser QA: no generated atomic snapshot is available in this worktree, so the ready/stale/failed/insufficient overview dialog at 1440px and 390px was not browser-verified or claimed as verified.

## 2026-07-13 - Refine index atomic detail readability

- Summary: Added scoped responsive presentation for the stored index-atomic overview: four desktop cards, two at 960px, one at 720px, plus compact MA/range/timeline/evidence and expandable-group styling. The page only presents stored snapshot facts; absent atomic items draw neither MA ladders, range markers, nor synthetic events.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_theme.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-detail-theme-red` first failed as expected for the missing overview selector; the green rerun passed 9 tests. `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py tests\test_nicegui_theme.py tests\test_nicegui_navigation.py tests\test_index_health_snapshot.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-detail-focused` passed 97 tests, and `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-detail-full` passed 423 tests. Browser plugin not available; the local app at `http://127.0.0.1:8502/page/market/%E6%8C%87%E6%95%B0%E4%BD%93%E6%A3%80` was checked with local Chrome at 1440px and 390px: the missing-snapshot alert appeared, root horizontal overflow was absent, and no captured console errors/warnings occurred. This worktree has no generated atomic snapshot, so the overview dialog, stale, and failed snapshot states were not fabricated or passed as browser-verified.
- Watch out next time:
  - Keep all overview rules under `.index-atomic-*`; do not expand responsive changes into shared workbench or main-table selectors.
  - A visual QA result for the missing state does not prove the generated-snapshot dialog; rebuild a real local snapshot before claiming the card, tabs, or expandable indicator groups have been browser-tested.

## 2026-07-12 - Design readable index atomic detail

- Summary: Approved a detail-dialog readability redesign for `市场地图 -> 指数体检`: the renamed `状态概览` reads position, events, and evidence in that order, while expandable full groups preserve every atomic fact and data-quality audit trail. It makes no score, trend conclusion, or trading recommendation and does not change snapshot computation.
- Verification: User approved three design sections, including the visual hybrid mockup. The specification defines read-only inputs, missing-data behavior, responsive layout, and test coverage.
- Watch out next time:
  - Keep interval bars and moving-average ladders as display-only transformations of stored snapshot facts; do not add or persist derived indicators.
  - Use colour for data quality only; all direction and position states require explicit text labels.

## 2026-07-12 - Simplify the contributor guide

- Summary: Replaced `AGENTS.md` with a minimal repository-specific guide covering layout, commands, style, tests, Task Memory, and review hygiene; linked extended procedures to existing documentation.
- Verification: `python -m pytest -q` passed with 410 tests; Markdown word-count, required-content, placeholder, and whitespace checks passed.
- Watch out next time:
  - Keep detailed workflows in `README.md` or focused `docs/` files instead of expanding the root contributor guide.
  - Update both primary NiceGUI and fallback Streamlit commands when application entry points change.

## 2026-07-12 - Design the minimal contributor guide

- Summary: Defined a 200–250 word `AGENTS.md` that keeps repository-specific commands and Task Memory requirements while linking longer explanations to existing documentation.
- Verification: Documentation-only change; checked the design for concrete sections, repository paths, commands, and external-document boundaries.
- Watch out next time:
  - Keep `AGENTS.md` optimized for daily contribution; put detailed procedures in `README.md` or focused files under `docs/`.
  - Preserve the Task Memory link and update requirement even when shortening the guide.

Use this file as the project-level memory for future Codex tasks. Read it at the start of substantive work and update it after every task that changes files or project behavior.

Keep entries concise and reusable. Prefer lessons, constraints, verification notes, and project-specific pitfalls over a raw activity log.

## 2026-07-31 - Explain empty profile momentum and risk panel

- Summary: The read-only profile overview now renders `数据不足` when every compact momentum/risk section is empty, instead of leaving a title-only blank panel.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-compact-empty-full` passed with 514 tests, 1 skipped, and 2 existing pandas warnings.
- Watch out next time:
  - A compact summary panel needs an explicit textual unavailable state when its complete source collection is empty; do not rely on an empty visual region to communicate that state.

## 2026-07-31 - Render unified index profile dialog

- Summary: Replaced the index-health row-click target with a five-tab, read-only unified index profile dialog backed only by `index_profile_view`; it presents summary, valuation, trend/risk, all facts, and data quality without scores or recommendations.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-ui-full` passed with 513 tests, 1 skipped, and 2 existing pandas warnings.
- Watch out next time:
  - Keep dialog interactions presentation-only: do not start a snapshot build, valuation sync, fetch, or write on row click or tab switch.
  - Keep all new dialog selectors under `index-profile-*`, including mobile grid and tab-overflow rules.

## 2026-07-12 - Keep index atomic rebuild inputs coherent and configured

- Summary: Restored the configured non-reserve catalog order after SQLite's code-sorted read, while retaining persisted metadata and putting unknown persisted codes last deterministically. Every atomic writer now requires an expected input signature captured before calculation and re-checks the current store/catalog/coverage and local-history signature under the publish lock; a mismatch preserves the old snapshot and persists a Chinese failed result.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-final-fix-full` passed (338 tests).
- Watch out next time:
  - `SQLiteStore.list_index_catalog()` is code-sorted, so maintenance inputs that expose `catalog_order` must reapply `default_index_catalog()` order without replacing persisted fields.
  - Capture an input signature before reading local histories and verify it again immediately before atomic publication; never sign an old summary with a post-build signature.
  - The process-local publish lock detects a changed signature before publishing but is not a cross-process transaction.

## 2026-07-12 - Serialize index atomic snapshot rebuild starts

- Summary: Closed the same-process race between checking for a running atomic rebuild and scheduling a new one. The runner now serializes reconciliation, claim, active-key registration, and scheduling; an injected writer also makes runner-level publication rollback regressions deterministic.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-maintenance-concurrency-full-final` passed (320 tests).
- Watch out next time:
  - A persisted "running" query plus a later insert is not an atomic claim; protect their entire same-process transition, including background scheduling.
  - Register the active task key before scheduling, and remove it plus persist failure if scheduling raises.
  - Test runner-level publication failure at the final metadata replacement as well as Task 2's lower-level rollback contract.

## 2026-07-12 - Redesign index health as an atomic workbench

- Summary: Replaced `市场地图 -> 指数体检` with a read-only atomic-indicator workbench. It reads the maintenance snapshot through the persisted catalog/coverage inputs, keeps the eight Task 4 table columns, separates core and research pools, and opens a three-tab wide detail dialog instead of rendering health conclusions or valuation data.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-market-full-final-6` passed (332 tests). Regular Playwright at `http://127.0.0.1:8515` and `http://127.0.0.1:8516` checked missing, ready, stale, and failed snapshots at 1440px and 390px with no console errors/warnings or root horizontal overflow; evidence is under `C:\Users\cjj\AppData\Local\Temp\index-atomic-market-browser*`.
- Watch out next time:
  - Pass `index_atomic_snapshot_inputs(create_store())` into the read-only loader; rebuilding coverage from the display summary loses signature fields and marks a valid maintenance snapshot stale.
  - A page reload may only read the snapshot again. Keep rebuild actions in data maintenance and retain the last successful rows when the snapshot is stale.
  - Validate the missing, stale, and corrupt-meta failed states with local fixtures; none may fabricate table rows.

## 2026-07-12 - Close atomic workbench review findings

- Summary: Sanitized every Task 5 status and source display boundary so unknown values render as `未知状态` or `未知数据源`; projected the index workbench table to its exact eight visible Task 4 columns while retaining the hidden row key. Restored the unrelated index-chart event binding, metric, event-normalization, and audit-copy changes to the pre-Task-5 baseline.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-market-review-full` passed (334 tests). Seeded regular Playwright asserted the exact eight headers, hidden `index_code`, no visible `computed` or unknown provider code, and no console errors/warnings; evidence is `C:\Users\cjj\AppData\Local\Temp\index-atomic-market-browser-seeded\review-result.json`.
- Watch out next time:
  - A view-model formatter may use a raw-code fallback. Page render boundaries still need safe Chinese fallbacks for unknown status and source codes.
  - Generic table inference is insufficient for a fixed UX contract; explicitly project display fields before passing rows to the shared table helper.

## 2026-07-12 - Close final atomic main-table status review

- Summary: Sanitized the explicit main-table `data_status` projection itself, so a known internal code displays in Chinese and any unknown code displays `未知状态` before reaching the shared table component.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-main-status-full` passed (335 tests). Seeded Playwright confirmed the visible table contains `已计算`, not `computed`, preserves the eight headers, and records no console errors/warnings in `C:\Users\cjj\AppData\Local\Temp\index-atomic-market-browser-seeded\main-status-result.json`.
- Watch out next time:
  - Sanitizing a detail or status-bar boundary is not sufficient when a separately projected main-table field passes through the shared table renderer.

## 2026-07-12 - Add durable index atomic snapshot maintenance task

- Summary: Added a persisted, local-only maintenance runner and `数据维护 -> 指数目录与完整性` entry point for rebuilding index atomic indicators. The task records per-index progress, published snapshot metadata, and its result so it restores after a page reload.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-maintenance-full` passed (318 tests).
- Watch out next time:
  - Keep index atomic rebuilds local-only: use persisted catalogue/coverage plus Parquet histories; never construct an initialization service, provider, or page-time builder.
  - Pass the maintenance task ID into the atomic writer and only mark the run successful after its three-file snapshot publication succeeds.
  - Progress callbacks belong after each index's local calculation, so a restart can distinguish an interrupted rebuild from a completed snapshot.

## 2026-07-12 - Harden index atomic snapshot publication

- Summary: Added a process-local read/write lock plus a backup-and-rollback publish protocol for the three index atomic snapshot files. Coverage metadata is now required and verified independently before a snapshot can be ready.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-state-review-full-final` passed (311 tests).
- Watch out next time:
  - A multi-file cache needs rollback as well as per-file replacement; a last-file failure must restore every earlier file before releasing the reader lock.
  - The process-local lock provides coherent reads only inside this Python process. Do not describe it as a cross-process or object-store transaction.
  - Validate explicit metadata signatures even when their source inputs are also folded into a broader source signature; missing and malformed metadata need distinct failure handling.

## 2026-07-12 - Make index atomic snapshots maintenance-only

- Summary: Replaced the NiceGUI index health cache rebuild path with a versioned, three-file index atomic snapshot contract. Pages now only read, report missing/stale/failed state, and retain a temporary legacy-name read-only forwarder until the market page migration.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_index_health_snapshot.py tests\test_nicegui_state_cache.py tests\test_nicegui_app_import.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-state-focused` passed (34 tests).
- Watch out next time:
  - Keep every index snapshot build in maintenance; a page-time cache miss must return `missing`, never schedule or run a builder.
  - Treat the summary, details, and metadata files as one logical version: write all temporary files before replacing any live file, and publish metadata last.
  - Remove `load_index_health_snapshot_cached` and its no-op invalidator when the market page moves to `load_index_atomic_snapshot_readonly`.

## Entry Template

```md
## YYYY-MM-DD - <task>

- Summary: ...
- Verification: `command` passed, or Not run: <reason>.
- Watch out next time:
  - ...
```

## 2026-07-11 - 设计数据可信层

- 摘要：定义第一阶段数据层重构，以统一就绪状态、唯一健康统计和 ETF 机会排名准入为核心。
- 验证：仅文档审查；`rg -n "TBD|TODO|FIXME|待定|待补|不确定|implement later|fill in" docs/superpowers/specs/2026-07-11-data-trust-layer-design.md` 未返回匹配项。
- 下次注意：
  - 源数据新鲜度、技术特征可用性和页面快照时间必须是三类独立事实。
  - 诊断原因可以重叠，但摘要统计只能使用一个互斥的主就绪状态。
  - 所有用户可见状态使用中文；英文状态码只用于内部计算与存储。
  - 数据维护是完整事实来源，顶部栏和研究页面只展示与当前位置相关的状态摘要。

## 2026-07-11 - 计划数据可信层实施

- 摘要：将统一历史数据评估、原子指标准入、覆盖摘要、中文状态展示和浏览器验证拆成五个可独立验证的任务。
- 验证：文档自审；实施前必须从每个任务的失败测试开始。
- 下次注意：
  - 缓存的快照列变化必须同步升级缓存 schema 版本。
  - 机会列表的分页可限制页面显示，不能截断筛选结果本身。

## 2026-07-11 - Prepare isolated data-trust-layer worktree

- Summary: Added the project-local `.worktrees/` ignore rule so the forthcoming data-trust-layer refactor can run in an isolated Git worktree without tracking its files.
- Verification: `git check-ignore -v .worktrees/data-trust-layer` identifies the new ignore rule.
- Watch out next time:
  - Keep feature worktrees under the ignored `.worktrees/` directory so active local changes remain isolated.

## 2026-07-05 - Add task memory convention

- Summary: Added a project-level memory file and updated `AGENTS.md` so future Codex tasks read and update it.
- Verification: Documentation-only change; verified by reviewing `AGENTS.md` and `docs/task-memory.md`.
- Watch out next time:
  - Read `docs/task-memory.md` before substantive edits so project-specific reminders shape the work.
  - Append only reusable notes after each task; avoid duplicate reminders and raw step-by-step logs.
  - Include the verification command or a clear reason verification was not run.

## 2026-07-05 - Commit current project work

- Summary: Prepared the current project changes for a Git commit and added ignore rules for local runtime artifacts.
- Verification: `.venv-win\Scripts\python.exe -m pytest` passed with 144 tests.
- Watch out next time:
  - Do not stage local virtual environments such as `.venv-win/` or generated agent/runtime folders such as `.superpowers/`.
  - Re-run `git status --short --untracked-files=all` after ignore-rule changes so the staged set is visible and reviewable.

## 2026-07-05 - Design market and ETF page boundary

- Summary: Added the approved design for separating `市场地图` as an index decision layer from `ETF数据` as the ETF asset layer.
- Verification: Documentation-only change; `rg -n "TBD|TODO|待定|待补|不确定|FIXME" docs\superpowers\specs\2026-07-05-market-etf-boundary-design.md` returned no matches.
- Watch out next time:
  - Keep ETF K line views under `ETF数据`; `市场地图` should stay focused on index and market participation decisions.
  - Treat `指数样本池` as ETF mapping/sample attribution, not as an index analysis page.

## 2026-07-05 - Compact index quick buttons

- Summary: Made the index-watch quick buttons denser by expanding the common index shortcuts to 8 items and rendering them in an 8-column compact Streamlit grid.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q` passed with 146 tests.
- Watch out next time:
  - Keep quick-index shortcuts focused on first-screen benchmarks; broader discovery still belongs in the category/search picker.
  - In this PowerShell tool environment, background Streamlit startup can be unreliable; foreground `streamlit run` still confirms the app command starts.

## 2026-07-05 - Implement market and ETF page boundary

- Summary: Moved ETF chart drilldown into `ETF数据`, made `市场地图` focus on market/index overview, index buy/sell reference, and index K lines.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q` passed with 154 tests.
- Watch out next time:
  - Route market pages by decision workflow, not by ETF-versus-index asset type.
  - Keep `platform_status["index_summary"]` as the shared source for market overview and index reference pages.

## 2026-07-05 - Custom common index shortcuts

- Summary: Added local preference support for replacing common index shortcut slots and a compact expander UI for saving or resetting those shortcuts.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q` passed with 151 tests.
- Watch out next time:
  - Store UI-only shortcut preferences in `data/ui_preferences.json`; do not add database state for per-user Streamlit convenience controls.
  - Keep custom common-index lists validated, unique, and filled back to the 8-slot default shape so the quick grid remains stable.

## 2026-07-05 - Design ETF atomic indicator foundation

- Summary: Added the approved design for using full exchange-traded ETF coverage and an atomic-indicator dashboard as platform foundation before implementing relative-strength strategy logic.
- Verification: Documentation-only change; `rg -n "TBD|TODO|FIXME|待定|待补|不确定" docs\superpowers\specs\2026-07-05-etf-atomic-indicator-foundation-design.md` returned no matches.
- Watch out next time:
  - Treat `fund_etf_spot_em` as the exchange-traded ETF source of truth; do not merge `fund_name_em` directly into the tradable pool.
  - Show atomic indicators and data completeness first; keep weighted scores and buy/sell actions out of the foundation layer.

## 2026-07-05 - Design NiceGUI UI migration

- Summary: Added the approved design for migrating the primary UI layer from Streamlit to NiceGUI while preserving backend storage, data, and strategy logic.
- Verification: Documentation-only change; `rg -n "TBD|TODO|待定|待补|不确定|FIXME" docs\superpowers\specs\2026-07-05-nicegui-ui-migration-design.md` returned no matches.
- Watch out next time:
  - Keep NiceGUI work inside a new UI layer and extract only UI-neutral view models from Streamlit code when needed.
  - Keep Streamlit as a fallback until the NiceGUI high-frequency pages pass browser screenshot verification.

## 2026-07-05 - Add NiceGUI visual quality bar

- Summary: Updated the NiceGUI migration design to require auditing current UI problems and delivering a more polished, modern, professional quantitative-workbench interface.
- Verification: Documentation-only change; `rg -n "TBD|TODO|待定|待补|不确定|FIXME" docs\superpowers\specs\2026-07-05-nicegui-ui-migration-design.md` returned no matches.
- Watch out next time:
  - Do not merely port Streamlit layouts to NiceGUI; each migrated page should fix the old page's density, hierarchy, and workflow problems.
  - Keep visual polish tied to data readability and operating speed, not decorative dashboard effects.

## 2026-07-05 - Plan NiceGUI UI migration implementation

- Summary: Added a task-by-task implementation plan for the NiceGUI migration, including UI audit, professional theme, high-frequency pages, chart wiring, tests, and browser verification.
- Verification: Documentation-only change; `rg -n "TBD|TODO|implement later|fill in|appropriate|handle edge cases|Similar to|待定|待补|不确定|FIXME" docs\superpowers\plans\2026-07-05-nicegui-ui-migration.md` returned no matches.
- Watch out next time:
  - Wire ETF and index K-line payloads before visual verification; placeholders are only temporary during intermediate tasks.
  - Keep implementation commits scoped because this worktree already has unrelated Streamlit UI/test changes.

## 2026-07-05 - Implement NiceGUI UI migration v1

- Summary: Added a NiceGUI-based ETF workbench with a compact professional shell, UI audit notes, high-frequency pages, table-focused ETF/maintenance views, and visible SVG K-line rendering for ETF/index history.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q` passed with 172 tests; browser verified `http://127.0.0.1:8502` desktop pages and 390px ETF table overflow.
- Watch out next time:
  - Keep future NiceGUI polish in `src/etf_trading/nicegui_app/theme.py` and page modules, not backend storage or strategy code.
  - The v1 K-line renderer is static SVG for robust local rendering; upgrade to interactive lightweight-charts only after local script loading is reliable.

## 2026-07-05 - Align atomic indicator spec with NiceGUI

- Summary: Updated the ETF atomic indicator foundation design so the dashboard lands in the NiceGUI `ETF数据` workflow with UI-neutral view models instead of the old Streamlit-style page plan.
- Verification: Documentation-only change; `rg -n "TBD|TODO|FIXME|待定|待补|不确定" docs\superpowers\specs\2026-07-05-etf-atomic-indicator-foundation-design.md` returned no matches.
- Watch out next time:
  - Put new user-facing ETF diagnostics into `nicegui_app` pages and reusable `view_models.py`; avoid burying calculations in page render functions.
  - Keep `ETF数据 -> 原子指标` diagnostic-only and send repair actions to `数据维护 -> 补齐任务`.

## 2026-07-05 - Design index valuation healthcheck

- Summary: Added the approved design for a multi-source index valuation cache and atomic valuation healthcheck page under `市场地图`.
- Verification: Documentation-only change; `rg -n "TBD|TODO|FIXME|待定|待补|不确定|implement later|fill in|appropriate|Similar to" docs\superpowers\specs\2026-07-05-index-valuation-healthcheck-design.md` returned no matches.
- Watch out next time:
  - Do not compute weighted, median, or composite valuation scores; show atomic valuation indicators and their own percentiles.
  - Keep iFind, AKShare, Tushare, and CSV behind provider interfaces so the healthcheck calculation and UI do not depend on one source.

## 2026-07-05 - Compact NiceGUI chart tooltip

- Summary: Replaced the default ECharts axis tooltip with a compact grouped formatter for K-line, moving-average, and volume values with right-aligned tabular numbers.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_charts.py -q` passed with 13 tests; bundled Node evaluated the formatter and confirmed `9,991.03`, `11,032.22`, and `39.80亿` sample output.
- Watch out next time:
  - Use NiceGUI `:formatter` keys for ECharts JavaScript callbacks; plain `formatter` strings will not execute.
  - Keep tooltip values grouped and fixed to two price decimals so MA precision does not overwhelm the chart.

## 2026-07-05 - Left-align NiceGUI section tabs

- Summary: Moved NiceGUI page-level section tabs from the title row's right side to a left-aligned row under the page caption across all pages.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py tests/test_nicegui_theme.py tests/test_nicegui_navigation.py -v` passed with 9 tests; browser checked `http://127.0.0.1:8503/page/market` and `http://127.0.0.1:8503/page/research`.
- Watch out next time:
  - Keep high-frequency page switches near the left content start; avoid sending section-level controls to the far right on wide screens.
  - Use shared NiceGUI shell changes for global navigation polish so every page gets the same interaction improvement.

## 2026-07-05 - Implement ETF atomic indicator foundation

- Summary: Added exchange-traded ETF master boundaries, atomic daily/weekly feature columns, UI-neutral ETF atomic snapshots, NiceGUI `ETF数据 -> 原子指标`, and all-master history job creation.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_akshare_provider_fallback.py tests/test_features.py tests/test_atomic_indicators.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_storage_and_services.py -q --basetemp pytest-tmp-atomic-focused` passed with 29 tests; `.venv-win\Scripts\python.exe -m pytest tests/test_data_coverage.py tests/test_nicegui_app_import.py tests/test_nicegui_charts.py tests/test_nicegui_state_cache.py -q --basetemp pytest-tmp-atomic-broad` passed with 23 tests.
- Watch out next time:
  - Keep `fund_name_em` out of the tradable ETF master pool; use it only as auxiliary discovery data.
  - Keep atomic indicator tables diagnostic-only; scores and trading actions belong to later strategy layers.
  - Long-running all-ETF history work should remain a maintenance task, not an automatic page-load side effect.

## 2026-07-05 - Plan index valuation healthcheck implementation

- Summary: Added the task-by-task implementation plan for source-switchable index valuation cache, atomic valuation healthcheck calculations, and NiceGUI `市场地图 -> 指数估值体检`.
- Verification: Documentation-only change; `rg -n "TBD|TODO|implement later|fill in|appropriate|handle edge cases|Similar to|待定|待补|不确定|FIXME" docs\superpowers\plans\2026-07-05-index-valuation-healthcheck.md` returned no matches.
- Watch out next time:
  - Keep implementation tasks atomic and diagnostic-only; no weighted, median, or composite valuation outputs.
  - Treat forbidden score/action terms in tests as absence assertions, not as production UI labels.

## 2026-07-05 - Initialize all-ETF history cache

- Summary: Refreshed the exchange-traded ETF master pool to 1,528 rows and fetched local Parquet price histories for every active master ETF. Added an operational all-master history fetch script with resumable fresh-cache skipping and fixed AkShare Sina fallback exchange inference for `52/53` SSE ETF codes.
- Verification: Data quality scan found `history_files=1528`, `missing_files=0`, `missing_required_cols_files=0`, `fresh_files=1526`, with stale source histories only for `560000` (latest `2026-04-30`) and `560650` (latest `2026-07-01`). Atomic snapshot built 1,528 rows: `feature_status=complete` for 1,310 and `missing_features` for 218 short-history ETFs. `.venv-win\Scripts\python.exe -m pytest -q --basetemp pytest-tmp-full-after-fetch` passed with 197 tests.
- Watch out next time:
  - AkShare/Eastmoney can transiently fail through the local proxy; rerun `scripts/fetch_all_etf_history.py --years 5 --sleep 0.15 --no-refresh-master` to skip fresh files and fill gaps.
  - `560000` and `560650` are present in the spot master but their history source is stale; keep them visible as data-quality exceptions rather than treating them as missing files.
  - Many new ETFs have fewer than 60 rows, so 60-day breakout/return and weekly trend atoms should stay `missing_features` until enough history accumulates.

## 2026-07-05 - Make NiceGUI atomic indicators responsive

- Summary: Moved the full-pool atomic indicator calculation off the NiceGUI page-render path by adding disk/in-memory snapshot caching plus background refresh, then restarted `8504` with a fresh 1,528-row cache.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q --basetemp pytest-tmp-atomic-full3` passed with 201 tests; after restarting `8504`, `curl` verified `ETF数据 -> 原子指标` returns `200` in `0.088s` cold and `0.160s` warm; browser verified the click path reaches the page with 15 visible rows and no `Connection lost`.
- Watch out next time:
  - Do not synchronously recompute all ETF atomic indicators during page render; use `load_atomic_snapshot_cached` and keep heavy refresh work out of the NiceGUI server process.
  - Keep the base NiceGUI platform snapshot warm for operator sessions; a 60-second TTL makes full-pool pages feel cold too often.
  - The generated cache lives under ignored `data/parquet/cache/`; after bulk history refreshes, warm this cache before judging UI speed.
  - NiceGUI route `curl` can be fast while browser navigation waits on long-lived connections, so verify visible DOM state rather than relying only on navigation timing.

## 2026-07-05 - Align NiceGUI chart controls globally

- Summary: Unified NiceGUI K-line selector rows and the shared ranged chart header so ETF/index selection, chart titles, record counts, and range toggles stay visually grouped across market, ETF, and research pages.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q` passed with 23 tests; `.venv-win\Scripts\python.exe -m pytest -q --basetemp pytest-tmp-global-chart-toolbar` passed with 207 tests; browser checked `8506` market index K-line, ETF行情, research 指数过滤实验, and 390px market layout with no horizontal overflow or control overlap.
- Watch out next time:
  - Keep business toolbars left-aligned unless a shell-level layout genuinely needs split alignment.
  - Put K-line title, record count, and range controls in the shared chart component so research pages inherit fixes automatically.

## 2026-07-05 - Fix NiceGUI moving-average line alignment

- Summary: Preserved `time` values when converting sparse moving-average payloads to ECharts line series, so MA51/MA120/MA250/MA850 stay date-aligned with candles and extend to the latest available trade date.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_charts.py -q` passed with 15 tests; `.venv-win\Scripts\python.exe -m pytest -q --basetemp pytest-tmp-ma-line-alignment` passed with 208 tests; checked real 000300 payload where each MA line's final point is `2026-07-03`, matching the last candle date.
- Watch out next time:
  - ECharts category-axis line data must retain `[time, value]` pairs when leading moving-average rows are missing.
  - When changing ECharts data shapes, update tooltip extraction so hover values do not accidentally show the x-axis date.

## 2026-07-05 - Make NiceGUI topbar operational

- Summary: Replaced the right-side `NiceGUI` framework marker with the platform snapshot refresh time and reused the same snapshot for page rendering.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py tests/test_nicegui_navigation.py tests/test_nicegui_theme.py -q` passed with 11 tests.
- Watch out next time:
  - Keep the global topbar for operator state such as data freshness, cache health, or refresh actions, not implementation details.
  - Load the platform snapshot once in the shell when both chrome and page content need it.

## 2026-07-05 - Compact index reference table

- Summary: Added a compact NiceGUI table mode and used it on `市场地图 -> 指数买卖参考`, plus a short trend-filter note so the page reads as a regime reference rather than a full-width spreadsheet.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q --basetemp pytest-tmp-index-table` passed with 209 tests; Playwright/Chrome verified the `8507` market page and the compact index table measured 938px wide in a 1600px viewport.
- Watch out next time:
  - Keep market-index pages framed as trend filters; do not imply direct buy/sell instructions in the table itself.
  - When a NiceGUI table feels too airy, try a compact width preset plus CSS shrink-wrap before redesigning the whole page.
  - Use browser measurement, not just screenshots, to confirm a compact table actually stopped stretching to the full content width.

## 2026-07-05 - Localize NiceGUI table display

- Summary: Added shared NiceGUI table header/value localization so internal fields and status codes do not leak into market, ETF, maintenance, action, or research tables.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q --basetemp pytest-tmp-full-i18n` passed with 205 tests; browser verified `市场地图 -> 指数买卖参考` and `ETF数据 -> 原子指标` show Chinese headers/status values.
- Watch out next time:
  - Route every NiceGUI table through `table_columns` and `table_rows`; raw DataFrame records should not be passed directly to `ui.table`.
  - Add new backend status codes to `VALUE_LABELS` before exposing them in filters or tables.

## 2026-07-05 - Raise NiceGUI connection timeout for slow first render

- Summary: Increased NiceGUI `reconnect_timeout` to 60 seconds in the app entry point so the 16-second first snapshot load does not trip the default 3-second connection-loss popup.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_app_import.py tests/test_nicegui_table_display.py -q` passed with 11 tests.
- Watch out next time:
  - `render_shell()` still does a heavy synchronous snapshot load on a cold start; if the dataset grows again, revisit that render path instead of only stretching the timeout.
  - Keep browser verification on a cold app start in the loop whenever connection loss reappears.

## 2026-07-07 - Plan ETF atomic detail toggle

- Summary: Added the implementation plan for `ETF数据 -> 原子指标` view switching between `机会特征` and `体检特征`, plus selected-ETF grouped atomic details.
- Verification: `rg -n "TBD|TODO|FIXME|待定|待补|不确定|implement later|fill in|appropriate|Similar to|handle edge cases" docs\superpowers\plans\2026-07-07-etf-atomic-detail-toggle.md` returned no matches.
- Watch out next time:
  - Keep ETF atomic list columns purpose-specific; full per-ETF diagnostics belong in the detail area.
  - Preserve the existing atomic snapshot calculation layer when adding display modes.

## 2026-07-08 - ETF atomic detail toggle

- Summary: Added `机会特征` and `体检特征` views for `ETF数据 -> 原子指标`, plus selected-ETF grouped atomic indicator details.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q --basetemp pytest-tmp-etf-atomic-toggle-focused-final` passed with 36 tests; `.venv-win\Scripts\python.exe -m pytest tests/test_atomic_indicators.py tests/test_nicegui_navigation.py tests/test_nicegui_state_cache.py tests/test_nicegui_charts.py -q --basetemp pytest-tmp-etf-atomic-toggle-regression-final` passed with 27 tests; browser checked default `机会特征`, grouped detail area, and `体检特征` columns on `ETF数据 -> 原子指标`.
- Watch out next time:
  - Keep the atomic snapshot calculation unchanged when adding UI views; view models should slice and format only.
  - Preserve shared table helpers so localized pagination and empty-state labels do not regress.
  - Keep list views narrow and purpose-specific; use the detail area for complete per-ETF diagnostics.

## 2026-07-07 - Localize NiceGUI maintenance tables

- Summary: Added shared NiceGUI table rendering with Chinese pagination text, expanded column labels for price history and maintenance logs, and translated common maintenance dataset/job/status codes.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q --basetemp pytest-tmp-localized-table-full` passed with 215 tests; browser verified `数据维护 -> 日志与设置` on `http://127.0.0.1:8512` shows Chinese headers, Chinese dataset values, and no `Records per page`.
- Watch out next time:
  - Route NiceGUI tables through `render_table` so Quasar pagination labels stay localized.
  - Add both `COLUMN_LABELS` and `VALUE_LABELS` entries when exposing new backend fields or internal codes.

## 2026-07-08 - Design maintenance task center

- Summary: Added the approved design for a page-level task center on `数据维护 -> 补齐任务` so users can see the latest maintenance task status, timing, summary, and result.
- Verification: `rg -n "TBD|TODO|FIXME|待定|待补|不确定|implement later|fill in|appropriate|Similar to|handle edge cases" docs\superpowers\specs\2026-07-08-maintenance-task-center-design.md` returned no matches.
- Watch out next time:
  - Keep the first implementation page-local; do not turn it into a durable queue until real background-task requirements appear.
  - Preserve `_run_task` feedback before `run.io_bound` so slow provider calls never leave the UI looking idle.

## 2026-07-08 - Implement maintenance task center

- Summary: Added a page-level task center to `数据维护 -> 补齐任务` so maintenance actions show running, success, failure, or cancelled state with the latest result.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_theme.py tests/test_nicegui_app_import.py -q --basetemp pytest-tmp-maintenance-task-center-focused` passed with 17 tests; `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_navigation.py tests/test_nicegui_table_display.py tests/test_nicegui_state_cache.py -q --basetemp pytest-tmp-maintenance-task-center-regression` passed with 18 tests; `.venv-win\Scripts\python.exe -m pytest -q --basetemp pytest-tmp-maintenance-task-center-full` passed with 228 tests.
- Watch out next time:
  - Keep maintenance task feedback visible before entering `run.io_bound`.
  - Do not add per-asset progress to the task center until the service exposes real progress callbacks.

## 2026-07-08 - Design ETF atomic data update health

- Summary: Added the approved design for replacing misleading row-level `正在刷新` status with a data-update health summary on `ETF数据 -> 原子指标`.
- Verification: `rg -n "TBD|TODO|FIXME|待定|待补|不确定|implement later|fill in|appropriate|Similar to|handle edge cases" docs\superpowers\specs\2026-07-08-etf-atomic-data-update-health-design.md` returned no matches; `git diff --check -- docs/superpowers/specs/2026-07-08-etf-atomic-data-update-health-design.md` passed.
- Watch out next time:
  - Keep row-level history freshness labels distinct from atomic snapshot cache refresh labels.
  - Route repair actions to `数据维护 -> 补齐任务`; the atomic page should diagnose and filter, not execute long-running maintenance.

## 2026-07-08 - Plan ETF atomic data update health

- Summary: Added the implementation plan for atomic data-update health, including status relabeling, summary counts, filter wiring, styling, and browser QA.
- Verification: `rg -n "TBD|TODO|FIXME|待定|待补|不确定|implement later|fill in|appropriate|Similar to|handle edge cases" docs\superpowers\plans\2026-07-08-etf-atomic-data-update-health.md` returned no matches; `git diff --check -- docs/superpowers/plans/2026-07-08-etf-atomic-data-update-health.md` passed.
- Watch out next time:
  - Test the `stale` wording in both table localization and atomic-specific display rows.
  - Keep the health summary click behavior as filter selection, not as direct data fetching.

## 2026-07-08 - ETF atomic data update health

- Summary: Replaced misleading row-level `正在刷新` history status with `行情滞后`, added a data-update health summary to `ETF数据 -> 原子指标`, and linked health items to existing filters and maintenance flow, including post-refresh option rebuilding.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_nicegui_view_models.py tests/test_nicegui_table_display.py tests/test_nicegui_app_import.py tests/test_nicegui_theme.py -q --basetemp pytest-tmp-etf-atomic-health-focused` passed with 45 tests; `.venv-win\Scripts\python.exe -m pytest tests/test_atomic_indicators.py tests/test_nicegui_navigation.py tests/test_nicegui_state_cache.py tests/test_nicegui_maintenance_tasks.py -q --basetemp pytest-tmp-etf-atomic-health-regression` passed with 16 tests; browser verified `http://127.0.0.1:8516/page/etf-data/原子指标` desktop health summary, quick-filter resets, and 390px content with no horizontal overflow.
- Watch out next time:
  - Keep row-level history freshness labels separate from snapshot cache refresh status.
  - Keep repair execution in `数据维护 -> 补齐任务`; the atomic page should diagnose and filter.
  - The mobile left sidebar remains cramped at 390px; this is outside the atomic health panel and should be handled as a shell responsiveness task.

## 2026-07-11 - Add resumable all-ETF history catch-up

- Summary: Added a resumable `数据维护 -> 补齐任务 -> ETF历史` one-click all-ETF catch-up action with task-center progress, fresh-file skipping, per-ETF failure isolation, and local-master fallback when master refresh fails.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_storage_and_services.py tests/test_nicegui_maintenance_tasks.py tests/test_nicegui_app_import.py tests/test_nicegui_table_display.py -q --basetemp pytest-tmp-etf-history-batch` passed with 32 tests; HTTP check of `http://127.0.0.1:8502/page/maintenance/补齐任务` returned 200 and contained the new all-ETF button text.
- Watch out next time:
  - Keep all-ETF catch-up resumable by checking existing Parquet freshness before provider calls.
  - Do not let one failed ETF abort the whole batch; record `FAILED` in `data_update_state` and continue.
  - Browser-plugin validation of localhost may be blocked by enterprise policy; use local HTTP plus pytest when direct browser access is unavailable.

## 2026-07-11 - Add index health atomic dashboard

- Summary: Added `市场地图 -> 指数体检` as the index atomic dashboard, backed by local index valuation Parquet, a page-ready index health snapshot cache, and separate trend/valuation atomic detail tables.
- Verification: `.venv-win\Scripts\python.exe -m pytest tests/test_index_valuations.py tests/test_index_health_snapshot.py tests/test_nicegui_navigation.py tests/test_nicegui_view_models.py tests/test_nicegui_state_cache.py tests/test_nicegui_app_import.py -q --basetemp pytest-tmp-index-health-focused` passed with 47 tests; nearby NiceGUI/storage regression passed with 73 tests.
- Watch out next time:
  - Keep `指数买卖参考` as the trend gate view only; put diagnostics in `指数体检`.
  - Keep the page render cache-only; heavy snapshot work belongs in `research/*` and `nicegui_app/state.py`.
  - Show missing or insufficient valuation rows explicitly instead of filling fake valuation values.

## 2026-07-11 - Build data trust layer

- Summary: Unified ETF/index history readiness into Chinese user-facing states (`数据可用`、`行情滞后`、`历史不足`、`历史缺失`、`读取失败`), excluded non-ready ETF data from opportunity rankings, and exposed source-data health consistently in the top bar, ETF atomic health panel, index health page, and `数据维护 -> 数据体检`.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-data-trust-full-final` passed with 264 tests. Browser QA used Playwright with the local Chrome executable because the Browser plugin and Playwright-managed browser were unavailable; desktop checked top-bar routing, the index readiness notice, and Chinese valuation states, while 390px mobile checked compact accessible navigation with no horizontal overflow or console errors.
- Watch out next time:
  - Keep the source-data effective trade date separate from the page calculation time; never relabel a page render timestamp as a data update.
  - Count ETF repair issues by mutually exclusive primary history status; show feature gaps only as additional diagnostics.
  - Every internal data-status code added to a visible NiceGUI table needs a Chinese value mapping and a table-display test.
  - The browser smoke environment intentionally had an empty isolated data directory; assess real production freshness from the user’s normal local data workspace, not from this QA fixture.

## 2026-07-12 - Persist index-history maintenance tasks

- Summary: Made the full index-history catch-up task durable across page refreshes, persisted live progress and results, marked orphaned runs as interrupted after a server restart, and refreshed the platform snapshot after success. The task center now renders every task state and index result status in Chinese.
- Verification: `.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-maintenance-full-final` passed with 276 tests. Chrome DevTools browser QA on `http://127.0.0.1:8513/page/maintenance/补齐任务` confirmed the persisted result remains after reload, has no raw `STALE` text, and logged no warnings or errors.
- Watch out next time:
  - A successful provider call is not enough: preserve `STALE` when local history still has not reached the expected trade date.
  - Persisted task polling must not overwrite another active page-local maintenance task.
  - Update task result tables and progress labels together whenever a new internal maintenance status becomes user-visible.

## 2026-07-12 - Design index universe expansion

- Summary: Approved a controlled A-share and Hong Kong index expansion: a 210-entry versioned candidate catalog yields 180 validated formal indexes split into a 100-index ETF-backed core pool and an 80-index research-only pool. First fetches request all history from 1990 and explicitly display incomplete history against the index base date.
- Verification: Read-only AkShare check confirmed 31 Shenwan first-level categories, 131 second-level categories, and full daily history availability for representative first-level indices. Design and implementation plan passed placeholder scans and structural checks.
- Watch out next time:
  - Never infer history completeness only from a recent latest date; compare local earliest date with the configured index base date.
  - Keep the static catalog versioned and validate it live; source enumeration alone is not an investor-suitable index universe.
  - Treat ETF mapping as a separate gate from index history availability so research-only indexes cannot leak into strategy inputs.

## 2026-07-12 - Expand index universe and data-maintenance workflows

- Summary: Added a 210-entry A-share/Hong Kong index catalog (100 core, 80 research, 30 reserve), source-aware CSI/Shenwan/Hong Kong history pulls, strict base-date completeness assessment, core-only ETF research samples, and five resumable index-maintenance operations. Market pages now default to the core pool and explicitly label the research pool as observation-only.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-universe-full-final` passed with 294 tests. Browser QA on `http://127.0.0.1:8504/page/market/指数买卖参考` verified the core/research toggle, the research-only state, no console errors, and no horizontal overflow at 1440px or 390px; the temporary QA server was stopped afterward.
- Watch out next time:
  - `IndexCatalogEntry.baseline_source == "unverified"` must always stay `BASELINE_UNVERIFIED`; never turn a long provider history into an unverified "历史完整" claim.
  - Keep page control containers before their dynamic table containers in NiceGUI; otherwise controls can be rendered below a long table.
  - Add new task, pool, and completeness codes to `VALUE_LABELS` and validate both persisted task summaries and table output in Chinese.

## 2026-07-12 - Design index health trend workbench

- Summary: Approved a trend-only redesign for `市场地图 -> 指数体检`: fixed configured ordering and search, a row-click tabbed dialog for trend summary/atomic indicators/data quality, and no valuation display or conclusion.
- Verification: `rg -n "TBD|TODO|FIXME|待定|待补|不确定|implement later|fill in|appropriate|Similar to|handle edge cases" docs/superpowers/specs/2026-07-12-index-health-trend-workbench-design.md` returned no matches; `git diff --check --no-index /dev/null docs/superpowers/specs/2026-07-12-index-health-trend-workbench-design.md` passed.
- Watch out next time:
  - Keep data-invalid indexes visible and inspectable, but suppress all trend-based transaction conclusions.
  - Search must retain `DEFAULT_INDEXES` relative order; never replace it with category or code sorting.
  - Keep valuation interfaces intact but outside the trend page's data flow until a complete, validated source is available.

## 2026-07-12 - Align index health design with expanded index universe

- Summary: Revised the approved trend-workbench design for the current 210-entry catalog: `指数体检` defaults to the 100-index core pool, switches to the 80-index research pool, and excludes the 30-index reserve pool; research never produces a transaction conclusion.
- Verification: `DEFAULT_INDEXES` contains 180 formal indexes generated from the current catalog; the catalog contains 100 core, 80 research, and 30 reserve entries.
- Watch out next time:
  - Do not flatten core and research pools into an undifferentiated table in a trading-assistance workflow.
  - Preserve the catalog's declared order independently inside both visible pools.

## 2026-07-12 - Refine index health to atomic indicators

- Summary: Reframed `指数体检` as an atomic indicator panel with price/MA positions, MA crossings, range breakouts, returns, drawdowns, volatility, volume, and data quality. Removed every trend tier, gate, score, ranking, and transaction conclusion from the approved design.
- Verification: The revised specification enumerates every first-version atomic indicator and its calculation boundary; the page remains limited to local index history.
- Watch out next time:
  - A crossed moving average or new range high is an atomic fact, not a transaction recommendation.
  - Keep cross-event definitions dependent on both the current and preceding trading day so a persistent above/below state is not mislabeled as a new crossing.
  - Mark missing amount data only on volume indicators; do not invalidate unrelated price-derived indicators.

## 2026-07-12 - Move index atomic calculation to data maintenance

- Summary: Approved a two-stage index workflow: data maintenance first initializes or repairs raw index history, then a separate manual, persistent “重建指数原子指标” task writes the atomic snapshot. The index-health page is snapshot-read-only and strongly flags stale, missing, or failed snapshots.
- Verification: Current `load_index_health_snapshot_cached` was inspected and confirmed to rebuild synchronously on a cache miss; the revised design explicitly removes this page-time calculation path.
- Watch out next time:
  - A page refresh may reload a snapshot but must never trigger full atomic recomputation or external fetching.
  - After raw-history or coverage changes, mark the snapshot stale and require an explicit maintenance rebuild rather than silently serving it as current.
  - Preserve a prior successful snapshot on rebuild failure, but show its generated time and strong stale/failure warning.

## 2026-07-12 - Plan index health atomic workbench implementation

- Summary: Converted the approved index-health redesign into a six-task implementation plan. It replaces page-time health rebuilding with a manual persistent atomic-snapshot maintenance task, keeps the market page snapshot-read-only, removes valuation and trend/strategy output, and specifies core/research pool ordering, search, wide tabbed details, and strong data-state warnings.
- Verification: Reviewed the 326-line plan for six concrete tasks and 29 executable steps; the prohibited-placeholder scan returned no matches, and the plan's whitespace check reported no diff errors.
- Watch out next time:
  - Do not reuse `index_health_snapshot*` caches because their schema contains valuation and trend-era fields.
  - Treat `stale`, `missing`, and `failed` snapshots as persistent, user-visible data-quality states; only the maintenance task may write a replacement snapshot.
  - Keep atomic facts independent: missing amount invalidates only volume metrics, and a moving-average crossing is never a trading conclusion.

## 2026-07-12 - Clarify index history status explanations

- Summary: Replaced opaque index-history status text with factual Chinese explanations across data maintenance and market snapshots. New and legacy task results now state the missing latest trading date, actual local coverage range, missing official base date and non-trading restriction, or the source that returned no history. Legacy coverage records are upgraded at display time without changing stored enums or schema.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-final` passed with 310 tests; final independent code review approved commit `d9e757a`.
- Watch out next time:
  - Maintenance task `result_json` and persisted coverage can predate a wording change; normalize recognized legacy messages before rendering rather than assuming a new data run has occurred.
  - Keep `source_kind` when converting catalog entries to `IndexDefinition`, otherwise old empty-history records lose their concrete Chinese data-source explanation in market snapshots.
  - Only default an empty completeness message to “尚未校验历史完整性” for `NOT_VALIDATED`; empty `MISSING_HISTORY` must still be interpreted as a recoverable legacy state.

## 2026-07-12 - Refresh index baseline evidence

- Summary: Added the formal-index evidence verification CLI, refreshed 78 durable baseline records, and isolated custom catalog fixtures from the global evidence overlay unless they explicitly request one.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-full` passed with 348 tests. `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe scripts\verify_index_baselines.py --through 2026-07-10 --write-evidence --formal` first completed with OFFICIAL 76, THIRD_PARTY_PUBLICATION 2, UNRESOLVED 102; its immediate repeat completed through CSI 403 throttling with OFFICIAL 0, THIRD_PARTY_PUBLICATION 17, UNRESOLVED 163.
- Watch out next time:
  - CSI may return HTTP 403 after a successful batch; keep individual failures unresolved and do not treat a JoinQuant publication date as an official base date.
  - Audit every official record against its code-specific CSI endpoint and every third-party record for `聚宽` publication-date semantics before committing the YAML.
- A non-default catalog path must opt in with `evidence_path` before an external baseline overlay is applied.

## 2026-07-12 - Preserve official index baseline evidence

- Summary: Prevented lower-confidence third-party publication records from replacing existing official baseline evidence, then restored CSI official records with a bounded recheck of the 17 downgraded codes.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-preservation-full` passed with 348 tests. The CSI probe recovered from the prior 403; the targeted 17-code pass restored 15 official records and retained `399001`/`399006` as third-party publications because CSI returned mismatched codes.
- Watch out next time:
  - Evidence writes must be monotonic by reliability: `third_party_*` and unresolved outcomes may never overwrite `official_methodology`, `official_factsheet`, or `official_api`.
  - After a CSI rate limit, recheck only downgraded candidates after a successful single-code probe; do not repeat the complete formal-index batch.
  - Keep JoinQuant publication dates as explicit third-party references when CSI does not return a code-matching official basic date.

## 2026-07-12 - Enforce baseline evidence gates across every entry point

- Summary: Applied monotonic evidence merging to YAML and SQLite, added official-complete gating to NiceGUI and Streamlit summaries/signals, and localized the baseline-verification CLI including missing values.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-final-signal-controller` passed with 401 tests. The refreshed NiceGUI maintenance page returned HTTP 200 on `http://127.0.0.1:8503/page/maintenance`.
- Watch out next time:
  - Apply the official-baseline + COMPLETE + fresh-data gate at every signal-generation path, not only at summary tables or visible action controls.
  - Treat third-party and unresolved evidence as monotonic lower-confidence states: they may not overwrite official records in YAML, SQLite, cache projections, or derived coverage.
  - Normalize pandas `NaN` and `NaT` before any user-facing CLI/table text so internal sentinel values never leak into Chinese output.
## 2026-07-12 - Restore index-worktree baseline

- Summary: Synced the verified-base-date coverage assertion to the current Chinese completeness message; no production behavior changed.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-workbench-baseline-green` passed with 298 tests.
- Watch out next time:
  - When changing user-facing data-quality copy, update direct storage assertions in the same change.

## 2026-07-12 - Compute index atomic indicator snapshots

- Summary: Replaced the index health calculation with local-price atomic metrics for MA position/crossing, range, return/drawdown, volatility, amount, and data quality; valuation and transaction-conclusion outputs are absent.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_index_health_snapshot.py tests\test_index_valuations.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-kernel-green-final` passed with 11 tests.
- Watch out next time:
  - Migrate `nicegui_app.state` from the removed `build_index_health_snapshot` / `INDEX_HEALTH_*` interface before running the full suite.
  - A moving-average cross requires an adjacent-day side switch; a persistent above/below position is not a new event.
  - Missing `amount` is a volume-only input gap and must not invalidate price-derived atoms.

## 2026-07-12 - Present index atomic indicator rows

- Summary: Added atomic index summary rows with core/research pool filtering, stable catalog-order sorting, code/name-only search, Chinese fixed-column formatting, and six stored-fact detail groups. Promoted the existing 20-day range high/low facts into the atomic summary schema so the list can distinguish new high, new low, and in-range without recomputation. The snapshot cache now uses schema v2 so existing v1 snapshots are stale rather than silently presented as current data.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_view_models.py tests\test_nicegui_table_display.py tests\test_nicegui_theme.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-view-model-green-final-review` passed with 48 tests; `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_state_cache.py tests\test_nicegui_app_import.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-atomic-state-app-green` passed with 36 tests; full `pytest -q` passed with 328 tests.
- Watch out next time:
  - Keep `range_20_high` and `range_20_low` as stored summary facts; `range_20_status` is only the calculation-state field and cannot identify the range position by itself.
  - Any atomic-summary schema change needs the index-atomic cache schema version, boolean-safe Parquet serialization, and an old-schema stale-cache regression in the same change.
  - Filter the selected visible pool before searching only code/name, then sort solely and stably by `catalog_order`; reserve rows stay hidden.
  - Detail groups format stored values and statuses only. Do not add calculations, valuation, trend tiers, scoring, ranking, position permission, strategies, or transaction conclusions.

## 2026-07-12 - Keep NiceGUI maintenance routes lightweight

- Summary: Routed NiceGUI pages through explicit snapshot policies so maintenance task/log pages, index health, and lightweight ETF data sections no longer load the full platform-health snapshot on open. Added a SQLite-only maintenance snapshot, redirected the sidebar maintenance entry to 补齐任务, replaced full-master ETF select boxes with code/name inputs on heavy entry points, capped maintenance task-result previews, and cached default index source-kind lookup so legacy task-result display no longer reparses the index catalog once per row.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_nicegui_app_import.py tests\test_nicegui_state_cache.py tests\test_nicegui_maintenance_tasks.py tests\test_nicegui_view_models.py tests\test_nicegui_table_display.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\nicegui-route-snapshot-focused-2` passed with 132 tests. Full `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\nicegui-route-snapshot-full-3` passed with 410 tests. Real HTTP checks on the running service returned 补齐任务 in 0.239s/0.274s, 指数体检 in 0.126s, and ETF行情 in 0.333s on `http://127.0.0.1:56587/`.
- Watch out next time:
  - Do not call `load_snapshot_cached()` from generic shell rendering before deciding which page section is active; page routes must declare whether they need full, maintenance-only, or atomic-index data.
  - Do not render full ETF/master lists as select options on first paint; use searchable inputs or bounded filtered results.
  - Legacy maintenance task results can be large and old; display-time upgrades must cache static catalog data and preview rows instead of reparsing or rendering everything.

## 2026-07-14 - Keep index atomic ladder labels readable

- Summary: Fixed the index atomic overview ladder so endpoint markers stay inside the 124px scale and clustered moving-average labels receive a collision-safe 15px display gap while preserving their real value order and printed values.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\etf0614-index-dialog-layout-full-20260714` passed with 430 tests. Chrome DevTools validation on `http://127.0.0.1:8503/page/market/指数体检` opened the 000300 detail dialog at 1440×900 and 390×844; all five markers stayed within the ladder, marker overlap count was zero, the overview used 4/1 columns respectively, and no console error or warning remained.
- Watch out next time:
  - A normalized market value is not directly usable as an absolutely positioned text row: account for half the label height at 0%/100% and spread labels whose pixel distance is smaller than their line height.
  - Collision avoidance may adjust display spacing only; keep the actual stored values, ordering, and factual relation text unchanged.

## 2026-07-31 - Calculate index valuation percentile atoms

- Summary: Added local-only, atomic PE-TTM/PB valuation facts with aligned valuation dates, fixed 3/5/10-calendar-year mid-rank percentiles, bands, medians, turnover observations, and explicit supported/missing/stale states.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_index_valuation_atoms.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-valuation-atoms-green-refactor` passed with 7 tests; full `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-valuation-atoms-full` passed with 470 tests and 1 skipped.
- Watch out next time:
  - Keep PE-TTM/PB percentiles as independent mid-rank facts; do not turn their bands into a score, rank, or trading conclusion.
  - Apply the positive, finite, numeric filter before selecting current metric values as well as before computing historical samples.
- Retain exact calendar-year window dates and sample counts even when a percentile is unavailable.

## 2026-07-31 - Publish unified index profile snapshots

- Summary: Unified local price atoms with independent official-valuation atoms in one snapshot, preserving the latest price date as the valuation observation date and exposing only atomic facts.
- Verification: Focused unified snapshot regression suite passed; full suite result is recorded in `.superpowers/sdd/unified-index-profile-task-6-report.md`.
- Watch out next time:
  - Read valuation histories only for codes in `OFFICIAL_INDEX_VALUATION_TS_CODES`; unsupported codes retain explicit unsupported atoms and no percentile tracks.
  - A valuation cache file is part of the snapshot input signature, including its absence; recheck that combined signature before publication.
  - Keep valuation dates no later than the price observation date and treat more than five unique price trading days of lag as stale.

## 2026-07-31 - Bind index snapshot signatures to input content

- Summary: Hardened unified index snapshot input signatures with chunked file-content SHA-256 digests for selected price files and supported official-valuation files, preventing metadata-preserving replacement from publishing an obsolete snapshot.
- Verification: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-signature-full` passed with 503 tests, 1 skipped, and 2 existing pandas warnings.
- Watch out next time:
  - Size and mtime are only hints: retain a deterministic, chunked content digest in every freshness-critical local-file signature.
  - The same content-signature function must supply both cache reads and the publication-time recheck, or a rebuild can still publish stale inputs.

## 2026-07-31 - Add read-only cross-index valuation comparison

- Summary: Added the Market “指数估值” section, projecting configured official valuation atoms from the already-published unified snapshot into a stable compact comparison table.
- Verification: H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-comparison-full passed with 517 tests, 1 skipped, and 2 existing pandas warnings.
- Watch out next time:
  - Keep comparison rows sourced exclusively from the read-only index snapshot loader; UI refreshes must never fetch, calculate, or write.
  - Preserve configured official-code ordering and render percentiles as independent facts, never as a score, rank, or trading conclusion.
  - Exclude unsupported rows from the official comparison table while keeping missing, failed, stale, and not-synced states explicit in the presentation.

## 2026-07-31 - Keep valuation comparison on the read-only snapshot path

- Summary: Routed Market “指数估值” through the atomic-index lightweight snapshot mode and retained not-synced/stale official rows with their specific Chinese valuation states.
- Verification: H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-comparison-review-full passed with 519 tests, 1 skipped, and 2 existing pandas warnings.
- Watch out next time:
  - A new read-only market section must explicitly select atomic_index; otherwise shell startup can invoke the full snapshot loader and its cold-cache writes.
  - Use valuation-specific labels for stale, not the generic atomic snapshot “待重建” label.
  - Exclude only explicit unsupported valuation rows; retain official mappings whose synchronization state is not yet ready.

## 2026-07-31 - Make atomic-index shell rendering SQLite-free

- Summary: Replaced the atomic-index shell path’s maintenance snapshot with a direct published-atomic projection and removed the valuation renderer’s SQLite store creation; canonical not-synced valuation rows now fall back from freshness to support state.
- Verification: H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-comparison-second-review-full passed with 521 tests, 1 skipped, and 2 existing pandas warnings.
- Watch out next time:
  - Do not reuse a “lightweight” maintenance loader for a read-only route unless it is verified not to initialize or migrate SQLite.
  - A published atomic shell projection must accept no SQLite store, so the call boundary itself prevents initialization and write paths.
  - For valuation state display, use freshness when available and otherwise support status; canonical not-synced rows intentionally have no freshness value.

## 2026-07-31 - Avoid filesystem creation on atomic-index shell routes

- Summary: Moved snapshot-mode selection before store construction and introduced a root-only atomic snapshot reader so the index valuation shell cannot create SQLite or Parquet directories.
- Verification: H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-comparison-third-review-full passed with 523 tests, 1 skipped, and 2 existing pandas warnings.
- Watch out next time:
  - Determining a route’s read/write policy after creating storage objects is too late: constructors may mutate the filesystem.
  - A read-only filesystem handle should carry only a path and must not call mkdir, even if the corresponding mutable store normally does.
  - Exercise lifecycle guarantees in a real previously nonexistent directory; constructor mocks cannot reveal mkdir side effects.

## 2026-07-31 - Separate valuation and health shell lifecycles

- Summary: Added an index-valuation-only read-only shell mode; index health remains on its initialized atomic-index lifecycle so direct empty-database rendering can read the catalog safely.
- Verification: H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-comparison-fourth-review-full passed with 524 tests, 1 skipped, and 2 existing pandas warnings.
- Watch out next time:
  - Shared data labels do not imply shared lifecycle rules: valuation may be path-only read-only while health needs initialized SQLite metadata.
  - Any new lightweight mode needs an explicit route-policy regression; do not broaden an existing mode merely because two sections read the same published snapshot.
  - Test a renderer’s prerequisite queries from a truly empty database, not only its shell snapshot construction.

## 2026-07-30 - Add unified index valuation and trend profile

- Summary: Added Tushare official index valuation history, transparent 3/5/10-year PE-TTM and PB percentiles, expanded price/risk atoms, one signed unified snapshot, and the five-tab index profile dialog. Current valuation fields come only from the latest aligned official record; the all-indicators tab preserves valuation, price, and data-quality atoms.
- Verification: Final review-focused: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest tests\test_index_valuation_atoms.py tests\test_nicegui_view_models.py tests\test_nicegui_app_import.py tests\test_index_health_snapshot.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-final-review-focused-r3` observed 149 passed and 2 known pandas `RuntimeWarning`s. Final full: `H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-profile-final-review-full-fix` observed 530 passed, 1 skipped (the opt-in live smoke test because `TUSHARE_TOKEN` is unset), and 2 known pandas `RuntimeWarning`s. Final Browser-plugin Chrome QA used viewport overrides 390x844 and 1440x900 on `/page/market/指数体检`: the 390 viewport had root client/scroll width 375/375, profile card rect 327.02x810.41 at (23.99, 23.99) with no card overflow, title/date own scroll widths equal client widths, 48px tabs with horizontal scrolling (454px content in 303px client width), and internally scrolling panels; the 1440 viewport had root 1425/1425, card 1180x828, non-overflowing title/date/header, 48px tabs, and 1144x666 internal panels. The `000300` row opened the profile at both sizes; all five tabs switched at both sizes; all five full-indicator groups were expanded on mobile before the final review added valuation and data-quality groups; browser console and final server stderr were empty. Evidence: `C:\Users\cjj\AppData\Local\Temp\unified-index-profile-task10-evidence-20260731\mobile-overview-final.png` is a 375x844 captured-content PNG (not a 390px PNG because of browser content/scrollbar sizing), and `desktop-overview-fixed.png` is the visually complete desktop evidence. Chrome's final 1440 screenshot capture timed out, so no final desktop PNG is claimed; the computed geometry and interactions above passed.
- Caution: Keep valuation and price histories as separate inputs, include both in the snapshot signature, never derive unsupported index valuations from constituents, keep invalid latest-record fields unavailable instead of backfilling older values, and keep market-page interactions read-only.
