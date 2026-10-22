# Design

## Context

See proposal.md for owner choices. Guardian has saved audit/period-review artifacts,
deterministic handoff formatting, SQLite audit history and a persistent kill switch.
The current alert outbox is local-only; no Telegram code or listener exists.
Reports and bot credentials stay local. A dedicated VPS is deferred.

## Goals / Non-Goals

**Goals:** private-recipient enrollment, one bounded caption plus downloadable detail,
durable delivery/command tracking, and a manually started read-only listener that can
move to a VPS without website-side changes.

**Non-goals:** automatic scans from chat, a general Telegram chatbot, approval buttons,
production writes, public report hosting, new scheduled jobs or deployment.

## Decisions

### 1. Separate Telegram adapter and manual CLI

Use the existing httpx dependency against fixed allowlisted Bot API methods. Proposed
commands: `telegram-pair`, `telegram-send`, `telegram-listen` and `telegram-status`.
`telegram-send` accepts a saved run ID and supports a no-network preview. The token
and chat ID come from the existing local environment placeholders. Add no bot SDK or
LLM formatter. This avoids another dependency and prevents free-form tool execution.

Credentials appear in Telegram API URL paths by protocol; library HTTP debug logs
and tracing must be suppressed/redacted, and raw exceptions/URLs must never reach
CLI or persisted diagnostics. Use fixed HTTPS host, no environment proxies, no
redirects, method allowlists, response caps and short timeouts.

### 2. Pair a verified private owner

An explicit local pairing invocation calls `getMe`, generates a random challenge
valid for five minutes and asks the owner to send `/start <challenge>` privately.
Store only the challenge hash/expiry and a bot ID. A follow-up pairing check reads
bounded updates and accepts only a matching recent challenge from a non-bot sender
whose ID equals the private chat ID. Display that numeric ID for local owner
confirmation; enrollment binds bot ID, chat ID and sender ID. The owner puts the
confirmed ID in `GUARDIAN_TELEGRAM_CHAT_ID`. Delivery stays disabled until enabled.

Do not enroll the first random `/start`, use a public ID-discovery bot or show all
updates. A changed bot or chat invalidates the enrollment. Pairing must coordinate
with the same listener lease so two consumers cannot steal updates from each other.

### 3. Downloadable Markdown instead of a hosted link

Send a single `sendDocument` request containing a generated Markdown report and a
an HTML-formatted caption capped at 900 characters (below Telegram's documented 1,024
caption limit). The caption contains dates, available key deltas, up to three
prioritized actions and an uncertainty/coverage line. Truncation refers to the
attachment rather than dropping a limitation silently. The owner requested bold
headings on 2026-10-22: use Telegram HTML parse mode with fixed bold tags and escaped
dynamic text. Budget whole blocks so tags/entities/sentences are never sliced.

The attachment is regenerated from allowlisted structured Report fields, with
validated site/source URLs, evidence IDs, scanner observations, safe model notes and
explicit uncertainty. It is not an arbitrary existing file upload. Accept only
schema-valid saved live reports within the configured root, size-capped at 1 MiB;
reject symlink/path escapes. Generated attachment cap: 256 KiB. Known secret values,
credential patterns, raw errors and infrastructure paths must be removed or block
delivery. Audit and period-review formats have separate tested numeric projections.
Synthetic/replay inputs are not eligible for automatic notifications.

This offers phone-accessible detail without introducing a public site or sending
raw JSON/configuration. Regenerated detail can omit unsafe fields; state that in
the attachment. Label observations older than 48 hours as stale, not fresh checks.

### 4. Durable delivery state, separate from operational issue history

Use a dedicated configurable SQLite database under `data/telegram.sqlite3` for
enrollment, pending pairings, delivery receipts, command updates, offsets and a
listener lease. Avoid changing the audit database schema just for transport.
Persist bot/destination identity as fingerprints where plaintext IDs are not needed.

