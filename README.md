# Website Guardian

A local, manual, read-only website audit CLI. Deterministic checks need no LLM
API key. Milestone 2 adds a LangGraph workflow with optional Claude investigation.

## Run on Windows

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e '.[dev]'
.venv\Scripts\guardian audit --site estateplanning
.venv\Scripts\python -m pytest -q
```

Each run saves `report.json` and `report.md` under a unique `reports/<run-id>/`
directory, preserving previous runs. Reports contain timestamped evidence,
checks passed, severity, confidence, failures, tool versions and next steps.
`reports/` is Git-ignored. Exit codes: 0 completed (possibly with findings),
1 partial collection, 2 configuration/startup/save error.

For the verified dependency snapshot, install with
` .venv\Scripts\python -m pip install -r requirements-dev.lock ` followed by
` .venv\Scripts\python -m pip install --no-deps -e . `.
See [Milestone 1 outcome](docs/MILESTONE_1.md) for validation and the first audit.

## LangGraph and Claude

All CLI audits now run through eight LangGraph nodes: validate configuration,
collect checks, normalize evidence, investigate, filter policy, persist history,
summarize the human handoff, and save report.
The default `--llm none` skips model reasoning. To print a beginner walkthrough:

```powershell
.venv\Scripts\guardian explain
```

Every workflow run prints a concise handoff and saves `summary.md` alongside the
full reports. The summary groups identical issues, counts distinct affected URLs,
retains scanner severity/confidence and lists impact, a human next step and evidence
references. It shows at most five issue groups, with an explicit count/link for
additional issues. Incomplete collection, unavailable checks, reasoning status and
replayed evidence remain visible. This is a deterministic formatting node with no
extra model call; model prose is retained in the full report rather than copied
into the handoff. Telegram delivery remains deferred.

To demonstrate the real graph without a model/API charge, using a previous report:

```powershell
.venv\Scripts\guardian audit --site estateplanning --llm demo --input-report reports/reviewed/32c1bc5cb90a4ea49317db45712d9410/report.json
```

Demo reasoning is explicitly fake. Replayed evidence retains the original scan
timestamps, with the original run ID recorded; no new website requests are made.
Omit `--input-report` for a new live scan. Previous reports are not overwritten.

For Claude, fill in `ANTHROPIC_API_KEY` and `GUARDIAN_MODEL` in the local `.env`
file, which is excluded from Git. Guardian loads `.env` from the current working
directory automatically, without variable interpolation. Existing shell variables
take precedence. You can alternatively enter the key in your shell without echoing
it or putting its value in PowerShell command history:

```powershell
$guardianKey = Read-Host 'Anthropic API key' -AsSecureString
$env:ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new('', $guardianKey).Password
$env:GUARDIAN_MODEL = Read-Host 'Claude model ID'
.venv\Scripts\guardian audit --site estateplanning --llm claude
Remove-Item Env:ANTHROPIC_API_KEY
Remove-Variable guardianKey
```

Claude mode makes one external request to Anthropic (no automatic retry, 30-second
HTTP timeouts, at most 1,800 output tokens). Only bounded scanner facts, known
labels and synthetic finding/evidence IDs are sent: no raw HTML, response header
strings, URLs, page text, repository content or credentials in the prompt. The
API key is used for API authentication. Input is capped at 32 KiB and 20 findings;
other deterministic findings remain in the report. Reports record the input hash,
selected model, token usage if available, accepted reasoning and node events.
LangSmith external tracing is explicitly disabled.

Model output must match a Pydantic schema. Python validates finding references,
evidence membership and duplicate entries, and screens obvious commands/URLs.
This does not prove the meaning of model prose: it remains advisory. The model
cannot alter scanner evidence/severity or execute any action. API failures and
invalid outputs preserve the deterministic report with an explicit analysis status.
The audit graph has no repository mutation nodes, resume checkpoints or additional agents.
Missing key/model fails before collection. Exit code 1 also means unavailable,
partial or rejected analysis; demo output is labelled `demo`, never Claude-tested.

See [Milestone 2 outcome](docs/MILESTONE_2.md) and
[the LangGraph walkthrough](docs/LANGGRAPH_WALKTHROUGH.md).

## Local history and alerts

Milestone 3 stores observation snapshots, active issues, comparisons and optional
local alert records in SQLite at `data/guardian.sqlite3`. Both `data/` and reports
are excluded from Git. Normal CLI audits persist history automatically.

```powershell
.venv\Scripts\guardian audit --site estateplanning --llm none --notify local
.venv\Scripts\guardian history --site estateplanning --limit 5
.venv\Scripts\guardian alerts --site estateplanning
```

Comparisons show new, changed, unchanged, resolved and not-observed issues.
Unchanged issues produce no new alert records. Missing evidence or incomplete
coverage cannot establish recovery. Replay/demo runs are stored separately and
do not change the live baseline or queue alerts. `--notify local` records new,
changed and resolved issue events in a local outbox; it sends no messages.
Default `--notify none` records history without alert events. Telegram is deferred.
Use `--database` or `GUARDIAN_DB` to select another local database.

`guardian run-due` is an optional one-shot dispatcher for an external job scheduler.
It currently prints `disabled`, because `config/schedule.json` has `enabled: false`.
No Windows task, cron entry, background worker or server service is installed.
Enabling scheduled operation remains a separate explicit decision. The dispatcher
uses deterministic checks only, durable UTC time slots and a one-hour site lease
to limit duplicate/overlapping runs. A claimed failed/interrupted slot is not
automatically retried. See [Milestone 3 details](docs/MILESTONE_3.md).

## Scope and controls

`config/sites.json` defines allowed HTTPS hosts and exact public paths, seed
routes, page/request limits and timeouts. Internal links are followed only
when their route is already approved. External links, query strings, admin
routes, forms and unknown API routes are excluded. No JavaScript is executed.
Requests are sequential, delayed, size capped, and retried at most once for
network failures or 5xx responses. Redirects are checked before each connection.
DNS answers must all be public; connections pin a validated IP while retaining
TLS hostname and chain verification. System proxy settings are not used.
DNS resolution itself is governed by the operating system resolver timeout.

Checks cover availability, TLS expiry, selected response headers, metadata
presence and broken links within configured scope. A health endpoint response
does not prove database or email delivery health. Missing headers are hardening
observations, not confirmed vulnerabilities. Metadata checks establish presence,
not SEO quality. Raw HTML, cookies and response bodies are not persisted.
Reports are a point-in-time sample, not an uptime or security guarantee.

To block a new run and stop subsequent network operations in the current process:

```powershell
$env:AGENT_ENABLED = 'false'
```

To stop from another terminal, use the persistent file switch:

```powershell
.venv\Scripts\guardian stop
.venv\Scripts\guardian resume
```

The stop file is `data/STOP` by default (`GUARDIAN_STOP_FILE` overrides it).
Every protected node/network operation checks it. It does not cancel an in-flight
request immediately; requests remain subject to their timeouts. Resume only clears
the file; `AGENT_ENABLED=false` still blocks runs. History remains readable while stopped.

Environment changes in another shell do not affect an already running process;
use the file switch or Ctrl+C for an existing run. No scheduled jobs, server
services or external notifications are installed. Optional environment variables:
`GUARDIAN_CONFIG`, `GUARDIAN_OUTPUT`, `GUARDIAN_DB`, `GUARDIAN_STOP_FILE`.
Copy `.env.example` to `.env` if setting up another checkout.

## Assisted patch proposals

Milestone 4 adds manual repository inspection and isolated proposal/approval
commands. The audit graph does not call them. Repository policy lives in
`config/repositories.json`. Publishing is disabled in the tracked defaults;
owner enrollment is stored in an ignored local policy selected through
`GUARDIAN_REPOSITORIES` in `.env`.
No repository/environment secrets are copied, and no website scripts are run.

```powershell
.venv\Scripts\guardian repo-inspect --site estateplanning --repo-path C:/Users/User/Desktop/Work/sisweb
.venv\Scripts\guardian proposal-check --site estateplanning --proposal data/proposals/2c6fe0c3eb014de9bb193d6dd251f1bc
```

`repo-inspect` reads only allowlisted committed files and prints hashes/sizes.
Omit `--repo-path` to use the GitHub read-only API with a separately configured
`GUARDIAN_GITHUB_READ_TOKEN`. Local source inspection needs no new token.

`propose` accepts a manually prepared replacement file, an existing audit report,
evidence IDs and an allowlisted path. It saves before/after copies, `diff.patch`,
bounded `evidence.json`, a hash-bound manifest and `REVIEW.md` under `data/proposals`.
`proposal-check` reconstructs the diff, verifies hashes, and runs `git apply --check`
in a temporary copy. It does not run a website build or its application tests.

Publishing requires explicit owner enrollment, an exact artifact-hash
approval with a 1–60 minute expiry, enabled repository policy, and a separate
repository-scoped `GUARDIAN_GITHUB_WRITE_TOKEN`. The authenticated local OS user
is shown by `guardian identity`. CLI commands `approve`, `revoke` and `create-pr`
implement this manual flow; none is invoked by an audit or scheduler. Branch
protection policy, unchanged base content, scope, expiry, revocation and the kill switch
are checked before publishing. Approvals are consumed once; partial API failures
require manual reconciliation rather than automatic retry. Publishing creates
an isolated branch and PR only. `draft_pr` chooses draft/normal mode.
Merge/deployment stay human-only.

See [Milestone 4 details](docs/MILESTONE_4.md) for commands, credential permissions,
the local approval trust boundary and validation limits. The owner explicitly
authorized an unprotected-branch exception for `estateplanning` on GitHub Free:
`require_protected_branch: false` with a recorded rationale, and `draft_pr: false`.
Other configurations require a protected branch by default. Exact-patch approval
and unchanged base checks apply in either mode. The first live result is
[sisweb PR #2](https://github.com/KeeLekHeng/sisweb/pull/2), open and unmerged with
auto-merge disabled. This exception does not make the token itself merge-proof.

Rollback: stop local runs, preserve any wanted reports/database, and revert code
or remove the local environment and generated data. There is no website deployment
or production configuration to roll back. Retention is manual; no automatic data
deletion is enabled.

Milestone 5 adds optional public SEO checks (`guardian audit --site estateplanning --seo`)
and Lighthouse/PageSpeed JSON import (`--lighthouse-report path/to/report.json`).
Imported lab results preserve measurement dates and disable live history/alerts.
Manual period reviews and PageSpeed collection are now implemented; Google account/API
authorization and actual historical measurements remain pending. Owner-selected
reporting default is seven days versus the previous seven days.
See [Milestone 5 outcomes and commands](docs/MILESTONE_5.md).

```powershell
guardian review --site estateplanning --llm claude
guardian performance-sample --site estateplanning --url https://estateplanning.com.my/ --strategy mobile
```

Reviews compare search clicks, impressions, CTR and average position, then provide
evidence-backed investigation/improvement actions with optional Claude reasoning.
See [period reviews and Google access](docs/PERIOD_REVIEWS.md). Search Console access
in the owner's browser is confirmed; Guardian's read-only OAuth connection is not
configured yet. Synthetic examples are explicitly labeled and are not live results.
