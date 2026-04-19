"""
Trading execution layer with hard-coded risk limits.
Safety principle: limits in CODE, not in prompt.

Paper mode: simulated locally in SQLite (default).
Live mode: real orders via ccxt (requires EXCHANGE_API_KEY + EXCHANGE_API_SECRET).

Architecture:
    Claude says: "buy 50% of portfolio"
        ↓
    trading.py: risk_check() → DENIED (max 20% per position)
        ↓
    Claude receives: "Trade rejected: exceeds max position size (20%)"
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone

import ccxt.async_support as ccxt_async

from bot.config import (
    TRADING_ENABLED, TRADING_MODE,
    MAX_POSITION_PCT, MAX_OPEN_POSITIONS, MAX_DAILY_LOSS_PCT,
    MAX_DRAWDOWN_PCT, STOP_LOSS_REQUIRED, MAX_TRADES_PER_DAY,
    TRADES_DB_PATH, MEMORY_DIR,
    EXCHANGE_ID, EXCHANGE_API_KEY, EXCHANGE_API_SECRET,
)
from bot.monitor import emit

log = logging.getLogger("claudio.trading")

_db: sqlite3.Connection | None = None
_mode: str = TRADING_MODE
_autonomous: bool = False
_INITIAL_BALANCE: float = 10_000.0
_live_exchange: ccxt_async.Exchange | None = None


def _get_live_exchange() -> ccxt_async.Exchange:
    """Get or create the exchange instance for live trading."""
    global _live_exchange
    if _live_exchange is not None:
        return _live_exchange
    if not EXCHANGE_API_KEY or not EXCHANGE_API_SECRET:
        raise RuntimeError("EXCHANGE_API_KEY e EXCHANGE_API_SECRET necessarie per live trading")
    exchange_class = getattr(ccxt_async, EXCHANGE_ID, None)
    if exchange_class is None:
        raise RuntimeError(f"Exchange '{EXCHANGE_ID}' non supportato da ccxt")
    _live_exchange = exchange_class({
        "apiKey": EXCHANGE_API_KEY,
        "secret": EXCHANGE_API_SECRET,
        "enableRateLimit": True,
    })
    log.info(f"Live exchange initialized: {EXCHANGE_ID}")
    return _live_exchange


# ── SQLite ────────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    global _db
    if _db is not None:
        return _db

    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _db = sqlite3.connect(str(TRADES_DB_PATH))
    _db.execute("PRAGMA journal_mode=WAL")
    _db.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            pair TEXT NOT NULL,
            side TEXT NOT NULL,
            type TEXT NOT NULL,
            volume REAL NOT NULL,
            price REAL NOT NULL,
            stop_loss REAL,
            take_profit REAL,
            status TEXT NOT NULL DEFAULT 'open',
            close_price REAL,
            closed_at TEXT,
            pnl_usd REAL,
            reasoning TEXT,
            mode TEXT NOT NULL DEFAULT 'paper'
        );
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            balance_usd REAL NOT NULL,
            initial_balance REAL NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
        CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(pair);
    """)
    # Initialize portfolio if empty
    if not _db.execute("SELECT 1 FROM portfolio LIMIT 1").fetchone():
        now = datetime.now(timezone.utc).isoformat()
        _db.execute(
            "INSERT INTO portfolio (id, balance_usd, initial_balance, updated_at) "
            "VALUES (1, ?, ?, ?)",
            (_INITIAL_BALANCE, _INITIAL_BALANCE, now),
        )
    _db.commit()
    log.info(f"Trades DB initialized at {TRADES_DB_PATH}")
    return _db


# ── Init ──────────────────────────────────────────────────────────────

def init():
    """Initialize trading module."""
    if not TRADING_ENABLED:
        log.info("Trading disabled (TRADING_ENABLED=false)")
        return
    _get_db()
    log.info(f"Trading initialized — mode: {_mode}, autonomous: {_autonomous}")


def is_ready() -> bool:
    return _db is not None and TRADING_ENABLED


# ── Mode control ─────────────────────────────────────────────────────

def get_mode() -> str:
    return _mode


