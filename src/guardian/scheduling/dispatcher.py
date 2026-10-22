"""One-shot dispatcher for a future external scheduler. No background loop or shell."""
from typing import Literal

from pydantic import BaseModel, Field

from guardian.storage.history import HistoryStore
from guardian.core.network import enabled


class ScheduleConfig(BaseModel):
    model_config = {"extra": "forbid"}
    enabled: bool = False
    site_id: str
    interval_minutes: int = Field(default=1440, ge=60, le=10080)
    notify: Literal["none", "local"] = "none"


def dispatch(schedule, state, runner, current_time=None):
    enabled()
    if not schedule.enabled:
        return {"status": "disabled"}
    store = HistoryStore(state["database"])
    # The graph takes its own lease; claiming a slot is atomic across dispatchers.
    slot = store.claim_job(schedule.site_id, schedule.interval_minutes, current_time)
    if slot is None:
        return {"status": "already_claimed"}
    try:
        result = runner({**state, "site_id": schedule.site_id, "mode": "none", "notify": schedule.notify})
        store.finish_job(schedule.site_id, slot, "complete")
        return {"status": "complete", "result": result}
    except BaseException:
        store.finish_job(schedule.site_id, slot, "failed")
        raise
