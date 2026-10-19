# Website Guardian discovery

Date: 2026-10-19. Scope: initial read-only repository inspection and document review. No production connection, scans, tests, dependency installation, or deployment was performed.

## Owner decisions

- Website repository: https://github.com/KeeLekHeng/sisweb; local checkout: `C:\Users\User\Desktop\Work\sisweb`.
- Hosting: DigitalOcean VPS, confirmed by the owner.
- Priority: website availability, then security hygiene, then SEO.
- Guardian starts locally; a VPS deployment is a later step.
- The PE6202 appendix is a governance reference, available in `docs/PE6202_Group_Project_2_-_Appendix.pdf`.

## Confirmed observations

- GitHub read access via `git ls-remote ... HEAD` succeeded. Remote HEAD and local HEAD were both `9791eefcd5b5535c81c40cc3d108eb0b981d695e`. This verifies access to Git references, not write permission or the production revision. Local `git status --short` returned no changes.
- Guardian currently contains planning documents and a minimal README; no implemented runtime was identified in the initial inventory.
- Website `package.json` declares Next.js 16.3.3, React 19.2.8, TypeScript, pnpm 10.18.2 and Node >=20.9.0. A `pnpm-lock.yaml` exists. These are declared versions, not verified installed versions or security assessments.
- Supabase libraries are declared for data/authentication. `README.md` describes Supabase-backed data and admin authentication. Resend email delivery is documented in the deployment guide; email webhook routes and tests exist.
- `package.json` exposes lint, typecheck, build, formatting and Playwright commands. `tests/unit`, `tests/integration`, and `tests/e2e` contain checks covering authentication, forms, email, security headers, public pages and SEO. Their presence does not establish passing status or coverage completeness. Tests were not executed because some may use external services or perform submissions.
- `src/app/api/health/route.ts` returns `{ "status": "ok" }`. It is an application-response check, not a Supabase or email-delivery health check.
- `next.config.ts` configures CSP restrictions, frame denial, MIME sniffing protection, referrer policy, and private/no-store headers for admin/API paths. This is source configuration, not proof of live headers.
- `deploy.sh` describes an operator-triggered deployment: fast-forward pull from main, frozen-lockfile install, in-place build, systemd restart, and local health check. No GitHub workflow was identified in the initial file inventory; other CI or external automation remains unknown.
- `ops/Caddyfile.final-domain` records estateplanning.com.my proxying to loopback port 3002, a www redirect, and a separate Chillix application. The deployment walkthrough labels earlier chillix.win routing as historical. The README still contains older routing text, so production topology needs independent verification.
- `docs/digitalocean-sis-deployment-walkthrough.md` records a shared 1 GB Droplet, a past build-related availability incident, and example systemd memory limits. These are historical documentation, not current capacity measurements.
- `docs/admin-sessions.md` describes signed expiring sessions and default-on MFA, but also documents a UAT override. The current production MFA setting is unknown; no environment files were read.

## Risks and unknowns

- Production revision, active Caddy/systemd configuration, current capacity and co-hosted workloads have not been verified.
- Existing uptime monitoring, alert routing, backup schedules, tested recovery procedures, and external CI status remain unknown. A Droplet backup does not establish coverage of external Supabase data.
- Search Console/analytics setup and live email-delivery status are unverified.
- Building in the running checkout may alter build files used by the active process before a restart; the script's build-before-restart sequence should not be treated as proof of atomic deployment or rollback safety.
- No dependency vulnerability conclusions can be drawn from package versions alone. Existing audit files, if used later, require dates, tool versions and scope validation.
- Permission to inspect the source does not authorize reading secrets, customer submissions, running production-connected tests, or modifying the website.

## Deployment assessment

Use local execution for V1, as directed by the owner. Safe same-host deployment is not established. Historical resource pressure and shared workloads are reasons to defer it. Any future VPS deployment needs measured capacity and explicit isolation/resource budgets; no numeric budget is justified by current evidence. Prefer a dedicated agent environment with outbound-only access, its own identity/storage/configuration, and no website filesystem or database access.

## Smallest proposed V1

1. A manual Python CLI with typed configuration and result schemas; configurable site URL, allowed hosts/routes, timeouts, request/page/response-size limits, and an enabled/disabled switch.
2. Deterministic availability checks for a small approved set of public pages and the health endpoint, bounded retries, redirect/SSRF protection, and TLS verification/expiry checks.
3. Passive security hygiene checks of public response headers and HTTPS behavior. Keep repository dependency analysis separate and read-only; do not install or run website packages as part of initial evidence collection.
4. Save timestamped JSON and Markdown reports locally, including checks passed, failures, evidence, tool versions, severity, confidence, limitations and prioritized next steps. Redact sensitive values.
5. Fixture-based pytest checks for blocked redirects/private addresses, timeouts, partial results, false positives and untrusted content. Add a single LangGraph investigation workflow after deterministic collection works; preserve evidence references and provide no mutation tools.

Proposed dependencies: Pydantic, one HTTP client selected during implementation, pytest for development, and later LangGraph plus an approved model-provider client. Prefer standard-library TLS/storage facilities where sufficient. No dependencies have been installed. Implementation and dependency installation await plan approval; scheduling and notifications are deferred.

## Appendix review

The six-page PE6202 appendix supports application-enforced A/H+A/H decision rights, explicit trust boundaries, named control owners, auditable evidence, exception handling, retention decisions, tabletop tests and stop criteria. Its academic rubric and regulatory starting points do not establish product requirements, legal compliance, provider retention guarantees or permission for multi-agent architecture. Existing project constraints remain authoritative.
