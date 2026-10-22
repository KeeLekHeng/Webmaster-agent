# Proposal

## Why

Guardian already saves evidence-backed reports, but the owner has to inspect the
local terminal to see them. A private Telegram bot will deliver concise handoffs
with downloadable detail and let the owner retrieve status or the latest report.

## What Changes

- Add one verified private-chat destination, using a separate BotFather token.
- Deliver important availability/security changes and SEO/speed summaries with
  duplicate suppression, a concise caption and a downloadable redacted report.
- Support read-only `/status` and `/report` through an explicitly started outbound
  polling listener, runnable locally now and on an independent VPS later.
- Add manual preview/send and private-chat pairing commands; delivery defaults off.
- Record delivery results, partial/uncertain failures and consumed command updates
  locally so restarts do not silently repeat actions.
- Record the owner's future preference: weekly Monday 09:00 Asia/Kuala_Lumpur,
  retaining 14-day SEO comparison windows. No scheduled job is enabled in this change.

Owner choices confirmed on 2026-10-21: private chat; important changes plus SEO/speed;
manual delivery first; weekly Monday 09:00 later; concise summary plus downloadable
attachment; `/status` and `/report` included.

## Capabilities

### New Capabilities

- `telegram-owner-handoff`: verified private-recipient delivery, concise reports and
  attachments, durable deduplication and authenticated read-only command handling.

### Modified Capabilities

None. This is the first OpenSpec capability; existing operational behavior remains
documented in the repository until intentionally specified in later changes.

## Impact

New Telegram adapter, formatter, local notification state and CLI commands; minimal
optional integration at report handoff. Existing httpx, Pydantic and SQLite suffice.
No additional model call is needed to format a message. No public server, webhook,
production mounts or website database access. Bot credentials and chat ID are local
environment configuration. Existing audits/reviews still work when Telegram is off.

This proposal does not enable a schedule, run a persistent listener, send a live
report, deploy a VPS, create credentials or grant Telegram approval/merge powers.