Delivery identity includes site, run/report type, destination and content identity;
automatic issue alerts additionally use stable issue identity and changed evidence
instead of timestamp-only hashes. Send only new/changed/resolved important HTTP,
TLS, security-header or health findings with medium/high severity; never infer an
outage from a collection exception alone. A future digest may include lower-severity
review items. Explicit manual sends are available independently of automatic alert
eligibility, but require enabled/verified delivery.

Record intent before sending, then Telegram message ID after confirmed success.
Use an explicit `uncertain` result if transport fails after possible acceptance;
do not assume exactly-once delivery or retry blindly. Confirmed 429 responses may
retry at most twice with a validated 1–30 second `retry_after`, checking the kill
switch at least every 250 ms. Other HTTP/API failures require manual retry unless
the adapter can prove nothing was sent. Do not inherit Claude's retry policy.

Each new authorized `/report` update is a distinct retrieval request, so deliberate
repeated retrieval works while reprocessing the same update does not. A crash after
recording command intent but before response completion is uncertain and is not
automatically replayed. Safe receipts contain IDs/hashes/outcome/times, no raw chat
text or tokens. Use no more than six owner command responses per minute; reject
excess work without an unbounded response queue.

### 5. Foreground outbound polling

`telegram-listen` uses `getUpdates` long polling with a short bounded timeout and
only ordinary message updates. Start without draining a large backlog: reject
commands more than five minutes old, ignore edited/forwarded messages and advance
offsets for ignored updates without saving their text. Check both enrolled private
chat ID and sender ID before interpreting any command. Only exact `/status` and
`/report`, optionally suffixed with this bot's username, are accepted. No arguments,
file paths, prompts or arbitrary chat instructions are executed.

`/status` reads known run timestamps and stale/unavailable state; `/report` loads the
latest eligible saved live audit/review for the configured site and sends the same
caption/document format. Neither command launches a scan or Claude call. Unknown
owner commands get fixed help; unauthorized chats get no response.

Acquire one per-bot lease before polling; renew it and persist offsets. If `getWebhookInfo`
shows a webhook, fail and explain locally; never delete webhook settings automatically.
On a VPS, move the same app/configuration/state and provision credentials separately;
stop the old listener before starting the new one. No inbound port or SSH connection
to the website is required. Availability follows the machine/process being online.

### 6. Manual rollout; scheduling remains a later activation

Keep `GUARDIAN_TELEGRAM_ENABLED=false`, existing scheduler disabled and no service
installation. Implement the manual path and optional enqueue hook; automatically
sending after every audit is not the default. Document the future weekly Monday
09:00 Asia/Kuala_Lumpur preference and 14-day SEO windows. Enabling a recurring
digest or urgent alert dispatch requires a later explicit owner action.

## Risks / Trade-offs

- Telegram sends are not end-to-end secret chats → send only minimized owner-approved
  report material, not credentials/customer records.
- Ambiguous network failure → durable uncertain state and manual reconciliation;
  exactly-once external delivery cannot be guaranteed.
- Polling shares one update stream → bot lease, persistent offsets and explicit
  webhook-conflict failure; use a dedicated Guardian bot.
- Local computer sleeps → no command response while offline; VPS can follow later.
- Malicious report/model/chat content → allowlisted projections, plain text, private
  command authentication and no model-to-tool execution path.
- Human review backlog is the scale bottleneck → concise top-three handoff plus
  detail; merge and production deployment remain human-only.

## Migration Plan

1. Implement and mock-test adapter, enrollment, formatter, delivery state and commands.
2. Owner creates a dedicated bot, saves its token locally and completes private pairing.
3. Preview a known live report locally. After owner configuration/enablement, send
   one manual summary/attachment and test both private commands.
4. Keep scheduling off; document results honestly. Live testing may remain pending
   until the owner supplies credentials and is available for pairing.
5. Roll back by disabling Telegram and stopping the listener. Preserve delivery
   state to avoid duplicate sends if re-enabled. Existing audits/reviews still work.
### Implementation clarification

Important-change integration is an explicit manual `telegram-send --important-only`
dispatcher over saved live audit history; no auto-enqueue hook is added to the audit
graph. This preserves default-off delivery and defers automatic dispatch to later
schedule activation. Existing history/outbox APIs remain unchanged.
