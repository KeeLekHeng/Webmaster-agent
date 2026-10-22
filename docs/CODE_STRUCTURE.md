# Python code structure

The October 2026 reorganization groups existing modules by responsibility. It
changes import paths, not workflows, permissions, saved formats or configuration.

```text
src/guardian/
  core/           Shared schemas, network scope and kill-switch controls
  checks/         HTTP/TLS audit, technical SEO and performance measurements
  integrations/   Google OAuth and Search Console API access
  workflows/      Audit graph, period-review graph and Claude investigation
  reporting/      Deterministic human handoff summaries
  storage/        SQLite observation history and issue comparisons
  scheduling/     Disabled-by-default one-shot dispatcher
  remediation/    Repository access, proposals, approvals and manual PR commands
  telegram/       Pairing, safe transport, delivery state, formatting and commands
  cli/            Main command parser and LangGraph terminal explanation
tests/
  checks/ cli/ integrations/ remediation/ reporting/ storage/ telegram/ workflows/
```

## Where to make changes

| Change | Starting point |
| --- | --- |
| Add or adjust a deterministic website check | `src/guardian/checks/` |
| Change audit graph steps | `src/guardian/workflows/audit.py` |
| Change SEO period comparisons | `src/guardian/workflows/period_review.py` |
| Change Claude reasoning or retries | `src/guardian/workflows/investigation.py` |
| Change Telegram message or attachment templates | `src/guardian/telegram/reporting.py` |
| Change Telegram command handling | `src/guardian/telegram/service.py` |
| Change shared evidence/report schemas | `src/guardian/core/models.py` |
| Change command arguments | `src/guardian/cli/app.py` or the domain's `cli.py` |

Use absolute `guardian.<package>.<module>` imports for cross-package code. Keep
domain helpers together; do not introduce another layer just to move a function.
Tests mirror responsibility groups; history and dispatcher tests remain together
in `tests/storage/test_history.py` because they exercise the same persistence flow.

## Compatibility and validation

Both `guardian ...` and `python -m guardian.cli ...` remain supported. The public
`guardian.cli:main` entry point is exported by the CLI package. Internal flat
module imports such as `guardian.workflow` now use their documented package paths;
scripts importing internals must update accordingly. No extra wrapper files are
needed for the supported commands.

Site configuration, environment variable names, SQLite/report paths, database
schemas and JSON/Markdown formats are unchanged. Historical milestone documents
retain the source paths that existed when their evidence was recorded.

Validation: 260 tests passed and one Windows symlink test skipped, matching the
pre-move baseline. Both CLI entry points were checked without running a scan.
Rollback is a Git revert of the structure commit; no data migration is required.
