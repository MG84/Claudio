"""
Monitor module: captures events, stores in SQLite, broadcasts via WebSocket.
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone

import aiohttp
import psutil

from bot.config import (
    MONITOR_DB_PATH, METRICS_INTERVAL_SECONDS,
    MONITOR_RETENTION_DAYS, MONITOR_EVENT_HISTORY_LIMIT,
    MEMORY_DIR, DEFAULT_MODEL, DEFAULT_EFFORT, DEFAULT_MAX_TURNS,
    TTS_HOST,
)

log = logging.getLogger("claudio.monitor")

_start_time = time.monotonic()
_messages_today_count = 0
_messages_today_date: str = ""
_db: sqlite3.Connection | None = None


# ── SQLite ────────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(MONITOR_DB_PATH))
        _db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        _db.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
        _db.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp DESC)")
        _db.commit()
        log.info(f"Monitor DB initialized at {MONITOR_DB_PATH}")
    return _db


def _store_event(event_type: str, data: dict, timestamp: str) -> None:
    try:
        db = _get_db()
        db.execute(
            "INSERT INTO events (timestamp, event_type, data, created_at) VALUES (?, ?, ?, ?)",
            (timestamp, event_type, json.dumps(data, default=str), time.time()),
        )
        db.commit()
    except Exception as e:
        log.error(f"Failed to store event: {e}")


def _cleanup_old_events() -> None:
    try:
        db = _get_db()
        cutoff = time.time() - (MONITOR_RETENTION_DAYS * 86400)
        cursor = db.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
        if cursor.rowcount:
            db.commit()
            log.info(f"Cleaned up {cursor.rowcount} old monitor events")
    except Exception as e:
        log.error(f"Monitor cleanup error: {e}")


def get_history(event_type: str | None = None, limit: int = MONITOR_EVENT_HISTORY_LIMIT) -> list[dict]:
    """Get historical events from SQLite."""
    try:
        db = _get_db()
        if event_type:
            rows = db.execute(
                "SELECT timestamp, event_type, data FROM events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT timestamp, event_type, data FROM events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"timestamp": r[0], "type": r[1], "data": json.loads(r[2])}
            for r in reversed(rows)
        ]
    except Exception as e:
        log.error(f"Failed to get history: {e}")
        return []


# ── Public API ────────────────────────────────────────────────────────

async def emit(event_type: str, data: dict | None = None) -> None:
    """Emit a monitor event to WebSocket clients and SQLite."""
    global _messages_today_count, _messages_today_date

    timestamp = datetime.now(timezone.utc).isoformat()
    event_data = data or {}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if today != _messages_today_date:
        _messages_today_count = 0
        _messages_today_date = today
    if event_type == "message_received":
        _messages_today_count += 1

    _store_event(event_type, event_data, timestamp)

    from bot.ws_server import broadcast
    asyncio.create_task(broadcast(event_type, {
        "timestamp": timestamp,
        **event_data,
    }))


def _collect_metrics() -> dict:
    """Collect system metrics."""
    from bot.handlers._state import bridge

    uptime = time.monotonic() - _start_time
    mem = psutil.virtual_memory()

    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_mb": round(mem.used / (1024 * 1024)),
        "ram_percent": mem.percent,
        "uptime_s": round(uptime),
        "active_sessions": len(bridge._sessions),
        "messages_today": _messages_today_count,
    }


async def start_metrics_task() -> None:
    """Background task: publish system metrics and cleanup old events."""
    from bot.ws_server import broadcast

    cleanup_counter = 0
    cleanup_every = 3600 // METRICS_INTERVAL_SECONDS

    psutil.cpu_percent(interval=None)

    while True:
        await asyncio.sleep(METRICS_INTERVAL_SECONDS)
        try:
            metrics = _collect_metrics()
            await broadcast("metrics", {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **metrics,
            })

            cleanup_counter += 1
            if cleanup_counter >= cleanup_every:
                cleanup_counter = 0
                _cleanup_old_events()

        except Exception as e:
            log.debug(f"Metrics task error: {e}")


async def emit_status() -> None:
    """Emit current system status (called on startup)."""
    model = os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)
    effort = os.getenv("CLAUDE_EFFORT", DEFAULT_EFFORT)
    max_turns = os.getenv("CLAUDE_MAX_TURNS", str(DEFAULT_MAX_TURNS))

    tts_status = "unknown"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
            async with session.get(f"{TTS_HOST}/docs") as resp:
                tts_status = "online" if resp.status == 200 else "offline"
    except Exception:
        tts_status = "offline"

    await emit("status", {
        "model": model,
        "effort": effort,
        "max_turns": max_turns,
        "tts_status": tts_status,
    })
