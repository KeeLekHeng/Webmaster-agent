# Telegram setup: private pairing

Implemented: private pairing, concise summaries with downloadable redacted Markdown,
manual delivery, durable duplicate suppression and a read-only polling listener.
No service or schedule is installed. New Telegram code is grouped under
`src/guardian/telegram/`; existing pairing entry points remain compatible.

Live validation on 2026-10-21: private enrollment was verified, one real saved
period-review summary/attachment was delivered, and an identical manual send was
suppressed. Owner-triggered live command validation is tracked in the active
OpenSpec tasks; mocked command/authentication/restart/stop tests are passing.

1. In Telegram, create a dedicated Guardian bot through BotFather with `/newbot`.
2. Put its token in the ignored local `.env` as `GUARDIAN_TELEGRAM_BOT_TOKEN`.
   Keep `GUARDIAN_TELEGRAM_ENABLED=false`; leave chat ID blank until verified.
3. Open that bot's private chat. A plain `/start` opens the conversation but does
   not prove to Guardian which private chat belongs to the local owner.
4. Run from the Guardian project directory:

   ```powershell
   .venv\Scripts\guardian.exe telegram-pair
   ```

5. Send the exact `/start <challenge>` printed by that command to your bot within
   five minutes. The challenge is single-use; the database stores only its hash.
6. Run:

   ```powershell
   .venv\Scripts\guardian.exe telegram-pair --check
   ```

   Only the matching private message is accepted. Its sender must match the private
   chat ID and must not be a bot. Unrelated messages are not displayed or saved.
7. Confirm the numeric candidate locally using the command printed by the check:

   ```powershell
   .venv\Scripts\guardian.exe telegram-pair --confirm YOUR_NUMERIC_CHAT_ID
   ```

8. Save that number as `GUARDIAN_TELEGRAM_CHAT_ID` in `.env`. Keep delivery disabled
   until you are ready for an explicit manual send/listener run.

Bot identity and owner enrollment are stored in `data/telegram.sqlite3` (ignored
by Git). A different bot cannot reuse the pairing. Existing enrollment cannot be
silently overwritten. Pairing API requests are read-only, bounded, non-redirecting
and use the official Telegram endpoint. No token-bearing URL needs to be opened
in a browser or shared in chat. Raw Telegram responses are not logged.

An existing webhook causes pairing to fail without deleting it. Use a dedicated
Guardian bot. Pairing operations coordinate through a short per-bot SQLite lease;
the future polling listener must share that same state/lease before it is enabled.

If the challenge expires, run the first command again to generate a new challenge.
If you need to change an already confirmed owner/bot, stop and review enrollment;
there is deliberately no automatic destination replacement.

## Preview and manual delivery

```powershell
guardian telegram-send --site estateplanning --preview
```

Preview requires no Telegram network access and does not enable delivery. It reads
the latest eligible saved live report; use `--run-id YOUR_SAVED_RUN_ID` to select one.
It regenerates safe detail rather than uploading arbitrary files. Partial/stale data
and advisory model content remain labeled; captions show up to three actions.
Telegram headings use safe HTML bold tags; all dynamic text is escaped. Dates are
human-readable in MYT. Reporting windows retain Google's original Pacific dates.
Captions omit lower-priority whole blocks if needed instead of cutting sentences.
The Markdown attachment leads with changes/actions and keeps evidence in an appendix.
Owner's message template: bold WEBSITE STATISTICS (explicitly Google Search data
for SEO reports), SEO IMPROVEMENTS TO REVIEW with numbered page actions, confidence
on each action and an overall confidence line. Other audits use availability,
security/HTTPS or speed categories as appropriate. Confidence is taken from saved
findings, not invented percentages. Telegram supports bold text but not custom
message font sizes; use strong headings and whitespace. The report avoids the
ambiguous label "Search review". Empty findings show confidence as not assessed.

To send, explicitly enable Telegram in your process or local `.env`:

```powershell
$env:GUARDIAN_TELEGRAM_ENABLED='true'
guardian telegram-send --site estateplanning
guardian telegram-status --site estateplanning
```

This sends one document with a concise caption. The same manual report/content is
suppressed after a confirmed or uncertain attempt. Status shows safe receipt counts.
There is deliberately no blind `--force` resend option: inspect uncertain/pending
receipts and reconcile with Telegram first. Explicit new owner `/report` commands
can retrieve the same saved report again; reprocessing the same update cannot.

For opt-in important operational changes:

```powershell
guardian telegram-send --site estateplanning --run-id YOUR_AUDIT_RUN_ID --important-only
```

This dispatcher considers medium/high HTTP, TLS, health and header findings from
live audit history. It ignores unchanged state and does not call a collection failure
a confirmed outage. Recovery requires an explicit resolution from a complete audit.
State revisions let a resolved issue trigger again if it recurs. This command is
manual; ordinary audit/review commands never send Telegram automatically.

## Read-only commands

```powershell
$env:GUARDIAN_TELEGRAM_ENABLED='true'
guardian telegram-listen --site estateplanning
```

While that foreground process is running, your enrolled private chat can use:

- `/status`: latest saved observation time, collection/reasoning state and stale label.
- `/report`: latest eligible saved live report, concise caption plus Markdown attachment.

Commands start no scan or Claude call and grant no PR/approval/deployment authority.
Other chats, groups, forwarded/edited messages and commands over five minutes old
are ignored. Unknown owner commands receive fixed help. At most six owner responses
per minute are accepted; no incoming text is saved. The SQLite state stores offsets,
command IDs/outcomes and delivery receipts so restarts do not replay completed work.

`--once` processes one bounded poll and exits. Only one bot consumer can hold the
lease in this state store; another process fails instead of consuming updates.
Polling uses outbound HTTPS and requires no inbound public port. It stops on the
Guardian kill switch or Ctrl+C. If a network/API error stops it, inspect the safe
diagnostic before restarting; it is not an installed supervised service.

```powershell
guardian stop
# Once the listener has exited and you are ready to permit future runs:
guardian resume
```

The stop command affects all Guardian operations using that stop file. Telegram
also checks its enable setting before each protected action. Changing `.env` in a
running process is not automatically reloaded: stop/restart the listener, or use
the persistent kill switch for immediate interruption.

## Failure and disclosure boundaries

Telegram API methods/host are fixed; redirects/proxies and raw HTTP logging are
disabled. Reads/writes have bounded time, response and file sizes. A confirmed 429
may retry twice with a validated 1–30 second delay; uncertain timeouts are not
retried. Tokens and raw provider responses are not persisted. Attachments exclude
raw scanner errors/configuration and known secrets. No arbitrary file attachment,
public report hosting, message instructions or user-selected file path is supported.

Telegram bot conversations are not end-to-end secret chats. Send only the minimized
maintenance reports to the verified owner. Report input remains untrusted; unsafe,
out-of-scope, synthetic/replayed or oversized reports are rejected. Report discovery
skips unsafe entries, so no-eligible-report is possible even if files exist.

## Scheduling and future VPS

The owner preference is Monday 09:00 Asia/Kuala_Lumpur digests, comparing 14-day SEO
windows. No scheduled task, startup service or unattended listener has been enabled.
Local delivery/commands work only while the computer and process are available.

For a future dedicated VPS, provision configuration/secrets separately, stop the old
listener first, and move the durable Telegram database plus selected reports to the
new restricted service. Do not run two hosts polling one bot. Keep report/database
paths configurable; do not mount the production website filesystem or require its
database/SSH credentials. Scheduling/service activation remains separate work.
