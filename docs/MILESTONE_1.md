# Milestone 1 outcome

Completed on 2026-10-19: local manual read-only audit CLI, configurable approved
targets, typed Pydantic results, bounded sequential GET collection, validated
redirects, public-IP-only pinned connections, TLS verification/expiry checks,
selected security headers, basic metadata presence and scoped internal links.
Reports preserve evidence, timestamps, failures, tool versions and recommendations.
No LLM is used and no Claude key is needed.

## Validation

` .venv/Scripts/python -m pytest -q `: 25 tests passed. Cases include route
allowlists, private/metadata IPs and IPv6, validated IP pinning, safe and blocked
redirects, timeout retry/error redaction, HTTP recovery, broken internal links,
duplicate links/findings, inert embedded instructions/forms, truncated responses,
health payload errors, request budgets, report persistence and kill switch.
`git diff --check` passed. Dependencies were installed only in this project's
local `.venv`; `requirements-dev.lock` records the verified environment.

## First live audit

Run ID: `32c1bc5cb90a4ea49317db45712d9410`.
Observation: 2026-10-19 10:15:43–10:15:50 UTC (18:15 Malaysia time).
Source: https://estateplanning.com.my/ and configured public routes.

- Nine HTTP GET requests, all HTTP 200: homepage, health endpoint, about,
  services, will writing, trust planning, blogs, careers and contact page.
- Health payload reported `status: ok`; this does not verify backend dependencies.
- TLS chain/hostname verification passed. Certificate expires
  2026-12-30 11:31:25 UTC, approximately 72.1 days after observation.
- Eight HTML pages contained titles, descriptions and canonical metadata.
- No broken links were observed among the approved routes checked. Other paths,
  external links, page assets and JavaScript behavior were outside scope.
- One grouped low-severity hardening finding: Strict-Transport-Security was absent
  from all nine sampled responses. Framing restrictions and nosniff were present.
  Review HSTS suitability at the HTTPS edge before any separately approved change;
  do not infer an exploitable vulnerability from header absence alone.

Evidence-backed Markdown and JSON reports are stored locally under
`reports/reviewed/32c1bc5cb90a4ea49317db45712d9410/`. The initial ungrouped report
is retained under `reports/32c1bc5cb90a4ea49317db45712d9410/`. The reviewed copy
groups the same nine header observations without making additional requests.

## Boundaries and next milestone

No production files, repositories, server settings or customer data were changed
or accessed. No forms were submitted. No scheduler or notification service was
enabled. The read-only HTTP requests may appear in normal website access logs.

The check is one local-network sample, not proof of continuous uptime or complete
security. DNS uses OS resolver timeouts. Metadata checks establish presence only.
Optional dependency/security report ingestion is deferred; no scanner report was
needed for this milestone. Cross-run comparison, durable scheduling and alerts
belong to Milestone 3. Local report files currently have no automatic retention
policy; the operator controls their storage and removal.

Milestone 2 adds a single LangGraph investigation workflow, with an external Claude
API selected by configuration, to explain and prioritize bounded evidence. The
deterministic audit remains usable without an LLM.
