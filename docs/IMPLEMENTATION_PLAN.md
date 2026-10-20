# Website Guardian — Milestones, Acceptance Criteria & Codex Handoff

The sequence is deliberately **small-first**. Estimated days are learning targets, not delivery commitments.

## Milestone 0 — Read-only discovery (first)
**Codex's immediate assignment:** inspect accessible repos and deployment descriptions without modifying anything. Produce `docs/DISCOVERY.md` with:
- Actual framework, package manager, dependency manifests, CMS, database and version control layout.
- Hosting model, production deployment flow, CI/CD, rollback method, backups, and known monitoring.
- Current test coverage, scanner availability, and whether Search Console/analytics are configured.
- Read-only access scope and permissions. Avoid exposing environment variables, secrets or customer records.
- Safe same-server deployment assessment: available CPU/RAM/disk; runtime isolation; backup/recovery impact; permission boundary; resource limits.
- Confirmed observations with evidence/file paths; unverified assumptions and remaining questions.
- Recommended minimal dependency list and scan tools selected based on the actual stack.

**Gate:** Obtain explicit go-ahead before installing anything on the website server or editing its repo.

## Milestone 1 — Reproducible local audit
Implement a CLI such as `guardian audit --site estateplanning` (illustrative, not a preexisting command) with:
- allowlisted URL checks with safe redirects, timeouts and bounded concurrency;
- TLS certificate metadata and expiry when practical;
- page title/description/canonical and simple broken internal link detection;
- normalized tool result schema containing source, timestamps, failures and evidence;
- optional existing dependency/security scan ingestion, only if source access approved;
- no LLM required to collect deterministic results.

**Acceptance:** Local dry-run/report for site without modifications; stable fixture-driven pytest tests including false-positive, redirect, SSRF, and timeout cases. Reports may legitimately contain zero issues.

## Milestone 2 — LangGraph investigation
A single graph:
```text
START → validate_config → collect_checks → normalize_evidence
      → investigate_findings → policy_filter → persist_history → summarize_handoff → save_report → END
```
LLM role: reason over bounded evidence, distinguish confirmed/suspected/unknown, prioritize impact and confidence, identify possible next steps. Use structured outputs and avoid unverified claims.

**Acceptance:** Audits reproducible, failed tool represented explicitly, LLM cannot execute arbitrary actions, evidence IDs appear in each finding, saved JSON/Markdown report.

## Milestone 3 — Persistence, scheduling and alerts
Add SQLite locally (migration path to PostgreSQL), history, deduplication, diff since previous scan, optional scheduler and owner notification. Prefer cron/systemd timer/job scheduler separate from reasoning engine.

Implemented locally on 2026-10-19: SQLite observation history, per-site comparisons,
deduplicated opt-in local alert records, a persistent stop file, site run leases,
and a disabled-by-default one-shot scheduling dispatcher. No scheduled job or
external delivery is enabled. See `MILESTONE_3.md` for validation and limitations.

### Concise summary and human handoff
Owner authorized local summary implementation on 2026-10-19. Completed within
the existing graph using a deterministic formatter; Telegram remains deferred.

- [x] Add a summarization step after investigation/policy filtering to produce a short human handoff, within the single workflow and without another model call.
- [x] Present each distinct issue once, with affected URL count, severity, plain-language impact, uncertainty, recommended next step and evidence/report references. Nine missing-HSTS observations appear as one issue affecting nine checked URLs.
- [x] Preserve detailed evidence in the full report. Tests verify grouping, unchanged severity/evidence, incomplete scans, omitted issue counts and unavailable reasoning.
- [x] Save `summary.md` locally and print it for terminal review. Limit the handoff to five issue groups and refer to the full report for remaining issues and detailed limitations.
- [ ] Later add Telegram delivery to an explicitly approved owner destination, with separate bot credentials, redaction, message limits, duplicate suppression and delivery error handling. Do not send messages or enable scheduling until configured and authorized. Telegram delivery is informational; it does not authorize production actions.

**Acceptance:** Repeat scans do not spam the same issue; alerts only for approved destinations; kill switch stops new jobs; restart does not lose run history; expired TLS warning uses verified time data.

**Gate for temporary same-host deployment:** performance/isolation review, separate user/container, no production data mounts, resource limits, least-privilege network, safe restart policy and observability. Deploy only with explicit approval. If insufficient capacity, keep local or use separate host.

## Milestone 4 — Assisted fixes (after V1 succeeds)
Read-only GitHub integration first. Build isolated workspace patch proposal, tests and evidence record. Require a human-reviewed exact patch before any PR creation. Protect default branch and keep production deployment human-only.

