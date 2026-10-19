def explain():
    return """Website Guardian: your first LangGraph workflow

LangGraph runs a flowchart made from Python functions.
Claude is the model used by one step; LangGraph controls the whole sequence.

  START
    |
  validate_config       Check approved site configuration and kill switch.
    |
  collect_checks        Run Milestone 1 scanners OR replay saved evidence.
    |
  normalize_evidence    Keep only bounded numeric/boolean facts and known labels.
    |
  investigate_findings  Ask Claude to order and explain existing findings.
    |
  policy_filter         Reject invented IDs, invalid citations or unsafe output.
    |
  persist_history       Save SQLite observations, compare issues, queue local alerts.
    |
  summarize_handoff     Group issues into a concise human summary; no LLM call.
    |
  save_report           Save local JSON/Markdown, including the step log.
    |
   END

Three terms to know:
  STATE = the shared work folder: configuration, report and projected evidence.
  NODE  = one Python function that reads state and returns updated fields.
  EDGE  = the arrow saying which node runs next.

In src/guardian/workflow.py:
  StateGraph(AuditState) creates the flowchart using our typed shared state.
  add_node(...) registers each step; add_edge(...) connects them in order.
  compile() prepares the graph; stream(...) runs it and reports completed steps.

Example: the scanner finds a missing HSTS header on nine responses.
It records E003, E006, etc. The model sees known observations and finding F001.
Claude may explain F001 and cite those IDs. Python checks those links before saving.
The model cannot create a scanner fact, change severity, or run a fix.
Valid citations still do not guarantee a correct explanation: review the prose.

Modes:
  --llm none    Real graph, deterministic checks; skips model reasoning (default).
  --llm demo    Real graph, explicitly fake investigator; no API key or API charge.
  --llm claude  Real graph plus an Anthropic API request using your selected model.
  --input-report <report.json> reuses old observations; it is not a fresh scan.

If Claude fails, the graph preserves the scanner report and marks reasoning unavailable.
If the kill switch is off, it stops before further protected work.
There are no automatic fixes, production write tools or cloud graph service.
SQLite stores history between runs; replay/demo runs do not alter the live baseline.
run-due is an optional one-shot dispatcher; no scheduled job is enabled by default.
guardian stop blocks future work using a local stop file; guardian resume clears it.
The state exists in memory during a run. Reports persist locally; resumable
graph checkpoints are separate from the SQLite observation history.
"""
