# Follow-up work

## Python module organization (owner requested 2026-10-21)

After Telegram implementation and verification, propose a small behavior-preserving
reorganization. Keep the public `guardian` command and saved report/database formats
compatible. Do not mix the move into feature debugging or silently change policy.

- Group deterministic audit/network/SEO/performance checks.
- Group Google authorization and Search Console integrations.
- Group report formatting and period-review reasoning/orchestration.
- Group SQLite storage and scheduling interfaces.
- Group repository proposals/approvals/publishing policy.
- Keep Telegram's new code under its existing `guardian/telegram/` package.
- Move incrementally, update imports and tests, retain compatibility wrappers where
  needed, run the full suite, and document the resulting package map.

Do not add a multi-agent framework or a broad abstraction layer just to rearrange files.

## Later activation

- Owner-approved weekly Monday 09:00 Malaysia digest and periodic collection.
- Dedicated VPS preparation/cutover with secrets, storage, lease and backup checks.
- Delivery-state reconciliation tooling for uncertain sends, before unattended use.