Local implementation and mocked publishing validation completed on 2026-10-19.
Manual CLI commands support allowlisted repository reads, isolated before/after
artifacts, hash-bound evidence, patch application checks, OS-identity approvals,
expiry/revocation and a disabled-by-default draft-PR executor. A concrete HSTS
proposal is ready for review. No website checkout changes, live approvals or
GitHub writes were performed. Owner enrollment, scoped GitHub credentials and
verification of live branch protection/provider access remain prerequisites for
publishing; see `MILESTONE_4.md`.

After explicit owner authorization, the policy was extended with a per-repository
unprotected-branch exception and normal PR mode for GitHub Free. An eligible local
owner approved the unchanged artifact hash, and `sisweb` PR #2 was created and
verified: one file matching the approved content, open/unmerged, auto-merge off.
All 125 tests pass. The audit graph still cannot publish or merge automatically.

**Acceptance:** Unapproved changes cannot be pushed; approver identity and exact diff hash checked by code; simulated missing/expired approval blocks execution; GitHub token has minimum required permissions.

## Milestone 5 — SEO / performance insights
Add Lighthouse, Google Search Console/analytics only if permissions and data availability are confirmed. Distinguish technical facts from causal hypotheses and business recommendations. Keep legal/estate-planning content changes human-reviewed.

## Milestone 6 — Separate agent-server migration
Deploy same artifact on an independent server/container environment with externalized configuration and storage. No dependency on shared `localhost`, host volume, production database or SSH credentials. Test cutover, duplicate job prevention, backup, alert routing, rollback and credential rotation.

## Long-term commercial evaluation (not in MVP)
Conduct customer interviews and a small service pilot. Before multi-client onboarding implement tenant-scoped access, isolation, billing/operational controls, separate legal/privacy review, response ownership and service boundaries. Do not promise guaranteed security or uptime.

## Recommended working structure (adapt after discovery)
```text
website-guardian/
├── AGENTS.md
├── docs/
│   ├── PROJECT_BLUEPRINT.md
│   ├── ARCHITECTURE_AND_SECURITY.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── DISCOVERY.md                # Codex creates after inspection
├── src/guardian/
│   ├── agent/                     # graph and state
│   ├── checks/                    # deterministic probes
│   ├── policies/                  # allowlists, decision rights
│   ├── integrations/              # GitHub, alerts, etc.
│   ├── storage/                   # audits/checkpoints
│   └── reports/
├── tests/
├── pyproject.toml
└── .env.example
```
Do **not** scaffold all modules before their scope is justified. Keep runtime, scanner tools and policies testable independently.

## Codex first-turn prompt
> Read `AGENTS.md` and all files in `docs/`. Do a **read-only** discovery of the Website Guardian repository and, only where separately authorized, the private `estateplanning.com.my` repository and deployment metadata. Create `docs/DISCOVERY.md` with confirmed evidence, unknowns, and a safe same-host deployment assessment. Then propose the smallest V1 architecture and exact first coding tasks. Do not edit the live website, install packages on its server, access customer data/secrets, configure cron, or deploy anything. Stop and request approval before changes.

## Decisions deliberately deferred
- Model provider/model ID; select after cost/privacy requirements and simple evaluation.
- Exact website framework, scanners and build commands; inspect first.
- Deployment software and cloud vendor; inspect existing environment, then choose portable options.
- Approval UI and notification channel; start with CLI/manual review until needed.
- Multi-agent orchestration and autonomous remediation; not needed to demonstrate value.

## Milestone 5 implementation status (2026-10-19)
Public SEO checks and safe Lighthouse/PageSpeed lab JSON import implemented locally.
Live public validation: nine HTTP 200 routes, eight HTML pages, no new SEO findings;
robots and sitemap available (17 sitemap locations, none followed).
Manual PageSpeed collection and a six-node period-review graph now support
Search Console totals/pages, numeric changes, comparable lab medians and optional
Claude investigation of evidence-backed decline/improvement candidates.
Owner selected seven-day comparisons and confirmed browser Search Console access.
Guardian OAuth authorization is not configured. One PageSpeed attempt was unavailable;
no live score was saved. Analytics, query-level ranking data, automatic OAuth refresh
and scheduled collection remain pending. See `PERIOD_REVIEWS.md` for acceptance,
commands, thresholds and actual data limitations. Real business outcomes are not yet validated.

Update 2026-10-20: owner selected 14-day comparisons; actual Search Console reads
with the manual token are verified. Low-volume review actions and Claude retries
are implemented. Persistent read-only Google refresh is implemented locally and
mock-tested, with safe authorization diagnostics and a manual `gsc-auth-check`.
Owner supplied the OAuth client/refresh grant and enabled Search Console API.
Live token renewal, search reads and a Claude-assisted 14-day review succeeded
on 2026-10-20. No credentials or consent grants were created by the agent.
See `GOOGLE_AUTH_SETUP.md`. Scheduling,
VPS deployment and external notifications remain disabled.
