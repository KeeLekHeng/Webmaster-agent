# Milestone 5: SEO and performance insights

Implemented locally on 2026-10-19. No dependencies installed, scheduled jobs,
production changes, deployments or external notifications.

```powershell
.venv\Scripts\guardian.exe audit --site estateplanning --seo --llm none
.venv\Scripts\guardian.exe audit --site estateplanning --seo --lighthouse-report path\to\lighthouse.json --llm none
```

The existing eight-node LangGraph workflow remains. Collection now optionally
checks noindex directives, canonical scope/duplicate declarations, missing H1s,
duplicate sampled titles (hashes only), robots.txt and sitemap.xml. Additional
GETs share existing transport budgets, redirect and DNS controls. Sitemap URLs
are counted, never followed. XML entity declarations and incomplete/invalid
resources produce unavailable evidence. The basic Python robots parser is only
a review aid. Optional Claude receives safe SEO booleans/counts, never raw content.

## Performance input and limits

Imports standard Lighthouse JSON or PageSpeed's `lighthouseResult` offline.
It never executes artifact code or a browser. Requested/final URLs must match
approved public HTTPS routes. Localhost fixture artifacts are rejected.
The 10 MiB input cap, schema/range checks, failure detection and original timestamp
preservation prevent misleading successful imports. Future timestamps are rejected.
Artifact authenticity is not independently verified.

Saved lab evidence contains version/device, artifact/profile hashes, category
scores (0–100), LCP/FCP/TBT/speed index in milliseconds and unitless CLS when
present. These are observations, not automatically assigned severity findings.
Mixed imported reports disable live SQLite history/alerts to protect baselines.

Extended with manual `performance-sample` (one PageSpeed API lab run) and `review`
(equal-period Search Console and comparable lab samples). Default reporting is
seven days versus the previous seven days. See [period review details](PERIOD_REVIEWS.md)
for Google access, action rules, optional Claude reasoning and offline demo.
The owner confirmed browser Search Console access; Guardian OAuth is not configured.
The first PageSpeed API attempt was unavailable; no score was saved. Analytics and
scheduled collection remain disabled. Real period outcomes are pending data access.

References: [PageSpeed and Lighthouse results](https://developers.google.com/speed/docs/insights/v5/get-started),
[robots.txt limitations](https://developers.google.com/search/docs/crawling-indexing/robots/intro),
[canonical guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls).

## Live validation

Run `reports/bff50c249e424c34bbe1dc692da84923`, observed 2026-10-19 15:08 UTC:
nine public routes returned 200, including eight HTML pages. No new SEO review
findings. robots.txt returned 200 and allowed the homepage under the basic parser.
sitemap.xml returned 200 with 17 approved-host HTTPS locations; none were fetched.
Existing missing-HSTS finding remained on nine routes at that scan time.
No indexing, rankings, traffic or visitor-performance conclusion is implied.

Tests cover scope/injection boundaries, malformed/entity XML, failed Lighthouse
runs, invalid timestamps/scores/URLs, safe projections, graph persistence and
exclusion from live history. No website application scripts or form tests ran.

Rollback: omit the two optional flags. No production rollback is needed.