def set_mode(mode: str) -> str:
    global _mode
    if mode not in ("paper", "live"):
        return f"Modalita' non valida: {mode}. Usa 'paper' o 'live'."
    if mode == "live" and (not EXCHANGE_API_KEY or not EXCHANGE_API_SECRET):
        return "Impossibile attivare live: EXCHANGE_API_KEY e EXCHANGE_API_SECRET non configurate."
    _mode = mode
    log.info(f"Trading mode: {mode}")
    return f"Modalita' trading: {mode}"


def is_autonomous() -> bool:
    return _autonomous


def set_autonomous(enabled: bool) -> str:
    global _autonomous
    _autonomous = enabled
    log.info(f"Autonomous trading: {'enabled' if enabled else 'disabled'}")
    return f"Trading autonomo: {'attivo' if enabled else 'disattivo'}"


# ── Risk checks (hard-coded, non-bypassable) ─────────────────────────

def risk_check(side: str, pair: str, volume: float,
               price: float, stop_loss: float | None = None) -> dict:
    """Run all risk checks BEFORE executing a trade.
    Returns {ok: bool, reason: str}."""
    db = _get_db()

    # 1. Stop-loss required
    if STOP_LOSS_REQUIRED and stop_loss is None:
        return {"ok": False, "reason": "Stop-loss obbligatorio per ogni trade"}

    # 2. Max position size (% of portfolio)
    balance = _get_balance_usd(db)
    position_value = volume * price
    position_pct = position_value / balance if balance > 0 else 1.0
    if position_pct > MAX_POSITION_PCT:
        return {
            "ok": False,
            "reason": (
                f"Posizione troppo grande: {position_pct:.0%} del portfolio "
                f"(max {MAX_POSITION_PCT:.0%})"
            ),
        }

    # 3. Max open positions
    open_count = db.execute(
        "SELECT COUNT(*) FROM trades WHERE status = 'open'"
    ).fetchone()[0]
    if open_count >= MAX_OPEN_POSITIONS:
        return {
            "ok": False,
            "reason": f"Troppe posizioni aperte: {open_count}/{MAX_OPEN_POSITIONS}",
        }

    # 4. Max trades per day
    today_start = _today_start_iso()
    today_trades = db.execute(
        "SELECT COUNT(*) FROM trades WHERE created_at >= ?", (today_start,)
    ).fetchone()[0]
    if today_trades >= MAX_TRADES_PER_DAY:
        return {
            "ok": False,
            "reason": f"Limite trade giornalieri: {today_trades}/{MAX_TRADES_PER_DAY}",
        }

    # 5. Max daily loss
    daily_pnl = _compute_daily_pnl(db)
    daily_loss_pct = abs(min(daily_pnl, 0)) / balance if balance > 0 else 0
    if daily_loss_pct >= MAX_DAILY_LOSS_PCT:
        return {
            "ok": False,
            "reason": (
                f"Limite perdita giornaliera: {daily_loss_pct:.1%} "
                f"(max {MAX_DAILY_LOSS_PCT:.0%})"
            ),
        }

    # 6. Max drawdown → kill switch
    initial = _get_initial_balance(db)
    drawdown = (initial - balance) / initial if initial > 0 else 0
    if drawdown >= MAX_DRAWDOWN_PCT:
        return {
            "ok": False,
            "reason": (
                f"Drawdown massimo raggiunto: {drawdown:.1%} "
                f"(max {MAX_DRAWDOWN_PCT:.0%}). Trading sospeso."
            ),
        }

    return {"ok": True, "reason": ""}


# ── Trade execution ──────────────────────────────────────────────────

