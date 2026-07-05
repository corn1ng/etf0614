# Task Memory

Use this file as the project-level memory for future Codex tasks. Read it at the start of substantive work and update it after every task that changes files or project behavior.

Keep entries concise and reusable. Prefer lessons, constraints, verification notes, and project-specific pitfalls over a raw activity log.

## Entry Template

```md
## YYYY-MM-DD - <task>

- Summary: ...
- Verification: `command` passed, or Not run: <reason>.
- Watch out next time:
  - ...
```

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
