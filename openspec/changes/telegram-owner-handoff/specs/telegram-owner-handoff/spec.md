# Telegram Owner Handoff

## Purpose

Give the verified website owner a private Telegram interface for maintenance
handoffs and retrieval of saved status/reports, without production action rights.

## ADDED Requirements

### Requirement: Delivery is opt in
The system SHALL block Telegram sends and command handling unless Telegram is enabled, the bot token and verified private destination are configured, and the Guardian kill switch permits operation. Explicit local pairing SHALL be allowed while delivery remains disabled.

#### Scenario: Default disabled state
- **WHEN** Telegram delivery has not been enabled
- **THEN** audits and reviews SHALL save locally without sending Telegram messages or starting a listener

#### Scenario: Stop during delivery
- **WHEN** the kill switch is set before a Telegram operation
- **THEN** no new Telegram request SHALL begin and pending work SHALL remain unsent

### Requirement: Private owner pairing
The system SHALL verify one private chat using an owner-initiated, expiring, single-use challenge. It SHALL require the sender ID to match the private chat ID, reject bot senders, and bind the enrollment to the bot identity. It SHALL not infer ownership from an arbitrary first message, display unrelated conversations or enroll a group.

#### Scenario: Successful pairing
- **WHEN** the owner sends the current challenge to the bot in a private conversation within five minutes
- **THEN** local pairing SHALL identify that chat for owner confirmation and keep live delivery disabled

#### Scenario: Unrelated or expired message
- **WHEN** an update has no matching challenge, is expired, comes from a group or is sent by a bot
- **THEN** the destination SHALL not be enrolled and that message's contents SHALL not be logged or answered

### Requirement: Concise handoff with downloadable detail
The system SHALL deliver each report as a concise summary with a downloadable redacted Markdown attachment, including observation dates, available key metrics, up to three action items and uncertainty. It SHALL identify unavailable data and advisory model content. It SHALL not publish local file paths as phone-accessible links or create public report hosting.

#### Scenario: Period review delivery
- **WHEN** an authorized saved period review is selected
- **THEN** the owner SHALL receive its comparison dates, metric changes and top actions with detailed evidence in the attachment

#### Scenario: Categorized owner template
- **WHEN** a period review is delivered
- **THEN** it SHALL use bold Website statistics and SEO improvements to review headings, numbered actions and saved confidence levels
- **AND** statistics SHALL explicitly identify Google Search scope rather than imply total website visits

#### Scenario: Unavailable or stale observations
- **WHEN** the selected report is partial, stale or lacks a comparable performance baseline
- **THEN** the message SHALL state the limitation instead of implying a fresh passing check or invented speed trend

### Requirement: Report disclosure boundaries
The system SHALL construct outgoing reports from validated allowlisted fields for the configured website. It SHALL exclude credentials, raw customer data, raw tool errors, configuration files, arbitrary filesystem attachments and private infrastructure paths. External content SHALL remain inert text. Unsafe or oversized report input SHALL be blocked before sending.

#### Scenario: Secret or path in an input report
- **WHEN** a report contains a known credential, disallowed source URL or unsafe file reference
- **THEN** delivery SHALL block or redact that content and SHALL record only a safe reason

#### Scenario: Report path escape
- **WHEN** an input or symlink resolves outside the configured report root
- **THEN** the file SHALL not be read or uploaded

### Requirement: Read-only private commands
The system SHALL accept only `/status` and `/report` from the enrolled private chat and matching owner sender. Commands SHALL return existing local observations only. They SHALL not initiate a scan, model call, shell command, approval, PR, merge, deployment or credential change. Unauthorized messages SHALL receive no response.

#### Scenario: Owner requests status
- **WHEN** the enrolled owner sends `/status`
- **THEN** the bot SHALL return the latest known run/observation times and whether local data is unavailable or stale

#### Scenario: Owner requests report
- **WHEN** the enrolled owner sends `/report`
- **THEN** the bot SHALL send the latest eligible saved report with its concise summary and attachment, or a fixed no-report message

#### Scenario: Unknown or unauthorized command
- **WHEN** another chat sends a command or the owner sends an unrecognized instruction
- **THEN** the system SHALL execute no action; only an authorized owner SHALL be eligible for a fixed supported-command help response

### Requirement: Portable outbound listener
The system SHALL provide an explicitly started polling listener usable on a local computer or dedicated VPS, with no inbound public port. It SHALL enforce one active listener per bot/state store, preserve processed update positions across restarts, and stop on the kill switch. An existing webhook SHALL cause a safe failure rather than automatic deletion.

#### Scenario: Polling after restart
- **WHEN** a listener restarts against the same durable state
- **THEN** completed commands SHALL not be processed again

#### Scenario: Concurrent listener
- **WHEN** a second listener attempts to use the same bot/state store
- **THEN** it SHALL fail without consuming updates or sending replies

### Requirement: Delivery deduplication and audit history
The system SHALL persist delivery intent, destination fingerprint, report/content identity, timestamps and sanitized outcomes. It SHALL suppress repeated automatic delivery of unchanged important issues or the same digest. A distinct owner `/report` request SHALL permit retrieval of the same report. Uncertain sends SHALL not be retried automatically as though definitely unsent.

#### Scenario: Repeated unchanged finding
- **WHEN** a later audit contains the same important issue without material change
- **THEN** no duplicate automatic Telegram alert SHALL be sent

#### Scenario: Response lost after send
- **WHEN** a send times out after Telegram might have accepted it
- **THEN** its outcome SHALL be recorded as uncertain and require explicit reconciliation rather than blind resending

### Requirement: Bounded Telegram communication
The system SHALL use only the official Telegram Bot API over HTTPS, with bounded time/response/file sizes, no redirects and no arbitrary API-method selection from messages or report content. It SHALL redact bot tokens and incoming/outgoing private text from diagnostic logs. Provider rate limits SHALL produce bounded backoff, while authorization failures SHALL fail closed.

#### Scenario: Redirect or raw provider error
- **WHEN** Telegram returns a redirect or error containing a token or private message
- **THEN** credentials SHALL not be forwarded and raw error bodies SHALL not be persisted

#### Scenario: Telegram rate limit
- **WHEN** Telegram rejects a request with a valid bounded retry delay
- **THEN** the system SHALL respect its retry policy while checking the kill switch and preserving delivery state

### Requirement: Manual rollout and future digest preference
The system SHALL begin with manual delivery and an explicitly launched listener. It SHALL document the owner's future weekly Monday 09:00 Asia/Kuala_Lumpur digest preference with 14-day SEO comparisons, but SHALL not install or enable a scheduled job as part of this change.

#### Scenario: Installation completed
- **WHEN** Telegram functionality is installed and configured
- **THEN** no job, service, timer or unattended listener SHALL start without a separate owner action

#### Scenario: Computer unavailable
- **WHEN** the local Guardian listener is not running
- **THEN** no immediate command-response or report-delivery guarantee SHALL be made