async def place_order(side: str, pair: str, order_type: str, volume: float,
                      price: float | None = None, stop_loss: float | None = None,
                      take_profit: float | None = None) -> dict:
    """Execute a trade: risk_check → log → execute → log result.

    Paper mode: simulated in SQLite.
    Live mode: real orders via ccxt exchange.
    """
    if not TRADING_ENABLED:
        return {"ok": False, "error": "Trading non abilitato"}

    # Get current price for market orders
    if price is None:
        from bot.market import get_ticker
        try:
            ticker = await get_ticker(pair)
            price = ticker["last"]
        except Exception as e:
            return {"ok": False, "error": f"Impossibile ottenere prezzo per {pair}: {e}"}

    # Risk check — BEFORE every trade, non-bypassable
    check = risk_check(side, pair, volume, price, stop_loss)
    if not check["ok"]:
        log.warning(f"Trade rejected: {check['reason']}")
        return {"ok": False, "error": check["reason"]}

    db = _get_db()
    now = datetime.now(timezone.utc).isoformat()
    position_cost = volume * price

    # ── Live mode — real orders via ccxt ──────────────────────────────
    if _mode == "live":
        try:
            exchange = _get_live_exchange()
            params = {}
            if stop_loss:
                params["stopLoss"] = {"triggerPrice": stop_loss}
            if take_profit:
                params["takeProfit"] = {"triggerPrice": take_profit}
            order = await exchange.create_order(
                symbol=pair, type=order_type, side=side,
                amount=volume, price=price if order_type == "limit" else None,
                params=params if params else None,
            )
            exchange_order_id = order.get("id", "unknown")
            fill_price = order.get("average") or order.get("price") or price
            log.info(f"LIVE trade: {side} {volume} {pair} @ ${fill_price:,.2f} (order {exchange_order_id})")
        except Exception as e:
            log.error(f"Live order failed: {e}")
            return {"ok": False, "error": f"Exchange error: {e}"}

        # Log to SQLite for tracking
        cursor = db.execute(
            "INSERT INTO trades "
            "(created_at, pair, side, type, volume, price, stop_loss, take_profit, status, mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', 'live')",
            (now, pair, side, order_type, volume, fill_price, stop_loss, take_profit),
        )
        trade_id = cursor.lastrowid
        db.commit()
        return {"ok": True, "trade_id": trade_id, "mode": "live", "price": fill_price,
                "exchange_order_id": exchange_order_id}

    # ── Paper mode — simulate locally ────────────────────────────────
    if side == "buy":
        balance = _get_balance_usd(db)
        if position_cost > balance:
            return {
                "ok": False,
                "error": f"Fondi insufficienti: ${position_cost:,.2f} > ${balance:,.2f}",
            }
        db.execute(
            "UPDATE portfolio SET balance_usd = balance_usd - ?, updated_at = ? WHERE id = 1",
            (position_cost, now),
        )

    cursor = db.execute(
        "INSERT INTO trades "
        "(created_at, pair, side, type, volume, price, stop_loss, take_profit, status, mode) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', 'paper')",
        (now, pair, side, order_type, volume, price, stop_loss, take_profit),
    )
    trade_id = cursor.lastrowid
    db.commit()

    asyncio.create_task(emit("trade_executed", {
        "trade_id": trade_id, "pair": pair, "side": side,
        "volume": volume, "price": price, "mode": "paper",
        "stop_loss": stop_loss, "take_profit": take_profit,
        "action": "opened",
    }))

    log.info(f"Paper trade #{trade_id}: {side} {volume} {pair} @ ${price:,.2f}")
    return {"ok": True, "trade_id": trade_id, "mode": "paper", "price": price}


