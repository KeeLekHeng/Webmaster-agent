# Telegram presentation redesign — Astra recommendation

Design review requested by the owner on 2026-10-22. Astra inspected the current
formatter, status command, schemas and project constraints. This is a presentation
proposal. The safe bold Telegram caption/status, human dates, whole-block budgeting
and prose-first Markdown attachment were applied after owner approval on 2026-10-22.
The accompanying HTML file remains a static visual
prototype using existing saved observations, not a fresh audit.

## Telegram summary

Lead with the scope and reporting window, then the useful takeaway, two primary
metrics and distinct review tasks. Use whitespace and whole sentences. Put the more
ambiguous CTR/average-position changes and their explanations in the attachment.
Do not truncate a sentence or force three actions when fewer are justified.

Example from the saved 14-day review:

```text
Website Guardian · Search review
estateplanning.com.my

3–16 Oct 2026
Compared with 19 Sep–2 Oct

More search visibility, with 8 clicks recorded.
Clicks: 3 → 8
Impressions: 18 → 103

What to review
• Homepage: inspect the queries behind its 5 clicks.
• Trust planning: inspect queries behind 25 impressions and no clicks.
• About us: review query intent before changing copy; 14 impressions is a small sample.

The sample is small. These figures do not establish why performance changed.

Saved 20 Oct 2026 · 2:55 pm MYT
Read-only. Open the attachment for explanations and evidence.
```

The example omits a stale banner because it represents the layout, not a current
freshness assessment. The real formatter must calculate freshness at send time.
Reserve space for stale/partial/analysis-unavailable warnings and a footer within
the existing 900-character caption limit. Remove lower-priority complete blocks if
needed; never slice the completed caption midway through an action.

## Status

```text
Website Guardian
estateplanning.com.my

Latest saved search review
20 Oct 2026 · 2:55 pm MYT

Collection: complete
Analysis: complete

/report opens the saved report.
This command does not run a new check.
```

Put a stale warning immediately beneath the timestamp when applicable. Say
“Analysis unavailable; measured results are still available” when that is true.
Do not equate a completed search review with healthy uptime/security. Do not claim
scheduling is enabled or disabled unless the command can actually establish it.

## Downloaded report

Astra recommends a self-contained HTML report for readable typography and spacing,
with Markdown retained as an alternative export. Telegram clients vary in how they
open HTML; test on the owner's device before making HTML the default. No public
hosting, extra dependency, scripts, remote assets or model call is necessary.

1. Search review header, separate reporting dates and saved timestamp, scope and warnings.
2. What changed: short measured takeaway, four metric cards and careful interpretation.
3. Review cards: observation, advisory interpretation, next step, confidence and evidence.
4. Coverage/uncertainty, including unavailable data and the next measurement checkpoint.
5. Evidence appendix: labeled facts, source, timestamps, references and tool provenance;
   no raw JSON blocks before the human explanation.

The static HTML prototype prioritizes this visual hierarchy. A production export
must retain the full approved evidence projection, matching model explanations and
uncertainties rather than treating the shortened prototype as the complete report.

## Preserved behavior

- Safe Telegram HTML bold headings, escaped dynamic text and one document per send.
- Existing pairing, private-destination checks and durable receipt/deduplication logic.
- Validated public source URLs, secret rejection and safe output size limits.
- Escaped dynamic HTML text and restrictive content policy; no executable content.
- Reporting-window dates remain Google's Pacific dates; saved timestamps display MYT.
- Existing findings, severity, confidence and measurements remain unchanged.
- The design phase performed no live send. After approval, one updated saved report
  was successfully sent to the paired owner; no new scan or website change was made.

## Suggested implementation order

Update caption/status/date helpers and whole-block budgeting first. Then generate
the prose-first Markdown report. Add the optional HTML renderer and validate the
phone attachment experience before changing the default attachment format.
