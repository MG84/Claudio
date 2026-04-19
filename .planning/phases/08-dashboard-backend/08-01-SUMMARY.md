---
phase: "08-dashboard-backend"
plan: "08-01"
subsystem: "dashboard-backend"
tags: ["cleanup", "events", "auth", "websocket"]
dependency_graph:
  requires: []
  provides: ["trade_executed events", "deterministic auth token"]
  affects: ["bot/trading.py", "bot/ws_server.py"]
tech_stack:
  added: []
  patterns: ["WebSocket event emission", "deterministic token generation"]
key_files:
  created: []
  modified:
    - "bot/trading.py"
    - "bot/ws_server.py"
decisions:
  - "Use asyncio.create_task for fire-and-forget event emission"
  - "Deterministic token via SHA256(claudio:password) instead of random secrets"
metrics:
  duration_seconds: 73
  completed_at: "2026-04-19T09:18:13Z"
  tasks_completed: 3
  files_modified: 2
---

# Phase 8 Plan 1: Cleanup + Events + Auth Fix Summary

Real-time trade events and persistent dashboard sessions via deterministic auth tokens.

## Completed Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Delete stale bot/static/ directory | 18c2bf2 | bot/static/ (deleted) |
| 2 | Emit trade_executed events from trading.py | be0e74d | bot/trading.py |
| 3 | Fix auth token to be deterministic | da78aa7 | bot/ws_server.py |

## What Was Built

### 1. Stale Assets Cleanup
- Deleted `bot/static/` directory containing 1.2MB of stale Next.js chunks from April 12
- Prevents conflicts with dashboard serving (Dockerfile copies `dashboard/` only)

### 2. Real-Time Trade Events
- Added `emit("trade_executed", ...)` in `place_order()` after SQLite commit
- Added `emit("trade_executed", ...)` in `close_position()` after SQLite commit
- Events include: trade_id, pair, side, volume, price, mode, action (opened/closed)
- Paper and live modes both emit events
- Fire-and-forget via `asyncio.create_task()` to avoid blocking trade execution

### 3. Deterministic Auth Token
- Replaced `secrets.token_hex(8)` (random) with `hashlib.sha256(f"claudio:{DASHBOARD_PASSWORD}")`
- Same password always produces same token
- Dashboard session cookies survive bot restarts without re-login
- Removed unused `secrets` import

## Deviations from Plan

None - plan executed exactly as written.

## Technical Decisions

**Event emission timing**: Events are emitted immediately after SQLite commit to ensure data consistency. Using `asyncio.create_task()` makes emission non-blocking.

**Token salt**: Using "claudio:" prefix in deterministic hash provides namespace isolation while keeping implementation simple.

## Known Stubs

None - all functionality is fully wired.

## Self-Check: PASSED

### Created Files
(none - only deletions and modifications)

### Modified Files
- bot/trading.py: FOUND
- bot/ws_server.py: FOUND

### Commits
- 18c2bf2: FOUND
- be0e74d: FOUND
- da78aa7: FOUND
