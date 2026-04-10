"""Simple user authorization for the Telegram bot."""

import os


def is_allowed_user(user_id: int) -> bool:
    allowed = os.getenv("TELEGRAM_ALLOWED_USERS", "")
    if not allowed:
        return True  # No restriction if not configured
    allowed_ids = {int(uid.strip()) for uid in allowed.split(",") if uid.strip()}
    return user_id in allowed_ids
