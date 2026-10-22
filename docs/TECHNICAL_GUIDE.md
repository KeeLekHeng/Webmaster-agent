# Website Guardian technical guide

Updated 22 October 2026. This is the maintained reference for architecture,
security, setup, operations and remaining work. It replaces separate blueprint,
milestone, walkthrough, setup and TODO documents; historical versions remain in
Git. OpenSpec change specifications and acceptance records remain separate.
Update this guide when behavior changes instead of creating another milestone file.

## Contents

- [Purpose and current state](#purpose-and-current-state)
- [Architecture and code structure](#architecture-and-code-structure)
- [Security and decision rights](#security-and-decision-rights)
- [Installation and configuration](#installation-and-configuration)
- [Audit and SEO commands](#audit-and-seo-commands)
- [Google authorization](#google-authorization)
- [Telegram](#telegram)
- [Local scheduling](#local-scheduling)
- [Assisted repository changes](#assisted-repository-changes)
- [Storage and retention](#storage-and-retention)
- [Discovery and VPS boundaries](#discovery-and-vps-boundaries)
- [Implementation and validation](#implementation-and-validation)
- [Remaining work](#remaining-work)

## Purpose and current state

Website Guardian is a separate Python/LangGraph maintenance assistant for
`https://estateplanning.com.my/`. Priorities are availability, security hygiene,
then SEO. Deterministic tools collect facts; optional Claude reasoning explains
and prioritizes evidence-backed review actions. Commercial demand is unvalidated.

Guardian runs on the owner's Windows computer. Public audits, Search Console,
PageSpeed, Telegram reports and local scheduling are implemented. The website is
reported to run on a DigitalOcean VPS; Guardian is not deployed there. A dedicated
Guardian VPS remains future work.

Tracked defaults leave scheduling and Telegram disabled. On 22 October the owner
enabled this computer's weekly digest and supervised Telegram listener. Ordinary
`audit` and `review` commands still do not send messages; the separate weekly
runner invokes collection and approved owner delivery.

Manual, exact-approval PR preparation/publishing exists outside the audit graphs.
Merge, production deployment, DNS/firewall/credential changes and backup restoration
remain human-only. There is no general chatbot, multi-agent platform, RAG system,
dashboard or multi-tenant SaaS.

## Architecture and code structure

```text
CLI / explicitly enabled local scheduler
  -> deterministic read-only collection -> bounded evidence projection
  -> optional Claude interpretation -> independent policy/citation checks
  -> history, summary and saved report
  -> approved private-owner delivery, when explicitly requested

Manual isolated patch -> exact human approval -> scoped PR only
Human operator -> merge and production deployment
```

Audit LangGraph:

```text
START -> validate_config -> collect_checks -> normalize_evidence
      -> investigate_findings -> policy_filter -> persist_history
      -> summarize_handoff -> save_report -> END
```

Period-review LangGraph:

```text
START -> validate_period -> collect_period -> compare_period
      -> investigate_period -> policy_filter -> save_period -> END
```

LangGraph runs the flowchart locally; Claude is the external model called by one
node. State is the shared typed data, a node is a Python function, and an edge
connects nodes. `StateGraph`, `add_node`, `add_edge`, `compile` and `stream` build
and execute the paths. Graph state lives in memory for one run; reports and SQLite
history persist, but interrupted graphs have no durable resume checkpoints.
`guardian explain` prints a beginner walkthrough without network requests.

| Package | Responsibility |
| --- | --- |
| `src/guardian/core/` | Schemas, HTTPS scope, kill switch |
| `src/guardian/checks/` | HTTP/TLS audit, SEO, lab measurements |
| `src/guardian/integrations/` | Google OAuth and Search Console |
| `src/guardian/workflows/` | Audit/review graphs, Claude adapter and filtering |
| `src/guardian/reporting/` | Deterministic human summaries |
| `src/guardian/storage/` | SQLite audit history, comparisons and local alerts |
| `src/guardian/scheduling/` | One-shot dispatcher and opt-in weekly runner |
| `src/guardian/remediation/` | Repository reads, proposals, approvals and PR commands |
| `src/guardian/telegram/` | Pairing, transport, receipts, formatting and commands |
| `src/guardian/cli/` | Entry point, parser and terminal walkthrough |
| `tests/` | Tests grouped by the same responsibilities |
| `config/`, `scripts/` | Tracked settings/templates and Windows task launchers |

Both `guardian ...` and `python -m guardian.cli ...` work; the entry point remains
`guardian.cli:main`. Internal flat imports changed, for example `guardian.workflow`
became `guardian.workflows.audit`. Use canonical cross-package imports. History
and dispatcher tests remain together in `tests/storage/`. Do not add extra layers
just to move functions.

## Security and decision rights

Application-side policy grants authority; model instructions never do.

| Action | Right |
| --- | --- |
| Bounded allowlisted reads, explanations and reports | A: scope, schemas, budgets and kill switch |
| Notifications | A only to the enrolled, approved owner destination |
| Manual PR publishing | H+A: eligible authenticated actor, exact artifact hash and expiring approval |
| Merge, deployment, DNS/firewall/credential changes, restoration | H: no autonomous executor route |

Public pages, repository files, reports and tool output are untrusted data. The
model has no execution tools, shell, credential selection or self-authorization.
It cannot change scanner facts/severity or run a proposed fix. Missing permission,
uncertain scope, expired/revoked approval and human non-response fail closed.

Public HTTP checks allow configured HTTPS hosts and exact paths only. Forms,
query strings, unknown/admin paths and arbitrary APIs are outside probe scope.
Redirects are validated, DNS answers must all be public, and connections pin a
validated IP while preserving TLS hostname/chain verification. Requests are
sequential, delayed, size/time bounded and retry at most once for network/5xx
failures. Proxy inheritance is disabled; DNS timeout remains OS-controlled.
Raw HTML, cookies, customer submissions and response bodies are not persisted.

Claude sees bounded numeric/boolean observations, known labels and opaque IDs,
not URLs, query phrases, page text, credentials or repository content. Inputs are
capped at 32 KiB and 20 findings, output at 1,800 tokens. LangSmith external tracing
is explicitly disabled. Pydantic and Python validate response structure, citation
membership, duplicate notes and obvious unsafe command/URL patterns. Citation
validity does not prove prose is semantically correct or establish causation.

Claude transient connection/timeouts and HTTP 408/409/429/5xx get up to three
retries after the initial request, waiting 2, 4 and 8 seconds. SDK retries are off;
each request has a 30-second timeout. Backoff checks the kill switch every 250 ms.
Invalid credentials/model, refusals and schema failures are not retried this way.
Failures preserve deterministic actions with safe diagnostics. Usage records the
successful response, not unknown failed-request costs. Google has no such retry loop.

```powershell
guardian stop
guardian resume
```

The persistent switch is `data/STOP` (`GUARDIAN_STOP_FILE` overrides it).
`AGENT_ENABLED=false` also blocks work. Use the file switch for existing processes:
another shell's environment and edited `.env` do not automatically reload.
Subsequent protected operations stop; in-flight requests finish or time out.
Resume clears the Guardian marker, not a false environment flag. History remains
inspectable; stopping does not unregister scheduled tasks.

Known boundaries: local owner processes can alter local files/state, model prose
needs review, and collector failure is not proof of outage. Never-alone action:
production deployment. Hosting gap: safe shared-host isolation is unverified.
Scale bottleneck: human review. The governance appendix is a design reference,
not a compliance certification or definitive Malaysian legal guidance.

## Installation and configuration

Run from the checkout with Python 3.11 or newer:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.lock
.venv\Scripts\python -m pip install --no-deps -e .
.venv\Scripts\python -m pytest -q
```

Alternatively use `pip install -e '.[dev]'`; the lock file captures the verified
dependency snapshot. Do not install/run the website's packages during an audit.
Copy [`.env.example`](../.env.example) to `.env` for a new setup. The CLI loads it
from its working directory without interpolation; existing environment values win.
It is plaintext configuration, not a vault. Restrict access and never commit it.

| Variable/configuration | Purpose |
| --- | --- |
| `config/sites.json`, `GUARDIAN_CONFIG` | Site/path allowlists and request budgets |
| `GUARDIAN_OUTPUT`, `GUARDIAN_DB` | Report root and audit-history database |
| `AGENT_ENABLED`, `GUARDIAN_STOP_FILE` | Kill-switch controls |
| `ANTHROPIC_API_KEY`, `GUARDIAN_MODEL` | Optional Claude key/model; owner selected Haiku |
| `GUARDIAN_GSC_PROPERTY` | Exact verified domain or URL-prefix property |
| `GUARDIAN_GSC_CLIENT_ID`, `GUARDIAN_GSC_CLIENT_SECRET`, `GUARDIAN_GSC_REFRESH_TOKEN` | Read-only OAuth renewal |
| `GUARDIAN_GSC_ACCESS_TOKEN` | Short-lived manual token when all refresh fields are empty |
| `GUARDIAN_PAGESPEED_API_KEY` | Separate PageSpeed API key |
| `GUARDIAN_TELEGRAM_ENABLED`, `GUARDIAN_TELEGRAM_BOT_TOKEN`, `GUARDIAN_TELEGRAM_CHAT_ID` | Explicit delivery flag and enrolled destination |
| `GUARDIAN_REPOSITORIES` | Ignored local owner-enrolled publishing policy |
| `GUARDIAN_GITHUB_READ_TOKEN`, `GUARDIAN_GITHUB_WRITE_TOKEN` | Separate scoped repository credentials |

Exit 0 means completed, possibly with findings; 1 includes partial collection or
unavailable/partial/rejected analysis; 2 means configuration/startup/save failure.
Individual command `--help` documents exact arguments/defaults.

## Audit and SEO commands

```powershell
guardian audit --site estateplanning --llm none
guardian audit --site estateplanning --seo --llm claude
guardian history --site estateplanning --limit 5
guardian alerts --site estateplanning
guardian review --site estateplanning --llm claude
guardian review --site estateplanning --days 7 --no-queries --llm none
guardian performance-sample --site estateplanning --url https://estateplanning.com.my/ --strategy mobile
guardian performance-sample --site estateplanning --url https://estateplanning.com.my/ --strategy desktop
```

Audits check public availability, TLS validity/expiry, selected headers, metadata
and internal links within approved scope. Optional SEO covers canonical/noindex,
H1/duplicate titles and bounded robots/sitemap discovery. Sitemap locations are
inspected, not automatically crawled. Metadata presence is not content quality or
indexing proof; missing headers are hardening observations, not proven exploits.
An `ok` health response does not prove database/email health. No forms are submitted.

Reports include timestamped evidence, source URLs/tool versions, severity,
confidence, limitations and actions. A deterministic handoff groups repeats into
at most five issues, counts unique affected URLs and links full evidence without
another model call. `--input-report <report.json>` replays original observations;
`--llm demo` is explicitly fake reasoning. Replay/demo cannot update live baselines
or alerts. `--lighthouse-report <file.json>` imports dated lab evidence without live
history and cannot be combined with replay. History distinguishes new, changed,
unchanged, resolved and not-observed issues; partial coverage cannot prove recovery.
`--notify local` queues local alert rows only. Default notification is none.

Period reviews compare 14 days with the prior 14 by default, optionally 7 or 28 per
window. Fully populated 28-day comparisons need 56 days. New sites may have sparse
earlier periods. Dates use Google's Pacific calendar: default end is three days
before Pacific today, or conservative UTC minus four days without Windows timezone
data. `--end-date YYYY-MM-DD` overrides it. Only finalized data is requested;
coverage for every date is not guaranteed.

Each period requests independent property totals, up to 1,000 page rows and up to
1,000 query/page rows: up to six read-only queries overall. `--no-queries` skips
query sampling. HTTP POST is Google's read API, not a property write. Page URLs
must pass scope checks; optional query failure preserves totals. Obvious phone/
email identifiers, controls and credentials are omitted, but filtering cannot
detect all personal text. Accepted phrases stay in local files and the approved
owner report, outside model inputs. Totals are not row sums; sampled/anonymized
missing rows are unknown, never zero. Position is impression-weighted, not a fixed
keyword rank. Intent, page defects, competitors and business causes remain unproven.

Python calculates deltas/candidates; Claude explains numeric evidence. Finding F,
evidence E and query Q labels are separate namespaces; exact bindings are enforced.
Thresholds are triage heuristics, not statistical significance:

- Click loss: previous clicks >=20, absolute loss >=10 and relative loss >=20%.
- Weaker position: >=100 impressions per period and position number increase >=2.
- CTR opportunity: >=100 impressions per period and drop >=1 percentage point.
- Page opportunity: >=100 current impressions, position 5–20 and CTR <=2%.
- Low-volume/query actions: bounded reviews with uncertainty; missing previous
  rows cannot support an invented decline.
- Lab action: matching URL/device/Lighthouse-major/profile, >=3 distinct samples
  per window, median performance score decline >=10.

Lab results are dated observations, not past real-visitor performance. Duplicate
artifacts/timestamps and boundary-day samples are excluded; distinct files alone
do not prove independent measurements. `--performance-sample` (repeatable) or
`--performance-dir` overrides default `data/performance/<site>/` inputs.
`--input-search <file.json>` imports validated owner-declared input, not authenticated
live provenance. Analytics, conversions, arbitrary SERPs and competitors are not
integrated. References: [Search Analytics API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query),
[sampling limits](https://developers.google.com/webmaster-tools/v1/how-tos/all-your-data),
[PageSpeed results](https://developers.google.com/speed/docs/insights/v5/get-started).

## Google authorization

The owner supplied their OAuth client and read-only grant; renewal/property reads
are verified. The owner reports External/In Production status. Guardian creates
no credentials, account permissions or consent grants. For a new installation:

1. In [Google Cloud Console](https://console.cloud.google.com/), select/create the
   Guardian project and enable Google Search Console API.
2. Configure OAuth branding/contact details/audience. Add yourself as a tester in
   Testing; review the provider's publishing requirements for lasting access.
3. Request only `https://www.googleapis.com/auth/webmasters.readonly`.
4. Create a Web application OAuth client for Playground with redirect URI
   `https://developers.google.com/oauthplayground`.
5. In [OAuth Playground](https://developers.google.com/oauthplayground/), enable
   **Use your own OAuth credentials**, supply that client and use offline/server-side
   consent. Authorize the read-only scope and exchange the code.
6. Store client ID, secret and refresh token in `.env`, never chat. Set the exact
   verified property, such as `sc-domain:estateplanning.com.my` or
   `https://estateplanning.com.my/`.

```powershell
guardian gsc-auth-check
guardian review --site estateplanning --llm none
```

Auth-check verifies renewal, not particular-property access. Each live review gets
a fresh access token from the fixed Google endpoint, retains it in memory and does
not rewrite secrets. All three refresh fields are required if any is set. Failure
does not silently fall back to a stale manual token. The response must confirm
exactly the permitted read-only scope, Bearer token and valid lifetime.
Exchange has a 15-second timeout, 64 KiB cap, read-time budget, no proxy/redirects/
automatic retries, and kill checks. Failures use safe fixed labels; raw responses
and tokens are not logged. Changed refresh tokens require human review. Imported
reports do not renew or verify authorization. Testing/Playground-default grant
limits matter; Production refresh grants can also expire or be revoked.

References: [offline access](https://developers.google.com/identity/protocols/oauth2/web-server#offline),
[client setup](https://support.google.com/cloud/answer/15549257),
[Testing-mode expiry](https://support.google.com/cloud/answer/15549945).
PageSpeed needs its separate API/key configuration, not Search Console OAuth.

## Telegram

Create a dedicated BotFather bot and put the token in `.env`, initially disabled.
A plain `/start` opens the chat but does not pair it with Guardian:

```powershell
guardian telegram-pair
# Send the exact /start <challenge> to your private bot within five minutes.
guardian telegram-pair --check
guardian telegram-pair --confirm YOUR_NUMERIC_CHAT_ID
```

Save the verified ID as `GUARDIAN_TELEGRAM_CHAT_ID`. Pairing stores a single-use
challenge hash, bot identity and confirmed owner. Sender must match the private
chat, not a bot/group/forward. Existing enrollment cannot be silently overwritten;
existing webhooks are not deleted. Then explicitly enable delivery locally:

```powershell
guardian telegram-send --site estateplanning --preview
# With GUARDIAN_TELEGRAM_ENABLED=true and valid enrollment:
guardian telegram-send --site estateplanning --run-id SAVED_RUN_ID
guardian telegram-status --site estateplanning --details
guardian telegram-listen --site estateplanning
```

Preview has no Telegram access. Sends regenerate a minimized Markdown report,
not an arbitrary attachment. The caption has bold WEBSITE STATISTICS and SEO
IMPROVEMENTS TO REVIEW headings, up to three numbered actions, per-action confidence
and overall uncertainty. Operational audits use availability/security/speed groups.
Dynamic HTML is escaped; Telegram has no custom message font sizes. Whole blocks
are omitted to fit 900 characters. Saved timestamps use MYT, Google periods Pacific.
The attachment leads with actions, advisory reasoning/uncertainty and an evidence
appendix. The [HTML prototype](design/telegram-report-preview.html) is a design
reference, not the live renderer; test device support before changing formats.
Avoid the ambiguous label “Search review.” Confidence comes from saved findings,
not invented percentages; empty findings show not assessed.

`/status` and `/report` read eligible saved live reports only. They cannot scan,
call Claude, approve, merge or deploy. Other chats/bots/groups, forwarded/edited
messages and commands older than five minutes are ignored. Unknown owner commands
get fixed help. Limit is six responses/minute. Incoming text is not saved; offsets
and command IDs prevent replay. `--once` polls once. Only update consumers hold
the polling lease; atomic receipts allow outbound sends while the listener polls.

Identical manual content/report sends are suppressed after confirmed or uncertain
attempts; a fresh owner `/report` can request it again. `--important-only` dispatches
changed medium/high HTTP/TLS/health/header state from live history. Complete
supporting coverage is required for recovery; revisions permit later recurrence.
Ordinary audits/reviews do not invoke delivery automatically.

Transport uses fixed official methods/host, no proxies/redirects/raw HTTP logs,
bounded responses/time and kill checks. Confirmed 429s may retry twice with validated
1–30 second waits. Uncertain sends never blindly retry. Read-only polling separately
retries transient errors after 2/4/8 seconds. Unsafe, out-of-scope, synthetic,
demo/replayed or oversized reports are rejected. Attachments are <=256 KiB and
exclude known secrets, private paths, configuration and raw scanner errors.
Telegram is not an end-to-end secret chat; local retention cannot delete sent or
downloaded Telegram/device copies.

### Delivery reconciliation

```powershell
guardian telegram-status --site estateplanning --details
guardian telegram-reconcile --site estateplanning --key RECEIPT_KEY --decision received
# OR, after checking the chat and accepting possible duplicate delivery:
guardian telegram-reconcile --site estateplanning --key RECEIPT_KEY --decision retry
```

`received` records owner confirmation, not API proof, and preserves suppression.
`retry` allows one subsequent attempt of the exact key, sending nothing itself.
Rerun the same manual `telegram-send --run-id ...` to consume it. Command/weekly
contexts have different keys; fresh `/report` requests are new deliveries. Decisions
are destination-scoped and record OS actor, timestamp and prior outcome. Pending
receipts <120 seconds old cannot be reconciled; successful sends cannot be reset.
Never delete unresolved state just to force a resend.

## Local scheduling

```powershell
powershell -NoProfile -File scripts/weekly-task.ps1 -Enable
powershell -NoProfile -File scripts/weekly-task.ps1
powershell -NoProfile -File scripts/weekly-task.ps1 -Disable
guardian weekly-digest --schedule-config data/weekly.json --preview
```

Activation writes ignored `data/weekly.json` from disabled `config/weekly.json`,
checks Malaysia UTC+8 system time and refuses to overwrite different task actions.
Both tasks use the current interactive owner and Limited privileges:

| Task | Behavior |
| --- | --- |
| `WebsiteGuardian-estateplanning-Weekly` | Monday 09:00 Malaysia: audit, mobile/desktop samples, 14-day query review with configured Claude; important changes plus SEO digest |
| `WebsiteGuardian-estateplanning-Telegram` | At owner login: read-only listener; failed process restart up to three times one minute apart |

The computer must be on, online and the owner logged in. Weekly catch-up is
requested without waking the machine or guaranteeing always-on operation. Only
the latest week runs, not a backlog. IgnoreNew and atomic site/week claims prevent
overlap/duplicate collection, model calls and sends. Failed/interrupted weeks are
not automatically rerun; independent successful stages remain recorded. Inspect
`data/weekly.sqlite3` and receipts before recovery. One sample/device/week normally
leaves fewer than three per 14-day period, so stronger lab alerts need more data.

The installer does not immediately launch tasks. Stop any foreground listener
before starting the Telegram task. Abruptly killed consumers can leave a lease
for up to 120 seconds: wait rather than remove active coordination state. `.env`
changes require restart. Disable stops running instances and disables both tasks;
`guardian stop` blocks protected work without unregistering them. Task arguments
contain no credentials. The launcher writes safe `data/logs/` output, rotating at
process start over 1 MiB; this is not continuous or time-based retention.

The older `guardian run-due` interval dispatcher uses disabled `config/schedule.json`,
deterministic checks, durable UTC slots and a one-hour audit lease. It is separate
from weekly collection. See [Windows task settings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).

## Assisted repository changes

Tracked `config/repositories.json` has publishing off/no approvers; ignored local
owner policy is selected by `GUARDIAN_REPOSITORIES`. Manual commands include:

```powershell
guardian identity
guardian repo-inspect --site estateplanning --repo-path C:/Users/User/Desktop/Work/sisweb
guardian propose --site estateplanning --repo-path LOCAL_CHECKOUT --report REPORT_JSON --evidence E003 --path next.config.ts --replacement CANDIDATE_FILE
guardian proposal-check --site estateplanning --proposal PROPOSAL_DIRECTORY
guardian approve --help
guardian revoke --help
guardian create-pr --help
```

Local reads use allowlisted committed Git objects, not working-tree secrets. Git
uses fixed arguments, shell/hooks/fsmonitor off, bounded output/time. Symlinks,
submodules, executable modes, traversal, environment/Git/workflow paths and Windows
device paths are blocked. GitHub reads use fixed HTTPS routes, pinned tree modes/
blob hashes and a separate scoped token. No website scripts are executed. Initial
read scope: package.json, pnpm-lock.yaml, next.config.ts; patch scope: next.config.ts.

Bundles contain before/after, diff.patch, evidence.json, proposal.json and REVIEW.md.
Hashes bind artifacts/evidence. Validation reconstructs the diff and runs
`git apply --check` in a temporary copy, not the website checkout. This proves
integrity/application, not functional correctness or website build/test success.

Publishing requires an eligible authenticated OS principal (Windows SID/POSIX UID),
exact hash-bound approval expiring in 1–60 minutes, unchanged base commit/content,
enabled policy and a separate writer scoped to Contents/Pull requests write. Reader
uses Contents read/metadata. Token scope cannot be attested from an opaque string.
Approval is transactional, single-use, and checked for expiry/revocation/kill switch
before mutations. Local owner processes can alter their files; this is a trusted
workstation boundary, not independent remote human authentication.

Branch protection is default. The owner accepted a recorded unprotected-branch
exception and normal rather than draft PR mode for the private GitHub Free site
repository; exact approval/base checks remain. A write token is not inherently
merge-proof. The executor has only bounded branch/content/PR routes, no merge or
deploy. Partial API failures can leave artifacts and need manual reconciliation.
The initial one-day HSTS proposal produced [sisweb PR #2](https://github.com/KeeLekHeng/sisweb/pull/2);
the owner subsequently reported merging and handling deployment separately.

## Storage and retention

These currently live on the Guardian computer, relative to the checkout unless
configured otherwise. SQLite databases are local files too, not a remote database
service. A future VPS needs explicit selected-data transfer, not just a code push.

| Location | Contents |
| --- | --- |
| `reports/<run-id>/report.json` | Full evidence, findings, reasoning and workflow metadata |
| `reports/<run-id>/report.md`, `summary.md` | Full readable report and concise handoff |
| `reports/<run-id>/search-periods.json` | SEO totals/pages and accepted query/page samples |
| `data/guardian.sqlite3` | Audit JSON snapshots, issue baselines, comparisons, local alerts, leases and interval jobs |
| `data/performance/<site>/*.json` | Minimized dated Lighthouse/PageSpeed samples |
| `data/telegram.sqlite3` | Pairing, offsets, command outcomes, receipts/reconciliation and important-state revisions |
| `data/weekly.sqlite3` | Weekly claims, stage status and report IDs; created when a weekly run executes |
| `data/approvals.sqlite3`, `data/proposals/` | Approval/attempt/event records and exact proposal artifacts |
| `data/logs/` | Safe launcher/listener outcomes |
| `.env`, `data/repositories.local.json`, `data/weekly.json` | Private credentials/policy and local activation |

Audit reports have file and database representations. SEO period reports are files;
their full contents are not saved to audit history or the weekly database. Telegram
renders/uploads a minimized attachment in memory and retains local delivery metadata,
not a separate attachment copy. Deleting files does not delete SQLite snapshots or
Telegram/device copies. `reports/`, `data/` and `.env` are Git-ignored.

### Recommended retention — not implemented or enabled

| Record | Recommendation |
| --- | --- |
| Detailed reports, query text, closed audit snapshots and old lab samples | 90 days, preserving live baselines and unresolved evidence |
| Compact monthly numeric statistics | 13 months for longer trends; aggregation is not yet implemented |
| Routine logs | 30 days plus size limits; current rotation only happens at startup |
| Approval/change audit records and referenced proposals | At least 12 months, longer while unresolved; an operator policy, not a legal claim |
| Pairing, offsets, current issues, active policy, unresolved delivery/approval state | Keep while in use; no blanket age-based purge |
| Compact delivery/job deduplication identifiers | Preserve while old artifacts/requests may be replayed, including restored backups |

Ninety days is a useful detailed-history default, not permission to wipe databases
or the data directory. A future cleanup command should preview candidates, use
evidence dates rather than file modification times, preserve latest live state and
unresolved references, coordinate with active runs, aggregate before deletion and
save a redacted cleanup receipt. Backups need separate expiry; freeing SQLite file
space is separate from deleting rows. Do not remove receipt/pairing/approval tables
to reclaim space or bypass deduplication. Local cleanup cannot erase remote copies.

No automated cleanup is enabled and no generated records are deleted by this
documentation consolidation. A 22 October inventory found about 0.56 MiB of reports
and 0.19 MiB under data, so there is no immediate disk pressure.

## Discovery and VPS boundaries

Initial 19 October discovery inspected separately authorized website source, not
production secrets or customer data. Local/remote HEAD then matched
`9791eefcd5b5535c81c40cc3d108eb0b981d695e`; this is historical, not today's production
revision. Confirmed declarations/paths included:

- `package.json`: Next.js 16.3.3, React 19.2.8, TypeScript, pnpm 10.18.2, Node
  >=20.9.0 and pnpm-lock.yaml. These are declared, not verified installed versions.
- Supabase libraries, documented Resend email and unit/integration/e2e test sources;
  production-connected website tests were not executed.
- `src/app/api/health/route.ts`: simple status; `next.config.ts`: security policy.
  Source does not establish live edge configuration or downstream service health.
- `deploy.sh`: operator pull/install/in-place build/systemd restart/health sequence;
  atomic deployment/rollback safety is unproven. No GitHub workflow was initially
  found; external CI remains unknown.
- `ops/Caddyfile.final-domain`: documented loopback port 3002 and co-hosted app.
  Deployment notes describe a historical shared 1 GB Droplet/build outage; these
  are not current capacity measurements. `docs/admin-sessions.md` documents MFA
  and a UAT override; production settings remain unverified.

Production revision/configuration, current load, monitoring, tested recovery and
backup coverage, external CI and live email delivery still need verification.
Later Search Console access does not resolve those infrastructure unknowns.

Local or dedicated-host operation remains preferred. Temporary same-host deployment
requires measured capacity, separate restricted identity/container, credentials,
storage and quotas; outbound-only communication; no website/database/Docker socket/
production SSH mounts. Containers do not remove shared-host risk. Safe separation
on the existing VPS has not been established.

Dedicated VPS cutover must independently provision secrets, coordinate SQLite
backup/transfer, move selected reports, stop the old scheduler/poller before
enabling the new host, verify leases/deduplication, backups and rollback, and retain
the kill switch. Do not casually copy active SQLite files. No localhost/shared
filesystem/website database/SSH dependency is allowed. Multiple clients would need
explicit credential/report isolation before onboarding.

## Implementation and validation

| Stage | Outcome |
| --- | --- |
| Milestone 0 | Source discovery, local-first decision, infrastructure unknowns recorded |
| Milestone 1 | Bounded deterministic audit and saved reports |
| Milestone 2 | Local LangGraph, optional Claude, citation policy and human summary |
| Milestone 3 | SQLite history, dedupe, kill switch, leases and interval dispatcher |
| Milestone 4 | Manual approved proposals/PRs; human merge/deployment |
| Milestone 5 | Public SEO, lab samples, 14-day GSC reviews, OAuth renewal and Claude retries |
| Owner follow-ups | Query actions, paired Telegram, reconciliation and weekly local scheduling |
| Milestone 6 | Dedicated Guardian VPS remains pending |

Latest suite: 271 passed, one Windows symlink-creation skip for missing privileges.
Coverage includes scope/redirect/SSRF, injection/citation rejection, duplicates,
partial/unreachable APIs, retries, approval expiry/revocation, query minimization,
unknown previous rows, reconciliation and weekly claims. These are Guardian tests,
not website application/build verification.

Live 22 October review compared 5–18 October with 21 September–4 October Pacific:
clicks 3 to 10, impressions 24 to 120, CTR 12.50% to 8.33%, average position 26.04
to 44.95. Recommendations remained low confidence. Wider exposure/weaker average
position does not prove regression or its cause. Report
`reports/1f988f33c65746dfae740c947b047f10/` saved complete reasoning. Fresh lab scores
were mobile 99 and desktop 100; mobile recovered after API 400 failures. These
are dated observations, not current guarantees.

Latest Telegram summary/document sent, repeated send suppressed, and owner-confirmed
`/report` and supervised `/status`. Tasks were Interactive/Limited with IgnoreNew;
next weekly run at validation time was 26 October 2026, 09:00 Malaysia. First
automatic Monday execution was still upcoming; weekly stages have mocked integration
tests. Both active OpenSpec changes passed strict validation.

Rollback uses Git and preservation of required local state. Disable tasks/stop
work before reverting commands they depend on. No production deployment was part
of these changes, so no website rollback is involved.

## Remaining work

- Verify the first automatic Monday digest and real missed-run behavior.
- Implement retention separately with preview, aggregation and protected references.
- Consider more frequent speed samples for stronger comparisons.
- Prepare dedicated VPS identity, secrets, backup and state cutover.
- Corroborate keyword/content recommendations before human-reviewed edits,
  particularly legal/estate-planning content.
- Preserve the owner's idea: assess relevant new security advisories against a
  verified dependency inventory. Headlines alone do not prove site exposure.
- Validate service demand before multi-tenancy, billing or dashboards.

References: [governance appendix](PE6202_Group_Project_2_-_Appendix.pdf),
[OpenSpec records](../openspec/changes/), [agent instructions](../AGENTS.md).
