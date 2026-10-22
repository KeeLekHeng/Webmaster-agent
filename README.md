# Website Guardian

A separate Python/LangGraph website maintenance assistant for
`estateplanning.com.my`: read-only availability/security checks, Search Console
SEO insights, dated speed samples and private-owner Telegram reports. Deterministic
checks work without an LLM; optional Claude reasoning explains the evidence.
Production merge and deployment remain human-controlled.

## Quick start

Run from the checkout on Windows with Python 3.11 or newer:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.lock
.venv\Scripts\python -m pip install --no-deps -e .
# Copy .env.example to .env and fill integration credentials locally.
.venv\Scripts\guardian audit --site estateplanning --llm none
.venv\Scripts\guardian explain
.venv\Scripts\python -m pytest -q
```

```powershell
guardian review --site estateplanning --llm claude
guardian telegram-send --site estateplanning --preview
guardian telegram-status --site estateplanning --details
guardian stop
```

Reports and summaries live in ignored `reports/<run-id>/` folders. Local SQLite
and operational state live in ignored `data/`. Secrets stay in `.env`. A code push
does not upload those files. Automatic data deletion is not enabled.

Source schedule/notification defaults are disabled. The owner's local installation
has Monday 09:00 Malaysia weekly collection and a supervised Telegram listener
enabled; the computer must be on, online and logged in.

See the **[technical guide](docs/TECHNICAL_GUIDE.md)** for architecture, package map,
security, integration setup, commands, scheduling, storage, retention recommendations,
validation and remaining work. Keep that guide current instead of adding separate
milestone/setup documents. OpenSpec change records remain under `openspec/`;
agent instructions are in [AGENTS.md](AGENTS.md).
