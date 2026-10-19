# Period reviews: what changed and what should the owner do?

Added 2026-10-19 to extend Milestone 5 beyond static technical checks.

## Owner outcome

`guardian review` compares adjacent equal 7- or 28-day windows and saves:

- Property clicks, impressions, CTR and average position, with absolute changes.
- Comparable page-level changes, supporting evidence and prioritized next actions.
- Optional Claude interpretation with explicit uncertainty and validated references.
- Comparable Lighthouse lab sample counts/medians, kept separate from visitor data.
- Missing coverage and next data needed, rather than invented figures.

Owner-selected default is 7 days versus the previous 7 days; 28 days is optional.
Dates use Google's Pacific calendar; end defaults to three days
before today there. On Windows without timezone data, UTC minus four days gives a
conservative cutoff without installing packages. `--end-date YYYY-MM-DD` overrides
the cutoff. Only finalized API data is requested; this does not guarantee the latest
requested date has data. Equal windows help weekday comparison, not seasonality.

## Search Console access (still needed for the real site)

The owner confirmed on 2026-10-19 that they can open the verified property and its
Performance report. Guardian still needs separate read-only API authorization.
The owner can access the property in the Performance
report in [Google Search Console](https://search.google.com/search-console).
An Anthropic key, GitHub token or Google API key does not grant Search Console access.
Use an existing Google OAuth access token authorized with
`https://www.googleapis.com/auth/webmasters.readonly` for an account with property
access. This implementation does not create OAuth clients, consent grants,
credentials or Google account permissions. Never send tokens in chat.

Set the following locally in the ignored `.env`:

```dotenv
GUARDIAN_GSC_PROPERTY=sc-domain:estateplanning.com.my
GUARDIAN_GSC_ACCESS_TOKEN=
```

Use the exact verified property: the domain example above, or the configured base
URL-prefix `https://estateplanning.com.my/`. The authenticated API determines whether
the account has access; Guardian checks the property against its site configuration
first. Tokens are short-lived; automatic OAuth refresh is not implemented. Do not
enable unattended operation until token lifecycle is implemented and authorized.

```powershell
.venv\Scripts\guardian.exe review --site estateplanning --days 28 --llm claude
# Or use an explicit final reporting date:
.venv\Scripts\guardian.exe review --site estateplanning --days 7 --end-date 2026-10-15 --llm none
```

The connector makes four bounded read queries: property totals and top 1,000 page
rows for each period. Search Analytics uses HTTP POST to query data; it does not
modify the property. No search-query strings, customer data or analytics events are
requested. Page URLs outside Guardian's existing public route allowlist are dropped,
with an omitted count. Property totals can therefore cover more pages than detailed
actions. Totals are not reconstructed by summing page rows. Missing page rows are
unknown, not zero. Country/device/query breakdowns are suggested human follow-ups,
not evidence already collected by this increment.

Average position is not a fixed keyword ranking. This version does not track named
keyword SERPs, competitor rankings, conversions or revenue. Those need separately
scoped data sources. Query-level inspection is currently a human action in GSC.

## Reasoning and action selection

One six-node LangGraph path: validate_period → collect_period → compare_period →
investigate_period → policy_filter → save_period. It shares the existing bounded
Claude adapter and reference validation. It is a separate manual report mode of the
same application, with no multi-agent system or autonomous changes.

Python calculates all deltas and selects candidates; Claude receives numeric
comparisons and IDs, not page URLs, raw exports or query text. It explains likely
relationships and investigation steps within the evidence. Prose is advisory and
can be wrong; valid IDs do not prove semantic correctness or causation. There is no
model call when no action candidates exist. Deterministic actions survive model
failure. This is not an open-ended competitor/content research agent.

Transparent triage defaults (not statistical significance):

- Click loss: previous clicks at least 20, loss at least 10 and at least 20%.
- Otherwise, weaker position by at least 2, with at least 100 impressions per window.
- Otherwise, CTR drop at least 1 percentage point, with 100 impressions per window.
- Otherwise, page visibility opportunity: 100 current impressions, position 5–20
  and CTR at most 2%. Query mix must be reviewed before assuming an opportunity.
- Lab-score action: same URL/device/version-major/profile, at least three distinct
  measurement timestamps per window, median performance-score decline of at least 10.

Candidates are bounded, ranked primarily by absolute click loss, and retain exact
evidence. Each action includes owner investigation/experiment and what to recheck.
Legal/estate-planning content stays human-reviewed. No automated change is enabled.

## Start speed history

```powershell
.venv\Scripts\guardian.exe performance-sample --site estateplanning --url https://estateplanning.com.my/ --strategy mobile
```

Runs one explicit public PageSpeed lab measurement using a fixed Google endpoint.
No local browser installation. Requests have a 60-second wall budget, a 10 MiB
response cap, no redirects or automatic retries; kill switch checks continue while
reading. Optional `GUARDIAN_PAGESPEED_API_KEY` is separate from Search Console OAuth.
Provider quotas/authentication can prevent a run. No score is saved on failure.
Only numeric results, URL, measurement timestamp, version and a profile fingerprint
are retained, not screenshots, HTML or diagnostic prose. Keep
`data/performance/estateplanning`; reviews automatically read that site's saved
samples (maximum 200). No current speed history exists yet.

Override automatic sample loading with explicit paths if needed (repeat the flag):

```powershell
.venv\Scripts\guardian.exe review --site estateplanning --performance-sample data/performance/estateplanning/one.json --performance-sample data/performance/estateplanning/two.json --llm claude
```

Comparison uses supplied in-period samples only. Exact duplicate timestamps/profile
are deduplicated; changed profiles or major Lighthouse versions are separated.
Boundary calendar days are conservatively excluded to avoid mixing UTC and Pacific
dates without installing timezone data. Three samples do not prove statistical
significance. Import authenticity/run independence is unverified. Lighthouse is lab
data, not historical real-user speed; the past cannot be reconstructed without
existing measurements. Scheduler and external notifications remain disabled.

## Offline demonstration and imports

```powershell
.venv\Scripts\guardian.exe review --site demo --config examples/sites.demo.json --input-search examples/search-periods.demo.json --llm demo
```

The demo is visibly synthetic, uses fictional example.com data, calls neither Google
nor Claude and makes no site claims. For a real offline import use the same normalized
schema with `source: owner-import`. A raw GSC CSV is not accepted directly because
periods, filters and aggregation must be explicit. Imported `google-api` provenance
is downgraded; authenticity cannot be verified from a file.

Reports save under an independent UUID directory with `summary.md`, `report.md`,
`report.json` and normalized `search-periods.json`. They never update the operational
audit SQLite baseline or send alerts. Missing access/API errors/empty periods produce
a partial report, not zero traffic or an invented decline. Raw errors and tokens are
omitted. Stopping Guardian blocks collection and save operations.

## Validation and present limitations

Current-site connection test found no configured Search Console access token; real
rankings/search metrics remain unavailable. One explicit mobile PageSpeed attempt
returned unavailable; no performance score or sample was fabricated or saved.
The offline demo and mocked Google/Claude tests validate behavior, not current-site
search performance. Owner confirmed Search Console availability and selected
seven-day comparisons; API authorization remains pending.

References: [Search Analytics API, dates/aggregation/limits](https://developers.google.com/webmaster-tools/v1/searchanalytics/query),
[Google authorization](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing),
[PageSpeed and Lighthouse](https://developers.google.com/speed/docs/insights/v5/get-started).
