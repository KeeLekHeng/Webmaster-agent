"""Telegram-only CLI registration; importing it starts no listener or network I/O."""
import json
import os
from pathlib import Path

from guardian.core.models import SiteConfig
from guardian.telegram.reporting import load_report, render
from guardian.telegram.service import OwnerBot
from guardian.telegram.state import TelegramStore

COMMANDS = {"telegram-send", "telegram-listen", "telegram-status"}


def register(commands):
    for name in sorted(COMMANDS):
        parser = commands.add_parser(name)
        parser.add_argument("--site", required=True)
        parser.add_argument("--config", default=os.getenv("GUARDIAN_CONFIG", "config/sites.json"))
        parser.add_argument("--reports", default=os.getenv("GUARDIAN_OUTPUT", "reports"))
        parser.add_argument("--state", default="data/telegram.sqlite3")
        if name == "telegram-send":
            parser.add_argument("--run-id")
            parser.add_argument("--preview", action="store_true", help="Render locally without Telegram access")
            parser.add_argument("--important-only", action="store_true", help="Dispatch only changed important audit state")
        if name == "telegram-listen":
            parser.add_argument("--once", action="store_true", help="Process one bounded poll and exit")


def run(args):
    configs = json.loads(Path(args.config).read_text(encoding="utf-8"))
    config = SiteConfig.model_validate(configs[args.site])
    if args.command == "telegram-status":
        print(json.dumps({"enabled": os.getenv("GUARDIAN_TELEGRAM_ENABLED", "false").lower() == "true",
                          "receipts": TelegramStore(args.state).receipts(),
                          "scheduled_by_this_command": False}))
        return 0
    if args.command == "telegram-send" and args.preview:
        report = load_report(args.reports, args.site, config, args.run_id)
        caption, document = render(report)
        print(caption)
        print(f"Attachment: guardian-report.md ({len(document)} bytes). Preview only; no message sent.")
        return 0
    bot = OwnerBot(args.site, config, args.reports, args.state)
    if args.command == "telegram-listen":
        print("Telegram listener starting for the enrolled private owner. Press Ctrl+C to stop; no schedule installed.", flush=True)
        try:
            bot.listen(once=args.once, progress=lambda message: print(message, flush=True))
        except KeyboardInterrupt:
            print("Telegram listener stopped; lease released.", flush=True)
    else:
        with bot.store.lease(bot.bot_id):
            outcome = bot.report(args.run_id, important_only=args.important_only)
        print(f"Telegram delivery: {outcome}")
    return 0
