"""
Trading commands: /portfolio, /market, /trades, /mode, /kill, /autonomous, /scan
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.auth import is_allowed_user
from bot.config import TRADING_ENABLED, KRONOS_ENABLED, CHRONOS_ENABLED

router = Router()

_DISABLED_MSG = "Trading non abilitato."


# ── /portfolio ────────────────────────────────────────────────────────

@router.message(Command("portfolio"))
async def cmd_portfolio(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    if not TRADING_ENABLED:
        await message.reply(_DISABLED_MSG)
        return

    from bot.trading import is_ready, get_balance, get_positions, get_daily_pnl

    if not is_ready():
        await message.reply("Trading module not ready.")
        return

    bal = get_balance()
    positions = get_positions()
    daily = get_daily_pnl()

    lines = [
        f"Portfolio ({bal['mode']})",
        f"Bilancio: ${bal['balance_usd']:,.2f}",
        f"Iniziale: ${bal['initial_balance']:,.2f}",
        f"P&L oggi: ${daily['pnl_usd']:+,.2f} ({daily['pnl_pct']:+.2f}%)",
        f"Trade oggi: {daily['trades_today']}",
    ]

    if positions:
        lines.append(f"\nPosizioni aperte ({len(positions)}):")
        for p in positions:
            sl = f" SL ${p['stop_loss']:,.2f}" if p.get('stop_loss') else ""
            lines.append(
                f"  {p['side'].upper()} {p['volume']} {p['pair']} "
                f"@ ${p['entry_price']:,.2f}{sl}"
            )
    else:
        lines.append("\nNessuna posizione aperta.")

    await message.reply("\n".join(lines))


# ── /market ───────────────────────────────────────────────────────────

@router.message(Command("market"))
async def cmd_market(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    if not TRADING_ENABLED:
        await message.reply(_DISABLED_MSG)
        return

    args = message.text.split()
    pair = args[1].upper() if len(args) > 1 else "BTC/USDT"
    if "/" not in pair:
        pair = pair + "/USDT"

    from bot.market import get_market_summary

    try:
        summary = await get_market_summary([pair])
    except Exception as e:
        await message.reply(f"Errore market data: {e}")
        return

    lines = [summary]

    # Append latest predictions if available
    if KRONOS_ENABLED:
        from bot.kronos import get_latest_prediction
        pred = get_latest_prediction(pair)
        if pred:
            p = pred["predictions"][-1]
            pct = (p["close"] - pred["current_price"]) / pred["current_price"] * 100
            lines.append(f"\nKronos: ${p['close']:,.0f} ({pct:+.2f}%) — {pred['created_at'][:16]}")

    if CHRONOS_ENABLED:
        try:
            from bot.chronos_predictor import get_latest_prediction as chronos_latest
            cpred = chronos_latest(pair)
            if cpred:
                lines.append(
                    f"Chronos: {cpred['direction']} {cpred['change_pct']:+.2f}% — "
                    f"{cpred['created_at'][:16]}"
                )
        except Exception:
            pass

    await message.reply("\n".join(lines))


# ── /trades ───────────────────────────────────────────────────────────

@router.message(Command("trades"))
async def cmd_trades(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    if not TRADING_ENABLED:
        await message.reply(_DISABLED_MSG)
        return

    from bot.trading import is_ready, get_trade_history

    if not is_ready():
        await message.reply("Trading module not ready.")
        return

    args = message.text.split()
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10

    trades = get_trade_history(limit)
    if not trades:
        await message.reply("Nessun trade registrato.")
        return

    lines = [f"Ultimi {len(trades)} trade:"]
    for t in trades:
        pnl = f" P&L ${t['pnl_usd']:+,.2f}" if t.get("pnl_usd") is not None else ""
        lines.append(
            f"  #{t['id']} {t['side'].upper()} {t['volume']} {t['pair']} "
            f"@ ${t['price']:,.2f} [{t['status']}]{pnl}"
        )

    await message.reply("\n".join(lines))


# ── /mode ─────────────────────────────────────────────────────────────

_pending_live_confirm: set[tuple[int, int | None]] = set()


@router.message(Command("mode"))
async def cmd_mode(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    if not TRADING_ENABLED:
        await message.reply(_DISABLED_MSG)
        return

    from bot.trading import get_mode, set_mode

    args = message.text.split()
    if len(args) < 2:
        await message.reply(f"Modalita' attuale: {get_mode()}")
        return

    mode = args[1].lower()
    if mode == "live":
        key = (message.chat.id, message.message_thread_id)
        _pending_live_confirm.add(key)
        await message.reply(
            "Stai per attivare il trading LIVE con soldi veri.\n"
            "Scrivi CONFERMA per procedere."
        )
        return

    result = set_mode(mode)
    await message.reply(result)


@router.message(lambda m: m.text and m.text.strip() == "CONFERMA")
async def confirm_live(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return

    key = (message.chat.id, message.message_thread_id)
    if key not in _pending_live_confirm:
        return

    _pending_live_confirm.discard(key)

    from bot.trading import set_mode
    result = set_mode("live")
    await message.reply(f"LIVE MODE ATTIVATO.\n{result}")


# ── /kill ─────────────────────────────────────────────────────────────

@router.message(Command("kill"))
async def cmd_kill(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    if not TRADING_ENABLED:
        await message.reply(_DISABLED_MSG)
        return

    from bot.trading import is_ready, emergency_close_all

    if not is_ready():
        await message.reply("Trading module not ready.")
        return

    result = await emergency_close_all()
    await message.reply(
        f"KILL SWITCH: {result['closed']} posizioni chiuse.\n"
        f"P&L totale: ${result['total_pnl']:+,.2f}"
    )


# ── /autonomous ──────────────────────────────────────────────────────

@router.message(Command("autonomous"))
async def cmd_autonomous(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    if not TRADING_ENABLED:
        await message.reply(_DISABLED_MSG)
        return

    from bot.trading import is_autonomous, set_autonomous

    args = message.text.split()
    if len(args) < 2:
        status = "attivo" if is_autonomous() else "disattivo"
        await message.reply(f"Trading autonomo: {status}")
        return

    enabled = args[1].lower() in ("on", "true", "1", "si")
    result = set_autonomous(enabled)
    await message.reply(result)


# ── /scan ─────────────────────────────────────────────────────────────

@router.message(Command("scan"))
async def cmd_scan(message: Message) -> None:
    if not is_allowed_user(message.from_user.id):
        return
    if not TRADING_ENABLED:
        await message.reply(_DISABLED_MSG)
        return

    from bot.config import TRADING_PAIRS
    from bot.market import get_market_summary
    from bot.trading import get_risk_status, get_positions

    await message.reply("Scanning mercato...")

    parts = []

    # Market data
    try:
        summary = await get_market_summary(TRADING_PAIRS)
        parts.append(summary)
    except Exception as e:
        parts.append(f"Market data error: {e}")

    # Kronos predictions
    if KRONOS_ENABLED:
        from bot.kronos import get_latest_prediction, get_prediction_confidence
        for pair in TRADING_PAIRS:
            pred = get_latest_prediction(pair)
            if pred:
                p = pred["predictions"][-1]
                pct = (p["close"] - pred["current_price"]) / pred["current_price"] * 100
                conf = get_prediction_confidence(pair)
                parts.append(
                    f"Kronos {pair}: ${p['close']:,.0f} ({pct:+.2f}%) "
                    f"confidence {conf['confidence']:.0%}"
                )

    # Chronos predictions
    if CHRONOS_ENABLED:
        try:
            from bot.chronos_predictor import get_latest_prediction as chronos_latest
            for pair in TRADING_PAIRS:
                cpred = chronos_latest(pair)
                if cpred:
                    parts.append(
                        f"Chronos {pair}: {cpred['direction']} {cpred['change_pct']:+.2f}%"
                    )
        except Exception:
            pass

    # Risk status
    try:
        risk = get_risk_status()
        parts.append(
            f"\nRisk: daily loss {risk['daily_loss_pct']:.1f}%/{risk['max_daily_loss_pct']:.0f}% | "
            f"drawdown {risk['drawdown_pct']:.1f}%/{risk['max_drawdown_pct']:.0f}% | "
            f"trades {risk['trades_today']}/{risk['max_trades_per_day']} | "
            f"positions {risk['open_positions']}/{risk['max_open_positions']}"
        )
    except Exception:
        pass

    # Positions
    positions = get_positions()
    if positions:
        parts.append(f"\nPosizioni aperte: {len(positions)}")
        for p in positions:
            parts.append(f"  {p['side'].upper()} {p['volume']} {p['pair']} @ ${p['entry_price']:,.2f}")

    await message.reply("\n".join(parts))
