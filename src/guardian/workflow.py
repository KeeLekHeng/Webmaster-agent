"""One local LangGraph workflow; no tools or production mutation capability for the LLM."""
import uuid
from importlib.metadata import version
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from .audit import audit, now, save_report
from .investigation import ClaudeInvestigator, DemoInvestigator, filter_investigation, project_evidence, investigation_failure_notice
from .models import AnalysisResult, Investigation, Report, SiteConfig
from .network import enabled, validate_url
from .summary import build_summary
from .history import HistoryStore


STEPS = ("validate_config", "collect_checks", "normalize_evidence",
         "investigate_findings", "policy_filter", "persist_history", "summarize_handoff", "save_report")


class AuditState(TypedDict, total=False):
    site_id: str
    config: SiteConfig
    mode: Literal["none", "demo", "claude"]
    model: str | None
    input_report: str | None
    output: str
    report: Report
    payload: dict
    candidate: Investigation | None
    directory: str
    validated_at: str
    database: str
    notify: Literal["none", "local"]
    lighthouse_report: str | None


def build_graph(collector=audit, investigator=None):
    def event(report, node, outcome="complete"):
        report.workflow.append({"node": node, "outcome": outcome, "timestamp": now()})

    def validate(state):
        enabled()
        if state.get("lighthouse_report") and (state.get("input_report") or state.get("database")):
            raise ValueError("Imported lab results require history disabled and no replay")
        config = SiteConfig.model_validate(state["config"])
        validate_url(config.base_url.rstrip("/") + "/", config)
        for path in config.seed_paths:
            validate_url(config.base_url.rstrip("/") + path, config)
        return {"config": config, "validated_at": now()}

    def collect(state):
        enabled()
        if state.get("input_report"):
            path = Path(state["input_report"])
            if path.stat().st_size > 1048576:
                raise ValueError("Replay report exceeds size limit")
            report = Report.model_validate_json(path.read_text(encoding="utf-8"))
            if report.site_id != state["site_id"]:
                raise ValueError("Replay site mismatch")
            for e in report.evidence:
                validate_url(e.source, state["config"])
            source_run_id = report.run_id
            report.run_id = uuid.uuid4().hex
            report.workflow = []
            report.limitations.append("Replayed saved observations; timestamps describe the original scan, not a new live check.")
        else:
            report = collector(state["site_id"], state["config"])
            source_run_id = None
        if state.get("lighthouse_report"):
            if state.get("input_report") or state.get("database"):
                raise ValueError("Imported lab reports cannot update live history or replay evidence")
            from .performance import import_lighthouse
            evidence = import_lighthouse(state["lighthouse_report"], state["config"])
            evidence.id = f"E{len(report.evidence) + 1:03d}"
            report.evidence.append(evidence)
            report.limitations.append("Imported Lighthouse lab measurement: see its original evidence timestamp. Artifact authenticity is not independently verified. It is not field Core Web Vitals, indexing, traffic or conversion evidence. Live history/alerts are disabled for this mixed report; no regression claim is made.")
        report.analysis = AnalysisResult(mode=state["mode"], source_run_id=source_run_id,
                                         model=state.get("model") if state["mode"] == "claude" else None)
        report.tools["langgraph"] = version("langgraph")
        report.tools["anthropic"] = version("anthropic")
        report.workflow.append({"node": "validate_config", "outcome": "complete", "timestamp": state["validated_at"]})
        event(report, "collect_checks", "replayed" if source_run_id else "complete")
        return {"report": report}

    def normalize(state):
        report = state["report"]
        try:
            payload, digest = project_evidence(report)
            report.analysis.input_sha256 = digest
        except ValueError:
            payload = {}
            report.analysis.status = "unavailable"
            report.analysis.notices.append("Evidence input budget/validation failed; no model request made.")
        event(report, "normalize_evidence", "complete" if payload else "unavailable")
        return {"payload": payload, "report": report}

    def investigate(state):
        enabled()
        report = state["report"]
        candidate = None
        mode = state["mode"]
        if mode == "none":
            report.analysis.status = "skipped"
        elif state["payload"]:
            try:
                client = investigator or (DemoInvestigator() if mode == "demo" else ClaudeInvestigator(state.get("model")))
                candidate = Investigation.model_validate(client(state["payload"]))
                report.analysis.usage = getattr(client, "usage", {})
                report.analysis.status = "demo" if mode == "demo" else "complete"
            except Exception as exc:
                report.analysis.status = "unavailable"
                report.analysis.notices.append(investigation_failure_notice(exc))
        event(report, "investigate_findings", report.analysis.status)
        return {"candidate": candidate, "report": report}

    def policy(state):
        enabled()
        report = state["report"]
        if state.get("candidate") is not None:
            notes, rejected = filter_investigation(state["candidate"], state["payload"])
            report.analysis.notes = notes
            if rejected:
                report.analysis.status = "partial" if notes else "rejected"
                report.analysis.notices.append(f"Policy rejected {rejected} model entries; rejected content was not saved.")
            report.analysis.notices.append("Model prose is advisory and unverified; evidence references are validated, semantic correctness requires human review.")
            if len(notes) < len(report.findings):
                report.analysis.notices.append("Some scanner findings have no accepted model explanation; all remain in the deterministic findings section.")
        event(report, "policy_filter", report.analysis.status)
        return {"report": report, "candidate": None}

    def summarize(state):
        enabled()
        report = state["report"]
        report.summary = build_summary(report)
        event(report, "summarize_handoff")
        return {"report": report}

    def persist(state):
        enabled()
        report = state["report"]
        report.history = {}
        if state.get("database"):
            report.history = HistoryStore(state["database"]).record(report, state.get("notify", "none"))
        event(report, "persist_history", "complete" if state.get("database") else "disabled")
        return {"report": report}

    def save(state):
        enabled()
        report = state["report"]
        report.limitations = [x for x in report.limitations if not x.startswith("No LLM used.")]
        report.limitations.append("External content remains untrusted. No model tools, shell execution or production writes exist in this workflow.")
        if state["mode"] != "none":
            report.limitations.append("The local workflow runs on this computer; Claude mode sends only the bounded evidence projection to Anthropic.")
        event(report, "save_report")
        return {"directory": str(save_report(report, state["output"])), "report": report}

    builder = StateGraph(AuditState)
    for name, function in zip(STEPS, (validate, collect, normalize, investigate, policy, persist, summarize, save)):
        builder.add_node(name, function)
    previous = START
    for name in STEPS:
        builder.add_edge(previous, name)
        previous = name
    builder.add_edge(previous, END)
    return builder.compile()


def run_workflow(state, progress=print, collector=audit, investigator=None):
    enabled()
    graph = build_graph(collector, investigator)
    result = dict(state)
    # Explicitly disable external LangSmith tracing, even if environment enables it.
    from contextlib import nullcontext
    lease = HistoryStore(state["database"]).lease(state["site_id"]) if state.get("database") else nullcontext()
    with lease, tracing_context(enabled=False):
        for update in graph.stream(state, stream_mode="updates", config={"recursion_limit": 12}):
            for node, values in update.items():
                result.update(values)
                if progress:
                    progress(f"[LangGraph] {node}")
    return result
