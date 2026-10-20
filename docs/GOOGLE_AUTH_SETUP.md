# Persistent read-only Search Console authorization

Implemented locally on 2026-10-20 without new dependencies or a public callback
server. Existing manual access tokens still work when refresh configuration is empty.
Nothing in this change creates Google credentials, changes account permissions,
or modifies the website. The owner performs Google sign-in and consent manually.

## How it works

At the beginning of each live review, Guardian uses the configured OAuth client ID,
client secret and refresh token to request a new access token from the fixed Google
token endpoint. It uses that access token for the four search-data queries, then
discards it when the process exits. A fresh token is requested on each run; no token
cache, browser server, background renewal process or file rewrite is needed.

Credentials stay in the ignored local `.env` or environment. Keep access to that
file restricted to the account running Guardian. It is plaintext configuration,
not an encrypted secret vault. For a VPS, provision secrets separately rather than
committing them or copying production website credentials.

## Set up your own Google OAuth client

The default OAuth Playground refresh grant is revoked after 24 hours, so it cannot
provide lasting unattended access. Use Playground with your own OAuth client instead.

1. Open [Google Cloud Console](https://console.cloud.google.com/) under the account
   that has Search Console access. Select or create a project for Website Guardian.
2. In **APIs & Services → Library**, enable **Google Search Console API** for that project.
3. Open **Google Auth Platform** and configure the app if prompted: name Website
   Guardian, your support/contact email and the appropriate audience. For a personal
   Google account use External. In Testing, add your own Google account as a test user.
4. In **Data Access**, request only this scope:

   ```text
   https://www.googleapis.com/auth/webmasters.readonly
   ```

5. In **Clients → Create client**, choose **Web application** for this Playground
   setup (the OAuth callback belongs to Playground). Set the authorized redirect URI to:

   ```text
   https://developers.google.com/oauthplayground
   ```

   Copy the resulting client ID and secret into your local `.env` only.
6. Open [OAuth Playground](https://developers.google.com/oauthplayground/), click
   the settings gear and enable **Use your own OAuth credentials**. Enter that
   client ID and secret. Keep Google endpoints, server-side flow, **Offline** access
   and the consent prompt. Request only the read-only scope above; do not reuse a
   combined grant containing other scopes.
7. Authorize using the account with Search Console access. Exchange the code for
   tokens, then copy the **refresh token** into the local `.env`. Do not copy the
   authorization code into Guardian. Do not share any token or secret in chat.

```dotenv
GUARDIAN_GSC_PROPERTY=sc-domain:estateplanning.com.my
GUARDIAN_GSC_CLIENT_ID=
GUARDIAN_GSC_CLIENT_SECRET=
GUARDIAN_GSC_REFRESH_TOKEN=
```

Keep the exact existing property value if yours is a URL-prefix property instead.
The old `GUARDIAN_GSC_ACCESS_TOKEN` can remain: refresh mode takes priority. If any
refresh field is nonempty, all three must be populated; incomplete/failed refresh
does not fall back silently to the old token. Existing shell variables take priority
over `.env`, so update/remove stale shell settings when changing credentials.

**Testing-mode limit:** Google's External/Testing grants expire after seven days
for this scope. For lasting use, review Google's publishing/verification requirements
and move the OAuth app to Production when appropriate. This refers to the Google
OAuth app's publishing status, not deploying or changing the website. Refresh tokens
can still expire or be revoked; persistent does not mean permanent access.

## Test

```powershell
.venv\Scripts\guardian.exe gsc-auth-check
.venv\Scripts\guardian.exe review --site estateplanning --llm none
```

`gsc-auth-check` only checks token refresh; it does not fetch search metrics and
does not prove access to a particular property. Success reports `refreshed` without
printing tokens. The review then checks actual property access and records safe
authorization status alongside the evidence. Add `--llm claude` for interpretation.

## Failure behavior

- Only the fixed `https://oauth2.googleapis.com/token` endpoint receives client
  credentials, via a form POST body. No credentials in URLs, LLM inputs or logs.
- No redirects, environment proxy settings or automatic token-exchange retries.
  Request timeout is 15 seconds; response cap is 64 KiB with an elapsed-time budget
  checked during reads. The kill switch is checked before and during collection.
- A refresh response must explicitly confirm exactly the read-only Search Console
  scope and a valid Bearer token/lifetime. Broader or unconfirmed scopes are rejected.
- Revoked/expired grants become `reauthorization-required`. Bad client configuration,
  scope mismatch and transient failures have separate fixed diagnostic labels.
  Raw responses/descriptions, refresh tokens and access tokens are never saved.
- No automatic credential replacement or grant renewal. If Google returns a changed
  refresh token, the run requires human review instead of silently overwriting secrets.
- Missing credentials keep manual mode available. Configured refresh failures produce
  partial reports with unavailable search data, not zero traffic or invented declines.
- Saved-report import neither refreshes nor verifies credentials; its authorization
  status is reset to unknown. No scheduling or Google permission changes are enabled.

## Validation and current state

Mocked tests cover successful refresh, preference over stale tokens, incomplete
configuration, revoked grants, scope rejection, malformed tokens, redirects, size
caps, transport errors, kill switch and redacted reports. After the owner supplied
their OAuth credentials/consent and enabled Search Console API in that project,
live refresh and a Claude-assisted 14-day review succeeded on 2026-10-20.
Saved evidence: `reports/5b3ef963d07e4e46bb175cc1f04e6f21` (ignored local output).
The owner reports the OAuth app is External/In production. No credentials or
consent grants were created by the agent. Scheduling remains disabled.

References: [Google refresh-token protocol](https://developers.google.com/identity/protocols/oauth2/web-server#offline),
[Playground and its 24-hour grant limit](https://developers.google.com/oauthplayground/),
[OAuth client setup](https://support.google.com/cloud/answer/15549257),
[Testing-mode authorization expiry](https://support.google.com/cloud/answer/15549945).
