"""
Periodic file cleanup for uploads directory.
"""

import asyncio
import logging
import time

from bot.config import UPLOADS_DIR, UPLOADS_MAX_AGE_HOURS, CLEANUP_INTERVAL_SECONDS

log = logging.getLogger("claudio.cleanup")


async def cleanup_uploads_task() -> None:
    """Background task: delete files older than UPLOADS_MAX_AGE_HOURS every hour."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            if not UPLOADS_DIR.exists():
                continue

            max_age_seconds = UPLOADS_MAX_AGE_HOURS * 3600
            now = time.time()
            count = 0

            for f in UPLOADS_DIR.iterdir():
                if f.is_file() and (now - f.stat().st_mtime) > max_age_seconds:
                    f.unlink(missing_ok=True)
                    count += 1

            if count:
                log.info(f"Cleaned up {count} old files from {UPLOADS_DIR}")

        except Exception as e:
            log.error(f"Cleanup error: {e}", exc_info=True)
