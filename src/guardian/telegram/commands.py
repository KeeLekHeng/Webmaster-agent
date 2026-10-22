"""Fixed, private-owner command discovery; menu visibility grants no authority."""

COMMAND_MENU = [
    {"command": "status", "description": "View latest saved check status"},
    {"command": "report", "description": "Get saved summary and downloadable report"},
    {"command": "help", "description": "Show commands and what they do"},
]

HELP_TEXT = (
    "<b>Website Guardian commands</b>\n\n"
    "/status — Latest saved check time and collection/analysis status.\n"
    "/report — Saved findings, confidence levels and downloadable report.\n"
    "/help — Show this command guide.\n\n"
    "These commands use saved data; they do not run a fresh scan.\n"
    "Only the paired private owner can use this bot."
)


def menu_payload(method, chat_id):
    if method == "setMyCommands":
        return {"commands": COMMAND_MENU, "scope": {"type": "chat", "chat_id": chat_id}, "language_code": ""}
    if method == "setChatMenuButton":
        return {"chat_id": chat_id, "menu_button": {"type": "commands"}}
    raise ValueError("Unknown command menu operation")
