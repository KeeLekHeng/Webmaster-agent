# Milestone 2 outcome

Implemented on 2026-10-19: one local LangGraph workflow with typed state,
deterministic evidence collection, bounded evidence projection, optional Claude
structured reasoning, independent output policy and local JSON/Markdown reports.

## What changed

- The CLI now runs the actual LangGraph StateGraph through the six nodes described
  in the implementation plan. Progress displays completed node names.
- `--llm none` remains the default. `--llm demo` uses fake reasoning clearly marked
  as a demonstration. `--llm claude` requires an explicitly selected model and an
  Anthropic API key supplied through the process environment.
- `--input-report` replays saved evidence without new site requests, preserving
  original observation timestamps and identifying the source run.
- Claude receives no tools and only a bounded projection of scanner evidence.
  No raw pages, response header strings, URLs, repository text, credentials or
  exception messages are included in the model prompt. Authentication uses the
  API key separately. External LangSmith tracing is explicitly disabled.
- Model schema and citation checks reject invented IDs, unrelated evidence,
  duplicate entries, confirmation from unavailable evidence, unexpected fields
  and obvious command/URL patterns. Rejected raw output is not persisted.
- Reports retain deterministic findings regardless of model failure/rejection.
  Model prose is labelled advisory; citation validation cannot establish semantic
  correctness. This is an honest remaining limitation, not a complete injection
  or hallucination guarantee.
- Reports include mode, selected model, input hash, accepted notes, analysis status,
  token usage when available and a timestamped workflow log.
- `guardian explain` prints a beginner walkthrough without network access.

## Verification

45 pytest cases passed, including the previous 25 scanner cases and 20 workflow
cases. New coverage exercises the real compiled graph, offline replay, explicit
demo/none behavior, injected investigator output, API failure, malformed output,
policy rejection, prompt-injection/secret exclusion from projected input, invented
and cross-finding citations, unavailable evidence, kill switch during a run,
empty findings and disabled external tracing.

The real Anthropic SDK structured parse path was tested with an HTTP mock
transport: the request has no tools, uses the fixed Anthropic host, supplies the
output schema and token cap, parses a typed response and records token usage.
This uses a synthetic key and makes no external API request. `pip check` passed.

A real graph demonstration replayed Milestone 1's 28 evidence records and one
grouped finding. Its output is in
`reports/2f82c4c744234213a3cd2ddcd673a71f/`. The original report remains unchanged.
`guardian explain` was also executed in the terminal.

Verified local library versions: LangGraph 1.2.16, Anthropic SDK 0.125.0.
The refreshed `requirements-dev.lock` records all installed dependency versions.

## Live provider validation

After the owner supplied the key and authorized a test, a real Claude request
using `claude-haiku-5-5` successfully replayed the saved Milestone 1 audit.
All six graph nodes completed. Structured output parsed successfully and the
policy accepted one explanation citing the nine existing header observations.
The report preserved the original evidence and low scanner severity. API usage
reported 2,593 input tokens and 521 output tokens. No monetary cost was calculated.

The result is saved in `reports/2e0eeec5dbce4db3a368af13adaf6014/`.
No new website requests were made for this test. The key was not printed or saved
in reports. This validates live authentication and structured-output compatibility
for the configured model; repeatability, broader reasoning quality and cost trends
need further observations.

No production changes, new live scans, form submissions, scheduled jobs, external
notifications or repository writes were performed for this milestone. New
dependencies were installed only in the local project virtual environment.
No approval executor, production action tool, LangGraph cloud deployment or
resumable checkpoint store is present. Production deployment remains human-only;
human review of model explanations remains the likely scaling bottleneck.
