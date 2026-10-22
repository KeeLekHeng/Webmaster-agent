# Design

Use the existing workflows and transport. The query/page request is an optional
third request per period (1,000-row cap); property totals remain independent.
Minimize likely personal identifiers, controls and credentials. Store accepted
query text only in local reports and the approved owner's minimized attachment.
Only numeric evidence and opaque labels reach Claude; citations remain checked.
Missing rows are unknown, and privacy/top-row omissions prevent exhaustive claims.

Receipt reconciliation is local-only, scoped to the enrolled destination, and
records OS actor, old outcome, decision and timestamp. Received means owner
confirmation, not API proof. Retry authorizes a single subsequent attempt for the
same key; it does not itself send. Recent pending sends cannot be reconciled.

The weekly runner uses an atomic site/week claim and per-stage redacted outcomes.
Failures preserve successful stages; the same week is never automatically retried.
A crash/interrupted job needs owner review. Partial collection is not site failure.
Uncertain sends are not resent by the runner. The bot's polling lease applies
only to update consumption; atomic delivery receipts allow concurrent outbound
reports while the listener runs.

Local activation writes ignored data/weekly.json and creates two restricted,
interactive-owner Windows tasks: Monday 09:00 UTC+8 collection, and a logon
listener with bounded restart policy. Missed weekly runs request catch-up; only
the most recent week is collected. Computer/network availability and owner login
are required. No password or privileged service is created. Disable script and
Guardian kill switch provide rollback; no report/database migration is needed.

Known limits: keyword minimization is heuristic; semantic interpretation remains
advisory. One lab sample per device/week is too sparse for the existing three-
samples-per-period alert threshold. Windows interactive tasks are not an always-on
VPS substitute; an exhausted listener restart budget still needs owner attention.
