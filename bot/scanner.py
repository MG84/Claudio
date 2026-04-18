"""
Market Scanner + Risk Monitor — background loops for autonomous analysis.

Scanner: assembles market context (indicators, predictions, portfolio) every hour.
Risk Monitor: enforces hard limits every 5 minutes (stop-loss, drawdown, daily loss).
"""

import asyncio
import logging
import os

from aiogram import Bot

from bot.config import (
    TRADING_ENABLED, TRADING_PAIRS, KRONOS_ENABLED, CHRONOS_ENABLED,
    MAX_DAILY_LOSS_PCT, MAX_DRAWDOWN_PCT,
)

log = logging.getLogger("claudio.scanner")

_SCANNER_INTERVAL = 3600      # 1 hour
_RISK_MONITOR_INTERVAL = 300  # 5 minutes
_RISK_WARN_THRESHOLD = 0.80   # warn at 80% of limit


def _get_notify_chat_id() -> int | None:
    """Get the first allowed user ID for notifications (private chat = user_id)."""
    allowed = os.getenv("TELEGRAM_ALLOWED_USERS", "")
    if not allowed:
        return None
    try:
        return int(allowed.split(",")[0].strip())
    except (ValueError, IndexError):
        return None


# ── Market Scanner ───────────────────────────────────────────────────

async def market_scanner_loop(bot: Bot) -> None:
    """Hourly market scan: assemble context, send brief to Telegram."""
    if not TRADING_ENABLED:
        return

    from bot.kronos import is_ready as kronos_ready
    from bot.chronos_predictor import is_ready as chronos_ready

    # Wait for prediction models
    log.info("Market scanner waiting for prediction models...")
    while True:
        kr = not KRONOS_ENABLED or kronos_ready()
        cr = not CHRONOS_ENABLED or chronos_ready()
        if kr and cr:
            break
        await asyncio.sleep(10)

    # Wait one full cycle so predictions exist
    await asyncio.sleep(60)

    chat_id = _get_notify_chat_id()
    if not chat_id:
        log.warning("No notify chat ID configured, scanner will only emit events")

    log.info(f"Market scanner started — pairs: {TRADING_PAIRS}")

    while True:
        try:
            brief = await _build_market_brief()
            if brief and chat_id:
                await bot.send_message(chat_id, brief)

            from bot.monitor import emit
            await emit("market_scan", {"pairs": TRADING_PAIRS})

        except Exception as e:
            log.error(f"Scanner error: {e}")

        await asyncio.sleep(_SCANNER_INTERVAL)


async def _build_market_brief() -> str | None:
    """Assemble market context from all available sources."""
    parts = []

    # Market indicators
    try:
        from bot.market import get_market_summary
        summary = await get_market_summary(TRADING_PAIRS)
        parts.append(summary)
    except Exception as e:
        log.warning(f"Market data unavailable: {e}")

    # Kronos predictions
    if KRONOS_ENABLED:
        try:
            from bot.kronos import get_latest_prediction, get_prediction_confidence
            for pair in TRADING_PAIRS:
                pred = get_latest_prediction(pair)
                if pred:
                    p = pred["predictions"][-1]
                    pct = (p["close"] - pred["current_price"]) / pred["current_price"] * 100
                    conf = get_prediction_confidence(pair)
                    parts.append(
                        f"Kronos {pair}: ${p['close']:,.0f} ({pct:+.2f}%) "
                        f"conf {conf['confidence']:.0%}"
                    )
        except Exception as e:
            log.warning(f"Kronos data unavailable: {e}")

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
        except Exception as e:
            log.warning(f"Chronos data unavailable: {e}")

    # Signal concordance
    if KRONOS_ENABLED and CHRONOS_ENABLED:
        try:
            from bot.kronos import get_latest_prediction
            from bot.chronos_predictor import get_latest_prediction as chronos_latest
            for pair in TRADING_PAIRS:
                kp = get_latest_prediction(pair)
                cp = chronos_latest(pair)
                if kp and cp:
                    k_dir = "UP" if kp["predictions"][-1]["close"] > kp["current_price"] else "DOWN"
                    c_dir = cp["direction"]
                    if k_dir == c_dir:
                        parts.append(f"Segnali {pair}: CONCORDI ({k_dir})")
                    else:
                        parts.append(f"Segnali {pair}: DISCORDI (K:{k_dir} C:{c_dir}) — cautela")
        except Exception:
            pass

    # Portfolio state
    try:
        from bot.trading import get_balance, get_positions, get_risk_status
        bal = get_balance()
        positions = get_positions()
        risk = get_risk_status()

        parts.append(
            f"\nPortfolio: ${bal['balance_usd']:,.2f} ({bal['mode']}) | "
            f"Posizioni: {len(positions)} | "
            f"Daily loss: {risk['daily_loss_pct']:.1f}%/{risk['max_daily_loss_pct']:.0f}%"
        )
    except Exception:
        pass

    if not parts:
        return None

    return "Market Scan\n" + "\n".join(parts)