async def close_position(trade_id: int, close_price: float | None = None) -> dict:
    """Close an open position and realize P&L.

    Paper mode: update SQLite balance.
    Live mode: sell on exchange via ccxt, then log to SQLite.
    """
    db = _get_db()
    row = db.execute(
        "SELECT pair, side, volume, price, status, mode FROM trades WHERE id = ?",
        (trade_id,),
    ).fetchone()

    if not row:
        return {"ok": False, "error": f"Trade #{trade_id} non trovato"}

    pair, side, volume, entry_price, status, trade_mode = row
    if status != "open":
        return {"ok": False, "error": f"Trade #{trade_id} gia' chiuso"}

    # ── Live mode — close on exchange ─────────────────────────────────
    if trade_mode == "live":
        try:
            exchange = _get_live_exchange()
            close_side = "sell" if side == "buy" else "buy"
            order = await exchange.create_order(
                symbol=pair, type="market", side=close_side, amount=volume,
            )
            close_price = order.get("average") or order.get("price")
            if close_price is None:
                from bot.market import get_ticker
                ticker = await get_ticker(pair)
                close_price = ticker["last"]
            log.info(f"LIVE close trade #{trade_id}: {close_side} {volume} {pair} @ ${close_price:,.2f}")
        except Exception as e:
            log.error(f"Live close failed for trade #{trade_id}: {e}")
            return {"ok": False, "error": f"Exchange error: {e}"}

        # P&L calculation
        if side == "buy":
            pnl = (close_price - entry_price) * volume
        else:
            pnl = (entry_price - close_price) * volume

        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "UPDATE trades SET status = 'closed', close_price = ?, closed_at = ?, pnl_usd = ? "
            "WHERE id = ?",
            (close_price, now, round(pnl, 2), trade_id),
        )
        db.commit()
        log.info(f"Closed live trade #{trade_id}: P&L ${pnl:,.2f}")
        return {"ok": True, "trade_id": trade_id, "pnl_usd": round(pnl, 2), "mode": "live"}

    # ── Paper mode — simulate locally ─────────────────────────────────
    if close_price is None:
        from bot.market import get_ticker
        try:
            ticker = await get_ticker(pair)
            close_price = ticker["last"]
        except Exception as e:
            return {"ok": False, "error": f"Impossibile ottenere prezzo: {e}"}

    # P&L calculation
    if side == "buy":
        pnl = (close_price - entry_price) * volume
        returned = volume * close_price
    else:
        pnl = (entry_price - close_price) * volume
        returned = volume * entry_price + pnl

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE portfolio SET balance_usd = balance_usd + ?, updated_at = ? WHERE id = 1",
        (returned, now),
    )
    db.execute(
        "UPDATE trades SET status = 'closed', close_price = ?, closed_at = ?, pnl_usd = ? "
        "WHERE id = ?",
        (close_price, now, round(pnl, 2), trade_id),
    )
    db.commit()

    asyncio.create_task(emit("trade_executed", {
        "trade_id": trade_id, "pair": pair, "side": side,
        "volume": volume, "close_price": close_price,
        "pnl_usd": round(pnl, 2), "mode": "paper",
        "action": "closed",
    }))

    log.info(f"Closed trade #{trade_id}: P&L ${pnl:,.2f}")
    return {"ok": True, "trade_id": trade_id, "pnl_usd": round(pnl, 2), "mode": "paper"}


async def cancel_order(trade_id: int) -> dict:
    """Cancel an open order and return funds.

    Paper mode: refund balance in SQLite.
    Live mode: cancel on exchange via ccxt, then update SQLite.
    """
    db = _get_db()
    row = db.execute(
        "SELECT side, volume, price, status, mode FROM trades WHERE id = ?",
        (trade_id,),
    ).fetchone()

    if not row:
        return {"ok": False, "error": f"Trade #{trade_id} non trovato"}

    side, volume, price, status, trade_mode = row
    if status != "open":
        return {"ok": False, "error": f"Trade #{trade_id} non e' aperto"}

    now = datetime.now(timezone.utc).isoformat()

    # Live mode — note: ccxt cancel requires exchange order ID, which we don't store yet.
    # For now, just close the position via market order (same as close_position).
    if trade_mode == "live":
        return await close_position(trade_id)

    # Paper mode — refund balance
    if side == "buy":
        db.execute(
            "UPDATE portfolio SET balance_usd = balance_usd + ?, updated_at = ? WHERE id = 1",
            (volume * price, now),
        )
    db.execute(
        "UPDATE trades SET status = 'cancelled', closed_at = ? WHERE id = ?",
        (now, trade_id),
    )
    db.commit()
    return {"ok": True, "trade_id": trade_id}


async def emergency_close_all() -> dict:
    """Kill switch — close all open positions immediately."""
    db = _get_db()
    open_trades = db.execute(
        "SELECT id FROM trades WHERE status = 'open'"
    ).fetchall()

    results = []
    for (trade_id,) in open_trades:
        result = await close_position(trade_id)
        results.append(result)

    closed = sum(1 for r in results if r.get("ok"))
    total_pnl = sum(r.get("pnl_usd", 0) for r in results if r.get("ok"))

    log.warning(f"EMERGENCY CLOSE: {closed} positions closed, total P&L: ${total_pnl:,.2f}")
    return {"closed": closed, "total_pnl": round(total_pnl, 2), "results": results}


def log_trade_rationale(trade_id: int, reasoning: str) -> bool:
    """Save Claude's reasoning for a trade decision."""
    db = _get_db()
    db.execute("UPDATE trades SET reasoning = ? WHERE id = ?", (reasoning, trade_id))
    db.commit()
    return True


# ── Portfolio queries ────────────────────────────────────────────────

