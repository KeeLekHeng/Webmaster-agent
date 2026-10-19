# How LangGraph runs Website Guardian

LangGraph is the Python library that runs the workflow. Claude is the external
model called inside one workflow step. All eight steps run on your computer; only
Claude reasoning requires an API request. No LangGraph cloud service is required.

The three building blocks are **state**, **nodes** and **edges**. State is the
shared information passed between steps. A node is a Python function doing one
piece of work. An edge connects that function to the next function. This follows
the [official Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).

```text
START
  -> validate_config
  -> collect_checks
  -> normalize_evidence
  -> investigate_findings
  -> policy_filter
  -> persist_history
  -> summarize_handoff
  -> save_report
  -> END
```

## Follow one finding through the graph

1. `validate_config` checks the approved site and initial routes and whether the
   agent is enabled. An invalid target stops the workflow.
2. `collect_checks` reuses the Milestone 1 scanner. It may record a missing HSTS
   header with evidence IDs such as E003 and E006. Alternatively it reads an
   existing JSON report for offline replay and checks its site/source scope.
3. `normalize_evidence` constructs a small, bounded data object for reasoning.
   It includes known labels, numbers, booleans and IDs. It excludes raw page text,
   headers, URLs, repository files and exception messages. The first existing
   finding is called F001, the second F002, and so on.
4. `investigate_findings` asks Claude to order these existing findings and explain
   their meaning and uncertainty. Claude has no tools. In demo mode, a Python
   fake produces explicitly labelled notes instead. In none mode it skips reasoning.
5. `policy_filter` checks the structured response. A note citing an invented
   F999 or E999 is rejected. Citing another finding's evidence is also rejected.
   Confirmed conclusions from unavailable/blocked evidence are rejected. Obvious
   command/URL patterns are screened. The original scanner evidence, severity
   and recommendations remain intact, including findings the model omits.
6. `persist_history` saves an observation snapshot to SQLite, compares active issues
   with previous live runs, and optionally queues local alert records. Replay/demo
   runs cannot change the live baseline. Missing coverage cannot establish recovery.
7. `summarize_handoff` formats existing scanner findings into a short human handoff.
   Repeated observations become one issue with a distinct affected-URL count.
   Severity and confidence come from the scanner; evidence references, collection
   failures, limitations and reasoning status remain visible. It uses no LLM call.
8. `save_report` writes local JSON and Markdown with scanner results, accepted
   advisory notes and a timestamped node log. If Claude fails, this step still
   saves the scanner report and summary with reasoning marked unavailable. A kill-switch stop
   takes priority and stops further protected work, including report saving.

The policy validates structure and evidence membership, not the truth of every
sentence. A model explanation remains subject to human review. No model text is
passed to a shell or action executor.

## Where to read the code

- `src/guardian/workflow.py`: `AuditState` describes the shared state. `build_graph`
  registers functions using `add_node`, connects them with `add_edge`, and calls
  `compile`. `run_workflow` uses `stream` to execute the graph and print completed
  step names without dumping state or credentials.
- `src/guardian/investigation.py`: minimizes evidence, calls Claude with the
  [official structured-output SDK interface](https://platform.claude.com/docs/en/build-with-claude/structured-outputs),
  supplies the fake demo response, and validates citations independently.
- `src/guardian/models.py`: Pydantic schemas describe the allowed report and model
  response shapes. Extra model response fields, including attempted action fields,
  are rejected.
- `src/guardian/summary.py`: deterministic summary formatting, issue grouping and
  unique affected-URL counts. The output is printed and saved as `summary.md`.
- `src/guardian/history.py`: SQLite observation history, comparisons, site leases
  and the local alert outbox. `scheduling.py` provides a disabled-by-default dispatcher.
- `src/guardian/audit.py`: deterministic checks from Milestone 1 remain separate
  from model reasoning.

## Try it in the terminal

```powershell
.venv\Scripts\guardian explain
.venv\Scripts\guardian audit --site estateplanning --llm demo --input-report reports/reviewed/32c1bc5cb90a4ea49317db45712d9410/report.json
```

The second command prints eight `[LangGraph]` lines as the nodes complete. It uses
the real LangGraph runtime and saved observations, with fake model reasoning.
It neither rescans the website nor contacts Anthropic. The output is labelled demo.

Graph state currently lives in memory for one run. SQLite observations and saved reports survive exit; graph
state does not automatically resume after interruption. LangGraph can support
more complex flows, but this milestone deliberately uses a single fixed sequence,
no loops, multi-agent orchestration, approval executor or persistent checkpoints.