# ── Risk Monitor ─────────────────────────────────────────────────────

async def risk_monitor_loop(bot: Bot) -> None:
    """Every 5 minutes: check risk limits, enforce stop-loss, emit events."""
    if not TRADING_ENABLED:
        return

    from bot.trading import is_ready
    while not is_ready():
        await asyncio.sleep(5)

    chat_id = _get_notify_chat_id()
    log.info("Risk monitor started")

    while True:
        try:
            await _check_risk(bot, chat_id)
        except Exception as e:
            log.error(f"Risk monitor error: {e}")

        await asyncio.sleep(_RISK_MONITOR_INTERVAL)


async def _check_risk(bot: Bot, chat_id: int | None) -> None:
    """Run all risk checks and take action if limits breached."""
    from bot.trading import get_risk_status, emergency_close_all, set_autonomous
    from bot.monitor import emit

    risk = get_risk_status()

    # Emit portfolio update
    await emit("portfolio_update", risk)

    # Check drawdown → kill switch
    drawdown_ratio = risk["drawdown_pct"] / risk["max_drawdown_pct"] if risk["max_drawdown_pct"] > 0 else 0
    if drawdown_ratio >= 1.0:
        log.warning("DRAWDOWN LIMIT BREACHED — emergency close all")
        result = await emergency_close_all()
        set_autonomous(False)
        msg = (
            f"RISK ALERT: Drawdown {risk['drawdown_pct']:.1f}% ha superato "
            f"il limite {risk['max_drawdown_pct']:.0f}%.\n"
            f"Posizioni chiuse: {result['closed']}. Trading autonomo disattivato."
        )
        if chat_id:
            await bot.send_message(chat_id, msg)
        await emit("risk_alert", {
            "type": "drawdown_breach", "current": risk["drawdown_pct"],
            "limit": risk["max_drawdown_pct"], "message": msg,
        })
        return

    # Check daily loss → stop trading for the day
    daily_loss_ratio = risk["daily_loss_pct"] / risk["max_daily_loss_pct"] if risk["max_daily_loss_pct"] > 0 else 0
    if daily_loss_ratio >= 1.0:
        set_autonomous(False)
        msg = (
            f"RISK ALERT: Perdita giornaliera {risk['daily_loss_pct']:.1f}% ha superato "
            f"il limite {risk['max_daily_loss_pct']:.0f}%. Trading autonomo disattivato."
        )
        if chat_id:
            await bot.send_message(chat_id, msg)
        await emit("risk_alert", {
            "type": "daily_loss_breach", "current": risk["daily_loss_pct"],
            "limit": risk["max_daily_loss_pct"], "message": msg,
        })
        return

    # Warnings at 80% threshold
    if drawdown_ratio >= _RISK_WARN_THRESHOLD:
        await emit("risk_alert", {
            "type": "drawdown_warning",
            "current": risk["drawdown_pct"],
            "limit": risk["max_drawdown_pct"],
            "message": f"Drawdown al {risk['drawdown_pct']:.1f}% (limite {risk['max_drawdown_pct']:.0f}%)",
        })

    if daily_loss_ratio >= _RISK_WARN_THRESHOLD:
        await emit("risk_alert", {
            "type": "daily_loss_warning",
            "current": risk["daily_loss_pct"],
            "limit": risk["max_daily_loss_pct"],
            "message": f"Perdita giornaliera al {risk['daily_loss_pct']:.1f}% (limite {risk['max_daily_loss_pct']:.0f}%)",
        })
