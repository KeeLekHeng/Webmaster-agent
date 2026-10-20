import argparse
import json
import os
import sqlite3
import subprocess
import httpx
from pathlib import Path
from dotenv import load_dotenv

from .models import SiteConfig
from .network import enabled


def main():
    load_dotenv(Path.cwd() / ".env", override=False, interpolate=False)
    parser = argparse.ArgumentParser(description="Local read-only Website Guardian")
    commands = parser.add_subparsers(dest="command", required=True)
    from .remediation_cli import COMMANDS, register
    register(commands)
    commands.add_parser("explain", help="Explain the LangGraph workflow without network access")
    commands.add_parser("stop", help="Create the persistent local kill switch")
    commands.add_parser("resume", help="Remove the persistent local kill switch")
    review = commands.add_parser("review", help="Compare search visibility and lab speed across equal periods")
    review.add_argument("--site", required=True)
    review.add_argument("--config", default=os.getenv("GUARDIAN_CONFIG", "config/sites.json"))
    review.add_argument("--output", default=os.getenv("GUARDIAN_OUTPUT", "reports"))
    review.add_argument("--property", dest="property_name", default=os.getenv("GUARDIAN_GSC_PROPERTY"))
    review.add_argument("--days", type=int, choices=[7, 14, 28], default=14)
    review.add_argument("--end-date", help="Last current-period date, YYYY-MM-DD in Pacific time")
    review.add_argument("--input-search", help="Import normalized search-periods.json instead of calling Google")
    review.add_argument("--performance-sample", action="append", default=[], help="Repeat for each Lighthouse lab sample")
    review.add_argument("--performance-dir", help="Default: data/performance/<site>; used when no explicit samples supplied")
    review.add_argument("--llm", choices=["none", "demo", "claude"], default="none")
    review.add_argument("--model", default=os.getenv("GUARDIAN_MODEL"))
    speed = commands.add_parser("performance-sample", help="Run one explicit public PageSpeed lab measurement")
    speed.add_argument("--site", required=True)
    speed.add_argument("--config", default=os.getenv("GUARDIAN_CONFIG", "config/sites.json"))
    speed.add_argument("--url", required=True)
    speed.add_argument("--strategy", choices=["mobile", "desktop"], default="mobile")
    speed.add_argument("--output", help="Default: data/performance/<site>")
    for name in ("history", "alerts"):
        view = commands.add_parser(name)
        view.add_argument("--site", required=True)
        view.add_argument("--database", default=os.getenv("GUARDIAN_DB", "data/guardian.sqlite3"))
        view.add_argument("--limit", type=int, choices=range(1, 101), default=20)
    scan = commands.add_parser("audit")
    scan.add_argument("--site", required=True)
    scan.add_argument("--config", default=os.getenv("GUARDIAN_CONFIG", "config/sites.json"))
    scan.add_argument("--output", default=os.getenv("GUARDIAN_OUTPUT", "reports"))
    scan.add_argument("--llm", choices=["none", "demo", "claude"], default="none")
    scan.add_argument("--model", default=os.getenv("GUARDIAN_MODEL"))
    scan.add_argument("--input-report", help="Replay saved JSON evidence without scanning the website")
    scan.add_argument("--seo", action="store_true", help="Include bounded public SEO/discovery checks")
    scan.add_argument("--lighthouse-report", help="Import a Lighthouse or PageSpeed JSON lab result for this site")
    scan.add_argument("--database", default=os.getenv("GUARDIAN_DB", "data/guardian.sqlite3"))
    scan.add_argument("--notify", choices=["none", "local"], default="none")
    due = commands.add_parser("run-due", help="One-shot dispatcher; scheduling must be explicitly enabled")
    due.add_argument("--schedule-config", default="config/schedule.json")
    due.add_argument("--config", default=os.getenv("GUARDIAN_CONFIG", "config/sites.json"))
    due.add_argument("--database", default=os.getenv("GUARDIAN_DB", "data/guardian.sqlite3"))
    due.add_argument("--output", default=os.getenv("GUARDIAN_OUTPUT", "reports"))
    args = parser.parse_args()
    if args.command in COMMANDS:
        from .remediation_cli import run
        try:
            return run(args)
        except (ValueError, KeyError, OSError, sqlite3.Error, httpx.HTTPError, subprocess.SubprocessError) as exc:
            parser.exit(2, f"Remediation blocked/failed ({type(exc).__name__}); check scope, proposal integrity, approval and policy. Raw tool/API output omitted.\n")
    if args.command == "explain":
        from .tutorial import explain
        print(explain())
        return 0
    if args.command in ("stop", "resume"):
        stop = Path(os.getenv("GUARDIAN_STOP_FILE", "data/STOP"))
        marker = "Website Guardian stopped\n"
        if args.command == "stop":
            stop.parent.mkdir(parents=True, exist_ok=True)
            if not stop.exists():
                stop.write_text(marker, encoding="utf-8")
            print("Kill switch set. New runs and subsequent protected operations are blocked.")
        else:
            if stop.exists():
                if stop.read_text(encoding="utf-8") != marker:
                    parser.exit(2, "Stop file is not a Guardian marker; remove it manually after review.\n")
                stop.unlink()
            print("Kill switch file cleared. AGENT_ENABLED must also be true to run.")
        return 0
    if args.command in ("history", "alerts"):
        from .history import HistoryStore
        store = HistoryStore(args.database)
        items = store.history(args.site, args.limit) if args.command == "history" else store.alerts(args.site, args.limit)
        print(json.dumps(items, indent=2, ensure_ascii=True))
        return 0
    try:
        enabled()
        if args.command in ("review", "performance-sample"):
            from datetime import date
            import re
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", args.site):
                raise ValueError("Invalid site storage identifier")
            configs = json.loads(Path(args.config).read_text(encoding="utf-8"))
            config = SiteConfig.model_validate(configs[args.site])
            sample_directory = Path("data/performance") / args.site
            if args.command == "performance-sample":
                from .performance import collect_pagespeed
                path = collect_pagespeed(args.url, config, args.output or sample_directory, args.strategy)
                print(f"Saved one dated lab measurement: {path}. No retrospective visitor-performance claim.")
                return 0
            if args.llm == "claude" and (not os.getenv("ANTHROPIC_API_KEY") or not args.model):
                raise ValueError("Claude configuration required")
            from .period_review import run_review
            samples = args.performance_sample or [str(p) for p in sorted(Path(args.performance_dir or sample_directory).glob("*.json"))]
            result = run_review({"site_id": args.site, "config": config, "output": args.output,
                                 "property_name": args.property_name or config.base_url.rstrip("/") + "/",
                                 "days": args.days, "end": date.fromisoformat(args.end_date) if args.end_date else None,
                                 "input_path": args.input_search, "lighthouse_paths": samples,
                                 "mode": args.llm, "model": args.model})
            print(result["report"].summary)
            print(f"Saved review: {Path(result['directory']) / 'summary.md'}")
            return 1 if result["report"].status == "partial" or result["report"].analysis.status in ("unavailable", "partial", "rejected") else 0
        if args.command == "run-due":
            from .scheduling import ScheduleConfig, dispatch
            from .workflow import run_workflow
            schedule = ScheduleConfig.model_validate_json(Path(args.schedule_config).read_text(encoding="utf-8"))
            configs = json.loads(Path(args.config).read_text(encoding="utf-8"))
            config = SiteConfig.model_validate(configs[schedule.site_id])
            dispatched = dispatch(schedule, {"config": config, "database": args.database,
                                            "output": args.output}, run_workflow)
            if dispatched["status"] != "complete":
                print(f"Scheduler: {dispatched['status']}; no audit started.")
                return 0
            result = dispatched["result"]
            report = result["report"]
            directory = Path(result["directory"])
            print(report.summary)
            print(f"Summary saved: {directory / 'summary.md'}")
            return 1 if report.status == "partial" else 0
        if args.llm == "claude" and (not os.getenv("ANTHROPIC_API_KEY") or not args.model):
            parser.exit(2, "Claude needs ANTHROPIC_API_KEY and GUARDIAN_MODEL (or --model); no request made.\n")
        configs = json.loads(Path(args.config).read_text(encoding="utf-8"))
        config = SiteConfig.model_validate(configs[args.site])
        if args.input_report and (args.seo or args.lighthouse_report):
            raise ValueError("Replay cannot be combined with new observations")
        config.seo_checks = config.seo_checks or args.seo
        if args.lighthouse_report:
            from .performance import import_lighthouse
            import_lighthouse(args.lighthouse_report, config)  # Validate before any web requests.
        from .workflow import run_workflow
        result = run_workflow({"site_id": args.site, "config": config, "mode": args.llm,
                               "model": args.model, "input_report": args.input_report, "output": args.output,
                               "database": "" if args.lighthouse_report else args.database, "notify": args.notify,
                               "lighthouse_report": args.lighthouse_report})
        report = result["report"]
        directory = Path(result["directory"])
    except (ValueError, KeyError, OSError, sqlite3.Error, httpx.HTTPError) as exc:
        if type(getattr(exc, "google_status", None)) is int:
            parser.exit(2, f"Google API returned HTTP {exc.google_status}; check API access/key/quota. No measurement saved. Raw response omitted.\n")
        parser.exit(2, f"Audit could not start/save ({type(exc).__name__}); check configuration and permissions.\n")
    print(report.summary)
    print(f"Summary saved: {directory / 'summary.md'}")
    print(f"Full report: {directory / 'report.md'}")
    return 1 if report.status == "partial" or report.analysis.status in ("unavailable", "partial", "rejected") else 0


if __name__ == "__main__":
    raise SystemExit(main())
