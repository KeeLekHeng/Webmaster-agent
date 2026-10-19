# Milestone 3 outcome

Implemented on 2026-10-19 for local operation. The workflow now has eight nodes,
including `persist_history` before summary formatting. No additional dependencies
were required; persistence uses Python's SQLite library.

## Persistent observation history

The CLI uses `data/guardian.sqlite3`, configurable through `GUARDIAN_DB` or
`--database`. Schema version 1 separates runs, active issues, local alert records,
site leases and scheduling slots. Unsupported schema versions fail closed.
Queries are parameterized; transactions make issue updates, run registration and
alert deduplication atomic. A repeated run ID does not insert duplicate records.

SQLite stores the evidence/analysis snapshot and comparison at the persistence
node, before final summary/file generation. Final JSON/Markdown/summary artifacts
remain in the per-run reports directory. If later file generation fails, the
SQLite snapshot remains available; database and report-file writes are not one
atomic transaction. Report observation timestamps are distinct from database
recording times. No credentials or rejected raw model outputs are stored.

The storage interface is isolated from scanning and reasoning. A future PostgreSQL
backend can implement the same record/history/alert/lease operations with a schema
migration/export; PostgreSQL and migration automation are not installed now.

## Comparison and local alerts

- New: issue identity was not active before this live audit.
- Changed: severity or stable observations changed, such as affected URLs or the
  missing controls. Volatile body hashes, timestamps, raw headers and daily TLS
  countdown changes do not cause repeated issue alerts.
- Unchanged: active issue and stable observations match.
- Resolved: issue is absent, collection completed, and each affected source/check
  has a successful last observation in the new audit.
- Not observed: insufficient coverage to establish recovery. The previous active
  issue remains outstanding. Previously affected routes omitted from partial scans
  are retained rather than silently forgotten.

Replay/demo runs are archived separately; they never modify live baselines or
queue alerts. Site IDs scope history, active issues and outbox queries. This is
local configuration separation, not a multi-tenant authorization system.

`--notify local` opts into local outbox records for new, changed and resolved
issues. Default notification mode is none. Only none/local are accepted; no
external transport or recipients exist. Alert rows reference the run and issue;
they are not delivered messages and are not replayed externally on restart.
Scan failures remain in evidence, run status and the human summary; local issue
alerts are not independent uptime-monitoring or incident paging.

## Optional scheduling and stop controls

`guardian run-due` is a one-shot dispatcher intended for a future Windows Task
Scheduler/cron invocation. It has no sleep loop. `config/schedule.json` is disabled
and no operating-system job was registered. Enabling a schedule still needs the
owner's explicit decision. Site configuration and network policies apply equally
to scheduled and manual scans. Scheduled reasoning is none, so it cannot silently
spend Claude tokens.

When explicitly enabled, the dispatcher atomically claims one durable UTC time
slot per site/interval (60 minutes to seven days). Slots are aligned to UTC epoch
boundaries, not a chosen local wall-clock time. A failed or interrupted claim is
not automatically retried in that slot. Concurrent audits use a one-hour site
lease; normal completion/error releases it. A hard-killed process may leave a
lease until expiry. Extremely long runs exceeding that lease are a remaining
overlap risk; DNS resolution remains subject to the OS resolver timeout. No
unattended operation is enabled while these choices are awaiting owner review.

`guardian stop` creates `data/STOP`; protected workflow nodes, network actions,
history writes and job claims check it. `guardian resume` removes a recognized
Guardian marker. `AGENT_ENABLED=false` remains an independent stop control.
In-flight network requests are not immediately cancelled. Local read-only history
and alert queries remain available while stopped. A restart never resumes a
pending production write: no write executor or write approval queue exists.

## Verification

78 pytest cases passed. New tests cover persistence across reopened stores,
idempotency, changed/recovered/reappearing issues, incomplete coverage, later
failed checks, site isolation, notification allowlists and opt-in behavior,
leases, persistent stops, durable scheduler slots, disabled scheduling, failed
job suppression, schema versions and TLS expiry derived from certificate times.

Two real read-only audits were run with no LLM call:

1. `ce95bcc4d4934b56a3447198a637e06a`: one new low-severity HSTS issue; one local
   alert record queued.
2. `7174faecaa6e48b19179663f404858ef`: the same issue unchanged; zero additional
   alert records. Its comparison references the first run.

Both returned HTTP 200 for all nine checked URLs; verified TLS had approximately
72 days remaining. The `history` and `alerts` commands confirmed two saved live
runs and one local alert record across separate CLI processes. `run-due` printed
disabled and started no audit. Evidence-backed reports are under those run IDs
in the local reports directory.

No production modifications, form submissions, customer-data access, Claude calls,
Telegram messages, scheduler registration or hosting changes were made.

## Retention and next steps

SQLite and reports are Git-ignored and remain local. Retention and backup are
manual; no automatic pruning/deletion is enabled. Back up the database only when
no run is active, or use SQLite's backup API. Owner review is required before
choosing unattended timing, retention budgets or a notification destination.
Telegram delivery remains deferred. Same-host production deployment has not been
assessed or approved; continue running locally.
