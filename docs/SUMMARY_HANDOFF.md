# Local summary and human handoff

Implemented on 2026-10-19 as the `summarize_handoff` node between `policy_filter`
and `save_report`. It formats existing findings deterministically; no additional
LLM call, service, dependency or messaging integration is required.

Each workflow run prints the handoff, saves `summary.md`, includes its text in
`report.json`, and links to it from `report.md`. It groups findings sharing the
same title, severity and recommended next step, counts distinct evidence source
URLs, and preserves all original findings/evidence in the full reports. Severity
is never increased; grouped confidence uses the lowest original confidence.

The handoff includes observation time, replay warning where applicable, collection
and reasoning status, HTTP outcomes, available TLS validity information, severity,
affected URL count, impact, human next step and abbreviated evidence references.
Known HSTS observations receive a short explanation; other findings retain their
scanner recommendation with a cautious generic impact statement. It does not copy
model-generated explanations or invent new scanner findings. Human-readable data
fields are escaped and terminal control characters removed.

At most five issue groups are displayed, ordered by scanner severity. Additional
issues are counted and linked through the full report. Blocked/unavailable checks,
partial collection, missing evidence and collection-budget limits are called out.
Detailed limitations remain in the linked full report. This is a handoff for human
review, not authorization to modify production.

Validation: 55 tests passed, including nine focused summary cases and updated
graph integration assertions. These cover duplicate findings, unique URL counting,
partial/empty scans, missing references, severity preservation, omitted issue counts,
excluding model prose, replay/reasoning failure, retry outcomes and escaping.

Offline end-to-end validation replayed the saved Milestone 1 report using
`--llm none`. All seven graph nodes completed, producing one low-severity HSTS
issue affecting nine checked URLs. No new website or Claude requests were made.
Example output: `reports/00ba237ae9df4d028d94b75e638f292d/summary.md`.

Telegram delivery is still a deferred roadmap item. No bot credentials,
notifications, approval actions or scheduled jobs were configured.
