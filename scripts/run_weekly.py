"""Task Scheduler launcher: fixed working directory and bounded redacted log."""
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.chdir(root)
sys.path.insert(0, str(root / "src"))
directory = root / "data" / "logs"
directory.mkdir(parents=True, exist_ok=True)
listening = sys.argv[1:] == ["--listen"]
log = directory / ("telegram-listener.log" if listening else "weekly.log")
if log.exists() and log.stat().st_size > 1048576:
    log.replace(directory / "weekly.previous.log")
with log.open("a", encoding="utf-8") as stream, redirect_stdout(stream), redirect_stderr(stream):
    from datetime import datetime, timezone
    label = "Telegram listener" if listening else "Weekly"
    print(label + " invocation " + datetime.now(timezone.utc).isoformat(), flush=True)
    try:
        from guardian.cli import main
        sys.argv = (["guardian", "telegram-listen", "--site", "estateplanning"] if listening else
                    ["guardian", "weekly-digest", "--schedule-config", "data/weekly.json"])
        code = main()
    except SystemExit as exc:
        code = exc.code
    except Exception:
        print(label + " invocation failed; raw error omitted.")
        code = 2
    print(f"{label} exit: {code}", flush=True)
raise SystemExit(code)
