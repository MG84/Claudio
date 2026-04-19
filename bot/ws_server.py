"""
WebSocket + static file server for the monitoring dashboard.
Serves Next.js static export, provides real-time events via WebSocket,
handles authentication and quick actions.
"""

import asyncio
import hashlib
import json
import logging
import secrets
import weakref

from aiohttp import web

from bot.config import (
    DASHBOARD_PORT, DASHBOARD_STATIC_DIR, WS_PATH,
    HISTORY_ON_CONNECT_LIMIT, DASHBOARD_PASSWORD,
    AUTH_COOKIE_NAME, AUTH_COOKIE_MAX_AGE,
    GIT_ACTIONS, CHANGES_EVENT,
)

log = logging.getLogger("claudio.ws")

_clients: weakref.WeakSet[web.WebSocketResponse] = weakref.WeakSet()
_auth_token: str = ""
MAX_WS_CLIENTS = 20


def _generate_auth_token() -> str:
    """Generate a session token from the password."""
    if not DASHBOARD_PASSWORD:
        return ""
    return hashlib.sha256(f"{DASHBOARD_PASSWORD}:{secrets.token_hex(8)}".encode()).hexdigest()


def _verify_password(password: str) -> bool:
    return DASHBOARD_PASSWORD and password == DASHBOARD_PASSWORD


def _check_auth(request: web.Request) -> bool:
    """Check if request has a valid auth cookie."""
    if not DASHBOARD_PASSWORD:
        return True  # No password = no auth required
    cookie = request.cookies.get(AUTH_COOKIE_NAME, "")
    return cookie == _auth_token


# ── WebSocket ─────────────────────────────────────────────────────────

async def broadcast(event_type: str, data: dict) -> None:
    """Send an event to all connected WebSocket clients."""
    if not _clients:
        return

    message = json.dumps({"name": event_type, "data": data}, default=str)
    dead: list[web.WebSocketResponse] = []

    for ws in list(_clients):
        try:
            await ws.send_str(message)
        except (ConnectionError, RuntimeError):
            dead.append(ws)

    for ws in dead:
        _clients.discard(ws)