def get_balance() -> dict:
    """Current portfolio balance."""
    db = _get_db()
    row = db.execute(
        "SELECT balance_usd, initial_balance, updated_at FROM portfolio WHERE id = 1"
    ).fetchone()
    if not row:
        return {"balance_usd": 0, "initial_balance": 0}
    return {
        "balance_usd": round(row[0], 2),
        "initial_balance": round(row[1], 2),
        "updated_at": row[2],
        "mode": _mode,
    }


def get_positions() -> list[dict]:
    """Open positions."""
    db = _get_db()
    rows = db.execute(
        "SELECT id, created_at, pair, side, volume, price, stop_loss, take_profit "
        "FROM trades WHERE status = 'open' ORDER BY created_at DESC"
    ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "pair": r[2], "side": r[3],
            "volume": r[4], "entry_price": r[5], "stop_loss": r[6], "take_profit": r[7],
        }
        for r in rows
    ]


def get_trade_history(limit: int = 10) -> list[dict]:
    """Recent trades (all statuses)."""
    db = _get_db()
    rows = db.execute(
        "SELECT id, created_at, pair, side, type, volume, price, stop_loss, "
        "take_profit, status, close_price, closed_at, pnl_usd, reasoning, mode "
        "FROM trades ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r[0], "created_at": r[1], "pair": r[2], "side": r[3],
            "type": r[4], "volume": r[5], "price": r[6], "stop_loss": r[7],
            "take_profit": r[8], "status": r[9], "close_price": r[10],
            "closed_at": r[11], "pnl_usd": r[12], "reasoning": r[13], "mode": r[14],
        }
        for r in rows
    ]


def get_daily_pnl() -> dict:
    """P&L for today."""
    db = _get_db()
    pnl = _compute_daily_pnl(db)
    balance = _get_balance_usd(db)
    initial = _get_initial_balance(db)
    today_trades = db.execute(
        "SELECT COUNT(*) FROM trades WHERE created_at >= ?", (_today_start_iso(),)
    ).fetchone()[0]
    return {
        "pnl_usd": round(pnl, 2),
        "pnl_pct": round(pnl / initial * 100, 2) if initial > 0 else 0,
        "trades_today": today_trades,
        "balance_usd": round(balance, 2),
    }


def get_risk_status() -> dict:
    """Current risk metrics vs limits."""
    db = _get_db()
    balance = _get_balance_usd(db)
    initial = _get_initial_balance(db)
    daily_pnl = _compute_daily_pnl(db)

    drawdown = (initial - balance) / initial if initial > 0 else 0
    daily_loss = abs(min(daily_pnl, 0)) / balance if balance > 0 else 0

    today_trades = db.execute(
        "SELECT COUNT(*) FROM trades WHERE created_at >= ?", (_today_start_iso(),)
    ).fetchone()[0]
    open_positions = db.execute(
        "SELECT COUNT(*) FROM trades WHERE status = 'open'"
    ).fetchone()[0]

    return {
        "daily_loss_pct": round(daily_loss * 100, 2),
        "max_daily_loss_pct": MAX_DAILY_LOSS_PCT * 100,
        "drawdown_pct": round(drawdown * 100, 2),
        "max_drawdown_pct": MAX_DRAWDOWN_PCT * 100,
        "trades_today": today_trades,
        "max_trades_per_day": MAX_TRADES_PER_DAY,
        "open_positions": open_positions,
        "max_open_positions": MAX_OPEN_POSITIONS,
        "autonomous": _autonomous,
        "trading_active": daily_loss < MAX_DAILY_LOSS_PCT and drawdown < MAX_DRAWDOWN_PCT,
    }


# ── Internal helpers ─────────────────────────────────────────────────

def _get_balance_usd(db: sqlite3.Connection) -> float:
    row = db.execute("SELECT balance_usd FROM portfolio WHERE id = 1").fetchone()
    return row[0] if row else 0.0


def _get_initial_balance(db: sqlite3.Connection) -> float:
    row = db.execute("SELECT initial_balance FROM portfolio WHERE id = 1").fetchone()
    return row[0] if row else 0.0


def _compute_daily_pnl(db: sqlite3.Connection) -> float:
    row = db.execute(
        "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades "
        "WHERE status = 'closed' AND closed_at >= ?",
        (_today_start_iso(),),
    ).fetchone()
    return row[0] if row else 0.0


def _today_start_iso() -> str:
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
