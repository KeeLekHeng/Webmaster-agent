# Tasks

## 1. Configuration and bounded transport

- [x] 1.1 Add typed Telegram configuration, fixed method/host allowlists and default-off policy; verify missing/disabled settings and kill-switch tests pass.
- [x] 1.2 Implement bounded Bot API calls with redacted diagnostics, no redirects/proxies and bounded 429 handling; verify transport mocks cover success, rate limit, timeout, authorization failure and token-safe debug logging.
- [x] 1.3 Document bot creation, environment settings and private delivery boundaries; verify the guide matches CLI help and leaves scheduling disabled.

## 2. Private owner enrollment

- [x] 2.1 Implement five-minute single-use pairing challenges and bot-bound enrollment; verify private-owner success, expiry, replay, group/bot rejection and unrelated-update nondisclosure tests.
- [x] 2.2 Implement local pairing/confirmation CLI and destination checks; verify changing bot/chat invalidates enrollment and cannot silently overwrite an existing destination.
- [x] 2.3 Document chat ID discovery and confirmation; verify no external ID-discovery service or public token-bearing URL is required.

## 3. Report formatting and delivery state

- [x] 3.1 Implement site-scoped safe report loading and redacted attachment projection; verify path/symlink escapes, invalid URLs, secrets, synthetic/replay inputs and oversized artifacts are rejected or safely handled.
- [x] 3.2 Format a bounded caption with up to three actions and a downloadable Markdown attachment; verify audit/review metrics, dates, stale/partial data, uncertainty and truncation remain accurate.
- [x] 3.3 Implement durable delivery intent/results and stable important-change deduplication; verify repeated runs, changed evidence, manual retrieval, restart and uncertain-send behavior in SQLite tests.
- [x] 3.4 Add manual preview/send/status commands and opt-in important-change dispatch; verify default audits/reviews still make no Telegram requests.
- [x] 3.5 Document delivery receipts, retry/reconciliation behavior and future Monday 09:00 Malaysia digest preference; verify no timer/service is enabled by the commands.

## 4. Read-only listener

- [x] 4.1 Implement leased foreground polling, webhook-conflict checks and durable update offsets; verify concurrent listeners, restarts, stale updates and kill-switch interruption tests.
- [x] 4.2 Authenticate private chat and sender before handling exact `/status` and `/report`; verify unauthorized/forwarded/edited messages and unsupported actions cause no privileged operation or external reply to strangers.
- [x] 4.3 Implement bounded owner command responses with safe latest-report selection; verify no-report/stale-report paths, rate limiting and that commands never start audits, Claude requests, PRs or shell execution.
- [x] 4.4 Document local startup/shutdown and future VPS cutover; verify instructions require stopping the old listener and preserve state without production mounts or public ports.

## 5. Integration and owner handoff

- [x] 5.1 Run full pytest and strict OpenSpec validation; record actual results and unresolved limitations without fabricated live sends.
- [ ] 5.2 After owner pairing and enablement, send one approved live summary/attachment and exercise `/status` and `/report`; verify the correct private destination and persist redacted receipts, or explicitly record the owner-dependent live-test blocker.
- [x] 5.3 Demonstrate duplicate suppression and listener shutdown in integration checks; confirm no scheduled job, merge/deployment route or public endpoint was enabled.

## Workflow follow-up

- Keep the proposal active until implementation and validation are complete; archive only after verifying the finished capability.
- Schedule activation and dedicated VPS deployment are separate later work, not unchecked implementation tasks hidden in this proposal.

## Validation notes (2026-10-21)

- Full suite: 255 passed, 1 skipped before two additional focused tests; final counts are recorded at handoff.
- Strict OpenSpec validation passed.
- Actual saved review summary/document delivered once to the enrolled private owner; repeated manual send was suppressed.
- Owner-generated live /status and /report checks remain pending. Mocked command, authorization, rate-limit, offset/restart and stop-during-poll checks pass.
- The real-symlink test is skipped on this Windows session because link creation requires extra privileges.
- New code is grouped in guardian/telegram; broader Python organization is tracked in docs/TODO.md.