async def _ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle a new WebSocket connection."""
    if not _check_auth(request):
        return web.Response(status=401, text="Unauthorized")

    if len(_clients) >= MAX_WS_CLIENTS:
        return web.Response(status=503, text="Too many connections")

    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)
    _clients.add(ws)
    log.info(f"Dashboard connected ({len(_clients)} clients)")

    # Send history + changes on connect; abort if client already gone
    try:
        from bot.monitor import get_history
        history = get_history(limit=HISTORY_ON_CONNECT_LIMIT)
        await ws.send_str(json.dumps({"name": "history", "data": history}, default=str))

        from bot.git_ops import get_all_projects_changes
        all_changes = await get_all_projects_changes()
        for changes in all_changes:
            await ws.send_str(json.dumps({"name": CHANGES_EVENT, "data": changes}, default=str))
    except Exception as e:
        log.error(f"Failed to send initial data: {e}")
        _clients.discard(ws)
        return ws

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                await _handle_ws_message(msg.data)
    except (asyncio.CancelledError, ConnectionError):
        pass
    finally:
        _clients.discard(ws)
        log.info(f"Dashboard disconnected ({len(_clients)} clients)")

    return ws


async def _handle_ws_message(raw: str) -> None:
    """Handle incoming WebSocket messages (quick actions)."""
    try:
        data = json.loads(raw)
        action = data.get("action")

        if action == "message":
            text = data.get("text", "").strip()
            project = data.get("project")
            if text:
                asyncio.create_task(_execute_quick_action(text, project))

        elif action == "command":
            command = data.get("command", "")
            if command:
                asyncio.create_task(_execute_command(command))

        elif action == "git_refresh_all":
            asyncio.create_task(_refresh_all_changes())

        elif action in GIT_ACTIONS:
            asyncio.create_task(_execute_git_action(action, data))

    except (json.JSONDecodeError, Exception) as e:
        log.error(f"WS message error: {e}")


async def _execute_quick_action(text: str, project: str | None) -> None:
    """Execute a message from the dashboard as if it came from Telegram."""
    from bot.handlers._state import bridge
    from bot.projects import resolve_project

    project_path = None
    if project and project != "general":
        matches = resolve_project(project)
        if matches:
            project_path = matches[0].path
            project = matches[0].name

    try:
        await bridge.query(
            chat_id=0,  # Dashboard pseudo-chat
            prompt=text,
            project_name=project,
            project_path=project_path,
        )
    except Exception as e:
        from bot.monitor import emit
        await emit("error", {"module": "quick_action", "message": str(e)})


async def _execute_command(command: str) -> None:
    """Execute a slash command from the dashboard."""
    import os
    from bot.handlers._state import bridge

    if command == "new":
        bridge.reset_session(0, None)
    elif command in ("opus", "sonnet", "haiku"):
        from bot.config import MODEL_OPUS, MODEL_SONNET, MODEL_HAIKU
        models = {"opus": MODEL_OPUS, "sonnet": MODEL_SONNET, "haiku": MODEL_HAIKU}
        os.environ["CLAUDE_MODEL"] = models[command]
    elif command.startswith("effort:"):
        level = command.split(":")[1]
        if level in ("low", "medium", "high"):
            os.environ["CLAUDE_EFFORT"] = level


async def _refresh_all_changes() -> None:
    """Scan all projects and broadcast their git changes."""
    try:
        from bot.git_ops import get_all_projects_changes
        all_changes = await get_all_projects_changes()
        for changes in all_changes:
            await broadcast(CHANGES_EVENT, changes)
    except Exception as e:
        log.error(f"Failed to refresh all changes: {e}")


async def _execute_git_action(action: str, data: dict) -> None:
    """Execute a git action from the dashboard."""
    from bot.git_ops import (
        stage_file, unstage_file, revert_file,
        revert_all, commit, get_project_diff,
    )
    from bot.projects import resolve_project
    from bot.monitor import emit

    project_name = data.get("project", "")
    matches = resolve_project(project_name)
    if not matches:
        await emit("error", {"module": "git", "message": f"Project not found: {project_name}"})
        return

    project_path = matches[0].path

    try:
        file_path = data.get("file", "")

        if action == "git_stage":
            await stage_file(project_path, file_path)
        elif action == "git_unstage":
            await unstage_file(project_path, file_path)
        elif action == "git_revert":
            await revert_file(project_path, file_path)
        elif action == "git_revert_all":
            await revert_all(project_path)
        elif action == "git_commit":
            await commit(project_path, data.get("message", ""))
        elif action == "git_diff":
            pass  # just re-emit below

        # Re-emit updated diff
        diff = await get_project_diff(project_path)
        await emit(CHANGES_EVENT, diff or {
            "project": project_name, "summary": {"files": 0, "insertions": 0, "deletions": 0}, "files": []
        })
    except Exception as e:
        await emit("error", {"module": "git", "message": str(e)})


# ── HTTP Auth ─────────────────────────────────────────────────────────

async def _auth_handler(request: web.Request) -> web.Response:
    """Handle login POST request."""
    try:
        data = await request.json()
        password = data.get("password", "")
    except Exception:
        return web.json_response({"error": "Invalid request"}, status=400)

    if not _verify_password(password):
        return web.json_response({"error": "Password errata"}, status=401)

    response = web.json_response({"ok": True})
    response.set_cookie(
        AUTH_COOKIE_NAME, _auth_token,
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )
    return response


async def _check_auth_handler(request: web.Request) -> web.Response:
    """Check if the current session is authenticated."""
    if _check_auth(request):
        return web.json_response({"authenticated": True})
    return web.json_response({"authenticated": False}, status=401)


async def _kronos_handler(request: web.Request) -> web.Response:
    """Return Kronos prediction history + actual OHLCV + accuracy stats."""
    if not _check_auth(request):
        return web.Response(status=401, text="Unauthorized")

    try:
        from bot.kronos import get_accuracy_stats, fetch_ohlcv, _get_db
        import json as _json

        db = _get_db()
        rows = db.execute(
            "SELECT id, created_at, symbol, timeframe, current_price, predictions, "
            "verified, actual_prices, direction_correct, mae "
            "FROM predictions ORDER BY created_at DESC LIMIT 20"
        ).fetchall()

        predictions = []
        for row in rows:
            predictions.append({
                "id": row[0],
                "created_at": row[1],
                "symbol": row[2],
                "timeframe": row[3],
                "current_price": row[4],
                "predictions": _json.loads(row[5]),
                "verified": bool(row[6]),
                "actual_prices": _json.loads(row[7]) if row[7] else None,
                "direction_correct": row[8],
                "mae": row[9],
            })

        # Last 48h of actual BTC/USDT candles
        try:
            ohlcv = await fetch_ohlcv(limit=48)
            actual = [{"timestamp": c[0], "close": c[4]} for c in ohlcv]
        except Exception as e:
            log.warning(f"Kronos API: failed to fetch OHLCV: {e}")
            actual = []

        stats = get_accuracy_stats()

        return web.json_response({
            "predictions": predictions,
            "actual": actual,
            "stats": stats,
        })
    except Exception as e:
        log.error(f"Kronos API error: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


# ── Static files ──────────────────────────────────────────────────────

async def _index_handler(request: web.Request) -> web.FileResponse:
    return web.FileResponse(DASHBOARD_STATIC_DIR / "index.html")


# ── Server startup ────────────────────────────────────────────────────

async def start_server() -> None:
    """Start the dashboard HTTP + WebSocket server."""
    global _auth_token
    _auth_token = _generate_auth_token()

    app = web.Application()

    # API routes
    app.router.add_post("/api/auth", _auth_handler)
    app.router.add_get("/api/auth/check", _check_auth_handler)
    app.router.add_get("/api/kronos", _kronos_handler)
    app.router.add_get(WS_PATH, _ws_handler)

    # Static dashboard files
    if DASHBOARD_STATIC_DIR.exists():
        app.router.add_get("/", _index_handler)
        app.router.add_static("/_next", DASHBOARD_STATIC_DIR / "_next")
        app.router.add_static("/", DASHBOARD_STATIC_DIR)
        log.info(f"Serving dashboard from {DASHBOARD_STATIC_DIR}")
    else:
        log.warning(f"Dashboard directory not found: {DASHBOARD_STATIC_DIR}")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", DASHBOARD_PORT)
    await site.start()
    log.info(f"Dashboard server running on http://0.0.0.0:{DASHBOARD_PORT}")
    if DASHBOARD_PASSWORD:
        log.info("Dashboard authentication enabled")
