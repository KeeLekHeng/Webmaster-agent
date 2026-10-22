"""Bounded weekly read-only collection and owner digest; explicit local activation."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from guardian.core.models import SiteConfig
from guardian.core.network import enabled, PolicyError

MYT = timezone(timedelta(hours=8))


class WeeklyConfig(BaseModel):
    model_config = {"extra": "forbid"}
    enabled: bool = False
    site_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    llm: str = Field(default="claude", pattern="^(none|claude)$")
    send_telegram: bool = False
    collect_speed: bool = True
    days: int = Field(default=14, ge=14, le=14)


def weekly_slot(now=None):
    if now is not None and now.tzinfo is None:
        raise ValueError("Weekly timestamps must include timezone")
    now = (now or datetime.now(timezone.utc)).astimezone(MYT)
    monday = (now - timedelta(days=now.weekday())).replace(hour=9, minute=0, second=0, microsecond=0)
    if now < monday:
        monday -= timedelta(days=7)
    return monday.isoformat()


def run_weekly(settings, *, database="data/weekly.sqlite3", sites="config/sites.json",
               output="reports", history="data/guardian.sqlite3", telegram="data/telegram.sqlite3",
               now=None, audit_runner=None, review_runner=None, speed_collector=None, bot_factory=None):
    enabled()
    if not settings.enabled:
        return {"status": "disabled"}
    from guardian.workflows.audit import run_workflow
    from guardian.workflows.period_review import run_review
    from guardian.checks.performance import collect_pagespeed
    from guardian.telegram.service import OwnerBot
    import os
    config = SiteConfig.model_validate(json.loads(Path(sites).read_text(encoding="utf-8"))[settings.site_id])
    model = os.getenv("GUARDIAN_MODEL")
    if settings.llm == "claude" and (not model or not os.getenv("ANTHROPIC_API_KEY")):
        raise ValueError("Weekly Claude configuration missing")
    config.seo_checks = True
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    slot = weekly_slot(now)
    db = sqlite3.connect(path, timeout=10)
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS weekly_jobs(site_id TEXT,slot TEXT,status TEXT,details TEXT,PRIMARY KEY(site_id,slot))")
            try:
                db.execute("INSERT INTO weekly_jobs VALUES(?,?,?,?)", (settings.site_id,slot,"started","{}"))
            except sqlite3.IntegrityError:
                return {"status": "already-claimed", "slot": slot}
        outcomes = {}
        def save(stage, result):
            outcomes[stage] = result
            with db:
                db.execute("UPDATE weekly_jobs SET details=? WHERE site_id=? AND slot=?", (json.dumps(outcomes),settings.site_id,slot))
        def attempt(stage, operation):
            enabled()
            try:
                result = operation()
                if "report" in result:
                    report = result["report"]
                    status = "partial" if report.status != "complete" or report.analysis.status in {"unavailable", "partial", "rejected"} else "complete"
                    save(stage, {"status": status, "run_id": report.run_id})
                else:
                    save(stage, {"status": "complete", **result})
                return result
            except PolicyError:
                raise
            except Exception:
                enabled()
                save(stage, {"status": "unavailable"})  # no raw provider errors
                return None
        bot = None
        if settings.send_telegram:
            bot = (bot_factory or OwnerBot)(settings.site_id, config, output, telegram)
        audit = attempt("audit", lambda: (audit_runner or run_workflow)(
            {"site_id":settings.site_id,"config":config,"mode":"none","output":output,"database":history,"notify":"none"}, progress=None))
        # Persist only references/status; never serialize the report/model object.
        if audit and bot:
            attempt("important_delivery", lambda: {"outcome":bot.report(audit["report"].run_id,important_only=True)})
        samples = Path("data/performance") / settings.site_id
        if settings.collect_speed:
            for strategy in ("mobile", "desktop"):
                attempt("speed_"+strategy, lambda strategy=strategy: {"sample":str((speed_collector or collect_pagespeed)(config.base_url,config,samples,strategy))})
        review = attempt("review", lambda: (review_runner or run_review)(
            {"site_id":settings.site_id,"config":config,"property_name":os.getenv("GUARDIAN_GSC_PROPERTY") or config.base_url.rstrip('/')+'/',
             "days":14,"include_queries":True,"mode":settings.llm,"model":model,"output":output,
             "lighthouse_paths":[str(p) for p in sorted(samples.glob('*.json'))]}, progress=None))
        if review and bot:
            attempt("digest_delivery", lambda: {"outcome":bot.report(review["report"].run_id,context="weekly:"+slot)})
        status = "complete" if all(v["status"] == "complete" for v in outcomes.values()) else "partial"
        with db:
            db.execute("UPDATE weekly_jobs SET status=? WHERE site_id=? AND slot=?",(status,settings.site_id,slot))
        return {"status":status,"slot":slot,"stages":outcomes}
    except BaseException:
        with db:
            db.execute("UPDATE weekly_jobs SET status='interrupted' WHERE site_id=? AND slot=?",(settings.site_id,slot))
        raise
    finally:
        db.close()
