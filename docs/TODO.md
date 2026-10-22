# Follow-up work

## Python module organization (completed 2026-10-22)

Completed after Telegram implementation and verification. The public `guardian`
command and saved report/database formats remain compatible. See
[the package map](CODE_STRUCTURE.md). Telegram and restructuring have separate
commits; the move introduces no policy changes.

- [x] Group deterministic audit/SEO/performance checks and shared network controls.
- [x] Group Google authorization and Search Console integrations.
- [x] Group report formatting and period-review reasoning/orchestration.
- [x] Group SQLite storage and scheduling interfaces.
- [x] Group repository proposals/approvals/publishing policy.
- [x] Keep Telegram under `guardian/telegram/`, including pairing.
- [x] Update imports and tests, preserve CLI entry points, run the full suite and
  document the resulting package map (260 passed, one platform-dependent skip).

Do not add a multi-agent framework or a broad abstraction layer just to rearrange files.

## Later activation

- Owner-approved weekly Monday 09:00 Malaysia digest and periodic collection.
- Dedicated VPS preparation/cutover with secrets, storage, lease and backup checks.
- Delivery-state reconciliation tooling for uncertain sends, before unattended use.
