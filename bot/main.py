"""
Claudio — Personal AI Assistant
Entry point: wires up handlers and starts the bot.
"""

import asyncio
import logging
import os
import signal
import sys

from aiogram import Bot, Dispatcher

from bot.cleanup import cleanup_uploads_task
from bot.chronos_predictor import init as init_chronos, chronos_loop
from bot.kronos import init as init_kronos, kronos_loop
from bot.memory import init as init_memory
from bot.monitor import start_metrics_task, emit_status
from bot.trading import init as init_trading
from bot.ws_server import start_server as start_dashboard
from bot.handlers import commands, model, projects_cmds, voice_cmds, kronos_cmds, messages

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("claudio")


async def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        log.error("TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    bot = Bot(token=token)
    dp = Dispatcher()

    # Register routers (order matters — commands before catch-all messages)
    dp.include_router(commands.router)
    dp.include_router(model.router)
    dp.include_router(projects_cmds.router)
    dp.include_router(voice_cmds.router)
    dp.include_router(kronos_cmds.router)
    dp.include_router(messages.router)  # catch-all, must be last

    # Initialize per-chat memory (Mem0)
    init_memory()

    # Initialize trading (SQLite, paper mode)
    init_trading()

    # Initialize prediction models (async, non-blocking)
    await init_kronos()
    await init_chronos()

    # Start background tasks
    asyncio.create_task(cleanup_uploads_task())
    asyncio.create_task(kronos_loop())
    asyncio.create_task(chronos_loop())
    asyncio.create_task(start_dashboard())
    asyncio.create_task(start_metrics_task())
    asyncio.create_task(emit_status())

    log.info("Claudio is starting...")

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(dp, bot)))

    await dp.start_polling(bot)


async def shutdown(dp: Dispatcher, bot: Bot) -> None:
    log.info("Shutting down...")
    await dp.stop_polling()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
